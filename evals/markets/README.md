# markets

Daily market and macro series from FRED (Federal Reserve Bank of St. Louis), turned into one
prose item per series per observation date, plus a fully programmatic quiz.

Build: `uv run python -m factbase.datasets.markets.build` (raw CSVs cached in `data/raw/markets/`).
Validate: `uv run python -m factbase.datasets.validate markets`.

## Source and terms

- CSV downloads, no API key: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=2024-10-01&coed=2026-10-31`.
- Series: DCOILBRENTEU (Brent spot), DCOILWTICO (WTI spot), DHHNGSP (Henry Hub gas spot), DGS10, DGS2
  (Treasury constant-maturity yields), DEXUSEU (USD per EUR), DEXJPUS (JPY per USD), VIXCLS (VIX close),
  SP500, NASDAQCOM, DFEDTARL + DFEDTARU (fed funds target range).
- Every series has data through late October 2026, so no series was dropped. Last observations in the cache:
  oil and gas 2026-10-27, FX 2026-10-23, yields, VIX and NASDAQ 2026-10-29, S&P 500 2026-10-28, and the Fed
  target range 2026-10-31.
- FRED data is public. Some series carry third-party copyright (S&P 500 from S&P Dow Jones Indices, NASDAQ
  from Nasdaq, VIX from Cboe, and oil and gas from EIA/Refinitiv). Use it for internal research only. Do not
  redistribute it.
- October 2024 is downloaded only to supply the "previous close" for the first items in the window.

## Items (`items.jsonl`): 4,990

| Series | Items |
|---|---|
| DCOILBRENTEU | 502 |
| DCOILWTICO | 494 |
| DHHNGSP | 494 |
| DGS10 / DGS2 | 497 / 497 |
| DEXUSEU / DEXJPUS | 494 / 494 |
| VIXCLS | 514 |
| SP500 | 498 |
| NASDAQCOM | 499 |
| DFEDTAR (target range) | 7 |

- The window runs from 2024-11-01 to 2026-10-31. There is one item per series per observation date. Missing
  values (empty or ".") are skipped.
- `id` = `markets:<date>:<SERIES>`, and `ts` = `<observation date>T22:00:00Z`.
- `text` gives the weekday, the value, and the change from the previous observation, with that observation's
  value and date. Percent changes are shown for prices, indices and FX. Yield changes are shown in percentage
  points. For example: "On 3 March 2025 (Monday), the Brent crude oil spot price closed at 72.85 USD per
  barrel, down 1.91 (-2.6%) from the previous close of 74.76 on 28 February 2025."
- `meta` = `{series, date, value, unit, prev_value, prev_date}`. Fed items also carry `lower` and `upper`, and
  their `value` is a string such as "4.00-4.25%".
- Fed target range: one initial item on 2024-11-01 (4.75-5.00%), then one item per change. The changes on
  FRED's effective dates are:
  - 2024-11-08: cut to 4.50-4.75%
  - 2024-12-19: cut to 4.25-4.50%
  - 2025-09-18: cut to 4.00-4.25%
  - 2025-10-30: cut to 3.75-4.00%
  - 2025-12-11: cut to 3.50-3.75%
  - 2026-09-17: hike to 3.75-4.00%
- Values are rounded to the series' display precision: 2 decimals, or 4 for DEXUSEU. NASDAQ is published with
  3 decimals and shown with 2.

## Quiz (`questions.jsonl`): 92 base questions, 242 instances

All gold answers have `gold_source = "structured"`. They are computed in `build.py` from the same cached FRED
values that produce the items. The build makes no LLM calls, so its LLM cost is $0.

| Category | Instances | Base | What it is |
|---|---|---|---|
| point_recent / point_old | 22 / 67 | 22 | Value of one series on one date. Re-asked at the first month-end after the date, then +3, +6 and +12 months, and on 2026-10-31. |
| as_of_state | 13 | 13 | Most recent value as of the ask date. Some ask dates fall on weekends or holidays, so the latest value is from an earlier day. Four questions ask for the Fed target range as of a date. Each is asked once, on that date. |
| aggregate | 41 | 16 | Highest or lowest value, or its date, in a month or quarter. Number of days the VIX closed above 25 in a quarter. A monthly average rounded to 2 decimals. |
| change | 28 | 11 | Percent change between two dated values, rounded to 1 decimal. Yield change in basis points. Number and direction of Fed target-range changes between two dates. |
| ordering | 21 | 8 | Which of two threshold crossings happened first. The date a series first closed above a level. Days between two Fed changes. |
| multi_hop | 29 | 8 | Brent minus WTI spread, 10-year minus 2-year spread, implied yen per euro, and lookups keyed on another event (for example, the S&P 500 on the day of a Fed change). |
| abstain | 21 | 14 | Seven ask about a date after `ask_at`. Four ask about a holiday or weekend with no value, asked twice. Three ask about an untracked series (gold, Dow Jones, 30-year yield), asked twice. |

- Non-point questions are re-asked at the first month-end after `fact_time`, then +6 months, and on
  2026-10-31, where those dates fall inside the window.
- Asks fall in 24 distinct months.
- Tolerances:
  - Direct lookups use 0.001: exact at 2 decimals for yields, about 0.1% for prices and indices. DEXJPUS uses
    0.0005 and DEXUSEU uses 0.0002.
  - Derived values use 0.005 for percent changes and spreads, and 0.001 for averages.
  - Counts and basis-point answers use 0.
  - Percent-change golds list both the 1-decimal and the 2-decimal value, so rounding at the boundary is not
    penalised.
- The build asserts that every argmax or argmin is unique, that every date used in a question has a value,
  and that every holiday premise really has no value.

## Known issues and limitations

- `ts` is the observation date at 22:00Z, as the task specifies, not FRED's real publication time.
  - EIA oil and gas spot prices appear on FRED with a lag of several days.
  - H.10 FX rates are published weekly.
  - Treasury yields appear the next business day.
  
  The stream is therefore earlier than real-time availability. This is the same for every architecture.
- Fed dates are FRED's effective dates, which are the day after each FOMC announcement (for example, the
  17 September 2025 decision appears as 18 September). A closed-book model may answer with the announcement
  date. Questions avoid asking for those dates directly, except through the record.
- The VIX has values on some US equity holidays (Cboe extended hours), so it has 16 more dates than the
  S&P 500. VIX counts are counts of VIX records.
- Brent has a few multi-day gaps (around Easter and Christmas). WTI, gas and FX have entries on some dates
  where Brent does not, and the reverse.
- Each item repeats the previous observation's value. A point fact can therefore also be recovered from the
  next item. This is intended redundancy. Evidence ids list only the item for the date itself.
- FRED revises some series. The cached CSVs (downloaded 2026-11-02) are the reference.
- Leakage: values up to the model's training cutoff (roughly through 2025) may be known to a closed-book
  model, especially well-known levels such as index closes on notable days and Fed decisions. Values from 2026
  should not be. Compare with A0.
