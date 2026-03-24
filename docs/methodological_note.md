# Methodological Note: Tariffs and Profit Shifting Dataset

## Overview

This dataset examines the relationship between Section 301 tariff exposure and foreign profit shifting among US publicly traded firms from 2015 to 2024. The main outcome variable is Effective Tax Rate (ETR), sourced from Bloomberg, which captures profit shifting broadly --- when a firm shifts profits to a low-tax jurisdiction through any mechanism, the result is a lower effective tax rate. Foreign Profit Share (FPS), defined as Foreign Pre-Tax Income divided by Total Pre-Tax Income, is used as a robustness check but proved too narrow and noisy to detect an effect (see `docs/regression_note.md`).

The final panel contains 14,397 firm-year observations across 1,674 firms and draws on three primary sources: SEC EDGAR XBRL filings for geographic income data, Bloomberg Terminal for firm characteristics and annual financial variables, and a Section 301 tariff exposure dataset measured at the NAICS 3-digit industry level.

## Data Construction

The starting dataset consists of 3,000 US-listed firms from Bloomberg. Of these, 1,108 are ETFs, mutual funds, or other non-operating entities that do not file 10-K reports and are excluded. I matched the remaining 1,892 firms to their SEC filings using a ticker-to-CIK lookup from the SEC's public index. After matching, 1,674 firms had at least one year of usable pre-tax income data.

Foreign and domestic pre-tax income are pulled from the SEC's CompanyFacts API, which provides structured data from each firm's 10-K filing. My script looks for four specific data tags: foreign pre-tax income, domestic pre-tax income, and two versions of total pre-tax income (there are two because the SEC changed its labeling system over time). I assign each observation to a fiscal year based on when the reporting period actually ended, not when the filing was submitted. This avoids mismatches for companies whose fiscal year doesn't end in December. I also filter out anything that isn't a full-year figure.

Many firms don't report foreign income directly, but they do report total and domestic income. In those cases, foreign income is calculated as the difference (total minus domestic). This substantially increases coverage, since the domestic tag is more widely reported than the foreign tag. Foreign Profit Share is then calculated as foreign income divided by total income. Because FPS can get extreme when total income is close to zero, I cap it at the 1st and 99th percentiles to keep outliers from driving my results. I flag the extreme observations separately so I can test whether they matter.

Eight time-varying financial control variables are merged from Bloomberg: total revenue, pre-tax income, R&D expense, total assets, total debt, capital expenditure, effective tax rate, and operating expenses. These are available annually for 2015-2024 with high coverage (94-99% for most variables, 73% for effective tax rate). Static firm characteristics (SIC code, NAICS code, ICB subsector, market cap, and stock price) are also included from Bloomberg, though market cap and price reflect the most recent available date rather than year-specific values.

Tariff exposure is merged at the NAICS 3-digit level. The tariff dataset covers 26 goods-producing industries (NAICS 111-339). Service-sector firms do not match and have missing tariff values by design, since Section 301 tariffs apply only to imported goods.

## Panel Structure

The panel is unbalanced --- not every firm appears in every year. If they all did, there would be 16,740 rows. I'm missing about 14% of those firm-years. Most of the gaps are because companies went public after 2015 (via IPOs or SPACs), so they just weren't around in the earlier years. A smaller portion is companies that disappeared before 2024 because they got acquired, went bankrupt, or got delisted. A few gaps come from quirks in how companies formatted their filings from year to year. About 65% of the firms have the full 10 years of data.

Because the missingness is driven primarily by when firms began trading --- rather than by anything related to profit shifting or tariff exposure --- it's unlikely to bias my estimates. Firm fixed effects handle the unbalanced structure by absorbing time-invariant firm characteristics regardless of how many years each firm is observed. If the companies that dropped out early happened to be doing unusually more or less profit shifting, my results could slightly overrepresent the companies that survived the full period. I keep this in mind when interpreting results.

## Limitations and Remaining Gaps

About 35% of my data points don't have the foreign vs. domestic income breakdown. That's because many companies mention it in their filings but don't format it in the structured way my code can automatically pull. This is one reason FPS was replaced as the main outcome variable by ETR, which has broader coverage (73% non-missing vs 65% for FPS). The foreign/domestic breakdown is still used to construct the TCJA exposure control (pre-treatment average FPS) and as a robustness check outcome.

Tariff exposure is assigned by broad industry group, but companies within the same industry can make very different products. A company in "Computer and Electronic Products" might make some products that got tariffed and some that didn't — but in my data, they all get the same tariff score. Constructing firm-specific tariff measures would require product-level import data from sources like the US Census or UN Comtrade.

About a third of my observations have a Foreign Profit Share below 0 or above 1. That's not an error. It happens when a company is losing money domestically but making money abroad (pushes FPS above 1), or losing money overall (pushes FPS below 0). These are real situations, but they make the variable harder to interpret cleanly, which is why I cap the extremes.

Finally, my sample is limited to US-listed firms, and extending the panel back before 2015 would provide more pre-tariff baseline years but the structured filing data gets spotty before 2015.

## Reproducibility

All code is in the `code/` directory:

1. `01_acquire_sec_data.py` --- Downloads pre-tax income data from the SEC EDGAR CompanyFacts API
2. `02_clean_and_merge.py` --- Cleans firm characteristics, reshapes Bloomberg financials, and merges all sources
3. `03_data_dictionary_and_stats.py` --- Generates the data dictionary, summary statistics, and data quality checks
4. `04_regression_analysis.py` --- Diff-in-diff regressions, event study, robustness checks, and alternative tariff measures
