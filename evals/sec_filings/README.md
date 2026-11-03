# sec_filings

Periodic reports (10-Q, 10-K, 10-K/A) and current reports (8-K, 8-K/A, 8-K12B) filed with the SEC
from 2024-11-01 to 2026-10-31 by 30 large US companies. The dataset tests entity-heavy knowledge updates:
each new quarter replaces the previous "latest" figures, 10-K amendments arrive, and officers change (8-K Item 5.02).

Build: `uv run python -m factbase.datasets.sec_filings.build`. The code is in `factbase/datasets/sec_filings/`.
Raw downloads are cached in `data/raw/sec_filings/`, and a rerun does not download them again.

## Source and terms

- SEC EDGAR public APIs. No key is needed. Requests send the User-Agent from `factbase.paths.user_agent()`; set `FACTBASE_CONTACT` to your email and are rate-limited to under 10 per second.
  - `https://www.sec.gov/files/company_tickers.json`: maps tickers to CIKs.
  - `https://data.sec.gov/submissions/CIK##########.json`, plus the paged older-filing files for JPM and BAC: filing list with form, filingDate, reportDate and 8-K item codes.
  - `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`: XBRL facts, keyed by accession number.
- EDGAR data is public US government information. The SEC fair-access policy applies.
- Downloaded on 2026-11-02.

## Companies

XOM, CVX, COP (energy); LMT, RTX, NOC, GD, BA (defense/aerospace); AAPL, MSFT, NVDA, AMZN, GOOGL, META, ORCL,
INTC, TSLA, NFLX, DIS; JPM, BAC; WMT, KO, PFE, JNJ, UNH, CAT, GE, F, GM.

ExxonMobil reorganised under a new holding company, ExxonMobil Holdings Corp (CIK 2115436), on 2026-07-01. That company filed an 8-K12B. Both CIKs (34088 and 2115436) are merged under ticker XOM and de-duplicated by accession number. The Q2 2026 10-Q appears under both CIKs and is included once.

## Items (958)

| form | count |
|---|---|
| 8-K | 704 |
| 10-Q | 180 |
| 10-K | 60 |
| 8-K/A | 11 |
| 10-K/A | 2 |
| 8-K12B | 1 |

- `ts` = filing date at `21:00:00Z`. This is a convention; some filings were accepted later that evening. Items run from 2024-11-01 to 2026-10-30.
- `id` = `sec_filings:<TICKER>:<form>:<accession>`. `url` = the EDGAR filing folder.
- **10-Q/10-K text** includes: form, filing date, fiscal period, period end and accession number. It also gives the values reported in that filing for the period ending at the report date:
  - 3-month revenue, net income and diluted EPS.
  - Fiscal year-to-date (6-month or 9-month) values.
  - Total assets at period end.
  - Year-to-date operating cash flow.
  - For 10-Ks: the annual values.
- **Quarterly and YTD/annual values** are separated by the duration of each XBRL fact (`start`..`end`): 80–100 days is a quarter, 170–195 days is 6 months, 260–285 days is 9 months and 350–380 days is a year. Only facts tagged with that filing's accession number and ending on its report date are used. This means the values are the ones *originally reported* in that filing. Later recasts are ignored, and prior-year comparatives are not used.
- **Fourth quarter (documented derivation).** For a 10-K that does not tag its own 3-month figures, the item states an *implied* fourth quarter for revenue and net income. It equals the annual value minus the 9-month YTD value originally reported in that fiscal year's Q3 10-Q. The item text labels these figures as implied. No Q4 EPS is derived. GE's FY2024 10-K tags Q4 directly, so that value is used as reported.
- **10-K/A** (Tesla, two filings): the amendments carry no income-statement or balance-sheet XBRL facts. The item says this and does not invent any content.
- **8-K text** includes: filer, form, filing date, event date (`reportDate`), accession number, and every item code written out in words (for example "Item 5.02 Departure of Directors or Certain Officers; …").
- **`meta`** holds the structured payload: ticker, CIK, form, accession, dates, fiscal year/period, the XBRL concepts used, and every value with its start/end dates and a `derived` flag. For 8-Ks it also holds the item code list.
- **Fiscal year** is computed from the fiscal-year start date (start + 364 days, taking the year of the end). The companyfacts `fy` field labelled Oracle's 10-Q for the quarter ended 2026-08-31 as FY2026; it is correctly FY2027 Q1. That was the only disagreement.

### Concept mapping (first concept with a fact for the filing wins)

| metric | XBRL us-gaap concept chain |
|---|---|
| revenue | `Revenues` → `RevenuesNetOfInterestExpense` → `RevenueFromContractWithCustomerExcludingAssessedTax` |
| net income | `NetIncomeLoss` → `NetIncomeLossAvailableToCommonStockholdersBasic` → `ProfitLoss` |
| diluted EPS | `EarningsPerShareDiluted` → `IncomeLossFromContinuingOperationsPerDilutedShare` |
| total assets | `Assets` (instant at period end) |
| operating cash flow | `NetCashProvidedByUsedInOperatingActivities` (fiscal YTD) |

Notes on how the chain resolves for particular companies:

