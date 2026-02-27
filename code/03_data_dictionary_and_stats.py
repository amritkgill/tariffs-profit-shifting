"""
03_data_dictionary_and_stats.py
Generate data dictionary, summary statistics, and data quality checks.

Inputs:
  - data/processed/merged_panel.csv

Outputs:
  - output/data_dictionary.csv
  - output/summary_statistics.csv
  - output/data_checks.txt
"""

import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data Dictionary
# ---------------------------------------------------------------------------
def create_data_dictionary(df):
    """Create a data dictionary describing all variables."""
    print("Creating data dictionary...")

    var_info = {
        "cik": {
            "description": "SEC Central Index Key - unique firm identifier",
            "source": "SEC EDGAR",
            "type": "identifier",
        },
        "clean_ticker": {
            "description": "Stock ticker symbol (e.g., AAPL, NVDA)",
            "source": "Bloomberg Terminal / SEC EDGAR",
            "type": "identifier",
        },
        "company_name": {
            "description": "Company name from SEC EDGAR filings",
            "source": "SEC EDGAR XBRL",
            "type": "identifier",
        },
        "company_name_bloomberg": {
            "description": "Company name from Bloomberg Terminal",
            "source": "Bloomberg Terminal",
            "type": "identifier",
        },
        "year": {
            "description": "Calendar year of financial data (2015-2024)",
            "source": "SEC EDGAR XBRL",
            "type": "time",
        },
        "sic_code": {
            "description": "Standard Industrial Classification code (4-digit)",
            "source": "Bloomberg Terminal",
            "type": "classification",
        },
        "naics_code": {
            "description": "North American Industry Classification System code (6-digit)",
            "source": "Bloomberg Terminal",
            "type": "classification",
        },
        "naics3": {
            "description": "NAICS 3-digit industry code (used to merge with tariff data)",
            "source": "Derived from naics_code",
            "type": "classification",
        },
        "icb_subsector": {
            "description": "Industry Classification Benchmark subsector name",
            "source": "Bloomberg Terminal",
            "type": "classification",
        },
        "market_cap": {
            "description": "Market capitalization in USD (raw dollars, not millions; most recent available)",
            "source": "Bloomberg Terminal",
            "type": "firm characteristic",
        },
        "price": {
            "description": "Most recent stock price in USD",
            "source": "Bloomberg Terminal",
            "type": "firm characteristic",
        },
        "foreign_pretax_income": {
            "description": "Pre-tax income from foreign operations (USD millions). Directly from XBRL tag or computed as Total - Domestic.",
            "source": "SEC EDGAR XBRL (IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign)",
            "type": "key variable",
        },
        "domestic_pretax_income": {
            "description": "Pre-tax income from domestic (US) operations (USD millions)",
            "source": "SEC EDGAR XBRL (IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic)",
            "type": "key variable",
        },
        "total_pretax_income": {
            "description": "Total pre-tax income from all operations (USD millions)",
            "source": "SEC EDGAR XBRL (IncomeLossFromContinuingOperationsBeforeIncomeTaxes...)",
            "type": "key variable",
        },
        "foreign_profit_share": {
            "description": "Foreign Profit Share = Foreign Pre-Tax Income / Total Pre-Tax Income. Used as robustness check outcome (R10).",
            "source": "Computed from SEC EDGAR data",
            "type": "key variable",
        },
        "foreign_profit_share_winsorized": {
            "description": "Foreign Profit Share winsorized at 1st and 99th percentiles to reduce outlier influence",
            "source": "Computed",
            "type": "key variable",
        },
        "fps_extreme": {
            "description": "Flag (True/False) indicating original FPS was outside 1st-99th percentile range",
            "source": "Computed",
            "type": "flag",
        },
        "sector_name": {
            "description": "NAICS-3 sector name from tariff exposure data",
            "source": "Section 301 tariff data",
            "type": "tariff variable",
        },
        "n_products_targeted": {
            "description": "Number of HS-8 products targeted by Section 301 tariffs in this NAICS-3 industry",
            "source": "Section 301 tariff data",
            "type": "tariff variable",
        },
        "n_varieties_targeted": {
            "description": "Number of product varieties (HS-8 x country) targeted by Section 301 tariffs",
            "source": "Section 301 tariff data",
            "type": "tariff variable",
        },
        "mean_tariff_increase": {
            "description": "Mean tariff rate increase (proportion) from Section 301 for products in this NAICS-3 industry",
            "source": "Section 301 tariff data",
            "type": "tariff variable",
        },
        "sd_tariff_increase": {
            "description": "Standard deviation of tariff rate increase within the NAICS-3 industry",
            "source": "Section 301 tariff data",
            "type": "tariff variable",
        },
        "total_revenue": {
            "description": "Total revenue in USD millions (annual)",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
        "pretax_income_bloomberg": {
            "description": "Pre-tax income in USD millions from Bloomberg (annual). Serves as cross-check against SEC EDGAR total_pretax_income.",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
        "rd_expense": {
            "description": "Research and development expense in USD millions (annual)",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
        "total_assets": {
            "description": "Total assets in USD millions (annual)",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
        "total_debt": {
            "description": "Total debt (short-term + long-term) in USD millions (annual)",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
        "capital_expenditure": {
            "description": "Capital expenditure in USD millions (annual, typically negative as cash outflow)",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
        "effective_tax_rate": {
            "description": "Effective tax rate as a percentage (annual). Main outcome variable — winsorized/trimmed variants constructed in regression script.",
            "source": "Bloomberg Terminal",
            "type": "key variable",
        },
        "operating_expenses": {
            "description": "Total operating expenses in USD millions (annual)",
            "source": "Bloomberg Terminal",
            "type": "financial variable",
        },
    }

    rows = []
    for col in df.columns:
        info = var_info.get(col, {"description": "No description", "source": "Unknown", "type": "unknown"})
        rows.append({
            "variable": col,
            "description": info["description"],
            "source": info["source"],
            "type": info["type"],
            "dtype": str(df[col].dtype),
            "n_nonmissing": int(df[col].notna().sum()),
            "n_missing": int(df[col].isna().sum()),
            "pct_missing": round(df[col].isna().mean() * 100, 1),
            "n_unique": int(df[col].nunique()),
        })

    dict_df = pd.DataFrame(rows)
    dict_df.to_csv(OUTPUT_DIR / "data_dictionary.csv", index=False)
    print(f"  Saved to output/data_dictionary.csv ({len(dict_df)} variables)")
    return dict_df


# ---------------------------------------------------------------------------
# Summary Statistics
# ---------------------------------------------------------------------------
def create_summary_statistics(df):
    """Create summary statistics for numeric variables."""
    print("\nCreating summary statistics...")

    numeric_cols = [
        "market_cap", "price",
        "effective_tax_rate",
        "foreign_pretax_income", "domestic_pretax_income", "total_pretax_income",
        "foreign_profit_share", "foreign_profit_share_winsorized",
        "total_revenue", "pretax_income_bloomberg", "rd_expense", "total_assets",
        "total_debt", "capital_expenditure", "operating_expenses",
        "n_products_targeted", "n_varieties_targeted",
        "mean_tariff_increase", "sd_tariff_increase",
    ]
    numeric_cols = [c for c in numeric_cols if c in df.columns]

    stats = df[numeric_cols].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).T
    stats["n_missing"] = df[numeric_cols].isna().sum()
    stats["pct_missing"] = (df[numeric_cols].isna().mean() * 100).round(1)

    stats.to_csv(OUTPUT_DIR / "summary_statistics.csv")
    print(f"  Saved to output/summary_statistics.csv")

    # Print to console
    print("\n  Key variable statistics:")
    key_vars = ["effective_tax_rate", "mean_tariff_increase",
                "foreign_profit_share", "total_pretax_income"]
    key_vars = [v for v in key_vars if v in stats.index]
    print(stats.loc[key_vars, ["count", "mean", "std", "min", "50%", "max", "n_missing"]].to_string())

    return stats


# ---------------------------------------------------------------------------
# Data Quality Checks
# ---------------------------------------------------------------------------
def run_data_checks(df):
    """Run data quality checks and save report."""
    print("\nRunning data quality checks...")
    checks = []

    # Check 1: Panel balance
    firms_per_year = df.groupby("year")["cik"].nunique()
    checks.append("=" * 65)
    checks.append("DATA QUALITY CHECKS")
    checks.append("=" * 65)
    checks.append("")
    checks.append("1. PANEL STRUCTURE")
    checks.append(f"   Total observations: {len(df)}")
    checks.append(f"   Unique firms: {df['cik'].nunique()}")
    checks.append(f"   Year range: {df['year'].min()}-{df['year'].max()}")
    checks.append(f"   Firms per year:")
    for yr, n in firms_per_year.items():
        checks.append(f"     {yr}: {n}")
    checks.append(f"   Panel is UNBALANCED (firms enter/exit over time)")

    # Check 2: Missing data
    checks.append("")
    checks.append("2. MISSING DATA")
    key_vars = ["foreign_pretax_income", "domestic_pretax_income", "total_pretax_income",
                "foreign_profit_share", "mean_tariff_increase"]
    for var in key_vars:
        if var in df.columns:
            n_miss = df[var].isna().sum()
            pct = df[var].isna().mean() * 100
            checks.append(f"   {var}: {n_miss} missing ({pct:.1f}%)")

    # Check 3: Negative total income
    if "total_pretax_income" in df.columns:
        n_neg = (df["total_pretax_income"] < 0).sum()
        checks.append("")
        checks.append("3. NEGATIVE INCOME VALUES")
        checks.append(f"   Firms with negative total pre-tax income: {n_neg} ({n_neg/len(df)*100:.1f}%)")
        checks.append("   Note: Negative income is valid (firms can have losses)")

    # Check 4: Effective tax rate distribution (main outcome variable)
    if "effective_tax_rate" in df.columns:
        etr = df["effective_tax_rate"].dropna()
        checks.append("")
        checks.append("4. EFFECTIVE TAX RATE DISTRIBUTION (main outcome)")
        checks.append(f"   Obs with ETR data: {len(etr)} ({len(etr)/len(df)*100:.1f}%)")
        checks.append(f"   Mean: {etr.mean():.1f}%   Median: {etr.median():.1f}%")
        checks.append(f"   Min: {etr.min():.1f}%   Max: {etr.max():.1f}%")
        checks.append(f"   Obs with ETR < 0: {(etr < 0).sum()}")
        checks.append(f"   Obs with ETR > 100: {(etr > 100).sum()}")
        checks.append(f"   Obs with ETR > 200: {(etr > 200).sum()}")
        checks.append(f"   Obs in [0, 60] (normal range): {((etr >= 0) & (etr <= 60)).sum()}")
        checks.append(f"   Winsorization cutoffs:")
        checks.append(f"     p1/p99: [{etr.quantile(0.01):.1f}, {etr.quantile(0.99):.1f}]")
        checks.append(f"     p5/p95: [{etr.quantile(0.05):.1f}, {etr.quantile(0.95):.1f}]")
        checks.append(f"   Note: Extreme ETRs are driven by firms with very small pre-tax income")

    # Check 4b: Foreign profit share bounds (robustness outcome)
    if "foreign_profit_share" in df.columns:
        fps = df["foreign_profit_share"].dropna()
        checks.append("")
        checks.append("4b. FOREIGN PROFIT SHARE DISTRIBUTION (robustness outcome)")
        checks.append(f"   Obs with FPS > 1 (foreign > total): {(fps > 1).sum()}")
        checks.append(f"   Obs with FPS < 0 (negative foreign or total): {(fps < 0).sum()}")
        checks.append(f"   Obs with FPS in [0, 1] (normal range): {((fps >= 0) & (fps <= 1)).sum()}")
        checks.append(f"   Note: FPS outside [0,1] occurs when domestic or foreign income is negative")

    # Check 5: Duplicates
    checks.append("")
    checks.append("5. DUPLICATE CHECK")
    n_dup = df.duplicated(subset=["cik", "year"]).sum()
    checks.append(f"   Duplicate firm-year observations: {n_dup}")
    if n_dup > 0:
        checks.append("   WARNING: Duplicates found!")
    else:
        checks.append("   No duplicates found (clean)")

    # Check 6: Tariff merge quality
    if "mean_tariff_increase" in df.columns:
        checks.append("")
        checks.append("6. TARIFF MERGE QUALITY")
        has_tariff = df["mean_tariff_increase"].notna().sum()
        checks.append(f"   Obs matched to tariff data: {has_tariff} ({has_tariff/len(df)*100:.1f}%)")
        checks.append(f"   Unmatched obs: {len(df) - has_tariff}")
        checks.append("   Note: Unmatched firms are in industries not covered by Section 301 tariffs")
        checks.append("   (e.g., services, finance, healthcare - tariffs apply to goods-producing sectors)")

    # Check 7: Accounting identity
    checks.append("")
    checks.append("7. ACCOUNTING IDENTITY CHECK (Foreign + Domestic ≈ Total)")
    has_all = df[["foreign_pretax_income", "domestic_pretax_income", "total_pretax_income"]].notna().all(axis=1)
    if has_all.any():
        sub = df[has_all].copy()
        sub["residual"] = sub["foreign_pretax_income"] + sub["domestic_pretax_income"] - sub["total_pretax_income"]
        checks.append(f"   Obs with all three income vars: {len(sub)}")
        checks.append(f"   Mean residual: {sub['residual'].mean():.2f}")
        checks.append(f"   Max absolute residual: {sub['residual'].abs().max():.2f}")
        checks.append(f"   Obs where |residual| > 1000: {(sub['residual'].abs() > 1000).sum()}")

    # Check 8: Year coverage by key variables
    checks.append("")
    checks.append("8. EFFECTIVE TAX RATE COVERAGE BY YEAR")
    if "effective_tax_rate" in df.columns:
        etr_by_year = df.groupby("year")["effective_tax_rate"].apply(lambda x: x.notna().sum())
        total_by_year = df.groupby("year").size()
        for yr in sorted(df["year"].unique()):
            n_etr = etr_by_year.get(yr, 0)
            n_total = total_by_year.get(yr, 0)
            checks.append(f"   {yr}: {n_etr} / {n_total} firms ({n_etr/n_total*100:.1f}%)")

    checks.append("")
    checks.append("9. FOREIGN PROFIT SHARE COVERAGE BY YEAR")
    fps_by_year = df.groupby("year")["foreign_profit_share"].apply(lambda x: x.notna().sum())
    total_by_year = df.groupby("year").size()
    for yr in sorted(df["year"].unique()):
        n_fps = fps_by_year.get(yr, 0)
        n_total = total_by_year.get(yr, 0)
        checks.append(f"   {yr}: {n_fps} / {n_total} firms ({n_fps/n_total*100:.1f}%)")

    report = "\n".join(checks)
    with open(OUTPUT_DIR / "data_checks.txt", "w") as f:
        f.write(report)
    print(f"  Saved to output/data_checks.txt")
    print("\n" + report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 65)
    print("Data Dictionary, Summary Statistics, and Quality Checks")
    print("=" * 65)

    df = pd.read_csv(PROCESSED_DIR / "merged_panel.csv")

    data_dict = create_data_dictionary(df)
    stats = create_summary_statistics(df)
    run_data_checks(df)
