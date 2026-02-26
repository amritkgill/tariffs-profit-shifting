"""
04_regression_analysis.py
Regression analysis: continuous difference-in-differences with TWFE.

Main specification: effective tax rate ~ tariff exposure x post-2018
Event study: year-by-year tariff exposure interactions (reference: 2017)
Robustness: no controls, NAICS-2 x year FE, FPS as alternative outcome

Input:
  - data/processed/merged_panel.csv

Output:
  - Regression results printed to console
  - output/event_study_etr.png (event study plot)
"""

import pandas as pd
import numpy as np
import pyfixest as pf
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# -----------------------------------------------------------------------
# Step 1: Load data and construct regression variables
# -----------------------------------------------------------------------
print("=" * 65)
print("STEP 1: Variable Construction")
print("=" * 65)

df = pd.read_csv(PROCESSED_DIR / "merged_panel.csv")
print(f"Loaded {len(df):,} observations, {df['cik'].nunique():,} firms\n")

# -- Post-2018 indicator --
# Tariffs were imposed in mid-2018 but the full effect shows up in 2019+
# (firms' 2018 annual reports mostly cover pre-tariff activity)
df["post2018"] = (df["year"] >= 2019).astype(int)

# -- Log revenue (firm size control) --
# Using log because revenue is heavily right-skewed
df["log_revenue"] = np.log(df["total_revenue"] + 1)

# -- R&D intensity (R&D / revenue) --
# Measures how innovation-heavy the firm is
df["rd_intensity"] = df["rd_expense"] / df["total_revenue"]

# -- Leverage (debt / assets) --
# Measures how indebted the firm is
df["leverage"] = df["total_debt"] / df["total_assets"]

# -- Winsorize ETR at 1st/99th percentiles --
# Raw Bloomberg ETR has extreme outliers (values up to 138,000+)
# that distort regressions, so we cap them like we did for FPS
p01 = df["effective_tax_rate"].quantile(0.01)
p99 = df["effective_tax_rate"].quantile(0.99)
df["etr_winsorized"] = df["effective_tax_rate"].clip(lower=p01, upper=p99)
print(f"Winsorized ETR: clipped to [{p01:.1f}, {p99:.1f}]")

# -- Interaction term: tariff exposure x post-2018 --
# This is the key DiD variable
df["tariff_x_post"] = df["mean_tariff_increase"] * df["post2018"]

# -- NAICS 2-digit (for industry x year FE robustness check) --
df["naics2"] = df["naics_code"].astype(str).str[:2]

# -- Event study year interactions (reference year: 2017) --
years = sorted(df["year"].unique())
for y in years:
    if y != 2017:
        df[f"tariff_x_{y}"] = df["mean_tariff_increase"] * (df["year"] == y).astype(int)

print("Constructed variables:")
print(f"  post2018:            {df['post2018'].sum():,} obs in post period")
print(f"  log_revenue:         {df['log_revenue'].notna().sum():,} non-null")
print(f"  rd_intensity:        {df['rd_intensity'].notna().sum():,} non-null")
print(f"  leverage:            {df['leverage'].notna().sum():,} non-null")
print(f"  tariff_x_post:       {df['tariff_x_post'].notna().sum():,} non-null")
print(f"  etr_winsorized:     {df['etr_winsorized'].notna().sum():,} non-null")


# -----------------------------------------------------------------------
# Step 2: Main diff-in-diff — ETR as outcome
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 2: Main Diff-in-Diff Regression")
print("ETR (winsorized) ~ tariff_x_post + controls | firm FE + year FE")
print("=" * 65)

model_main = pf.feols(
    "etr_winsorized ~ tariff_x_post + log_revenue + rd_intensity + leverage | cik + year",
    data=df,
)
print(model_main.summary())


# -----------------------------------------------------------------------
# Step 3: Event study — ETR with year-by-year tariff interactions
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 3: Event Study")
print("ETR (winsorized) ~ tariff_x_year + controls | firm FE + year FE")
print("Reference year: 2017")
print("=" * 65)

event_vars = [f"tariff_x_{y}" for y in years if y != 2017]
event_formula = "etr_winsorized ~ " + " + ".join(event_vars)
event_formula += " + log_revenue + rd_intensity + leverage | cik + year"

model_event = pf.feols(event_formula, data=df)
print(model_event.summary())

