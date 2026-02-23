# Tariffs, Tax Incentives, and Profit Shifting

Examining whether the 2018 Section 301 tariffs on Chinese imports caused U.S. multinational firms to shift a greater share of profits to foreign jurisdictions. Uses a continuous difference-in-differences design with two-way fixed effects, exploiting cross-industry variation in tariff exposure.

## Data

- Bloomberg Terminal — firm-level annual financials (2015-2024)
- SEC EDGAR XBRL — foreign and domestic pre-tax income
- USITC / Section 301 tariff lists — industry-level tariff exposure by NAICS-3

## Completed

- Acquired foreign, domestic, and total pre-tax income from SEC EDGAR for 1,675 firms (2015-2024)
- Merged SEC income data with Bloomberg firm characteristics and tariff exposure
- Constructed Foreign Profit Share (Foreign Pre-Tax Income / Total Pre-Tax Income)
- Built final panel dataset (14,400 firm-year observations, 30 variables)
