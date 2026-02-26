"""
04_regression_analysis.py
Regression analysis: continuous difference-in-differences with TWFE.

Main specification: effective tax rate ~ tariff exposure x post-2018
Event study: year-by-year tariff exposure interactions (reference: 2017)

Standard errors clustered at NAICS 3-digit level (treatment varies at this level).
Wild cluster bootstrap corrects for few clusters (24 industries).

Robustness checks:
  - No controls
  - SIC 1-digit x year FE (broad industry trends)
  - NAICS-2 x year FE (aggressive industry trends, for comparison)
  - NAICS-2 linear time trends (less aggressive alternative)
  - Placebo test (fake 2017 treatment on pre-2019 data)
  - Goods-producing firms only (NAICS 111-339)
  - ETR winsorized at 5th/95th percentiles
  - ETR trimmed to [0, 100]
  - ETR trimmed to [0, 60]
  - FPS as alternative outcome

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

CONTROLS = "log_revenue + rd_intensity + leverage"
MAIN_FORMULA = f"etr_winsorized ~ tariff_x_post + {CONTROLS} | cik + year"


# -----------------------------------------------------------------------
# Step 1: Load data and construct regression variables
# -----------------------------------------------------------------------
print("=" * 65)
print("STEP 1: Variable Construction")
print("=" * 65)

df = pd.read_csv(PROCESSED_DIR / "merged_panel.csv")
print(f"Loaded {len(df):,} observations, {df['cik'].nunique():,} firms\n")

# -- Post-2018 indicator --
# Tariffs imposed mid-2018; full effect in fiscal years starting 2019
df["post2018"] = (df["year"] >= 2019).astype(int)

# -- Controls --
df["log_revenue"] = np.log(df["total_revenue"] + 1)
df["rd_intensity"] = df["rd_expense"] / df["total_revenue"]
df["leverage"] = df["total_debt"] / df["total_assets"]

# -- Main ETR winsorization (1st/99th percentiles) --
p01 = df["effective_tax_rate"].quantile(0.01)
p99 = df["effective_tax_rate"].quantile(0.99)
df["etr_winsorized"] = df["effective_tax_rate"].clip(lower=p01, upper=p99)
print(f"ETR winsorized (p1/p99): [{p01:.1f}, {p99:.1f}]")

# -- Tighter winsorization (5th/95th) for robustness --
p05 = df["effective_tax_rate"].quantile(0.05)
p95 = df["effective_tax_rate"].quantile(0.95)
df["etr_w5_95"] = df["effective_tax_rate"].clip(lower=p05, upper=p95)
print(f"ETR winsorized (p5/p95): [{p05:.1f}, {p95:.1f}]")

# -- Trimmed ETR variants for robustness --
df["etr_trim_100"] = df["effective_tax_rate"].where(
    (df["effective_tax_rate"] >= 0) & (df["effective_tax_rate"] <= 100)
)
df["etr_trim_60"] = df["effective_tax_rate"].where(
    (df["effective_tax_rate"] >= 0) & (df["effective_tax_rate"] <= 60)
)
print(f"ETR trimmed [0,100]: {df['etr_trim_100'].notna().sum():,} obs")
print(f"ETR trimmed [0,60]:  {df['etr_trim_60'].notna().sum():,} obs")

# -- Interaction term --
df["tariff_x_post"] = df["mean_tariff_increase"] * df["post2018"]

# -- Industry groupings for FE variants --
df["naics2"] = df["naics_code"].astype(str).str[:2]
df["sic1"] = df["sic_code"].astype(str).str[0]
df.loc[df["sic_code"].isna(), "sic1"] = "0"

# -- NAICS-3 as numeric cluster ID (wildboottest needs numeric, not string) --
df["naics3_str"] = df["naics3"].astype(str)
df["naics3_cluster"] = pd.Categorical(df["naics3_str"]).codes.astype(np.int64)

# -- Goods-producing flag (NAICS 111-339) --
naics3_num = pd.to_numeric(df["naics3"], errors="coerce")
df["goods_producing"] = naics3_num.between(111, 339)

# -- Placebo variables (fake treatment at 2017, using only pre-2019 data) --
df["post_placebo"] = (df["year"] >= 2017).astype(int)
df["tariff_x_post_placebo"] = df["mean_tariff_increase"] * df["post_placebo"]

# -- Event study year interactions (reference: 2017) --
years = sorted(df["year"].unique())
for y in years:
    if y != 2017:
        df[f"tariff_x_{y}"] = df["mean_tariff_increase"] * (df["year"] == y).astype(int)

# -- Regression sample summary --
reg_sample = df.dropna(subset=["etr_winsorized", "tariff_x_post", "log_revenue",
                                "rd_intensity", "leverage"])
n_clusters = reg_sample["naics3_str"].nunique()
print(f"\nRegression sample: {len(reg_sample):,} obs, "
      f"{reg_sample['cik'].nunique():,} firms, "
      f"{n_clusters} NAICS-3 clusters")


# -----------------------------------------------------------------------
# Step 2: Main diff-in-diff (NAICS-3 clustered SEs)
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 2: Main Diff-in-Diff Regression")
print("ETR ~ tariff_x_post + controls | firm FE + year FE")
print("Standard errors clustered at NAICS 3-digit industry level")
print("=" * 65)

model_main = pf.feols(MAIN_FORMULA, data=df, vcov={"CRV1": "naics3_str"})
print(model_main.summary())


# -----------------------------------------------------------------------
# Step 3: Wild cluster bootstrap
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 3: Wild Cluster Bootstrap")
print(f"Correcting for few clusters ({n_clusters} NAICS-3 industries)")
print("9,999 bootstrap replications, Rademacher weights")
print("=" * 65)

boot = model_main.wildboottest(
    param="tariff_x_post",
    cluster="naics3_cluster",
    reps=9999,
    seed=42,
)
print(boot)


# -----------------------------------------------------------------------
# Step 4: Event study (NAICS-3 clustered SEs)
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 4: Event Study")
print("ETR ~ tariff_x_year + controls | firm FE + year FE")
print("Reference year: 2017")
print("=" * 65)

event_vars = [f"tariff_x_{y}" for y in years if y != 2017]
event_formula = "etr_winsorized ~ " + " + ".join(event_vars)
event_formula += f" + {CONTROLS} | cik + year"

model_event = pf.feols(event_formula, data=df, vcov={"CRV1": "naics3_str"})
print(model_event.summary())

# Build event study coefficient table
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

print("\nEvent study coefficients (NAICS-3 clustered SEs):")
print("-" * 60)
print(f"{'Year':>6}  {'Coef':>10}  {'SE':>10}  {'p-value':>10}  {'95% CI':>22}")
print("-" * 60)
for y, row in event_df.iterrows():
    pval = f"{row['pvalue']:.3f}" if not np.isnan(row["pvalue"]) else "ref"
    ci = f"[{row['ci_low']:.1f}, {row['ci_high']:.1f}]"
    print(f"{y:>6}  {row['coef']:>10.3f}  {row['se']:>10.3f}  {pval:>10}  {ci:>22}")
print("-" * 60)


# -----------------------------------------------------------------------
# Step 5: Event study plot
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 5: Event Study Plot")
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
# Step 6: Robustness checks (all with NAICS-3 clustered SEs)
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 6: Robustness Checks")
print("All specifications use NAICS 3-digit clustered standard errors")
print("=" * 65)

robustness = {}

# -- R1: No controls --
print("\n--- R1: No controls ---")
r1 = pf.feols(
    "etr_winsorized ~ tariff_x_post | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R1: No controls"] = r1
print(r1.summary())

# -- R2: SIC 1-digit x year FE (broad industry trends) --
# 8 SIC divisions x 10 years = 80 FE: controls for broad sector trends
# without absorbing within-sector variation that identifies the effect
print("\n--- R2: SIC 1-digit x year FE ---")
r2 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS} | cik + sic1^year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R2: SIC1 x year FE"] = r2
print(r2.summary())

# -- R3: NAICS-2 x year FE (aggressive industry trends, for comparison) --
# 21 NAICS-2 groups x 10 years = 210 FE: absorbs most cross-industry variation
# Included for transparency but expected to lose significance
print("\n--- R3: NAICS-2 x year FE (aggressive, for comparison) ---")
r3 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS} | cik + naics2^year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R3: NAICS2 x year FE"] = r3
print(r3.summary())

# -- R4: NAICS-2 linear time trends --
# Less aggressive than full NAICS-2 x year FE: allows each industry its
# own linear slope over time rather than absorbing every industry-year cell
print("\n--- R4: NAICS-2 linear time trends ---")
r4 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS} + i(naics2, year) | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R4: NAICS2 linear trends"] = r4
print(r4.summary())

# -- R5: Placebo test (fake treatment at 2017, pre-2019 data only) --
# Uses 2015-2018 data with fake post = 2017+
# Should find NO significant effect if pre-trends are clean
print("\n--- R5: Placebo test (fake treatment at 2017, 2015-2018 data) ---")
df_pre = df[df["year"] <= 2018].copy()
r5 = pf.feols(
    f"etr_winsorized ~ tariff_x_post_placebo + {CONTROLS} | cik + year",
    data=df_pre, vcov={"CRV1": "naics3_str"},
)
robustness["R5: Placebo (2017)"] = r5
print(r5.summary())

# -- R6: Balanced panel only (firms with all 10 years) --
# Tests whether attrition (firms entering/exiting) drives the result
# Note: goods-only subsample is redundant because only goods firms have
# tariff data, so the main model already restricts to goods firms
print("\n--- R6: Balanced panel only (firms with all 10 years) ---")
firm_year_counts = df.groupby("cik")["year"].nunique()
balanced_firms = firm_year_counts[firm_year_counts == 10].index
df_balanced = df[df["cik"].isin(balanced_firms)].copy()
print(f"  Balanced sample: {len(df_balanced):,} obs, {df_balanced['cik'].nunique():,} firms")
r6 = pf.feols(
    MAIN_FORMULA,
    data=df_balanced, vcov={"CRV1": "naics3_str"},
)
robustness["R6: Balanced panel"] = r6
print(r6.summary())

# -- R7: ETR winsorized at 5th/95th --
print("\n--- R7: Tighter winsorization (5th/95th) ---")
r7 = pf.feols(
    f"etr_w5_95 ~ tariff_x_post + {CONTROLS} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R7: ETR p5/p95"] = r7
print(r7.summary())

# -- R8: ETR trimmed to [0, 100] --
# Drops firm-years with economically implausible ETR values
print("\n--- R8: ETR trimmed to [0, 100] ---")
r8 = pf.feols(
    f"etr_trim_100 ~ tariff_x_post + {CONTROLS} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R8: ETR [0,100]"] = r8
print(r8.summary())

# -- R9: ETR trimmed to [0, 60] --
# Most restrictive: only firms with normal-range effective tax rates
print("\n--- R9: ETR trimmed to [0, 60] ---")
r9 = pf.feols(
    f"etr_trim_60 ~ tariff_x_post + {CONTROLS} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R9: ETR [0,60]"] = r9
print(r9.summary())

# -- R10: FPS as alternative outcome --
print("\n--- R10: FPS as outcome (alternative measure) ---")
r10 = pf.feols(
    f"foreign_profit_share_winsorized ~ tariff_x_post + {CONTROLS} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R10: FPS outcome"] = r10
print(r10.summary())


# -----------------------------------------------------------------------
# Step 7: Summary table
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("SUMMARY: All specifications (NAICS-3 clustered SEs)")
print("=" * 65)

header = f"{'Specification':<30} {'Coef':>8} {'SE':>8} {'p-val':>8} {'N':>7}"
print(header)
print("-" * len(header))

# Main model
c = model_main.coef()["tariff_x_post"]
s = model_main.se()["tariff_x_post"]
p = model_main.pvalue()["tariff_x_post"]
n = model_main._N
print(f"{'Main (ETR + controls)':<30} {c:>8.1f} {s:>8.1f} {p:>8.3f} {n:>7}")

# Robustness checks
for label, m in robustness.items():
    param_name = "tariff_x_post"
    if label == "R5: Placebo (2017)":
        param_name = "tariff_x_post_placebo"
    c = m.coef()[param_name]
    s = m.se()[param_name]
    p = m.pvalue()[param_name]
    n = m._N
    print(f"{label:<30} {c:>8.1f} {s:>8.1f} {p:>8.3f} {n:>7}")

print("-" * len(header))
print("\nAnalysis complete.")
