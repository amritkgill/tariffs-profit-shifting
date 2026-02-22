# Methodological Note: Tariffs and Profit Shifting Dataset

## Overview

This dataset is constructed to examine the relationship between Section 301 tariff exposure and foreign profit shifting among US publicly traded firms for the period 2015-2024. The main variable of interest is **Foreign Profit Share** (Foreign Pre-Tax Income / Total Pre-Tax Income), which measures the proportion of a firm's earnings attributed to foreign operations.

## Data Sources

| Source | Variables | Access |
|--------|-----------|--------|
| SEC EDGAR XBRL CompanyFacts API | Foreign, domestic, and total pre-tax income | Free (public API) |
| SEC EDGAR company_tickers.json | Ticker-to-CIK mapping | Free |
| Bloomberg Terminal | Firm identifiers (ticker, SIC, NAICS), market cap, price, and annual financials (revenue, assets, debt, capex, R&D, effective tax rate, operating expenses) | Bloomberg Terminal |
| Section 301 tariff data | Tariff exposure by NAICS-3 industry | Research dataset |

## Key Decisions

### 1. Foreign Profit Share Construction

Foreign Pre-Tax Income is sourced from the XBRL tag `IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign`. Where this tag is missing but both Total and Domestic pre-tax income are available, Foreign is computed as the residual: **Foreign = Total - Domestic**. This residual approach substantially increases coverage (from ~2,100 to ~2,200 firms per year) since the Domestic tag is more widely used than the Foreign tag.

Total Pre-Tax Income comes from two XBRL tags (reflecting an SEC taxonomy change over time):
- `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` (newer)
- `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` (older)

When a firm uses both tags in the same year, the newer tag takes priority.

### 2. Outlier Treatment

Foreign Profit Share is winsorized at the 1st and 99th percentiles. The raw variable exhibits extreme values (min: -12,542; max: 329) driven by firms with near-zero total income. After winsorization, the range is approximately [-4.1, 4.9]. Observations with extreme values are flagged via `fps_extreme` for sensitivity analysis.

### 3. Tariff Merge Strategy

Tariff exposure is merged at the NAICS 3-digit level. The tariff data covers 26 goods-producing industries (NAICS 111-339). Service-sector firms (finance, tech services, healthcare, etc.) do not match and have missing tariff values. This is by design: Section 301 tariffs apply only to imported goods, so only manufacturing and resource extraction industries are exposed.

### 4. Sample Construction

Starting from 3,000 firms in the Bloomberg universe, 1,108 are ETFs/funds that cannot be matched to SEC EDGAR filings. The remaining 1,892 operating companies are matched to SEC data via ticker-CIK mapping, yielding 1,675 firms with income data. The final panel contains 14,400 firm-year observations across 2015-2024.

The panel is **unbalanced** --- not every firm appears in every year. A balanced panel would have 16,750 rows (1,675 x 10 years), so about 14% of firm-years are missing. Most of this is due to firms entering the sample after 2015 (e.g., IPOs or SPAC mergers), with smaller shares from firms exiting early (acquisitions, delistings) or occasional gaps in XBRL tag usage. About 65% of firms have all 10 years of data. This is common in SEC XBRL data. Because the missingness is driven mainly by when firms began trading rather than by anything related to profit shifting or tariff exposure, it is unlikely to bias estimation. Firm fixed effects handle the unbalanced structure by absorbing time-invariant firm characteristics regardless of how many years each firm is observed. That said, if firms that exit the sample early (e.g., through acquisition) differ systematically in their profit-shifting behavior, this could introduce mild survivorship bias and should be kept in mind when interpreting results.

## Data Limitations

1. **SEC XBRL coverage of geographic income breakdown**: Only ~65% of firm-year observations have the foreign/domestic income split. This is a known limitation of XBRL data --- many firms disclose geographic income in their 10-K tax footnotes but do not tag it with the standard XBRL elements. This creates potential selection bias: firms that tag foreign income may be systematically different (e.g., larger, more international) from those that do not.

2. **Cross-sectional firm characteristics**: Market cap and price from Bloomberg are as of the most recent date, not year-matched. These are useful as current-state descriptors but should not be used in panel regressions without year-specific alternatives.

3. **Tariff exposure granularity**: Tariff exposure is measured at the NAICS 3-digit level, which groups diverse product lines. A firm classified in NAICS 334 (Computer and Electronic Products) may produce both heavily tariffed and non-tariffed products. Firm-level tariff exposure would be more precise but requires product-level data not available here.

4. **Foreign Profit Share interpretation**: FPS values outside [0, 1] are valid but require careful interpretation. FPS > 1 occurs when domestic income is negative (losses) while foreign operations are profitable. FPS < 0 occurs when foreign income is negative or total income is negative. Approximately 32% of observations fall outside [0, 1].

5. **Fiscal year alignment**: The SEC CompanyFacts API provides exact period end dates, which we use to assign data to the correct fiscal year. This avoids the calendar-year misalignment that would occur with the Frames API for non-December fiscal year-end firms (approximately 30-40% of the sample).

## Remaining Gaps

- **Year-specific firm controls**: Eight time-varying control variables from Bloomberg (total revenue, pre-tax income, R&D expense, total assets, total debt, capital expenditure, effective tax rate, operating expenses) are included in the panel for 2015-2024. Coverage is high (94-99% for most variables, 73% for effective tax rate).
- **Firm-level tariff exposure**: Product-level import data (from US Census or UN Comtrade) could be used to construct firm-specific tariff exposure based on disclosed product segments.
- **Pre-2015 data**: Extending the panel back to 2010-2012 would provide more pre-tariff baseline years, but XBRL coverage declines significantly before 2015.
- **Non-US multinationals**: The sample is limited to US-listed firms. Foreign multinationals operating in the US are excluded.

## Reproducibility

All code is in the `code/` directory and numbered in execution order:
1. `01_acquire_sec_data.py` - Downloads data from SEC EDGAR
2. `02_clean_and_merge.py` - Cleans and merges all sources
3. `03_data_dictionary_and_stats.py` - Generates documentation and checks

To reproduce: set up a Python virtual environment, install `requirements.txt`, and run the scripts in order. The SEC EDGAR API is rate-limited (10 requests/second); full acquisition takes approximately 3-4 minutes (one API call per firm).
