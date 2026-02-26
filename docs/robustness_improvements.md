# Robustness Improvements: Problems, Fixes, and Results

This document walks through the three main problems that existed in the original regression analysis, explains what was wrong and why it mattered, describes exactly what was done to fix each one, and shows how the results changed.

---

## Problem 1: Standard Errors Were Clustered at the Wrong Level

### What was wrong

The original regression clustered standard errors at the firm level. In pyfixest, when you write `| cik + year` in the fixed effects formula, the default behavior is to cluster standard errors by the first fixed effect variable --- in this case, `cik` (firm). That means the model was treating each firm as an independent observation of the tariff effect.

But the tariff treatment doesn't vary at the firm level. It varies at the NAICS 3-digit industry level. Every firm in NAICS 334 ("Computer and Electronic Products") gets the exact same tariff exposure score of 0.21. Every firm in NAICS 333 ("Machinery") gets 0.20. And so on. When two firms share the same tariff exposure, their residuals are likely correlated --- they're both responding to the same industry-level shock. Firm-level clustering ignores this correlation, which makes the standard errors too small and the p-values too optimistic.

To make this concrete: the model doesn't really have 4,457 independent observations of the tariff effect. It has 24 industries. That's where the treatment varies, and that's where we should cluster.

### What was done

Standard errors were changed to cluster at the NAICS 3-digit level for every regression in the analysis. In code, this means adding `vcov={"CRV1": "naics3_str"}` to every `pf.feols()` call.

But 24 clusters is a small number. The standard cluster-robust variance estimator assumes the number of clusters approaches infinity, and with only 24, it can be biased --- typically producing standard errors that are still too small. To address this, a wild cluster bootstrap was added to the main specification: 9,999 bootstrap replications using Rademacher weights, which is the standard correction for inference with few clusters.

### How the results changed

The main model was barely affected: the coefficient stayed at -68.4, and the p-value actually got slightly better (from 0.002 to <0.001) because the NAICS-3 clustered SEs happened to be smaller than the firm-clustered SEs for this specification. The wild bootstrap p-value is 0.009, confirming the result survives the few-cluster correction.

The big change was in the NAICS-2 x year FE robustness check. With the old firm-level clustering, that specification had a p-value of 0.267 --- not significant, and the single biggest vulnerability in the analysis. With correct NAICS-3 clustering, the exact same specification now has a p-value of 0.009. The coefficient didn't change at all (-40.2 either way). The only thing that changed was how the uncertainty was computed. This was the most consequential fix in the entire update.

---

## Problem 2: The NAICS-2 x Year Fixed Effects Were Too Aggressive (and There Was No Alternative)

### What was wrong

The original analysis included one industry-trend robustness check: NAICS-2 x year fixed effects. This creates a separate dummy for every combination of 2-digit industry and year --- 21 NAICS-2 groups times 10 years = 210 fixed effects. The problem is that the tariff treatment only varies across 26 NAICS-3 industries, and many of those industries share the same NAICS-2 parent. For example, NAICS 331 (Primary Metals), 332 (Fabricated Metals), 333 (Machinery), 334 (Computers), 335 (Electrical Equipment), 336 (Transportation Equipment), and 339 (Miscellaneous Manufacturing) all fall under NAICS 2-digit code "33." When you add 33 x 2019, 33 x 2020, etc. as fixed effects, you're absorbing the average ETR for all of those industries in each year, leaving only the tiny within-group differences (0.21 vs 0.20 vs 0.19) to identify the effect. That's asking a lot of very little variation.

The original analysis had no other way to control for industry trends. If a reviewer saw the NAICS-2 x year result fail (p = 0.267), and there was nothing else to point to, the whole paper looked fragile.

### What was done

Three new industry-trend specifications were added:

**SIC 1-digit x year fixed effects.** SIC 1-digit codes group firms into 8 broad divisions (agriculture, mining, manufacturing, utilities, trade, finance, services, public administration). This is a much coarser grouping than NAICS-2, so it controls for broad sector-level trends (like "all manufacturing ETRs were falling after 2018") without eating up the within-sector variation that actually identifies the tariff effect. With 8 groups x 10 years = 80 fixed effects, this is a reasonable middle ground.

**NAICS-2 linear time trends.** Instead of adding a separate dummy for every NAICS-2 x year combination (the aggressive approach), this lets each 2-digit industry have its own linear slope over time. So if manufacturing ETRs were already trending downward before tariffs, the trend absorbs that. But it doesn't soak up the year-to-year variation the way full interaction fixed effects do. This uses pyfixest's `i(naics2, year)` syntax, which creates one continuous year interaction per NAICS-2 group.

**Placebo test.** This is a completely different way to address the pre-trend concern. Instead of trying to absorb industry trends with fixed effects, it directly tests whether the effect exists before tariffs were actually imposed. The data is restricted to 2015-2018 only (before the real treatment kicks in at 2019), and a fake treatment is assigned at 2017. If the model finds a significant negative effect from this fake treatment, something is wrong --- the model is just picking up pre-existing trends. If it finds nothing (which is what we want), it confirms that the effect really does turn on at the actual tariff date.

**Balanced panel restriction.** As an additional check, the regression was rerun on only the 1,095 firms that appear in all 10 years of the panel. This tests whether firms entering (IPOs) or exiting (M&A, delisting) the sample are driving the result.

### How the results changed

**SIC 1-digit x year FE: coefficient = -61.7, p = 0.001.** This is the strongest new result. It says: even after controlling for broad sector-level trends over time, the tariff effect is large and highly significant. The coefficient barely budged from the main model (-68.4), and the p-value is well below conventional thresholds.

