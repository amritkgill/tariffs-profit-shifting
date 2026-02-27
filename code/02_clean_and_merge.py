"""
02_clean_and_merge.py
Clean and merge all data sources into a single analysis-ready dataset.

Inputs:
  - data/processed/sec_pretax_income_panel.csv (from 01_acquire_sec_data.py)
  - firm_variables.xlsx (Bloomberg firm characteristics - 17 sheets):
      * firm_universe: static firm info (ticker, SIC, NAICS, market cap)
      * 8 time-series financial variable sheets (each in wide format: Ticker x Year):
        total_revenue, pretax_income, rd_expense, total_assets, total_debt,
        capital_expend, effective_tax_rate, operating_expenses
  - tariff_exposure_naics3.csv (Section 301 tariff exposure by industry)
  - data/raw/sec_ticker_cik_mapping.csv (SEC ticker-to-CIK mapping)

Output:
  - data/processed/merged_panel.csv (final analysis dataset)

Merge strategy:
  Bloomberg firms -> map to CIK via SEC ticker mapping -> merge with SEC income panel
  -> add Bloomberg time-series financials -> add NAICS-3 tariff exposure
"""

import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# ---------------------------------------------------------------------------
# Step 1: Load and clean firm characteristics (Bloomberg)
# ---------------------------------------------------------------------------
def clean_firm_variables():
    """Clean Bloomberg firm characteristics data."""
    print("Step 1: Cleaning firm characteristics (firm_variables.xlsx)...")

    df = pd.read_excel(BASE_DIR / "firm_variables.xlsx")
    # First row is a header/count row, skip it
    df = df.iloc[1:].reset_index(drop=True)

    # Extract clean ticker from Bloomberg format
    df["clean_ticker"] = (
        df["Ticker"]
        .str.replace(" US Equity", "", regex=False)
        .str.strip()
        .str.upper()
    )

    # Clean NAICS code -> 3-digit
    df["naics_code"] = df["NAICS Code"].astype(float).astype("Int64")
    df["naics3"] = df["naics_code"].astype(str).str[:3].astype("Int64")

    # Clean SIC code
    df["sic_code"] = df["SIC Code"].astype(float).astype("Int64")

    # Clean market cap
    df["market_cap"] = pd.to_numeric(df["Market Cap"], errors="coerce")

    # Rename and select columns
    df = df.rename(columns={
        "Short Name": "company_name_bloomberg",
        "ICB Subsector Name": "icb_subsector",
        "Price:D-1": "price",
    })

    cols = ["clean_ticker", "company_name_bloomberg", "sic_code", "naics_code",
            "naics3", "icb_subsector", "market_cap", "price"]
    df = df[cols].copy()

    # Drop ETFs / non-operating entities (no SIC or NAICS typically)
    # Keep all for now, will filter after merge
    print(f"  Firms loaded: {len(df)}")
    print(f"  With NAICS: {df['naics_code'].notna().sum()}")
    print(f"  With SIC: {df['sic_code'].notna().sum()}")

    return df


# ---------------------------------------------------------------------------
# Step 1b: Load Bloomberg time-series financial variables
# ---------------------------------------------------------------------------
# Map sheet names to clean column names for the final dataset
BLOOMBERG_TS_SHEETS = {
    "total_revenue":        "total_revenue",
    "pretax_income":        "pretax_income_bloomberg",
    "rd_expense":           "rd_expense",
    "total_assets":         "total_assets",
    "total_debt":           "total_debt",
    "capital_expend":       "capital_expenditure",
    "effective_tax_rate":   "effective_tax_rate",
    "operating_expenses":   "operating_expenses",
}


