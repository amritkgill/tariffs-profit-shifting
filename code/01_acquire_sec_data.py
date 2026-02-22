"""
01_acquire_sec_data.py
Acquire Foreign Pre-Tax Income and Total Pre-Tax Income from SEC EDGAR.

Uses the SEC XBRL Frames API to pull standardized financial data across all
US public firms for calendar years 2015-2024.

XBRL tags used:
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest
  - IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments

Key variable constructed:
  Foreign Profit Share = Foreign Pre-Tax Income / Total Pre-Tax Income

Data source: https://data.sec.gov/api/xbrl/frames/
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

YEARS = range(2015, 2025)  # CY2015 through CY2024

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
# Step 2: Pull data from SEC XBRL Frames API
# ---------------------------------------------------------------------------
def fetch_frames_data(tag_name, label, year):
    """
    Fetch one tag for one calendar year from the SEC Frames API.
    Returns a DataFrame with [cik, company_name, value, year].
    """
    url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag_name}/USD/CY{year}.json"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 404:
        return pd.DataFrame()
    resp.raise_for_status()
    data = resp.json()
    records = data.get("data", [])
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.rename(columns={"entityName": "company_name", "val": "value"})
    df["year"] = year
    df["tag_label"] = label
    # Keep relevant columns
    cols_to_keep = [c for c in ["cik", "company_name", "value", "year", "tag_label", "accn"] if c in df.columns]
    return df[cols_to_keep]


def download_all_frames():
    """Download all income tags for all years from the Frames API."""
    print("\nStep 2: Downloading data from SEC XBRL Frames API...")
    all_data = []

    for year in YEARS:
        print(f"  Year {year}:")
        for label, tag_name in TAGS.items():
            df = fetch_frames_data(tag_name, label, year)
            if not df.empty:
                all_data.append(df)
                print(f"    {label}: {len(df)} firms")
            else:
                print(f"    {label}: no data")
            time.sleep(0.12)  # SEC rate limit: ~10 req/sec

    combined = pd.concat(all_data, ignore_index=True)
    print(f"\n  Total raw records: {len(combined)}")
    return combined


# ---------------------------------------------------------------------------
# Step 3: Reshape into firm-year panel
# ---------------------------------------------------------------------------
def build_panel(raw_data):
    """
    Build firm-year panel with:
    - foreign_pretax_income
    - domestic_pretax_income
    - total_pretax_income
    - foreign_profit_share
    """
    print("\nStep 3: Building firm-year panel...")
    df = raw_data.copy()

    # Combine the two total income tags (v1 is newer, v2 is older)
    df["tag_label"] = df["tag_label"].replace({"total_v1": "total", "total_v2": "total"})

    # For firms with both total tags in the same year, keep v1 (higher priority)
    df = df.drop_duplicates(subset=["cik", "year", "tag_label"], keep="first")

    # Pivot to wide
    panel = df.pivot_table(
        index=["cik", "company_name", "year"],
        columns="tag_label",
        values="value",
        aggfunc="first"
    ).reset_index()
    panel.columns.name = None

    # Rename columns
    rename_map = {
        "foreign": "foreign_pretax_income",
        "domestic": "domestic_pretax_income",
        "total": "total_pretax_income",
    }
    panel = panel.rename(columns=rename_map)

    # Ensure columns exist
    for col in rename_map.values():
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

    panel = panel.sort_values(["cik", "year"]).reset_index(drop=True)
    return panel


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 65)
    print("SEC EDGAR Data Acquisition: Foreign & Total Pre-Tax Income")
    print("Source: SEC XBRL Frames API")
    print("=" * 65)

    # Step 1
    ticker_map = get_sec_ticker_mapping()

    # Step 2
    raw_data = download_all_frames()
    raw_data.to_csv(RAW_DIR / "sec_pretax_income_raw.csv", index=False)
    print(f"  Raw data saved to data/raw/sec_pretax_income_raw.csv")

    # Step 3
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
