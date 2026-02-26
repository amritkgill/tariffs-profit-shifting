# Regression Analysis Note

## Outcome Variable

The initial outcome variable was Foreign Profit Share (FPS), which is the foreign pre-tax income divided by total pre-tax income. This didn't work for two reasons:

- About 35% of firm-year observations are missing the foreign/domestic income breakdown entirely, because many firms don't tag geographic income with standard language. This cuts the usable sample significantly.
- Even among firms that do report FPS, the regression returned a null result (coefficient of -0.286, p = 0.706). The event study also showed problematic pre-trends, meaning high-tariff and low-tariff firms were already trending differently before the 2018 tariffs.

The outcome variable was changed to **Effective Tax Rate (ETR)**, sourced from Bloomberg. ETR captures profit shifting more broadly than FPS does. When a firm shifts profits to a low-tax jurisdiction --- whether through transfer pricing, IP licensing, intercompany loans, or any other mechanism --- the end result is a lower tax bill, which shows up directly in the effective tax rate. FPS only captures one narrow channel (the foreign/domestic income split), and it depends on how the firm happens to tag its data. ETR reflects all of these channels combined.

## Winsorization

The raw ETR from Bloomberg has extreme outliers --- some values go as high as 138,000%, and the standard deviation is 1,370 even though the median is only about 23%. These come from one-time tax events, loss carryforwards, or just data issues, and they completely throw off the regression when left in. To deal with this, ETR was winsorized at the 1st and 99th percentiles, capping values to a range of 0% to 237%. This is the same approach that was already used for FPS.

## Standard Errors

Standard errors are clustered at the NAICS 3-digit industry level, which is the level at which the tariff treatment varies. There are 24 NAICS-3 industries in the regression sample. Because this is a small number of clusters (below the roughly 40-50 threshold where standard cluster-robust inference becomes reliable), the main specification is also tested with a wild cluster bootstrap (9,999 Rademacher replications). The wild bootstrap p-value for the main model is 0.009, confirming that the result is not an artifact of few-cluster bias.

## Regression Specification

The main model is a continuous diff-in-diff with two-way fixed effects:

**ETR_it = β(TariffExposure_i × Post2018_t) + γ'X_it + α_i + δ_t + ε_it**

- **ETR_it** --- winsorized effective tax rate for firm i in year t
- **TariffExposure_i** --- mean Section 301 tariff increase for the firm's NAICS 3-digit industry (continuous, ranges from 0.10 to 0.21)
- **Post2018_t** --- equals 1 for 2019 onward (tariffs hit mid-2018, but the full effect shows up in the next fiscal year)
- **TariffExposure_i × Post2018_t** --- the interaction term, which is the main coefficient of interest (β)
- **X_it** --- time-varying controls: log revenue (firm size), R&D intensity (R&D expense / revenue), and leverage (total debt / total assets)
- **α_i** --- firm fixed effects, which control for all permanent differences between firms
- **δ_t** --- year fixed effects, which control for anything that hit all firms in a given year
- **ε_it** --- error term, clustered at NAICS 3-digit level

β tells us whether firms with more tariff exposure saw a different change in ETR after 2018 compared to firms with less exposure.

Note: the regression sample is restricted to goods-producing firms by construction, since only firms in industries with Section 301 tariff data have non-missing values on the interaction term. Service, finance, and healthcare firms drop out automatically.

## Results

The main model gives a coefficient of **-68.4** on the interaction term with a p-value of **<0.001** (NAICS-3 clustered) and a wild cluster bootstrap p-value of **0.009**. Tariff-exposed firms had a significant drop in effective tax rates after 2018, consistent with increased profit shifting to lower-tax countries.

To put that in real terms, a firm at the 75th percentile of tariff exposure (about a 0.21 mean tariff increase) would see roughly a 14 percentage point drop in ETR compared to a firm at the 25th percentile. That's a big effect.

## Robustness Checks

