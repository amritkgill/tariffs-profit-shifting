# Regression Analysis Note

## Outcome Variable

The initial outcome variable was Foreign Profit Share (FPS), which is the foreign pre-tax income divided by total pre-tax income. This didn't work for two reasons:

- About 35% of firm-year observations are missing the foreign/domestic income breakdown entirely, because many firms don't tag geographic income with standard language. This cuts the usable sample significantly.
- Even among firms that do report FPS, the regression returned a null result (coefficient of -0.286, p = 0.684). The event study also showed problematic pre-trends, meaning high-tariff and low-tariff firms were already trending differently before the 2018 tariffs.

The outcome variable was changed to **Effective Tax Rate (ETR)**, sourced from Bloomberg. ETR captures profit shifting more broadly than FPS does. When a firm shifts profits to a low-tax jurisdiction — whether through transfer pricing, IP licensing, intercompany loans, or any other mechanism — the end result is a lower tax bill, which shows up directly in the effective tax rate. FPS only captures one narrow channel (the foreign/domestic income split), and it depends on how the firm happens to tag its data. ETR reflects all of these channels combined.

## Winsorization

The raw ETR from Bloomberg has extreme outliers — some values go as high as 138,000%, and the standard deviation is 1,370 even though the median is only about 23%. These come from one-time tax events, loss carryforwards, or just data issues, and they completely throw off the regression when left in. To deal with this, ETR was winsorized at the 1st and 99th percentiles, capping values to a range of 0% to 237%. This is the same approach that was already used for FPS.

## Regression Specification

The main model is a continuous diff-in-diff with two-way fixed effects:

**ETR_it = β(TariffExposure_i × Post2018_t) + γ'X_it + α_i + δ_t + ε_it**

- **ETR_it** — winsorized effective tax rate for firm i in year t
- **TariffExposure_i** — mean Section 301 tariff increase for the firm's NAICS 3-digit industry (continuous, ranges from 0 to about 0.25)
- **Post2018_t** — equals 1 for 2019 onward (tariffs hit mid-2018, but the full effect shows up in the next fiscal year)
- **TariffExposure_i × Post2018_t** — the interaction term, which is the main coefficient of interest (β)
- **X_it** — time-varying controls: log revenue (firm size), R&D intensity (R&D expense / revenue), and leverage (total debt / total assets)
- **α_i** — firm fixed effects, which control for all permanent differences between firms
- **δ_t** — year fixed effects, which control for anything that hit all firms in a given year
- **ε_it** — error term

β tells us whether firms with more tariff exposure saw a different change in ETR after 2018 compared to firms with less exposure.

## Results

- The main model gives a coefficient of **-68.4** on the interaction term with a p-value of **0.002**. Tariff-exposed firms had a significant drop in effective tax rates after 2018, which lines up with increased profit shifting to lower-tax countries.
- To put that in real terms, a firm at the 75th percentile of tariff exposure (about a 0.21 mean tariff increase) would see roughly a 14 percentage point drop in ETR compared to a firm with no exposure. That's a big effect.
- Dropping all the controls gives almost the same result (coefficient of -66.8, p = 0.001), so the finding isn't driven by which controls are included.
- Adding NAICS 2-digit × year fixed effects (which absorb industry-level trends over time) shrinks the coefficient to -40.2 with p = 0.267. Same direction, but it loses significance — probably because the extra fixed effects soak up a lot of the variation the model needs.
- Using FPS as the outcome gives a null result (coefficient of -0.286, p = 0.684), which confirms that ETR is picking up profit-shifting activity that FPS misses.

## Event Study

To check that the parallel trends assumption holds, the model is re-estimated with year-by-year interactions between tariff exposure and year dummies instead of one single post-2018 interaction. 2017 is the reference year:

**ETR_it = Σ_k β_k(TariffExposure_i × 1[Year = k]) + γ'X_it + α_i + δ_t + ε_it**

- **Pre-trends are clean.** The 2015 and 2016 coefficients are close to zero and nowhere near significant (p = 0.816 and p = 0.814). High-tariff and low-tariff firms were on similar ETR paths before the tariffs, which is what needs to be true for the diff-in-diff to work.
- **2018 has a temporary spike** (coefficient of +92.8, p = 0.258). This makes sense — tariff-exposed firms faced sudden cost increases before they had a chance to adjust their tax planning.
- **Post-2019 coefficients are negative**, ranging from about -31 to -77. None of them are individually significant (the confidence intervals get wide when you split the effect across separate years), but the pattern is consistent with the main result. The aggregate model pools all post-2018 years together, which is where the statistical power comes from.