- **Total revenue line (`Revenues`):** XOM, CVX and COP report "total revenues and other income". GM reports "total net sales and revenue". BAC reports "total revenue, net of interest expense". WMT reports total revenues including membership income. For these companies the item text names the caption.
- **JPM:** "total net revenue" (`RevenuesNetOfInterestExpense`).
- **Companies whose 10-Qs only tag `RevenueFromContractWithCustomerExcludingAssessedTax`:** RTX, GD, F, ORCL and GOOGL (before mid-2025). For these companies the 10-K value is identical under both concepts, so the quarterly and annual figures are consistent.
- **Net income attributable to common shareholders:** CAT and F (from Q3 2025) only tag `NetIncomeLossAvailableToCommonStockholdersBasic`.
- **GD diluted EPS:** GD 10-Qs tag diluted EPS as `IncomeLossFromContinuingOperationsPerDilutedShare`. GD has no discontinued operations.
- **Q4 derivation with a concept switch:** if the 10-K and the Q3 10-Q use different concepts, the other concept is used only when the 10-K tags the identical annual value under it.

## Questions (94 base, 259 instances; all `gold_source = "structured"`)

Gold is computed in code from the same structured EDGAR data that produced the items. No LLM was used, and the LLM cost was $0.

| category | instances |
|---|---|
| point_old | 86 |
| point_recent | 29 |
| as_of_state | 35 |
| aggregate | 28 |
| abstain | 22 (8.5%) |
| ordering | 21 |
| change | 20 |
| multi_hop | 18 |

Base questions by type:

- **Point (29).** Quarterly revenue, net income and EPS; nine-month YTD revenue (versus the quarter); annual revenue; implied Q4 revenue; total assets; 10-K/A filing dates; the date of a company's only Item 5.02 8-K in a given month; and the item codes of a given 8-K.
  - Asked at the first month-end after filing, then +3, +6 and +12 months, and at 2026-10-31.
  - Each instance is labelled `point_recent` or `point_old` by its age at ask time (30 days or less counts as recent).
- **as_of_state (17).**
  - Revenue in the most recent 10-Q as of a date.
  - Period end of the most recent 10-Q.
  - Annual revenue in the most recent 10-K.
  - Date of the most recent Item 5.02 8-K.
  - These are asked at the as-of date and re-asked later, mostly at 2026-10-31. The gold is fixed by the explicit as-of date.
- **change (9).** YoY quarterly revenue change, and QoQ diluted-EPS change. Gold is the difference of the two-decimal figures shown in the items. Tolerance is relative, with a floor of about ±$0.01 billion or ±$0.005 per share.
- **aggregate (11).**
  - Highest quarterly revenue among 3–5 named companies for a calendar quarter. Only companies whose quarters end exactly on calendar quarter ends are used. One question is about Q4 2025, which uses 10-K fourth-quarter figures.
  - Number of original 8-Ks filed in a calendar quarter.
  - Number of Item 5.02 8-K/8-K/As filed in calendar 2025.
- **ordering (7).** Which of two companies filed its FY 10-K first; days between a company's two 10-K filings.
- **multi_hop (7).**
  - Net income of the top-revenue company in a named group.
  - Revenue from the latest 10-Q at the date of an Item 5.02 8-K.
  - Net income of the first FY2025 10-K filer among three companies.
- **abstain (14 base).**
  - A quarter whose 10-Q had not been filed by `ask_at` (asked at the month-end before filing).
  - Apple's non-existent 10-Q for its September quarter.
  - A Microsoft or NVIDIA 10-K/A that was never filed.
  - A Boeing or Intel 8-K with Item 1.03 that does not exist.
  - Q3 2026 YoY change for JPM and CAT, whose Q3 2026 10-Qs had not been filed by 2026-10-31.
  - The code asserts that these filings are absent.

Tolerances and units:

- Dollar answers state their units in the question ("in billions of USD, two decimals", or millions for amounts under $1 billion). They use `numeric_tolerance = 0.01`.
- 8-K counts and day gaps use tolerance 0.
- Dates accept ISO, "D Month YYYY" and "Month D, YYYY".

## Known issues / limitations

- **Coverage edges:**
  - 10-Qs for the quarter ending September 2024 that were filed before 2024-11-01 are outside the window, so for many companies the first item is the FY2024 10-K.
  - Q3 2026 10-Qs filed after 2026-10-31 (for example XOM, JPM, CAT) and Apple's FY2026 10-K are absent.
- **Captions:** the revenue captions in the item text (for example "total revenues and other income") come from a hand-written mapping of known income-statement captions. The values themselves come from the XBRL concept named in `meta.concepts`.
- **Implied Q4 figures** are derived (annual minus 9-month YTD). They are not filed numbers, though the item text says so explicitly. One aggregate question (calendar Q4 2025) and the implied-Q4 point questions depend on them.
- **Earnings 8-Ks:** an Item 2.02 8-K usually comes days before the 10-Q, but the 8-K items carry only item codes, not the numbers. "Not yet reported" abstain questions are about the *10-Q*. A closed-book model may still know the press-release figures from pretraining, which is a leakage risk the A0 control should show. Large-cap results for 2024–2025 are likely in pretraining data, and 2026 figures are less likely to be.
- **JPM and BAC** file many 8-Ks, some of which relate to structured-note programmes. All are included as filed.
- **The XOM holding-company reorganisation** creates two filers around 2026-07-01: an 8-K from Exxon Mobil Corporation (CIK 34088) and an 8-K12B from ExxonMobil Holdings Corp. The XOM 8-K count questions avoid this period.
- **`ts` convention:** using 21:00Z for every filing means a few filings accepted after 21:00Z are timestamped slightly early, but always on the correct day.