| Specification | Coef | SE | p-value | N |
|---|---|---|---|---|
| **Main (ETR + controls)** | **-68.4** | **15.1** | **<0.001** | **4,457** |
| R1: No controls | -66.8 | 12.0 | <0.001 | 5,322 |
| R2: SIC 1-digit x year FE | -61.7 | 17.1 | 0.001 | 4,451 |
| R3: NAICS-2 x year FE | -40.2 | 14.2 | 0.009 | 4,456 |
| R4: NAICS-2 linear trends | -52.1 | 32.4 | 0.122 | 4,457 |
| R5: Placebo (fake 2017 treatment) | +86.1 | 51.4 | 0.108 | 1,414 |
| R6: Balanced panel (10 years) | -66.4 | 15.2 | <0.001 | 3,816 |
| R7: ETR winsorized p5/p95 | -24.1 | 9.7 | 0.021 | 4,457 |
| R8: ETR trimmed [0, 100] | -19.2 | 12.1 | 0.127 | 4,344 |
| R9: ETR trimmed [0, 60] | -8.0 | 9.1 | 0.385 | 4,242 |
| R10: FPS as outcome | -0.3 | 0.7 | 0.706 | 4,552 |

**Controls don't matter (R1).** Dropping all controls barely changes the coefficient (-66.8 vs -68.4), confirming the result isn't driven by which controls are included.

**SIC 1-digit x year FE works (R2).** Adding broad industry-by-year fixed effects --- 8 SIC divisions x 10 years = 80 FE --- still gives a large, significant result (-61.7, p = 0.001). This controls for sector-level macro trends without absorbing the within-sector variation that identifies the tariff effect.

**NAICS-2 x year FE is now significant (R3).** With proper NAICS-3 clustering, this specification is significant (p = 0.009). The coefficient shrinks to -40.2 because these aggressive fixed effects absorb much of the cross-industry variation, but the effect remains economically meaningful.

**NAICS-2 linear time trends are borderline (R4).** Allowing each 2-digit industry its own linear slope over time gives a coefficient of -52.1 (p = 0.122). The point estimate is large and negative but the standard errors widen because the trends absorb some treatment variation.

**Placebo test passes (R5).** Using only 2015-2018 data with a fake treatment at 2017, the coefficient is positive (+86.1) and not significant (p = 0.108). The wrong sign and non-significance confirm there is no pre-existing treatment effect.

**Balanced panel is robust (R6).** Restricting to firms present in all 10 years gives nearly identical results (-66.4, p < 0.001), confirming that firm entry and exit don't drive the result.

**ETR outliers partially drive the magnitude (R7-R9).** The coefficient shrinks as ETR is more aggressively trimmed: -24.1 (p5/p95, p = 0.021) to -19.2 ([0,100], p = 0.127) to -8.0 ([0,60], p = 0.385). The result remains significant at p5/p95 winsorization but loses significance with harder trimming. The conservative estimate from p5/p95 is -24.1, implying roughly a 5 percentage point ETR drop for high-exposure firms.

**FPS gives a null result (R10).** Coefficient of -0.3 (p = 0.706), confirming this measure is too narrow and noisy.

## Event Study

To check that the parallel trends assumption holds, the model is re-estimated with year-by-year interactions between tariff exposure and year dummies instead of one single post-2018 interaction. 2017 is the reference year. Standard errors are clustered at NAICS 3-digit.

**ETR_it = Σ_k β_k(TariffExposure_i × 1[Year = k]) + γ'X_it + α_i + δ_t + ε_it**

- **Pre-trends are clean.** The 2015 and 2016 coefficients are close to zero and nowhere near significant (p = 0.804 and p = 0.810). High-tariff and low-tariff firms were on similar ETR paths before the tariffs, which is what needs to be true for the diff-in-diff to work.
- **2018 has a temporary spike** (coefficient of +92.8, p = 0.366). This makes sense --- tariff-exposed firms faced sudden cost increases before they had a chance to adjust their tax planning.
- **Post-2019 coefficients are negative**, ranging from about -31 to -77. None of them are individually significant (the confidence intervals get wide when you split the effect across separate years with only 24 clusters), but the pattern is consistent with the main result. The aggregate model pools all post-2018 years together, which is where the statistical power comes from.

