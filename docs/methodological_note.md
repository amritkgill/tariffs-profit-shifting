# Methodological Note: Tariffs and Profit Shifting Dataset

## Overview

This dataset examines the relationship between Section 301 tariff exposure and foreign profit shifting among US publicly traded firms from 2015 to 2024. The key outcome variable is Foreign Profit Share (FPS), defined as Foreign Pre-Tax Income divided by Total Pre-Tax Income, which captures the share of a firm's earnings attributed to foreign operations.

The final panel contains 14,400 firm-year observations across 1,675 firms and draws on three primary sources: SEC EDGAR XBRL filings for geographic income data, Bloomberg Terminal for firm characteristics and annual financial variables, and a Section 301 tariff exposure dataset measured at the NAICS 3-digit industry level.

## Data Construction

The starting universe consists of 3,000 US-listed firms from Bloomberg. Of these, 1,108 are ETFs, mutual funds, or other non-operating entities that do not file 10-K reports and are excluded. The remaining 1,892 firms are matched to SEC EDGAR filings using a ticker-to-CIK mapping from the SEC's public company index. After matching, 1,675 firms have at least one year of pre-tax income data from XBRL-tagged 10-K filings.

Foreign and domestic pre-tax income are pulled from the SEC's CompanyFacts API, which provides structured XBRL data for each firm. The acquisition script queries four XBRL tags: foreign pre-tax income, domestic pre-tax income, and two versions of total pre-tax income (reflecting an SEC taxonomy change over time). Each observation is assigned to a fiscal year using the period end date from the filing rather than the filing year, which avoids misalignment for firms with non-December fiscal year-ends. A duration filter (300-400 days) ensures only full-year income figures are retained.

Where the foreign income tag is missing but both total and domestic income are available, foreign income is computed as the residual (Total minus Domestic). This substantially increases coverage, since the domestic tag is more widely reported than the foreign tag. FPS is then calculated as foreign income divided by total income. The raw FPS variable is winsorized at the 1st and 99th percentiles to limit the influence of extreme values, which arise when firms have near-zero total income in the denominator. Observations with extreme values are flagged for sensitivity analysis.

Eight time-varying financial control variables are merged from Bloomberg: total revenue, pre-tax income, R&D expense, total assets, total debt, capital expenditure, effective tax rate, and operating expenses. These are available annually for 2015-2024 with high coverage (94-99% for most variables, 73% for effective tax rate). Static firm characteristics (SIC code, NAICS code, ICB subsector, market cap, and stock price) are also included from Bloomberg, though market cap and price reflect the most recent available date rather than year-specific values.

Tariff exposure is merged at the NAICS 3-digit level. The tariff dataset covers 26 goods-producing industries (NAICS 111-339). Service-sector firms do not match and have missing tariff values by design, since Section 301 tariffs apply only to imported goods.

## Panel Structure

The panel is unbalanced --- not every firm appears in every year. A balanced panel would have 16,750 rows, so about 14% of firm-years are missing. The majority of this gap comes from firms that entered the sample after 2015 through IPOs or SPAC mergers. Smaller shares come from firms that exited before 2024 (through acquisition, delisting, or bankruptcy) and from occasional gaps where a firm's XBRL tagging changed between filings. About 65% of firms have all 10 years of data.

Because the missingness is driven primarily by when firms began trading --- rather than by anything related to profit shifting or tariff exposure --- it is unlikely to bias estimation. Firm fixed effects handle the unbalanced structure by absorbing time-invariant firm characteristics regardless of how many years each firm is observed. That said, if firms that exit the sample early differ systematically in their profit-shifting behavior, this could introduce mild survivorship bias and should be kept in mind when interpreting results.

## Limitations and Remaining Gaps

The most significant limitation is that only about 65% of firm-year observations have the foreign/domestic income split. Many firms disclose geographic income in their 10-K footnotes but do not tag it with the standard XBRL elements, which creates potential selection bias if firms that report are systematically different from those that do not.

Tariff exposure is measured at a relatively coarse level. A firm classified in NAICS 334 (Computer and Electronic Products) may produce both heavily tariffed and non-tariffed products, so the industry-level measure is an imperfect proxy for firm-level exposure. Constructing firm-specific tariff measures would require product-level import data from sources like the US Census or UN Comtrade.

FPS values outside the [0, 1] range are economically valid but require careful interpretation. FPS greater than 1 occurs when domestic income is negative while foreign operations are profitable; FPS below 0 occurs when foreign or total income is negative. Approximately 32% of observations fall outside [0, 1].

Finally, the sample is limited to US-listed firms, and extending the panel back before 2015 would provide more pre-tariff baseline years but at the cost of declining XBRL coverage.

## Reproducibility

All code is in the `code/` directory and numbered in execution order:

1. `01_acquire_sec_data.py` --- Downloads pre-tax income data from the SEC EDGAR CompanyFacts API (~4 minutes at 10 requests/second)
2. `02_clean_and_merge.py` --- Cleans firm characteristics, reshapes Bloomberg financials, and merges all sources
3. `03_data_dictionary_and_stats.py` --- Generates the data dictionary, summary statistics, and data quality checks

To reproduce, set up a Python virtual environment, install the packages listed in `requirements.txt`, and run the scripts in order.