# Build a table of event study coefficients
event_rows = []
for y in years:
    if y == 2017:
        event_rows.append({"year": y, "coef": 0.0, "se": 0.0, "pvalue": np.nan})
    else:
        var = f"tariff_x_{y}"
        event_rows.append({
            "year": y,
            "coef": model_event.coef()[var],
            "se": model_event.se()[var],
            "pvalue": model_event.pvalue()[var],
        })

event_df = pd.DataFrame(event_rows).set_index("year")
event_df["ci_low"] = event_df["coef"] - 1.96 * event_df["se"]
event_df["ci_high"] = event_df["coef"] + 1.96 * event_df["se"]

print("\nEvent study coefficients:")
print("-" * 55)
print(f"{'Year':>6}  {'Coef':>10}  {'SE':>10}  {'p-value':>10}  {'95% CI':>20}")
print("-" * 55)
for y, row in event_df.iterrows():
    pval = f"{row['pvalue']:.3f}" if not np.isnan(row["pvalue"]) else "ref"
    ci = f"[{row['ci_low']:.1f}, {row['ci_high']:.1f}]"
    print(f"{y:>6}  {row['coef']:>10.3f}  {row['se']:>10.3f}  {pval:>10}  {ci:>20}")
print("-" * 55)


# -----------------------------------------------------------------------
# Step 4: Event study plot
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 4: Event Study Plot")
print("=" * 65)

fig, ax = plt.subplots(figsize=(10, 6))

ax.fill_between(
    event_df.index, event_df["ci_low"], event_df["ci_high"],
    alpha=0.15, color="#2c3e50",
)
ax.errorbar(
    event_df.index, event_df["coef"],
    yerr=1.96 * event_df["se"],
    fmt="o-",
    color="#2c3e50",
    capsize=4,
    capthick=1.5,
    linewidth=1.5,
    markersize=6,
)
ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
ax.axvline(
    x=2018, color="red", linestyle="--", linewidth=0.8,
    alpha=0.7, label="Tariffs imposed (2018)",
)

ax.set_xlabel("Year", fontsize=12)
ax.set_ylabel("Coefficient (effect on ETR)", fontsize=12)
ax.set_title("Event Study: Tariff Exposure and Effective Tax Rate", fontsize=14)
ax.legend(fontsize=10)
ax.set_xticks(event_df.index)
plt.tight_layout()

plot_path = OUTPUT_DIR / "event_study_etr.png"
plt.savefig(plot_path, dpi=150)
print(f"Saved: {plot_path}")


# -----------------------------------------------------------------------
# Step 5: Robustness checks
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 5: Robustness Checks")
print("=" * 65)

# -- R1: No controls --
print("\n--- R1: No controls ---")
print("ETR (winsorized) ~ tariff_x_post | firm FE + year FE\n")
r1 = pf.feols(
    "etr_winsorized ~ tariff_x_post | cik + year",
    data=df,
)
print(r1.summary())

# -- R2: NAICS-2 x year FE (controls for industry-specific trends) --
print("\n--- R2: Industry x year fixed effects ---")
print("ETR (winsorized) ~ tariff_x_post + controls | firm FE + NAICS2 x year FE\n")
r2 = pf.feols(
    "etr_winsorized ~ tariff_x_post + log_revenue + rd_intensity + leverage | cik + naics2^year",
    data=df,
)
print(r2.summary())

# -- R3: FPS as alternative outcome (null result, included for comparison) --
print("\n--- R3: FPS as outcome (alternative measure) ---")
print("FPS_winsorized ~ tariff_x_post + controls | firm FE + year FE\n")
r3 = pf.feols(
    "foreign_profit_share_winsorized ~ tariff_x_post + log_revenue + rd_intensity + leverage | cik + year",
    data=df,
)
print(r3.summary())

# -----------------------------------------------------------------------
# Summary table
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("SUMMARY: Key coefficients on tariff_x_post")
print("=" * 65)
print(f"{'Specification':<40} {'Coef':>10} {'SE':>10} {'p-value':>10}")
print("-" * 70)

specs = [
    ("Main (ETR + controls)", model_main),
    ("R1: ETR, no controls", r1),
    ("R2: ETR, NAICS2 x year FE", r2),
    ("R3: FPS (alternative outcome)", r3),
]
for label, m in specs:
    c = m.coef()["tariff_x_post"]
    s = m.se()["tariff_x_post"]
    p = m.pvalue()["tariff_x_post"]
    print(f"{label:<40} {c:>10.3f} {s:>10.3f} {p:>10.3f}")

print("-" * 70)
print("\nAnalysis complete.")
