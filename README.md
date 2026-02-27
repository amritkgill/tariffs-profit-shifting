# Tariffs, Tax Incentives, and Profit Shifting

Examining whether the 2018 Section 301 tariffs on Chinese imports caused U.S. multinational firms to shift a greater share of profits to foreign jurisdictions. Uses a continuous difference-in-differences design with two-way fixed effects, exploiting cross-industry variation in tariff exposure.

## Data

- Bloomberg Terminal — firm-level annual financials (2015-2024)
- SEC EDGAR XBRL — foreign and domestic pre-tax income
- USITC / Section 301 tariff lists — industry-level tariff exposure by NAICS-3

## Methodology

- Continuous diff-in-diff with firm and year fixed effects
- Outcome variable: Effective Tax Rate (winsorized p1/p99)
- Treatment: Mean tariff increase by NAICS-3 industry × post-2018 indicator
- Controls: log revenue, R&D intensity, leverage
- SEs clustered at NAICS-3 level (24 industries), wild cluster bootstrap for inference

## Pipeline

1. `code/01_acquire_sec_data.py` — Pull income data from SEC EDGAR XBRL API
2. `code/02_clean_and_merge.py` — Merge SEC + Bloomberg + tariff data
3. `code/03_data_dictionary_and_stats.py` — Data dictionary and quality checks
4. `code/04_regression_analysis.py` — Diff-in-diff, event study, robustness checks

## Dataset

- 1,675 firms, 2015-2024 (14,400 firm-year observations, 30 variables)
- SEC EDGAR: foreign, domestic, and total pre-tax income (used for Foreign Profit Share robustness check)
- Bloomberg: effective tax rate, revenue, R&D, assets, debt, capex
- Tariff exposure: NAICS-3 level mean tariff increase from Section 301 lists