def load_bloomberg_timeseries():
    """Read all Bloomberg time-series sheets and reshape to long panel format.

    Each sheet is in wide format: Ticker | 2015 | 2016 | ... | 2025
    We melt each into long format (Ticker, year, value) and merge them all.
    """
    print("\nStep 1b: Loading Bloomberg time-series financial variables...")

    xlsx_path = BASE_DIR / "firm_variables.xlsx"
    all_vars = []

    for sheet_name, col_name in BLOOMBERG_TS_SHEETS.items():
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
        # Note: unlike firm_universe, time-series sheets do NOT have a
        # junk header row. Row 0 is real data (e.g., NVDA).

        # Extract clean ticker
        df["clean_ticker"] = (
            df["Ticker"]
            .str.replace(" US Equity", "", regex=False)
            .str.strip()
            .str.upper()
        )

        # Identify year columns (numeric column names)
        year_cols = [c for c in df.columns if str(c).isdigit()]

        # Melt wide -> long
        melted = df.melt(
            id_vars=["clean_ticker"],
            value_vars=year_cols,
            var_name="year",
            value_name=col_name,
        )
        melted["year"] = melted["year"].astype(int)
        melted[col_name] = pd.to_numeric(melted[col_name], errors="coerce")

        # Filter to 2015-2024 (same as SEC panel)
        melted = melted[(melted["year"] >= 2015) & (melted["year"] <= 2024)]

        all_vars.append(melted)
        n_obs = melted[col_name].notna().sum()
        print(f"  {col_name}: {n_obs} non-null observations")

    # Merge all variables together on (clean_ticker, year)
    combined = all_vars[0]
    for df in all_vars[1:]:
        combined = combined.merge(df, on=["clean_ticker", "year"], how="outer")

    print(f"  Combined Bloomberg time-series: {len(combined)} rows, "
          f"{combined['clean_ticker'].nunique()} tickers")

    return combined


# ---------------------------------------------------------------------------
# Step 2: Map Bloomberg tickers to CIK via SEC mapping
# ---------------------------------------------------------------------------
def map_tickers_to_cik(firm_df):
    """Map Bloomberg tickers to SEC CIK numbers."""
    print("\nStep 2: Mapping Bloomberg tickers to SEC CIK numbers...")

    sec_map = pd.read_csv(RAW_DIR / "sec_ticker_cik_mapping.csv")
    sec_map["ticker"] = sec_map["ticker"].str.upper().str.strip()

    # Merge on ticker
    merged = firm_df.merge(
        sec_map[["ticker", "cik"]],
        left_on="clean_ticker",
        right_on="ticker",
        how="left"
    ).drop(columns=["ticker"])

    matched = merged["cik"].notna().sum()
    print(f"  Matched to CIK: {matched} / {len(merged)} ({matched/len(merged)*100:.1f}%)")
    print(f"  Unmatched (likely ETFs/funds): {merged['cik'].isna().sum()}")

    # Drop firms without CIK (can't merge with SEC data)
    merged = merged[merged["cik"].notna()].copy()
    merged["cik"] = merged["cik"].astype(int)

    return merged


# ---------------------------------------------------------------------------
# Step 3: Clean SEC income panel
# ---------------------------------------------------------------------------
def clean_sec_panel():
    """Clean the SEC pre-tax income panel data."""
    print("\nStep 3: Cleaning SEC income panel...")

    panel = pd.read_csv(PROCESSED_DIR / "sec_pretax_income_panel.csv")

    # Filter to 2015-2024
    panel = panel[(panel["year"] >= 2015) & (panel["year"] <= 2024)].copy()

    # Remove duplicate CIK-year rows (keep first, which has higher priority tag)
    n_before = len(panel)
    panel = panel.drop_duplicates(subset=["cik", "year"], keep="first")
    n_dropped = n_before - len(panel)
    if n_dropped > 0:
        print(f"  Dropped {n_dropped} duplicate CIK-year rows")
    print(f"  Observations (2015-2024): {len(panel)}")

    # Convert SEC income from raw dollars to millions (matching Bloomberg scale)
    income_cols = ["foreign_pretax_income", "domestic_pretax_income", "total_pretax_income"]
    for col in income_cols:
        panel[col] = panel[col] / 1e6
    print(f"  Converted income columns to USD millions (matching Bloomberg scale)")

    # Winsorize foreign_profit_share at 1st and 99th percentiles
    fps = panel["foreign_profit_share"]
    p01 = fps.quantile(0.01)
    p99 = fps.quantile(0.99)
    panel["foreign_profit_share_winsorized"] = fps.clip(lower=p01, upper=p99)

    # Flag extreme values
    panel["fps_extreme"] = (
        (panel["foreign_profit_share"] < p01) |
        (panel["foreign_profit_share"] > p99)
    )

    n_extreme = panel["fps_extreme"].sum()
    print(f"  Foreign profit share - p1: {p01:.4f}, p99: {p99:.4f}")
    print(f"  Extreme values flagged: {n_extreme}")
    print(f"  Obs with foreign profit share: {fps.notna().sum()}")

    return panel


