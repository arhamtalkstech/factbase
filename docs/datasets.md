# Dataset contract

Every dataset has a builder in `factbase/datasets/<name>/build.py`. It downloads the public source and writes to
`data/<name>/` (gitignored):

- `data/<name>/items.jsonl`: the stream, sorted by `ts` ascending.
- `data/<name>/questions.jsonl`: the quiz as built locally.
- `data/<name>/README.md`: source, licence/terms, counts, how gold was produced, known issues.

The canonical quiz and dataset card are committed in `evals/<name>/` (`questions.jsonl`, `README.md`); the runner uses
them in preference to the locally built `questions.jsonl`, so rebuilding a stream never changes the eval suite.

Common window: **2024-11-01 to 2026-10-31** unless a dataset documents a shorter window.

## Item (one line of `items.jsonl`)

```json
{
  "id": "markets:2025-03-03:DCOILBRENTEU",
  "dataset": "markets",
  "ts": "2025-03-03T21:00:00Z",
  "title": "Brent crude closes at $71.04",
  "text": "On 2025-03-03 the Brent crude spot price (FRED DCOILBRENTEU) closed at 71.04 USD per barrel, down 1.2% from the previous close of 71.90.",
  "source": "FRED",
  "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
  "meta": {"series": "DCOILBRENTEU", "value": 71.04, "unit": "USD/bbl"}
}
```

- `ts` is when the information became available (publication time), ISO 8601 UTC.
- `text` is what every memory sees. It must be self-contained, readable prose (or a
  headline), never a raw JSON dump.
- `meta` is the optional machine-readable payload of the same information. Only
  architectures that test "mechanical structured ingest" may read it.

## Question (one line of `questions.jsonl`)

```json
{
  "qid": "markets:q0042@2025-09-30",
  "base_id": "markets:q0042",
  "dataset": "markets",
  "ask_at": "2025-09-30T23:59:59Z",
  "question": "What was the Brent crude spot closing price on 3 March 2025?",
  "gold": ["71.04"],
  "answer_type": "number",
  "numeric_tolerance": 0.005,
  "category": "point_old",
  "fact_time": "2025-03-03",
  "evidence_item_ids": ["markets:2025-03-03:DCOILBRENTEU"],
  "gold_source": "structured"
}
```

Field rules:

- `ask_at`: always `T23:59:59Z` of a day inside the window. The memory has ingested every
  item with `ts <= ask_at` and nothing later.
- `question`: self-contained. Use explicit dates ("on 3 March 2025", "as of 30 September
  2025"); never "this week" or "recently".
- `gold`: list of acceptable answers (aliases). For numbers, the number as a string.
- `answer_type`: `text | number | date | abstain`.
  - `abstain` means the correct behaviour is to say the information is not in the record
    (false premise, or about a time after `ask_at`). `gold` then holds a short note
    describing why.
- `numeric_tolerance`: relative tolerance for numbers (e.g. 0.005 = 0.5%), else null.
- `category`, one of:
  - `point_recent`: a single fact from the last 30 days before `ask_at`.
  - `point_old`: a single fact more than 30 days before `ask_at` (retention).
  - `as_of_state`: the value or status of something at a given date when it changes over
    time (latest price, league leader, latest reported revenue).
  - `change`: how something changed between two dates, or what replaced what.
  - `aggregate`: counts, sums, maxima/minima, rankings over many items.
  - `ordering`: which of two or more events came first, or durations between them.
  - `abstain`: see above.
  - `multi_hop`: needs two or more items joined together.
- `fact_time`: date of the underlying fact (for retention-by-age plots). For aggregates,
  the end of the aggregated range.
- `base_id`: the same underlying question re-asked at different `ask_at` times shares a
  `base_id`. This is how retention curves are built.
- `gold_source`: `human_quiz | structured | curated_wcep | llm_from_source`.

## Re-asking for retention

For point facts, emit the same `base_id` at several ask times: the first month-end after
the fact, then roughly +3, +6 and +12 months, and the final day of the window, where
those fall inside the window. Rephrase only if the question needs a date anchor.

## Independence rule

Gold must never be produced by any memory architecture. It comes from human quizzes,
from structured data computed with code, or from an LLM that reads only the raw source
items for that fact, followed by a verification pass against the same source.