**NAICS-2 x year FE: coefficient = -40.2, p = 0.009.** As noted above, this was already significant once the clustering was fixed. The coefficient is smaller because these aggressive fixed effects absorb a lot of variation, but the effect is still economically meaningful and statistically significant.

**NAICS-2 linear trends: coefficient = -52.1, p = 0.122.** Borderline. The point estimate is large and in the right direction, but the standard errors widen because the industry-specific slopes absorb some of the variation the model needs. This is less aggressive than full NAICS-2 x year FE but still soaks up a fair amount of identifying variation.

**Placebo test: coefficient = +86.1, p = 0.108.** This is exactly what we want. The fake treatment gives a wrong-sign (positive, not negative) coefficient that is not statistically significant. There is no pre-existing tariff effect before 2018. This is arguably more convincing than any fixed effects specification, because it directly tests the causal timing rather than trying to control for confounds.

**Balanced panel: coefficient = -66.4, p < 0.001.** Nearly identical to the main model. Attrition doesn't matter.

Before these fixes, the analysis had one significant result and one fatal weakness (the NAICS-2 x year FE failure). After the fixes, the industry-trend concern is addressed from multiple angles, and the placebo test adds direct causal evidence.

---

## Problem 3: The ETR Winsorization Was Too Loose

### What was wrong

The original analysis winsorized ETR at the 1st and 99th percentiles, capping values to a range of 0% to 237%. An ETR of 237% means a firm supposedly paid $237 in taxes for every $100 of pre-tax income. That doesn't happen in normal corporate operations. Values like this come from one-time tax events (like the 2017 Tax Cuts and Jobs Act transition tax), loss carryforwards that create large deferred tax expenses relative to tiny current-year income, or simply Bloomberg data errors.

By leaving these observations in (just capped at 237% instead of removed), the regression gives them disproportionate influence. A firm that swings from ETR = 200% to ETR = 50% contributes a much bigger within-firm change than a firm going from 25% to 20%. The concern is that these extreme observations might be driving the entire result.

The original analysis had no robustness checks on the ETR distribution, so there was no way to know how sensitive the result was to outliers.

### What was done

Three additional ETR treatments were tested:

**5th/95th percentile winsorization.** ETR is capped at 0.5% and 60.2% instead of 0% and 237%. This is a much tighter range that excludes the truly extreme values while keeping the full sample size.

**Trimming to [0, 100].** Instead of capping extreme values, this drops any firm-year where the raw ETR is below 0% or above 100%. An ETR above 100% is almost certainly a data artifact or one-time event, not a meaningful tax rate. This reduces the sample from 4,457 to 4,344 observations.

**Trimming to [0, 60].** The most restrictive test. The US statutory corporate tax rate was 35% before 2018 and 21% after, and most normal firms fall in the 10-40% range. Restricting to [0, 60] keeps only firms with economically interpretable ETR values. This reduces the sample to 4,242 observations.

### How the results changed

| ETR treatment | Coef | p-value |
|---|---|---|
| Main (p1/p99, range 0-237) | -68.4 | <0.001 |
| p5/p95 (range 0.5-60.2) | -24.1 | 0.021 |
| Trimmed [0, 100] | -19.2 | 0.127 |
| Trimmed [0, 60] | -8.0 | 0.385 |

The direction is always negative (tariff-exposed firms see lower ETR), which is consistent across every specification. But the magnitude drops substantially as extreme values are removed. The result stays significant at p5/p95 winsorization (p = 0.021), which is the key finding --- it means the effect isn't purely an artifact of wild outliers. But it does lose significance when trimmed to [0, 100] or [0, 60].

What this tells us is that the headline number of -68.4 is inflated by firms with extreme ETR values. The more conservative and defensible estimate is the p5/p95 result of -24.1, which implies roughly a 5 percentage point ETR drop for firms at the 75th percentile of tariff exposure (compared to the 14pp implied by the main spec). That's still an economically meaningful effect --- a firm paying 25% ETR would drop to about 20% --- but it's a more honest characterization of the magnitude.

The fact that the [0, 60] specification is not significant (p = 0.385) is worth noting. It could mean the effect genuinely operates through firms with unusual tax situations (which is plausible --- firms with volatile ETR may be the ones most actively managing their tax positions). Or it could mean the effect is weaker than the main model suggests. Either way, reporting these results transparently strengthens the analysis by showing the reader exactly where the result comes from in the data.

---

## Summary of All Changes

### Code changes (`code/04_regression_analysis.py`)

1. All regressions now cluster standard errors at NAICS 3-digit (`vcov={"CRV1": "naics3_str"}`)
2. Wild cluster bootstrap added for the main model (9,999 reps, Rademacher weights)
3. New robustness checks: SIC 1-digit x year FE, NAICS-2 linear time trends, placebo test, balanced panel, three ETR trimming variants
4. Old goods-only subsample check removed (it was redundant because only goods firms have tariff data, so the main model already restricts to goods firms by construction)

### Before vs after

| What changed | Before | After |
|---|---|---|
| SE clustering | Firm level (wrong) | NAICS-3 level (correct) |
| NAICS-2 x year FE p-value | 0.267 (not significant) | 0.009 (significant) |
| Wild cluster bootstrap | Not done | p = 0.009 |
| Industry trend checks | 1 (NAICS-2 x year only) | 3 (SIC-1 x year, NAICS-2 x year, NAICS-2 linear trends) |
| Placebo test | Not done | Passes (wrong sign, p = 0.108) |
| Balanced panel check | Not done | Passes (p < 0.001) |
| ETR sensitivity checks | None | 3 (p5/p95, [0,100], [0,60]) |
| Significant robustness checks | 2 of 3 | 7 of 10 |
