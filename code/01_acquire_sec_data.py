"""
01_acquire_sec_data.py
Acquire Foreign Pre-Tax Income and Total Pre-Tax Income from SEC EDGAR.

Uses the SEC XBRL CompanyFacts API to pull fiscal-year-aligned financial data
for US public firms, FY2015-FY2024.

This approach calls the companyfacts endpoint for each firm individually,
which gives exact fiscal year labels (avoiding the calendar-year misalignment
issue in the Frames API for non-December fiscal year-end firms).

XBRL tags used:
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments

Key variable constructed:
  Foreign Profit Share = Foreign Pre-Tax Income / Total Pre-Tax Income

Data source: https://data.sec.gov/api/xbrl/companyfacts/
Ticker-CIK mapping: https://www.sec.gov/files/company_tickers.json
"""

import time
import requests
import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "AcademicResearch capstone-tariffs-profit-shifting@university.edu"}

FY_MIN = 2015
FY_MAX = 2024

# XBRL tag definitions
TAGS = {
    "foreign": "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",
    "domestic": "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    "total_v1": "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "total_v2": "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
}


# ---------------------------------------------------------------------------
# Step 1: Download SEC ticker-to-CIK mapping
# ---------------------------------------------------------------------------
def get_sec_ticker_mapping():
    """Download SEC's official ticker-to-CIK mapping."""
    print("Step 1: Downloading SEC ticker-to-CIK mapping...")
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    df = pd.DataFrame(data).T
    df.columns = ["cik", "ticker", "company_name"]
    df["cik"] = df["cik"].astype(int)
    df["ticker"] = df["ticker"].str.upper().str.strip()
    print(f"  Found {len(df)} ticker-CIK mappings")
    df.to_csv(RAW_DIR / "sec_ticker_cik_mapping.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# Step 2: Identify which CIKs we need (Bloomberg sample)
# ---------------------------------------------------------------------------
def get_target_ciks(ticker_map):
    """Load Bloomberg firm list and map to CIKs."""
    print("\nStep 2: Identifying target firms from Bloomberg universe...")
    firm = pd.read_excel(BASE_DIR / "firm_variables.xlsx")
    firm = firm.iloc[1:].reset_index(drop=True)
    firm["clean_ticker"] = (
        firm["Ticker"].str.replace(" US Equity", "", regex=False)
        .str.strip().str.upper()
    )

    merged = firm.merge(
        ticker_map[["ticker", "cik"]],
        left_on="clean_ticker", right_on="ticker", how="inner"
    )
    ciks = sorted(merged["cik"].unique().tolist())
    print(f"  Target firms with CIK: {len(ciks)}")
    return ciks


# ---------------------------------------------------------------------------
# Step 3: Pull data from SEC CompanyFacts API (per-firm)
# ---------------------------------------------------------------------------
def extract_tag_data(facts, tag_name, label, cik):
    """
    Extract annual (FY) data for one XBRL tag from a companyfacts response.
    Uses the 'end' date (period end) to determine the correct fiscal year,
    NOT the 'fy' field (which is the filing year and includes comparatives).
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    tag_data = us_gaap.get(tag_name, {})
    usd_data = tag_data.get("units", {}).get("USD", [])

    if not usd_data:
        return []

    rows = []
    for entry in usd_data:
        # Only keep annual 10-K filings
        if entry.get("form") != "10-K":
            continue

        # Use the period end date to determine the data's actual fiscal year
        end_date = entry.get("end", "")
        if not end_date or len(end_date) < 4:
            continue
        data_year = int(end_date[:4])

        # For income items, require ~12 month duration (start to end)
        start_date = entry.get("start", "")
        if start_date:
            from datetime import datetime
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")
                duration_days = (end - start).days
                # Accept 300-400 day durations (full fiscal year)
                if duration_days < 300 or duration_days > 400:
                    continue
            except ValueError:
                continue

        if data_year < FY_MIN or data_year > FY_MAX:
            continue

        rows.append({
            "cik": cik,
            "data_year": data_year,
            "tag_label": label,
            "value": entry["val"],
            "filed": entry.get("filed", ""),
            "accn": entry.get("accn", ""),
            "end": end_date,
        })
    return rows


def download_companyfacts(ciks):
    """Download companyfacts for each CIK and extract income data."""
    print(f"\nStep 3: Downloading CompanyFacts for {len(ciks)} firms...")
    print(f"  (estimated time: ~{len(ciks) // 10 // 60 + 1} minutes at 10 req/sec)")

    all_rows = []
    errors = 0
    for i, cik in enumerate(ciks):
        if (i + 1) % 200 == 0:
            print(f"  Progress: {i + 1} / {len(ciks)} ({(i+1)/len(ciks)*100:.0f}%)")

        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"

        try:
            resp = requests.get(url, headers=HEADERS)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            facts = resp.json()

            for label, tag_name in TAGS.items():
                rows = extract_tag_data(facts, tag_name, label, cik)
                all_rows.extend(rows)

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error for CIK {cik}: {e}")

        # SEC rate limit: 10 requests/second
        time.sleep(0.11)

    print(f"  Done. Errors: {errors}")
    print(f"  Total raw records: {len(all_rows)}")

    df = pd.DataFrame(all_rows)

    # Get company names from the ticker mapping
    ticker_map = pd.read_csv(RAW_DIR / "sec_ticker_cik_mapping.csv")
    df = df.merge(ticker_map[["cik", "company_name"]], on="cik", how="left")

    return df


# ---------------------------------------------------------------------------
# Step 4: Reshape into firm-year panel
# ---------------------------------------------------------------------------
def build_panel(raw_data):
    """
    Build firm-year panel with proper fiscal year alignment.
    For each firm-year-tag, keeps the value from the most recent filing.
    """
    print("\nStep 4: Building firm-year panel...")
    df = raw_data.copy()

    # For each firm-year-tag, keep the most recently filed value
    df = df.sort_values("filed", ascending=False)
    df = df.drop_duplicates(subset=["cik", "data_year", "tag_label"], keep="first")

    # Prefer total_v1 over total_v2 (they measure slightly different things:
    #   v1 = ...ExtraordinaryItemsNoncontrollingInterest (modern standard)
    #   v2 = ...MinorityInterestAndIncomeLossFromEquityMethodInvestments
    # When both exist for the same firm-year, keep only v1 for consistency.)
    has_v1 = df[df["tag_label"] == "total_v1"][["cik", "data_year"]].drop_duplicates()
    has_v1["_has_v1"] = True
    df = df.merge(has_v1, on=["cik", "data_year"], how="left")
    df = df[~((df["tag_label"] == "total_v2") & (df["_has_v1"] == True))]
    df = df.drop(columns=["_has_v1"])

    n_dropped_v2 = has_v1["_has_v1"].sum()  # firm-years where v2 was dropped
    print(f"  Preferred total_v1 over total_v2 for {len(has_v1)} firm-years (dropped v2 duplicates)")

    # Now rename both to a single "total" label
    df["tag_label"] = df["tag_label"].replace({"total_v1": "total", "total_v2": "total"})

    # Pivot to wide
    panel = df.pivot_table(
        index=["cik", "company_name", "data_year"],
        columns="tag_label",
        values="value",
        aggfunc="first"
    ).reset_index()
    panel.columns.name = None
    panel = panel.rename(columns={
        "data_year": "year",
        "foreign": "foreign_pretax_income",
        "domestic": "domestic_pretax_income",
        "total": "total_pretax_income",
    })

    # Ensure columns exist
    for col in ["foreign_pretax_income", "domestic_pretax_income", "total_pretax_income"]:
        if col not in panel.columns:
            panel[col] = np.nan

    # Fill missing foreign income: Foreign = Total - Domestic
    can_compute = (
        panel["foreign_pretax_income"].isna() &
        panel["total_pretax_income"].notna() &
        panel["domestic_pretax_income"].notna()
    )
    panel.loc[can_compute, "foreign_pretax_income"] = (
        panel.loc[can_compute, "total_pretax_income"] - panel.loc[can_compute, "domestic_pretax_income"]
    )

    # Compute Foreign Profit Share
    valid_total = panel["total_pretax_income"].notna() & (panel["total_pretax_income"] != 0)
    valid_foreign = panel["foreign_pretax_income"].notna()
    panel["foreign_profit_share"] = np.where(
        valid_total & valid_foreign,
        panel["foreign_pretax_income"] / panel["total_pretax_income"],
        np.nan
    )

    # Accounting identity check: Foreign + Domestic should ≈ Total.
    # When the identity fails by more than 5% of |Total|, the income
    # breakdown is unreliable (restatements, sign errors, tag mismatches).
    # Null out FPS for these observations.
    has_all_three = (
        panel["foreign_pretax_income"].notna() &
        panel["domestic_pretax_income"].notna() &
        panel["total_pretax_income"].notna() &
        (panel["total_pretax_income"] != 0)
    )
    residual = (
        panel["foreign_pretax_income"] + panel["domestic_pretax_income"]
        - panel["total_pretax_income"]
    )
    pct_error = residual.abs() / panel["total_pretax_income"].abs()
    identity_fails = has_all_three & (pct_error > 0.05)
    n_fails = identity_fails.sum()
    panel.loc[identity_fails, "foreign_profit_share"] = np.nan
    print(f"  Accounting identity check: nulled FPS for {n_fails} obs "
          f"where |Foreign + Domestic - Total| > 5% of |Total|")

    panel = panel.sort_values(["cik", "year"]).reset_index(drop=True)
    return panel


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 65)
    print("SEC EDGAR Data Acquisition: Foreign & Total Pre-Tax Income")
    print("Source: SEC XBRL CompanyFacts API (fiscal-year aligned)")
    print("=" * 65)

    # Step 1
    ticker_map = get_sec_ticker_mapping()

    # Step 2
    target_ciks = get_target_ciks(ticker_map)

    # Step 3
    raw_data = download_companyfacts(target_ciks)
    raw_data.to_csv(RAW_DIR / "sec_pretax_income_raw.csv", index=False)
    print(f"  Raw data saved to data/raw/sec_pretax_income_raw.csv")

    # Step 4
    panel = build_panel(raw_data)
    panel.to_csv(PROCESSED_DIR / "sec_pretax_income_panel.csv", index=False)
    print(f"  Panel saved to data/processed/sec_pretax_income_panel.csv")

    # Summary
    print(f"\n{'=' * 65}")
    print("SUMMARY")
    print(f"{'=' * 65}")
    print(f"Unique firms (CIKs):          {panel['cik'].nunique()}")
    print(f"Year range:                   {panel['year'].min()} - {panel['year'].max()}")
    print(f"Total firm-year obs:          {len(panel)}")
    print(f"Obs with foreign income:      {panel['foreign_pretax_income'].notna().sum()}")
    print(f"Obs with total income:        {panel['total_pretax_income'].notna().sum()}")
    print(f"Obs with foreign profit share:{panel['foreign_profit_share'].notna().sum()}")

    print(f"\nCoverage by year:")
    coverage = panel.groupby("year").agg(
        firms=("cik", "count"),
        has_foreign=("foreign_pretax_income", lambda x: x.notna().sum()),
        has_total=("total_pretax_income", lambda x: x.notna().sum()),
        has_fps=("foreign_profit_share", lambda x: x.notna().sum()),
    )
    print(coverage.to_string())

    print(f"\nForeign Profit Share distribution (where available):")
    fps = panel["foreign_profit_share"].dropna()
    print(f"  N:      {len(fps)}")
    print(f"  Mean:   {fps.mean():.4f}")
    print(f"  Median: {fps.median():.4f}")
    print(f"  Std:    {fps.std():.4f}")
    print(f"  Min:    {fps.min():.4f}")
    print(f"  Max:    {fps.max():.4f}")
    print(f"  p25:    {fps.quantile(0.25):.4f}")
    print(f"  p75:    {fps.quantile(0.75):.4f}")