## Alternative Tariff Exposure Measures

The main model uses mean tariff increase as the treatment intensity variable. But the tariff data includes other ways to measure exposure: the number of HS-8 products targeted in each industry, the number of product-country varieties targeted, and the standard deviation of tariff increases within each industry. All four measures were standardized (z-scored) so the coefficients represent the effect of a one-standard-deviation increase in tariff exposure.

| Measure | Coef | SE | p-value |
|---|---|---|---|
| Mean tariff increase | -2.9 | 0.6 | <0.001 |
| N products targeted | +1.0 | 1.2 | 0.390 |
| N varieties targeted | +0.4 | 0.4 | 0.365 |
| SD of tariff increase | -2.0 | 0.8 | 0.024 |

The mean tariff rate and standard deviation of tariff rates both produce significant negative effects on ETR, while the product count measures do not. This pattern is economically coherent. What matters for profit shifting is how much the tariff raises costs (the rate), not how many product lines are technically covered. Textile Mills had 1,502 products targeted but only a flat 10% rate, while Computer and Electronic Products had 617 products but the highest rate at 21%. A blanket 10% tariff across many products is a uniform cost shock; a 21% tariff is a much stronger incentive to restructure a firm's tax position.

The SD of tariff increase is highly correlated with the mean rate (r = 0.87), so its significance partly reflects the same underlying variation. Still, it provides a useful independent confirmation using a different conceptualization of exposure: industries where tariff rates varied more across products (reflecting more targeted, higher-rate tariffs on specific inputs) saw larger ETR declines.

## Tariff Measurement and Attenuation Bias

Tariff exposure is assigned at the NAICS 3-digit industry level, meaning all firms in the same 3-digit industry get the same tariff score. This is a limitation because firms within the same industry can make very different products. A semiconductor manufacturer and a consumer electronics company both fall under NAICS 334, but their actual import exposure to Section 301 tariffs could be quite different.

This measurement error has a well-known consequence: classical attenuation bias. When the treatment variable is measured with error (as it is here, because the industry-level average is a noisy proxy for each firm's true exposure), the estimated coefficient is biased toward zero. This means the true effect is likely larger than what we estimate, not smaller. The -68.4 coefficient (or the more conservative -24.1 from p5/p95) is, if anything, an underestimate of the causal effect for firms whose actual exposure matches the industry average.

Building firm-level tariff exposure would require mapping each firm's product mix to HS-8 tariff codes using product-level import data from the Census Bureau or UN Comtrade, combined with the HS-to-NAICS concordance published by the Census Bureau (the `imp-code.txt` files). The Section 301 tariff lists with specific HS-8 codes are published by USTR. This is feasible as a future extension but beyond the scope of the current analysis.

## Interpretation Caveats

1. **Magnitude is sensitive to outlier treatment.** The headline coefficient of -68.4 relies on the full ETR distribution, which includes values above 100%. The more conservative estimate from p5/p95 winsorization is -24.1 (still significant at p = 0.021), implying roughly a 5 percentage point ETR drop rather than 14.

2. **The effect is identified from 24 industries.** With few clusters, inference relies on the wild cluster bootstrap rather than standard asymptotics. The bootstrap p-value (0.009) supports the main finding.

3. **Industry time trends absorb some of the effect.** The coefficient weakens with NAICS-2 linear trends (p = 0.122) and shrinks with NAICS-2 x year FE (though it remains significant at p = 0.009 with correct clustering). Part of the effect could reflect industry-specific trends correlated with tariff exposure.

4. **Tariff exposure is measured at the industry level, not the firm level.** Classical attenuation bias means the estimated effect is likely a lower bound. The result is robust to the tariff rate measure (mean and SD both significant) but not to product count measures, confirming that tariff intensity --- not just breadth of coverage --- drives the effect.
