"""
04_regression_analysis.py
Regression analysis: continuous difference-in-differences with TWFE.

Main specification: effective tax rate ~ tariff exposure x post-2018
Event study: year-by-year tariff exposure interactions (reference: 2017)

Standard errors clustered at NAICS 3-digit level (treatment varies at this level).
Wild cluster bootstrap corrects for few clusters (24 industries).

Robustness checks:
  - No controls
  - TCJA control (pre-treatment foreign profit share x post-TCJA, starting 2018)
  - SIC 1-digit x year FE (broad industry trends)
  - NAICS-2 x year FE (aggressive industry trends, for comparison)
  - NAICS-2 linear time trends (less aggressive alternative)
  - Placebo test (fake 2017 treatment on pre-2019 data)
  - Goods-producing firms only (NAICS 111-339)
  - ETR winsorized at 5th/95th percentiles
  - ETR trimmed to [0, 100]
  - ETR trimmed to [0, 60]
  - FPS as alternative outcome
  - COVID interaction (tariff effect net of COVID disruption)
  - Excluding COVID years (2020-2021)
  - Leave-one-industry-out (drop each NAICS-3 and re-run main spec)
  - Quantile regression at tau=0.25/0.50/0.75 (modified Canay 2011, median FE, cluster bootstrap)
  - Quantile regression on [0,60] trimmed ETR (strongest outlier robustness)
  - Leave-3-industries-out (all C(24,3) = 2,024 combinations)

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
from itertools import combinations

try:
    from statsmodels.regression.quantile_regression import QuantReg
    import statsmodels.api as sm
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CONTROLS = "log_revenue + rd_intensity + leverage"
CONTROLS_TCJA = "log_revenue + rd_intensity + leverage + tcja_exposure"
MAIN_FORMULA = f"etr_winsorized ~ tariff_x_post + {CONTROLS_TCJA} | cik + year"


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
df["rd_intensity"] = df["rd_intensity"].replace([np.inf, -np.inf], np.nan)
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

# -- TCJA exposure control --
# The Tax Cuts and Jobs Act was signed Dec 2017 and took effect for fiscal years
# beginning after Dec 31, 2017 — so FY2018 is the first affected year.
# GILTI, BEAT, and FDII differentially hit firms with more foreign operations.
# We control for this by interacting each firm's pre-treatment average foreign
# profit share with a post-TCJA indicator (year >= 2018), which correctly starts
# one year before the tariff treatment (year >= 2019).
pre_fps = df[df["year"] <= 2017].groupby("cik")["foreign_profit_share"].mean()
df["pre_fps"] = df["cik"].map(pre_fps)
df["post_tcja"] = (df["year"] >= 2018).astype(int)
df["tcja_exposure"] = df["pre_fps"].fillna(0) * df["post_tcja"]
n_tcja = df["pre_fps"].notna().sum()
print(f"TCJA exposure: {n_tcja:,} obs with pre-treatment FPS, "
      f"mean pre-FPS = {df['pre_fps'].mean():.3f}")

# -- Interaction term --
df["tariff_x_post"] = df["mean_tariff_increase"] * df["post2018"]

# -- Alternative tariff measures (standardized for comparability) --
# Each is z-scored so coefficients measure "effect of 1 SD increase in exposure"
for col in ["mean_tariff_increase", "n_products_targeted", "n_varieties_targeted", "sd_tariff_increase"]:
    vals = df[col].dropna()
    df[f"{col}_z"] = (df[col] - vals.mean()) / vals.std()

df["products_x_post"] = df["n_products_targeted_z"] * df["post2018"]
df["varieties_x_post"] = df["n_varieties_targeted_z"] * df["post2018"]
df["sd_tariff_x_post"] = df["sd_tariff_increase_z"] * df["post2018"]
df["mean_tariff_z_x_post"] = df["mean_tariff_increase_z"] * df["post2018"]

# -- Industry groupings for FE variants --
df["naics2"] = df["naics_code"].astype(str).str[:2]
df["sic1"] = df["sic_code"].astype(str).str[0]
df.loc[df["sic_code"].isna(), "sic1"] = "0"

# -- NAICS-3 as numeric cluster ID (wildboottest needs numeric, not string) --
df["naics3_str"] = df["naics3"].astype(str)
df["naics3_cluster"] = pd.Categorical(df["naics3_str"]).codes.astype(np.int64)

# -- COVID indicator (2020-2021) for robustness --
# COVID differentially affected tariff-exposed manufacturing firms through
# supply chain disruptions, loss carryforwards, and pandemic relief programs.
# The interaction allows the tariff effect to differ during COVID years.
df["covid"] = df["year"].isin([2020, 2021]).astype(int)
df["tariff_x_covid"] = df["mean_tariff_increase"] * df["covid"]

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
event_formula += f" + {CONTROLS_TCJA} | cik + year"

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

# -- R1b: Without TCJA control (baseline comparison) --
print("\n--- R1b: Without TCJA control (baseline comparison) ---")
r1b = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R1b: No TCJA control"] = r1b
print(r1b.summary())

# -- R2: SIC 1-digit x year FE (broad industry trends) --
# 8 SIC divisions x 10 years = 80 FE: controls for broad sector trends
# without absorbing within-sector variation that identifies the effect
print("\n--- R2: SIC 1-digit x year FE ---")
r2 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS_TCJA} | cik + sic1^year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R2: SIC1 x year FE"] = r2
print(r2.summary())

# -- R3: NAICS-2 x year FE (aggressive industry trends, for comparison) --
# 21 NAICS-2 groups x 10 years = 210 FE: absorbs most cross-industry variation
# Included for transparency but expected to lose significance
print("\n--- R3: NAICS-2 x year FE (aggressive, for comparison) ---")
r3 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS_TCJA} | cik + naics2^year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R3: NAICS2 x year FE"] = r3
print(r3.summary())

# -- R4: NAICS-2 linear time trends --
# Less aggressive than full NAICS-2 x year FE: allows each industry its
# own linear slope over time rather than absorbing every industry-year cell
print("\n--- R4: NAICS-2 linear time trends ---")
r4 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + {CONTROLS_TCJA} + i(naics2, year) | cik + year",
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
    f"etr_winsorized ~ tariff_x_post_placebo + {CONTROLS_TCJA} | cik + year",
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
    f"etr_w5_95 ~ tariff_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R7: ETR p5/p95"] = r7
print(r7.summary())

# -- R8: ETR trimmed to [0, 100] --
# Drops firm-years with economically implausible ETR values
print("\n--- R8: ETR trimmed to [0, 100] ---")
r8 = pf.feols(
    f"etr_trim_100 ~ tariff_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R8: ETR [0,100]"] = r8
print(r8.summary())

# -- R9: ETR trimmed to [0, 60] --
# Most restrictive: only firms with normal-range effective tax rates
print("\n--- R9: ETR trimmed to [0, 60] ---")
r9 = pf.feols(
    f"etr_trim_60 ~ tariff_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R9: ETR [0,60]"] = r9
print(r9.summary())

# -- R10: FPS as alternative outcome --
print("\n--- R10: FPS as outcome (alternative measure) ---")
r10 = pf.feols(
    f"foreign_profit_share_winsorized ~ tariff_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R10: FPS outcome"] = r10
print(r10.summary())

# -- R11: COVID interaction (does COVID attenuate the tariff effect?) --
# If COVID differentially hit tariff-exposed firms, the baseline estimate
# blends the tariff effect with COVID disruption. Adding tariff_x_covid
# isolates the tariff effect net of COVID.
print("\n--- R11: COVID interaction (tariff_x_post + tariff_x_covid) ---")
r11 = pf.feols(
    f"etr_winsorized ~ tariff_x_post + tariff_x_covid + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
robustness["R11: COVID interaction"] = r11
print(r11.summary())

# -- R12: Excluding COVID years entirely --
# Most conservative: drops 2020-2021 so COVID cannot affect the estimate at all
print("\n--- R12: Excluding COVID years (2020-2021) ---")
df_nocovid = df[~df["year"].isin([2020, 2021])].copy()
r12 = pf.feols(
    MAIN_FORMULA,
    data=df_nocovid, vcov={"CRV1": "naics3_str"},
)
robustness["R12: Excl. COVID years"] = r12
print(r12.summary())


# -----------------------------------------------------------------------
# Step 6b: Alternative tariff exposure measures (all standardized)
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 6b: Alternative Tariff Exposure Measures")
print("All measures standardized (z-scored) for comparability")
print("Coefficients = effect of 1 SD increase in tariff exposure")
print("=" * 65)

alt_measures = {}

# -- Mean tariff (standardized, for baseline comparison) --
print("\n--- A1: Mean tariff increase (z-scored) ---")
a1 = pf.feols(
    f"etr_winsorized ~ mean_tariff_z_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
alt_measures["A1: Mean tariff (z)"] = ("mean_tariff_z_x_post", a1)
print(a1.summary())

# -- Number of products targeted --
# Measures the breadth of tariff coverage within an industry
# More products hit = more of the industry's supply chain is affected
print("\n--- A2: Number of products targeted (z-scored) ---")
a2 = pf.feols(
    f"etr_winsorized ~ products_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
alt_measures["A2: N products (z)"] = ("products_x_post", a2)
print(a2.summary())

# -- Number of varieties targeted --
# Measures product x country combinations, captures import diversity
# Primary Metals has 14,093 varieties vs 1,147 products (many source countries)
print("\n--- A3: Number of varieties targeted (z-scored) ---")
a3 = pf.feols(
    f"etr_winsorized ~ varieties_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
alt_measures["A3: N varieties (z)"] = ("varieties_x_post", a3)
print(a3.summary())

# -- SD of tariff increase --
# Measures within-industry dispersion in tariff rates
# Higher SD = more heterogeneous tariff exposure within the industry
print("\n--- A4: SD of tariff increase (z-scored) ---")
a4 = pf.feols(
    f"etr_winsorized ~ sd_tariff_x_post + {CONTROLS_TCJA} | cik + year",
    data=df, vcov={"CRV1": "naics3_str"},
)
alt_measures["A4: SD tariff (z)"] = ("sd_tariff_x_post", a4)
print(a4.summary())

# Summary of alternative measures
print(f"\n{'=' * 65}")
print("ALTERNATIVE MEASURES SUMMARY (all standardized)")
print("=" * 65)
alt_header = f"{'Measure':<25} {'Coef':>8} {'SE':>8} {'p-val':>8} {'N':>7}"
print(alt_header)
print("-" * len(alt_header))
for label, (param, m) in alt_measures.items():
    c = m.coef()[param]
    s = m.se()[param]
    p = m.pvalue()[param]
    n = m._N
    print(f"{label:<25} {c:>8.1f} {s:>8.1f} {p:>8.3f} {n:>7}")
print("-" * len(alt_header))


# -----------------------------------------------------------------------
# Step 6c: Leave-one-industry-out robustness
# -----------------------------------------------------------------------
# Drop each NAICS-3 industry one at a time and re-run the main regression.
# If one industry (e.g., 334 Computer and Electronic Products) is driving
# the entire result, the coefficient should collapse when that industry
# is excluded. Stability across exclusions means multiple industries
# contribute to the finding.
print(f"\n{'=' * 65}")
print("STEP 6c: Leave-One-Industry-Out")
print("Drop each NAICS-3 industry and re-run main specification")
print("=" * 65)

# Get NAICS-3 industries present in the regression sample
reg_industries = reg_sample.groupby("naics3_str").agg(
    sector_name=("naics3_str", "first"),
    n_firms=("cik", "nunique"),
    n_obs=("cik", "size"),
).reset_index()

# Merge sector names from tariff file for display
tariff_labels = pd.read_csv(BASE_DIR / "tariff_exposure_naics3.csv",
                            usecols=["naics3", "sector_name"])
tariff_labels["naics3"] = tariff_labels["naics3"].astype(str)
reg_industries = reg_industries.merge(
    tariff_labels, left_on="naics3_str", right_on="naics3", how="left",
    suffixes=("_drop", ""),
)
reg_industries = reg_industries.drop(columns=["sector_name_drop", "naics3"], errors="ignore")

loio_results = []
industries_in_sample = sorted(reg_sample["naics3_str"].unique())

for ind in industries_in_sample:
    df_excl = df[df["naics3_str"] != ind].copy()
    n_clusters_excl = df_excl.dropna(
        subset=["etr_winsorized", "tariff_x_post", "log_revenue",
                "rd_intensity", "leverage"]
    )["naics3_str"].nunique()
    try:
        m = pf.feols(MAIN_FORMULA, data=df_excl, vcov={"CRV1": "naics3_str"})
        loio_results.append({
            "naics3": ind,
            "coef": m.coef()["tariff_x_post"],
            "se": m.se()["tariff_x_post"],
            "pvalue": m.pvalue()["tariff_x_post"],
            "n_obs": m._N,
            "n_clusters": n_clusters_excl,
        })
    except Exception as e:
        print(f"  Warning: failed for NAICS {ind}: {e}")
        loio_results.append({
            "naics3": ind, "coef": np.nan, "se": np.nan,
            "pvalue": np.nan, "n_obs": np.nan, "n_clusters": np.nan,
        })

loio_df = pd.DataFrame(loio_results)
loio_df = loio_df.merge(
    tariff_labels, left_on="naics3", right_on="naics3", how="left",
)

print(f"\nMain estimate (full sample): {model_main.coef()['tariff_x_post']:.1f}")
print(f"\n{'Excluded Industry':<45} {'Coef':>8} {'SE':>8} {'p-val':>8} {'N':>6} {'Cl':>4}")
print("-" * 83)
for _, row in loio_df.iterrows():
    label = f"{int(row['naics3']):>3} {row.get('sector_name', '')}"
    if len(label) > 44:
        label = label[:44]
    print(f"{label:<45} {row['coef']:>8.1f} {row['se']:>8.1f} "
          f"{row['pvalue']:>8.3f} {int(row['n_obs']):>6} {int(row['n_clusters']):>4}")
print("-" * 83)

loio_valid = loio_df.dropna(subset=["coef"])
print(f"\nCoefficient range: [{loio_valid['coef'].min():.1f}, {loio_valid['coef'].max():.1f}]")
print(f"All significant (p < 0.05): {(loio_valid['pvalue'] < 0.05).all()}")
print(f"Min p-value: {loio_valid['pvalue'].min():.4f}")
print(f"Max p-value: {loio_valid['pvalue'].max():.4f}")


# -----------------------------------------------------------------------
# Step 6d: Quantile (Median) Regression — Canay (2011) Two-Step
# -----------------------------------------------------------------------
# The main OLS result is sensitive to ETR outliers (vanishes at [0,60] trim).
# Quantile regression estimates the effect at the MEDIAN of the conditional
# ETR distribution — outliers get zero extra influence, no trimming needed.
#
# Canay (2011) two-step estimator for fixed-effects quantile regression:
#   1. Estimate firm FE from OLS (mean regression with firm + year FE)
#   2. Subtract estimated firm FE from the dependent variable
#   3. Run quantile regression on the FE-adjusted outcome with year dummies
#
# Consistent under the assumption that firm FE are pure location shifts
# (affect the level but not the shape of each firm's ETR distribution).
#
# Inference: paired cluster bootstrap at NAICS-3 level (500 reps).
# -----------------------------------------------------------------------

if not HAS_STATSMODELS:
    print(f"\n{'=' * 65}")
    print("STEP 6d: Quantile Regression — SKIPPED (statsmodels not installed)")
    print("Install with: pip install statsmodels")
    print("=" * 65)
    qr_results = {}
else:
    print(f"\n{'=' * 65}")
    print("STEP 6d: Quantile (Median) Regression")
    print("Modified Canay (2011): median-based firm FE (outlier-robust)")
    print("Cluster bootstrap re-estimates FE each iteration (999 reps)")
    print("=" * 65)

    # Prepare regression sample (same filters as main model)
    qr_cols = ["etr_winsorized", "tariff_x_post", "log_revenue", "rd_intensity",
               "leverage", "tcja_exposure", "cik", "year", "naics3_str"]
    qr_df = df[qr_cols].dropna().copy()
    qr_df = qr_df.reset_index(drop=True)

    # Drop singletons (firms with only 1 obs can't have a meaningful FE)
    firm_counts = qr_df["cik"].value_counts()
    singleton_firms = firm_counts[firm_counts < 2].index
    qr_df = qr_df[~qr_df["cik"].isin(singleton_firms)].reset_index(drop=True)
    print(f"  QR sample: {len(qr_df):,} obs, {qr_df['cik'].nunique():,} firms "
          f"(dropped {len(singleton_firms)} singletons)")

    # Helper: estimate firm FE as within-firm median ETR (outlier-robust),
    # subtract from ETR, build design matrix, return (X, y) ready for QR.
    regressors = ["tariff_x_post", "log_revenue", "rd_intensity", "leverage", "tcja_exposure"]

    def prepare_qr_data(data):
        """Compute median-based firm FE and return (X, y) for quantile regression."""
        firm_medians = data.groupby("cik")["etr_winsorized"].median()
        data = data.copy()
        data["firm_fe"] = data["cik"].map(firm_medians)
        data["etr_adj"] = data["etr_winsorized"] - data["firm_fe"]
        yr_dum = pd.get_dummies(data["year"], prefix="yr", drop_first=True, dtype=float)
        X = pd.concat([data[regressors].reset_index(drop=True),
                        yr_dum.reset_index(drop=True)], axis=1)
        X = sm.add_constant(X)
        y = data["etr_adj"].reset_index(drop=True)
        return X, y

    # Full-sample point estimates
    X_qr, y_qr = prepare_qr_data(qr_df)
    quantiles = [0.25, 0.50, 0.75]
    qr_results = {}

    for tau in quantiles:
        qr_fit = QuantReg(y_qr, X_qr).fit(q=tau, max_iter=1000)
        qr_results[tau] = {
            "coef": qr_fit.params["tariff_x_post"],
            "se_pointwise": qr_fit.bse["tariff_x_post"],
            "pvalue_pointwise": qr_fit.pvalues["tariff_x_post"],
        }
        print(f"\n  tau = {tau:.2f} (pointwise): coef = {qr_fit.params['tariff_x_post']:.1f}, "
              f"SE = {qr_fit.bse['tariff_x_post']:.1f}, "
              f"p = {qr_fit.pvalues['tariff_x_post']:.3f}")

    # Cluster bootstrap: re-estimates median firm FE + QR each iteration
    N_BOOT = 999
    print(f"\n  Running cluster bootstrap ({N_BOOT} reps, re-estimating FE each rep)...")
    np.random.seed(42)
    clusters = qr_df["naics3_str"].values
    unique_clusters = np.unique(clusters)
    cluster_indices = {cl: np.where(clusters == cl)[0] for cl in unique_clusters}
    boot_coefs = {tau: [] for tau in quantiles}

    for b in range(N_BOOT):
        # Resample entire NAICS-3 clusters with replacement
        boot_cls = np.random.choice(unique_clusters, size=len(unique_clusters), replace=True)
        boot_idx = np.concatenate([cluster_indices[cl] for cl in boot_cls])
        boot_data = qr_df.iloc[boot_idx].reset_index(drop=True)

        # Re-estimate median firm FE on bootstrap sample (Step 1 + 2)
        try:
            X_b, y_b = prepare_qr_data(boot_data)
        except Exception:
            continue

        for tau in quantiles:
            try:
                qr_b = QuantReg(y_b, X_b).fit(q=tau, max_iter=1000)
                boot_coefs[tau].append(qr_b.params["tariff_x_post"])
            except Exception:
                pass

        if (b + 1) % 200 == 0:
            print(f"    ... {b + 1}/{N_BOOT} bootstrap reps done")

    # Report cluster-bootstrapped results
    print(f"\n  {'tau':<6} {'Coef':>8} {'Boot SE':>10} {'95% CI':>28} {'Sig':>6}")
    print(f"  {'-' * 62}")
    for tau in quantiles:
        coefs_arr = np.array(boot_coefs[tau])
        point = qr_results[tau]["coef"]
        boot_se = coefs_arr.std()
        ci_lo = np.percentile(coefs_arr, 2.5)
        ci_hi = np.percentile(coefs_arr, 97.5)
        sig = "*" if (ci_lo > 0 or ci_hi < 0) else ""
        print(f"  {tau:<6} {point:>8.1f} {boot_se:>10.1f} "
              f"  [{ci_lo:>8.1f}, {ci_hi:>8.1f}] {sig:>6}")
        qr_results[tau]["boot_se"] = boot_se
        qr_results[tau]["ci_lo"] = ci_lo
        qr_results[tau]["ci_hi"] = ci_hi
        qr_results[tau]["sig"] = ci_lo > 0 or ci_hi < 0

    # Median regression on [0,60] trimmed ETR (strongest outlier robustness test)
    # If this is significant, the effect exists even among normal-range ETR firms
    # estimated with an outlier-robust method.
    print(f"\n  --- Median regression on ETR trimmed to [0, 60] ---")
    qr_trim_cols = ["etr_trim_60", "tariff_x_post", "log_revenue", "rd_intensity",
                    "leverage", "tcja_exposure", "cik", "year", "naics3_str"]
    qr_trim_df = df[qr_trim_cols].dropna().copy().reset_index(drop=True)
    trim_counts = qr_trim_df["cik"].value_counts()
    trim_singletons = trim_counts[trim_counts < 2].index
    qr_trim_df = qr_trim_df[~qr_trim_df["cik"].isin(trim_singletons)].reset_index(drop=True)
    print(f"  Trimmed sample: {len(qr_trim_df):,} obs, {qr_trim_df['cik'].nunique():,} firms")

    # Use same median FE approach but on trimmed ETR
    def prepare_qr_trimmed(data):
        firm_medians = data.groupby("cik")["etr_trim_60"].median()
        data = data.copy()
        data["firm_fe"] = data["cik"].map(firm_medians)
        data["etr_adj"] = data["etr_trim_60"] - data["firm_fe"]
        yr_dum = pd.get_dummies(data["year"], prefix="yr", drop_first=True, dtype=float)
        X = pd.concat([data[regressors].reset_index(drop=True),
                        yr_dum.reset_index(drop=True)], axis=1)
        X = sm.add_constant(X)
        y = data["etr_adj"].reset_index(drop=True)
        return X, y

    X_trim, y_trim = prepare_qr_trimmed(qr_trim_df)
    qr_trim_fit = QuantReg(y_trim, X_trim).fit(q=0.5, max_iter=1000)
    qr_trim_coef = qr_trim_fit.params["tariff_x_post"]
    qr_trim_se = qr_trim_fit.bse["tariff_x_post"]
    print(f"  Median QR on [0,60] (pointwise): coef = {qr_trim_coef:.1f}, "
          f"SE = {qr_trim_se:.1f}, p = {qr_trim_fit.pvalues['tariff_x_post']:.3f}")

    # Bootstrap for trimmed sample
    print(f"  Running cluster bootstrap ({N_BOOT} reps) for [0,60] median...")
    trim_clusters = qr_trim_df["naics3_str"].values
    trim_unique_cl = np.unique(trim_clusters)
    trim_cl_idx = {cl: np.where(trim_clusters == cl)[0] for cl in trim_unique_cl}
    trim_boot_coefs = []

    for b in range(N_BOOT):
        boot_cls = np.random.choice(trim_unique_cl, size=len(trim_unique_cl), replace=True)
        boot_idx = np.concatenate([trim_cl_idx[cl] for cl in boot_cls])
        boot_data = qr_trim_df.iloc[boot_idx].reset_index(drop=True)
        try:
            X_b, y_b = prepare_qr_trimmed(boot_data)
            fit_b = QuantReg(y_b, X_b).fit(q=0.5, max_iter=1000)
            trim_boot_coefs.append(fit_b.params["tariff_x_post"])
        except Exception:
            pass
        if (b + 1) % 200 == 0:
            print(f"    ... {b + 1}/{N_BOOT} bootstrap reps done")

    trim_arr = np.array(trim_boot_coefs)
    trim_boot_se = trim_arr.std()
    trim_ci_lo = np.percentile(trim_arr, 2.5)
    trim_ci_hi = np.percentile(trim_arr, 97.5)
    trim_sig = "*" if (trim_ci_lo > 0 or trim_ci_hi < 0) else ""
    print(f"\n  Median QR [0,60] (bootstrap): coef = {qr_trim_coef:.1f}, "
          f"SE = {trim_boot_se:.1f}, "
          f"95% CI = [{trim_ci_lo:.1f}, {trim_ci_hi:.1f}] {trim_sig}")
    qr_results["trim60"] = {
        "coef": qr_trim_coef, "boot_se": trim_boot_se,
        "ci_lo": trim_ci_lo, "ci_hi": trim_ci_hi,
        "sig": trim_ci_lo > 0 or trim_ci_hi < 0,
    }


# -----------------------------------------------------------------------
# Step 6e: Leave-Multiple-Industries-Out (drop 3 at a time)
# -----------------------------------------------------------------------
# The single-industry leave-out test (Step 6c) shows no one industry drives
# the result. But what if a coalition of 2-3 industries jointly drive it?
# Test all C(24,3) = 2,024 combinations of dropping 3 industries at once.
# If the result survives every combination, no small group of industries
# can explain the finding.
# -----------------------------------------------------------------------
print(f"\n{'=' * 65}")
print("STEP 6e: Leave-Multiple-Industries-Out (drop 3 at a time)")
print(f"Testing all C({len(industries_in_sample)},3) = "
      f"{len(list(combinations(industries_in_sample, 3))):,} combinations")
print("=" * 65)

drop3_combos = list(combinations(industries_in_sample, 3))
drop3_results = []

for i, combo in enumerate(drop3_combos):
    df_excl = df[~df["naics3_str"].isin(combo)].copy()
    try:
        m = pf.feols(MAIN_FORMULA, data=df_excl, vcov={"CRV1": "naics3_str"})
        drop3_results.append({
            "dropped": combo,
            "coef": m.coef()["tariff_x_post"],
            "se": m.se()["tariff_x_post"],
            "pvalue": m.pvalue()["tariff_x_post"],
            "n_obs": m._N,
        })
    except Exception:
        drop3_results.append({
            "dropped": combo, "coef": np.nan, "se": np.nan,
            "pvalue": np.nan, "n_obs": np.nan,
        })
    if (i + 1) % 500 == 0:
        print(f"  ... {i + 1:,}/{len(drop3_combos):,} combinations done")

drop3_df = pd.DataFrame(drop3_results).dropna(subset=["coef"])
print(f"\n  Completed {len(drop3_df):,} regressions")

n_sig = (drop3_df["pvalue"] < 0.05).sum()
pct_sig = n_sig / len(drop3_df) * 100

print(f"\n  Coefficient distribution:")
print(f"    Min:    {drop3_df['coef'].min():.1f}")
print(f"    p25:    {drop3_df['coef'].quantile(0.25):.1f}")
print(f"    Median: {drop3_df['coef'].median():.1f}")
print(f"    p75:    {drop3_df['coef'].quantile(0.75):.1f}")
print(f"    Max:    {drop3_df['coef'].max():.1f}")
print(f"\n  Significant at p < 0.05: {n_sig:,}/{len(drop3_df):,} ({pct_sig:.1f}%)")
print(f"  p-value range: [{drop3_df['pvalue'].min():.4f}, {drop3_df['pvalue'].max():.4f}]")

# Show the worst-case combination (highest p-value)
worst = drop3_df.loc[drop3_df["pvalue"].idxmax()]
worst_names = []
for ind in worst["dropped"]:
    match = tariff_labels[tariff_labels["naics3"] == ind]
    name = match["sector_name"].values[0] if len(match) > 0 else ind
    worst_names.append(f"{ind} ({name})")
print(f"\n  Worst-case combination (highest p-value):")
print(f"    Dropped: {', '.join(worst_names)}")
print(f"    Coef = {worst['coef']:.1f}, p = {worst['pvalue']:.3f}")

# Show the best-case combination (most negative coefficient)
best = drop3_df.loc[drop3_df["coef"].idxmin()]
best_names = []
for ind in best["dropped"]:
    match = tariff_labels[tariff_labels["naics3"] == ind]
    name = match["sector_name"].values[0] if len(match) > 0 else ind
    best_names.append(f"{ind} ({name})")
print(f"\n  Strongest combination (most negative coef):")
print(f"    Dropped: {', '.join(best_names)}")
print(f"    Coef = {best['coef']:.1f}, p = {best['pvalue']:.3f}")


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
print(f"{'Main (ETR + TCJA ctrl)':<30} {c:>8.1f} {s:>8.1f} {p:>8.3f} {n:>7}")

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
    # Print COVID interaction coefficient on its own line
    if label == "R11: COVID interaction":
        cc = m.coef()["tariff_x_covid"]
        cs = m.se()["tariff_x_covid"]
        cp = m.pvalue()["tariff_x_covid"]
        print(f"{'  └ tariff_x_covid':<30} {cc:>8.1f} {cs:>8.1f} {cp:>8.3f} {n:>7}")

print("-" * len(header))

# Quantile regression results
if qr_results:
    print(f"\n{'Quantile Regression (median FE)':<30} {'Coef':>8} {'BootSE':>8} {'95% CI':>24}")
    print("-" * 74)
    for tau in [0.25, 0.50, 0.75]:
        if tau in qr_results:
            r = qr_results[tau]
            sig = "*" if r.get("sig") else ""
            print(f"{'  QR tau=' + str(tau):<30} {r['coef']:>8.1f} {r.get('boot_se', 0):>8.1f} "
                  f"  [{r.get('ci_lo', 0):>8.1f}, {r.get('ci_hi', 0):>8.1f}] {sig}")
    if "trim60" in qr_results:
        r = qr_results["trim60"]
        sig = "*" if r.get("sig") else ""
        print(f"{'  QR median [0,60] trim':<30} {r['coef']:>8.1f} {r.get('boot_se', 0):>8.1f} "
              f"  [{r.get('ci_lo', 0):>8.1f}, {r.get('ci_hi', 0):>8.1f}] {sig}")
    print("-" * 74)

# Leave-3-industries-out summary
print(f"\n{'Leave-3-Industries-Out':<30} {'Median Coef':>12} {'% Sig (p<.05)':>15} "
      f"{'Coef Range':>20}")
print("-" * 80)
print(f"{'  Drop 3 (N=' + str(len(drop3_df)) + ')':<30} {drop3_df['coef'].median():>12.1f} "
      f"{pct_sig:>14.1f}% "
      f"  [{drop3_df['coef'].min():>8.1f}, {drop3_df['coef'].max():>8.1f}]")
print("-" * 80)

print("\nAnalysis complete.")
