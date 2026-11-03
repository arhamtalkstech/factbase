# Eval suites

Each folder holds one dataset's quiz (`questions.jsonl`) and its dataset card (`README.md`: source, window, counts, how
gold answers were produced, known issues). The item streams the memories ingest are built locally with
`uv run python -m factbase.datasets.<name>.build` and written to `data/<name>/items.jsonl` (gitignored). The runner
always prefers the committed suite in `evals/` over a locally rebuilt `data/<name>/questions.jsonl`.

The format is specified in [`../docs/datasets.md`](../docs/datasets.md). In short, each question has an `ask_at`
time (the memory sees nothing published after it), a self-contained `question`, `gold` answers, a `category`
(point_recent, point_old, as_of_state, change, aggregate, ordering, multi_hop, abstain), the `fact_time` used for retention
curves, and a `base_id` shared by every re-ask of the same fact.

| Suite | Window | Items (rebuilt locally) | Questions | Gold produced by |
|---|---|---|---|---|
| `markets` | 2024-11 to 2026-10 | 4,990 items: 10 daily FRED series plus fed funds target changes | 242 | code, from the series |
| `football` | 2024-08 to 2026-09 | 2,114 match results, 3 leagues | 256 | code (league tables, streaks, totals) |
| `sec_filings` | 2024-11 to 2026-10 | 958 filings, 30 companies | 259 | code, from XBRL facts |
| `fedreg` | 2024-11 to 2026-10 | 783 sanctions and export-control documents | 259 | code + LLM from single documents, verified |
| `world_quiz` | 2024-11 to 2026-10 | 13,066 Wikipedia current-events items | 265 (rebuild locally) | human-written news quizzes, filtered for answerability |
| `iran_headlines` | 2024-11 to 2026-10 | 339,210 GDELT headlines | 257 | LLM from Wikipedia event bullets, verified against headlines |
| `quakes` (held-out) | 2024-11 to 2026-10 | 16,259 USGS events M4.5+ | 217 | code; built by an agent that never saw the memory designs |
| `weather` (held-out) | 2024-11 to 2026-10 | 8,760 city-days, 12 cities | 215 | code; built the same way |
| `combined` | union | about 361k items, all feeds in one stream | 303 here (378 with world_quiz) | as above |
| `longmemeval` | per question | about 50 chat sessions per question | 500 (downloaded) | the benchmark's own answers |

`world_quiz` ships without question text (see `../DATA_LICENSES.md`); its builder recreates the suite locally. The
`combined` suite here omits world_quiz rows; rebuild it with `factbase.datasets.combined.build` after building world_quiz to
restore them.