# ---------------------------------------------------------------------------
# Step 4: Merge all datasets
# ---------------------------------------------------------------------------
def merge_all(firm_df, sec_panel, tariff_df, bloomberg_ts):
    """Merge firm characteristics, SEC income, Bloomberg financials, and tariff exposure."""
    print("\nStep 5: Merging all datasets...")

    # Merge firm characteristics with SEC income panel on CIK
    n_sec_firms_before = sec_panel["cik"].nunique()
    merged = sec_panel.merge(
        firm_df,
        on="cik",
        how="inner",
        suffixes=("_sec", "_bloom")
    )
    n_sec_firms_after = merged["cik"].nunique()
    print(f"  After firm-SEC merge: {len(merged)} obs, {n_sec_firms_after} firms")
    if n_sec_firms_after < n_sec_firms_before:
        print(f"  WARNING: Lost {n_sec_firms_before - n_sec_firms_after} SEC firms in inner join")

    # Add Bloomberg time-series financials on (clean_ticker, year)
    n_before = len(merged)
    merged = merged.merge(
        bloomberg_ts,
        on=["clean_ticker", "year"],
        how="left"
    )
    assert len(merged) == n_before, (
        f"Bloomberg TS merge changed row count: {n_before} -> {len(merged)}. "
        f"This suggests a many-to-many join — check for duplicate tickers."
    )
    print(f"  After Bloomberg time-series merge: {len(merged)} obs (unchanged, good)")
    ts_cols = list(BLOOMBERG_TS_SHEETS.values())
    for col in ts_cols:
        n_filled = merged[col].notna().sum()
        print(f"    {col}: {n_filled} non-null ({n_filled/len(merged)*100:.1f}%)")

    # Add tariff exposure by NAICS-3
    tariff_df["naics3"] = tariff_df["naics3"].astype("Int64")
    n_before_tariff = len(merged)
    merged = merged.merge(
        tariff_df[["naics3", "sector_name", "n_products_targeted", "n_varieties_targeted",
                    "mean_tariff_increase", "sd_tariff_increase"]],
        on="naics3",
        how="left"
    )
    assert len(merged) == n_before_tariff, (
        f"Tariff merge changed row count: {n_before_tariff} -> {len(merged)}. "
        f"Check for duplicate NAICS-3 codes in tariff data."
    )
    has_tariff = merged["mean_tariff_increase"].notna().sum()
    print(f"  Obs matched to tariff data: {has_tariff} ({has_tariff/len(merged)*100:.1f}%)")

    # Select and order final columns
    final_cols = [
        # Identifiers
        "cik", "clean_ticker", "company_name", "company_name_bloomberg", "year",
        # Firm characteristics (static)
        "sic_code", "naics_code", "naics3", "icb_subsector", "market_cap", "price",
        # SEC income variables
        "foreign_pretax_income", "domestic_pretax_income", "total_pretax_income",
        "foreign_profit_share", "foreign_profit_share_winsorized", "fps_extreme",
        # Bloomberg time-series financials
        "total_revenue", "pretax_income_bloomberg", "rd_expense", "total_assets",
        "total_debt", "capital_expenditure", "effective_tax_rate", "operating_expenses",
        # Tariff exposure
        "sector_name", "n_products_targeted", "n_varieties_targeted",
        "mean_tariff_increase", "sd_tariff_increase",
    ]
    # Only keep columns that exist
    final_cols = [c for c in final_cols if c in merged.columns]
    merged = merged[final_cols].sort_values(["cik", "year"]).reset_index(drop=True)

    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 65)
    print("Data Cleaning and Merging")
    print("=" * 65)

    # Step 1: Clean firm characteristics
    firm_df = clean_firm_variables()

    # Step 1b: Load Bloomberg time-series financials
    bloomberg_ts = load_bloomberg_timeseries()

    # Step 2: Map tickers to CIK
    firm_df = map_tickers_to_cik(firm_df)

    # Step 3: Clean SEC panel
    sec_panel = clean_sec_panel()

    # Step 4: Load tariff data
    tariff_df = pd.read_csv(BASE_DIR / "tariff_exposure_naics3.csv")

    # Step 5: Merge all
    final = merge_all(firm_df, sec_panel, tariff_df, bloomberg_ts)

    # Save
    final.to_csv(PROCESSED_DIR / "merged_panel.csv", index=False)
    print(f"\nFinal dataset saved to data/processed/merged_panel.csv")

    # -----------------------------------------------------------------------
    # Data quality checks
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("DATA QUALITY CHECKS")
    print(f"{'=' * 65}")

    # Check 1: No duplicate firm-years
    n_dup = final.duplicated(subset=["cik", "year"]).sum()
    assert n_dup == 0, f"FAIL: {n_dup} duplicate cik-year rows found"
    print(f"  [PASS] No duplicate firm-year observations")

    # Check 2: Year range is 2015-2024
    assert final["year"].min() >= 2015, f"FAIL: min year = {final['year'].min()}"
    assert final["year"].max() <= 2024, f"FAIL: max year = {final['year'].max()}"
    print(f"  [PASS] Year range: {final['year'].min()}-{final['year'].max()}")

    # Check 3: Key identifier columns have no nulls
    for col in ["cik", "clean_ticker", "year"]:
        n_null = final[col].isna().sum()
        assert n_null == 0, f"FAIL: {col} has {n_null} nulls"
    print(f"  [PASS] No nulls in cik, clean_ticker, year")

    # Check 4: NVDA has Bloomberg data (catches iloc[1:] regression)
    nvda = final[final["clean_ticker"] == "NVDA"]
    if len(nvda) > 0:
        nvda_has_rev = nvda["total_revenue"].notna().sum()
        nvda_has_etr = nvda["effective_tax_rate"].notna().sum()
        print(f"  [INFO] NVDA: {len(nvda)} rows, {nvda_has_rev} with revenue, {nvda_has_etr} with ETR")
        if nvda_has_rev == 0:
            print(f"  [WARN] NVDA has no Bloomberg time-series data — iloc bug may persist")
    else:
        print(f"  [WARN] NVDA not found in dataset")

    # Check 5: SEC income values are in millions (spot check)
    max_income = final["total_pretax_income"].abs().max()
    if max_income > 1e6:
        print(f"  [WARN] Max |total_pretax_income| = {max_income:,.0f} — "
              f"expected millions, this looks like raw dollars")
    else:
        print(f"  [PASS] total_pretax_income in millions (max abs = {max_income:,.0f})")

    # Check 6: Bloomberg financials present for most firms
    bloomberg_cols = ["total_revenue", "effective_tax_rate", "total_assets"]
    for col in bloomberg_cols:
        n_notna = final[col].notna().sum()
        pct = n_notna / len(final) * 100
        status = "[PASS]" if pct > 50 else "[WARN]"
        print(f"  {status} {col}: {n_notna:,} non-null ({pct:.1f}%)")

    # Check 7: Count firms with ALL Bloomberg TS missing
    ts_cols = ["total_revenue", "pretax_income_bloomberg", "rd_expense",
               "total_assets", "total_debt", "capital_expenditure",
               "effective_tax_rate", "operating_expenses"]
    all_ts_null = final[ts_cols].isna().all(axis=1)
    firms_all_null = final.loc[all_ts_null, "clean_ticker"].nunique()
    print(f"  [INFO] {firms_all_null} firms have zero Bloomberg time-series data (source gap)")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("FINAL DATASET SUMMARY")
    print(f"{'=' * 65}")
    print(f"Total observations:            {len(final)}")
    print(f"Unique firms:                  {final['cik'].nunique()}")
    print(f"Year range:                    {final['year'].min()} - {final['year'].max()}")
    print(f"Obs with ETR (main outcome):   {final['effective_tax_rate'].notna().sum()}")
    print(f"Obs with foreign profit share: {final['foreign_profit_share'].notna().sum()}")
    print(f"Obs with tariff exposure:      {final['mean_tariff_increase'].notna().sum()}")

    print(f"\nFirms per year:")
    print(final.groupby("year")["cik"].nunique().to_string())

    print(f"\nEffective Tax Rate stats:")
    print(final["effective_tax_rate"].describe().to_string())

    print(f"\nTop 10 industries by firm count:")
    if "sector_name" in final.columns:
        top_sectors = final.groupby("sector_name")["cik"].nunique().sort_values(ascending=False).head(10)
        print(top_sectors.to_string())

    # Document known data gaps
    print(f"\nKNOWN DATA GAPS (source data, not bugs):")
    print(f"  - 2017 total_revenue: ~75% missing in Bloomberg source data")
    print(f"  - ~{firms_all_null} firms have SEC data but no Bloomberg time-series coverage")
    print(f"  - effective_tax_rate: {final['effective_tax_rate'].isna().sum()} missing ({final['effective_tax_rate'].isna().mean()*100:.1f}%)")
    print(f"  - These gaps are handled by the regression (drops missing values)")
