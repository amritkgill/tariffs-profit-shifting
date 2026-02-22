"""
02_clean_and_merge.py
Clean and merge all data sources into a single analysis-ready dataset.

Inputs:
  - data/processed/sec_pretax_income_panel.csv (from 01_acquire_sec_data.py)
  - firm_variables.xlsx (Bloomberg firm characteristics)
  - tariff_exposure_naics3.csv (Section 301 tariff exposure by industry)
  - data/raw/sec_ticker_cik_mapping.csv (SEC ticker-to-CIK mapping)

Output:
  - data/processed/merged_panel.csv (final analysis dataset)

Merge strategy:
  Bloomberg firms -> map to CIK via SEC ticker mapping -> merge with SEC income panel
  -> add NAICS-3 tariff exposure
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
def merge_all(firm_df, sec_panel, tariff_df):
    """Merge firm characteristics, SEC income, and tariff exposure."""
    print("\nStep 4: Merging all datasets...")

    # Merge firm characteristics with SEC income panel on CIK
    merged = sec_panel.merge(
        firm_df,
        on="cik",
        how="inner",
        suffixes=("_sec", "_bloom")
    )
    print(f"  After firm-SEC merge: {len(merged)} obs, {merged['cik'].nunique()} firms")

    # Add tariff exposure by NAICS-3
    tariff_df["naics3"] = tariff_df["naics3"].astype("Int64")
    merged = merged.merge(
        tariff_df[["naics3", "sector_name", "n_products_targeted", "n_varieties_targeted",
                    "mean_tariff_increase", "sd_tariff_increase"]],
        on="naics3",
        how="left"
    )
    has_tariff = merged["mean_tariff_increase"].notna().sum()
    print(f"  Obs matched to tariff data: {has_tariff} ({has_tariff/len(merged)*100:.1f}%)")

    # Select and order final columns
    final_cols = [
        # Identifiers
        "cik", "clean_ticker", "company_name", "company_name_bloomberg", "year",
        # Firm characteristics
        "sic_code", "naics_code", "naics3", "icb_subsector", "market_cap", "price",
        # Income variables
        "foreign_pretax_income", "domestic_pretax_income", "total_pretax_income",
        "foreign_profit_share", "foreign_profit_share_winsorized", "fps_extreme",
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

    # Step 2: Map tickers to CIK
    firm_df = map_tickers_to_cik(firm_df)

    # Step 3: Clean SEC panel
    sec_panel = clean_sec_panel()

    # Step 4: Load tariff data
    tariff_df = pd.read_csv(BASE_DIR / "tariff_exposure_naics3.csv")

    # Step 5: Merge all
    final = merge_all(firm_df, sec_panel, tariff_df)

    # Save
    final.to_csv(PROCESSED_DIR / "merged_panel.csv", index=False)
    print(f"\nFinal dataset saved to data/processed/merged_panel.csv")

    # Summary
    print(f"\n{'=' * 65}")
    print("FINAL DATASET SUMMARY")
    print(f"{'=' * 65}")
    print(f"Total observations:            {len(final)}")
    print(f"Unique firms:                  {final['cik'].nunique()}")
    print(f"Year range:                    {final['year'].min()} - {final['year'].max()}")
    print(f"Obs with foreign profit share: {final['foreign_profit_share'].notna().sum()}")
    print(f"Obs with tariff exposure:      {final['mean_tariff_increase'].notna().sum()}")
    print(f"Obs with BOTH FPS & tariff:    {(final['foreign_profit_share'].notna() & final['mean_tariff_increase'].notna()).sum()}")

    print(f"\nFirms per year:")
    print(final.groupby("year")["cik"].nunique().to_string())

    print(f"\nForeign Profit Share (winsorized) stats:")
    print(final["foreign_profit_share_winsorized"].describe().to_string())

    print(f"\nTop 10 industries by firm count:")
    if "sector_name" in final.columns:
        top_sectors = final.groupby("sector_name")["cik"].nunique().sort_values(ascending=False).head(10)
        print(top_sectors.to_string())
