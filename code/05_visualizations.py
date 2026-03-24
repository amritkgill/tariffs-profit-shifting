"""
05_visualizations.py
Generate publication-quality figures for the capstone.

Inputs:
  - data/processed/merged_panel.csv
  - tariff_exposure_naics3.csv

Outputs (all saved to output/):
  - etr_trends_by_exposure.png   — Mean ETR over time by tariff exposure group
  - tariff_by_industry.png       — Tariff exposure by NAICS-3 industry
  - etr_distribution_pre_post.png — ETR density pre vs post tariffs
  - did_etr_means.png            — DiD 2x2 visualization
  - robustness_forest_plot.png   — Forest plot of all specifications
  - etr_change_by_industry.png   — Industry ETR change vs tariff exposure
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Style
sns.set_theme(style="whitegrid", font_scale=1.1)
COLORS = {"high": "#c0392b", "low": "#2c3e50", "main": "#2c3e50", "accent": "#c0392b"}


# ---------------------------------------------------------------------------
# Load and prepare data
# ---------------------------------------------------------------------------
print("Loading data...")
df = pd.read_csv(PROCESSED_DIR / "merged_panel.csv")
tariff = pd.read_csv(BASE_DIR / "tariff_exposure_naics3.csv")

# Construct variables (same as 04_regression_analysis.py)
df["post2018"] = (df["year"] >= 2019).astype(int)
p01 = df["effective_tax_rate"].quantile(0.01)
p99 = df["effective_tax_rate"].quantile(0.99)
df["etr_winsorized"] = df["effective_tax_rate"].clip(lower=p01, upper=p99)

# Tariff exposure groups (above/below median among firms with tariff data)
tariff_firms = df[df["mean_tariff_increase"].notna()].copy()
median_tariff = tariff_firms["mean_tariff_increase"].median()
tariff_firms["tariff_group"] = np.where(
    tariff_firms["mean_tariff_increase"] > median_tariff, "High tariff", "Low tariff"
)

print(f"Tariff firms: {tariff_firms['cik'].nunique()}, median tariff: {median_tariff:.3f}")
print(f"High tariff: {(tariff_firms['tariff_group'] == 'High tariff').sum()} obs")
print(f"Low tariff: {(tariff_firms['tariff_group'] == 'Low tariff').sum()} obs")


# ---------------------------------------------------------------------------
# Figure 1: ETR Trends by Tariff Exposure Group
# ---------------------------------------------------------------------------
print("\nFigure 1: ETR trends by exposure group...")

trends = (
    tariff_firms.dropna(subset=["etr_winsorized"])
    .groupby(["year", "tariff_group"])["etr_winsorized"]
    .agg(["mean", "sem", "count"])
    .reset_index()
)
trends["ci"] = 1.96 * trends["sem"]

fig, ax = plt.subplots(figsize=(10, 6))
for group, color in [("High tariff", COLORS["high"]), ("Low tariff", COLORS["low"])]:
    g = trends[trends["tariff_group"] == group]
    ax.plot(g["year"], g["mean"], "o-", color=color, label=group, linewidth=2, markersize=5)
    ax.fill_between(g["year"], g["mean"] - g["ci"], g["mean"] + g["ci"], alpha=0.12, color=color)

ax.axvline(x=2018, color="gray", linestyle="--", linewidth=1, alpha=0.7)
ax.annotate("Tariffs imposed", xy=(2018, ax.get_ylim()[1] * 0.95),
            fontsize=9, color="gray", ha="center")
ax.set_xlabel("Year")
ax.set_ylabel("Mean Effective Tax Rate (%)")
ax.set_title("Effective Tax Rate by Tariff Exposure Group")
ax.legend(frameon=True, loc="upper right")
ax.set_xticks(range(2015, 2025))
ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.0f%%"))
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "etr_trends_by_exposure.png", dpi=150)
plt.close()
print("  Saved: etr_trends_by_exposure.png")


# ---------------------------------------------------------------------------
# Figure 2: Tariff Exposure by Industry
# ---------------------------------------------------------------------------
print("\nFigure 2: Tariff exposure by industry...")

tariff_sorted = tariff.sort_values("mean_tariff_increase", ascending=True)

fig, ax = plt.subplots(figsize=(10, 8))
bars = ax.barh(
    tariff_sorted["sector_name"],
    tariff_sorted["mean_tariff_increase"] * 100,
    color=plt.cm.Reds(tariff_sorted["mean_tariff_increase"] / tariff_sorted["mean_tariff_increase"].max()),
    edgecolor="white",
    linewidth=0.5,
)
ax.set_xlabel("Mean Tariff Increase (%)")
ax.set_title("Section 301 Tariff Exposure by Industry (NAICS-3)")
ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.0f%%"))

# Annotate values
for bar, val in zip(bars, tariff_sorted["mean_tariff_increase"]):
    ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
            f"{val * 100:.0f}%", va="center", fontsize=8, color="#333")

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "tariff_by_industry.png", dpi=150)
plt.close()
print("  Saved: tariff_by_industry.png")


# ---------------------------------------------------------------------------
# Figure 3: ETR Distribution Pre vs Post
# ---------------------------------------------------------------------------
print("\nFigure 3: ETR distribution pre vs post...")

etr_data = tariff_firms.dropna(subset=["etr_winsorized"]).copy()
etr_data["period"] = np.where(etr_data["year"] < 2019, "Pre-tariff (2015-2018)", "Post-tariff (2019-2024)")

fig, ax = plt.subplots(figsize=(10, 6))
for period, color, ls in [
    ("Pre-tariff (2015-2018)", COLORS["low"], "-"),
    ("Post-tariff (2019-2024)", COLORS["high"], "--"),
]:
    subset = etr_data[etr_data["period"] == period]["etr_winsorized"]
    subset = subset[(subset >= -10) & (subset <= 80)]  # zoom in for readability
    sns.kdeplot(subset, ax=ax, color=color, linestyle=ls, linewidth=2, label=period)

ax.set_xlabel("Effective Tax Rate (%)")
ax.set_ylabel("Density")
ax.set_title("ETR Distribution: Pre vs Post Tariffs (Tariff-Exposed Firms)")
ax.legend(frameon=True)
ax.set_xlim(-10, 80)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "etr_distribution_pre_post.png", dpi=150)
plt.close()
print("  Saved: etr_distribution_pre_post.png")


# ---------------------------------------------------------------------------
# Figure 4: DiD 2x2 Visualization
# ---------------------------------------------------------------------------
print("\nFigure 4: DiD visualization...")

did_data = tariff_firms.dropna(subset=["etr_winsorized"]).copy()
did_data["period"] = np.where(did_data["year"] < 2019, "Pre (2015-2018)", "Post (2019-2024)")

did_means = (
    did_data.groupby(["period", "tariff_group"])["etr_winsorized"]
    .agg(["mean", "sem"])
    .reset_index()
)
did_means["ci"] = 1.96 * did_means["sem"]

fig, ax = plt.subplots(figsize=(8, 6))
x_pos = {"Pre (2015-2018)": 0, "Post (2019-2024)": 1}

for group, color, marker in [("High tariff", COLORS["high"], "s"), ("Low tariff", COLORS["low"], "o")]:
    g = did_means[did_means["tariff_group"] == group].sort_values("period")
    xs = [x_pos[p] for p in g["period"]]
    ax.errorbar(xs, g["mean"], yerr=g["ci"], fmt=f"{marker}-", color=color,
                label=group, linewidth=2.5, markersize=10, capsize=5, capthick=2)

# Annotate the DiD
high_pre = did_means[(did_means["tariff_group"] == "High tariff") & (did_means["period"] == "Pre (2015-2018)")]["mean"].values[0]
high_post = did_means[(did_means["tariff_group"] == "High tariff") & (did_means["period"] == "Post (2019-2024)")]["mean"].values[0]
low_pre = did_means[(did_means["tariff_group"] == "Low tariff") & (did_means["period"] == "Pre (2015-2018)")]["mean"].values[0]
low_post = did_means[(did_means["tariff_group"] == "Low tariff") & (did_means["period"] == "Post (2019-2024)")]["mean"].values[0]
did_estimate = (high_post - high_pre) - (low_post - low_pre)

ax.annotate(
    f"DiD = {did_estimate:+.1f} pp",
    xy=(0.5, (high_post + low_post) / 2),
    fontsize=13, fontweight="bold", color="#333", ha="center",
    bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", edgecolor="gray"),
)

ax.set_xticks([0, 1])
ax.set_xticklabels(["Pre-tariff\n(2015-2018)", "Post-tariff\n(2019-2024)"], fontsize=11)
ax.set_ylabel("Mean Effective Tax Rate (%)")
ax.set_title("Difference-in-Differences: ETR by Tariff Exposure")
ax.legend(frameon=True, fontsize=11)
ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.0f%%"))
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "did_etr_means.png", dpi=150)
plt.close()
print(f"  DiD estimate (raw means): {did_estimate:+.1f} pp")
print("  Saved: did_etr_means.png")


# ---------------------------------------------------------------------------
# Figure 5: Robustness Forest Plot
# ---------------------------------------------------------------------------
print("\nFigure 5: Robustness forest plot...")

# Results from the regression output (04_regression_analysis.py)
specs = [
    ("Main (ETR + TCJA ctrl)", -68.2, 15.0),
    ("R1: No controls", -66.4, 11.8),
    ("R1b: No TCJA control", -68.1, 15.0),
    ("R2: SIC1 x year FE", -61.5, 17.0),
    ("R3: NAICS2 x year FE", -39.8, 13.9),
    ("R4: NAICS2 linear trends", -51.8, 32.2),
    ("R5: Placebo (2017)", 85.2, 50.7),
    ("R6: Balanced panel", -66.2, 15.2),
    ("R7: ETR p5/p95", -24.4, 9.7),
    ("R8: ETR [0,100]", -19.4, 12.0),
    ("R9: ETR [0,60]", -8.4, 8.9),
    ("R10: FPS outcome", -0.2, 0.8),
]

labels = [s[0] for s in specs]
coefs = [s[1] for s in specs]
ses = [s[2] for s in specs]
ci_low = [c - 1.96 * s for c, s in zip(coefs, ses)]
ci_high = [c + 1.96 * s for c, s in zip(coefs, ses)]

fig, ax = plt.subplots(figsize=(10, 7))
y_pos = list(range(len(specs)))[::-1]

for i, (label, coef, se) in enumerate(specs):
    y = y_pos[i]
    color = COLORS["accent"] if label.startswith("Main") else COLORS["main"]
    weight = "bold" if label.startswith("Main") else "normal"
    size = 8 if label.startswith("Main") else 5

    ax.plot(coef, y, "o", color=color, markersize=size, zorder=3)
    ax.hlines(y, coef - 1.96 * se, coef + 1.96 * se, color=color, linewidth=2 if label.startswith("Main") else 1.2)
    ax.text(-210, y, label, va="center", ha="left", fontsize=9, fontweight=weight)

ax.axvline(x=0, color="gray", linestyle="--", linewidth=0.8)
ax.set_yticks([])
ax.set_xlabel("Coefficient on tariff_x_post")
ax.set_title("Robustness: Coefficient Estimates Across Specifications")
ax.set_xlim(-220, 200)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "robustness_forest_plot.png", dpi=150)
plt.close()
print("  Saved: robustness_forest_plot.png")


# ---------------------------------------------------------------------------
# Figure 6: ETR Change by Industry vs Tariff Exposure
# ---------------------------------------------------------------------------
print("\nFigure 6: Industry ETR change vs tariff exposure...")

industry_data = tariff_firms.dropna(subset=["etr_winsorized"]).copy()
industry_data["period"] = np.where(industry_data["year"] < 2019, "pre", "post")

# Mean ETR per industry-period
ind_means = (
    industry_data.groupby(["naics3", "sector_name", "mean_tariff_increase", "period"])["etr_winsorized"]
    .mean()
    .reset_index()
)
ind_wide = ind_means.pivot_table(
    index=["naics3", "sector_name", "mean_tariff_increase"],
    columns="period", values="etr_winsorized"
).reset_index()
ind_wide.columns.name = None
ind_wide["etr_change"] = ind_wide["post"] - ind_wide["pre"]

# Firm counts per industry for sizing
firm_counts = industry_data.groupby("naics3")["cik"].nunique().reset_index()
firm_counts.columns = ["naics3", "n_firms"]
ind_wide = ind_wide.merge(firm_counts, on="naics3")

fig, ax = plt.subplots(figsize=(10, 7))
scatter = ax.scatter(
    ind_wide["mean_tariff_increase"] * 100,
    ind_wide["etr_change"],
    s=ind_wide["n_firms"] * 3,
    c=ind_wide["mean_tariff_increase"],
    cmap="Reds",
    edgecolors=COLORS["main"],
    linewidth=0.8,
    alpha=0.8,
    zorder=3,
)

# Fit line
slope, intercept, r_value, p_value, std_err = stats.linregress(
    ind_wide["mean_tariff_increase"] * 100, ind_wide["etr_change"]
)
x_fit = np.linspace(9, 22, 100)
ax.plot(x_fit, intercept + slope * x_fit, "--", color=COLORS["accent"], linewidth=1.5,
        label=f"OLS fit (slope={slope:.2f}, r={r_value:.2f})")

# Label industries
for _, row in ind_wide.iterrows():
    if row["mean_tariff_increase"] >= 0.18 or abs(row["etr_change"]) > 5:
        ax.annotate(
            row["sector_name"].replace(" Manufacturing", "").replace(" Products", ""),
            xy=(row["mean_tariff_increase"] * 100, row["etr_change"]),
            fontsize=7, ha="center", va="bottom",
            xytext=(0, 6), textcoords="offset points",
        )

ax.axhline(y=0, color="gray", linestyle="-", linewidth=0.5)
ax.set_xlabel("Mean Tariff Increase (%)")
ax.set_ylabel("Change in Mean ETR (post - pre, pp)")
ax.set_title("Industry-Level ETR Change vs Tariff Exposure")
ax.legend(frameon=True, fontsize=9)

# Size legend
for n, label in [(10, "10 firms"), (50, "50 firms"), (100, "100 firms")]:
    ax.scatter([], [], s=n * 3, c="gray", alpha=0.5, edgecolors=COLORS["main"], label=label)
ax.legend(frameon=True, fontsize=8, loc="lower left")

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "etr_change_by_industry.png", dpi=150)
plt.close()
print("  Saved: etr_change_by_industry.png")


# ---------------------------------------------------------------------------
print(f"\nAll figures saved to {OUTPUT_DIR}/")
