# factbase

**A long-horizon memory layer for streams of facts, market data, documents and conversations, and the experiments that
produced it.**

The question behind it: if you pour every news item, price move, filing and conversation on a topic into one place for
months or years, what memory design lets a model answer *anything that ever happened*, at any later point in time?
Instead of arguing designs, factbase replays real one-to-two-year public data streams on a simulated clock through
twenty memory designs, quizzes each one about facts of every age, and keeps what the evidence supports.

All language-model calls use `grok-4.3` on the xAI API; embeddings run locally.

| | Result |
|---|---|
| Auto-compaction (one rolling summary) as long-term memory | **27.7%** overall; 56% on facts under a month old, 4% on facts over 14 months old |
| Search over raw items, single shot | 81.5% |
| Search agent over raw items | 89.1% |
| **factbase** (raw items as SQL rows + search + sandboxed Python, compute enforced) | **94.2%** on six streams; **93.5%** on two held-out datasets built blind (search agent: 55.6%) |
| All six feeds in one ~361k-item memory | 97.2% (97.5% with separate memories) |
| Conversations (LongMemEval-S, 413 held-out questions) | **87.2%**, up from 70.9% for the first design |
| Reliability of the numbers | Repeat runs ±1 point; independent audit found 0 wrong gold answers in 240 and 0 false passes in 720 verdicts |

---

## Contents

1. [The architecture](#the-architecture)
2. [Quick start](#quick-start)
3. [The research, phase by phase](#the-research-phase-by-phase)
4. [What we landed on](#what-we-landed-on)
5. [Latency and scaling](#latency-and-scaling)
6. [Eval suites and results in this repository](#eval-suites-and-results-in-this-repository)
7. [Repository layout](#repository-layout)
8. [Licence](#licence)

---

## The architecture

**Keep everything, make it queryable three ways, and put a careful agent with a calculator in front of it.**

```
                  ┌───────────────────────────────────────────────────────────────┐
 feeds  ────────► │ EVIDENCE VAULT  (append-only, never edited)                    │
 (news, prices,   │  one SQL row per item: id, ts, date, feed, source, title,     │
  filings, chat)  │  text, meta JSON (structured fields captured as they arrive)  │
                  │  + BM25 keyword index + vector index, all hard time-filtered  │
                  └───────────────────────────────────────────────────────────────┘
                          ▲                ▲                  ▲
 conversations ───► EXTRACTED FACTS (optional): atomic facts from what each person said, each with a topic,
                    a memory type and a priority; supersession keeps history (old values marked, never deleted)
                          ▲                ▲                  ▲
                  ┌───────┴────────────────┴──────────────────┴────────────────────┐
 question ──────► │ QUERY AGENT                                                     │
                  │  tools: search_records, list_records, sql (read-only),          │
                  │         python (sandboxed), read_records, search_facts          │
                  │  schema card in the prompt, one section per feed                │
                  │  rules: analytic questions must run sql/python before answering;│
                  │         two searches before saying "not in the record";         │
                  │         latest value wins; relative dates become date ranges    │
                  └─────────────────────────────────────────────────────────────────┘
```

### 1. Evidence vault

Every item is stored three ways at once and never changed:

```sql
CREATE TABLE records (
  item_id TEXT PRIMARY KEY, date TEXT, ts TEXT, source TEXT, title TEXT,
  meta TEXT,   -- JSON with the item's structured fields (price, series, league, form type, ...)
  text TEXT,   -- what the model reads
  feed TEXT    -- which stream it came from
);
```

plus a BM25 keyword index (SQLite FTS5, Porter stemming) and a dense vector index (`bge-small-en-v1.5`, 384
dimensions), fused with reciprocal rank fusion. Every lookup is capped at "now", so the memory can never see the future;
that also makes it safe to backtest.

Why three ways: keyword search finds names, numbers and exact phrases; vectors find paraphrases; SQL rows make counts,
maxima, "first time X happened" and "latest value as of a date" exhaustive. Search only ever returns the best matches,
never all of them, and that limitation was the biggest cause of error before SQL rows existed.

### 2. Query agent

A tool-using agent (`grok-4.3`, reasoning effort `low`, up to 10 steps) starts from the top hybrid hits and can:

| Tool | Purpose |
|---|---|
| `search_records(query, start_date, end_date, k)` | hybrid search with date filters |
| `list_records(start_date, end_date, contains)` | read everything in a window |
| `sql(query)` | read-only SELECT/WITH over the memory tables |
| `python(code)` | sandboxed Python (no network, no file writes) with an `sql()` helper, for league tables, streaks, crossings |
| `read_records(ids)` | exact raw records by id, for drilling down from any derived statement to its evidence |
| `search_facts`, `entity_history` | over extracted facts, when that layer is on |

Its system prompt carries a **schema card**: per feed, the row count, date range and each structured field with example
values, so the agent knows what it can query without spending a step. Rules that measurably helped:

- questions about counts, maxima, first/last, as-of, standings or streaks are refused once until the agent has run
  `sql` or `python`;
- an abstention is refused once until the agent has searched twice with different phrasings;
- for conversations: answer advice questions from what is remembered, turn "two weeks ago" into dates, take the latest
  of conflicting values, list instances before counting.

### 3. Extracted facts (for conversations)

In a conversation a fact is buried in a long turn, so the conversation configuration also extracts atomic facts from
each speaker's own turns, one LLM call per day of messages. Each fact records subject, attribute, object, number, unit,
event date, period, kind (state or event), source item ids, a **topic**, a **memory type** (preference, instruction,
plan, state, event) and a **priority** (0-100). State facts for the same subject and attribute supersede earlier ones;
the old value is kept with a `valid_to` date. Asking for topic, type and priority alone raised conversation accuracy
from 82.3% to 87.2%.

### 4. Optional layers (switches)

Implemented and measured; useful for auditability and human review, with no measurable accuracy gain on our tests:

| Switch | What it does |
|---|---|
| `profile` | standing profile rebuilt from current facts (never from its own last version), every bullet citing fact ids |
| `conflicts` | each new fact compared with similar older ones and marked duplicate, updates or contradicts; nothing deleted; every decision logged |
| `threads` | facts grouped into persistent topics or storylines, with `list_threads` and `get_thread` |
| `offload` | older tool outputs shrink to stubs that `open_ref` restores (no gain on short agent loops; it breaks the prompt cache) |
| `budget` | cap on searches per question |
| `export_views()` | profile and threads as Markdown with fact ids, for analysts |

Details and data structures: [`docs/architecture.md`](docs/architecture.md), [`docs/layers.md`](docs/layers.md).

### Recommended configurations

| Use | Name | Measured |
|---|---|---|
| Fact, market, filing and news feeds | `agentic_sql_v6f` | 96.4% on a 360-question sample of six streams; about 93% on the two held-out datasets |
| Conversations | `factbase_v7c` | 87.2% on the LongMemEval-S held-out test split |

---

## Quick start

```bash
git clone <this repository> && cd factbase
uv sync                                   # Python 3.12; deps: httpx, numpy, fastembed, pydantic, python-dotenv, tqdm
cp .env.example .env                      # set XAI_API_KEY (never commit .env)
```

**Reproduce every report from the committed results**, with no API key and no downloads:

```bash
uv run python -m factbase.eval.analyze --runs v1,v2,v3,v4,v5,v6 --out docs/results.md
uv run python -m factbase.eval.audit_summary          # docs/audit.md
uv run python -m factbase.eval.v7_report              # docs/v7_results.md
```

**Build a dataset and run a memory over it** (public data; SEC asks for a contact in the User-Agent):

```bash
export FACTBASE_CONTACT="you@example.com"
uv run python -m factbase.datasets.markets.build      # downloads FRED series, writes data/markets/
uv run python -m factbase.datasets.validate markets
uv run python -m factbase.eval.run --dataset markets --arch agentic_sql_v6f,raw_rag --run mine --until 2025-02-28
uv run python -m factbase.eval.grade --run mine        # results/runs/mine/report.md
scripts/run_dataset.sh markets mine                    # every pre-registered architecture, three parallel chains
```

Builders exist for `markets`, `football`, `sec_filings`, `fedreg`, `world_quiz`, `iran_headlines`, `quakes`, `weather`
and `combined`. `world_quiz`, `iran_headlines` and `fedreg` make LLM calls to write or verify questions.

**Conversations** (LongMemEval-S, downloaded separately; see [`evals/longmemeval/README.md`](evals/longmemeval/README.md)):

```bash
uv run python -m factbase.eval.longmemeval --arch factbase_v7c --run lme --split test
uv run python -m factbase.eval.longmemeval --grade --run lme
uv run python -m factbase.eval.longmemeval --arch factbase_v7c --run lme_inter --split test --subset 120 --interleave
```

**Controls.** Every LLM call is cached by request hash (`data/cache/llm.sqlite`), so a rerun replays for free. Spend is
logged per call and capped by `data/cache/budget_usd.txt` or `FACTBASE_BUDGET_USD`.

| Variable | Default | Purpose |
|---|---|---|
| `XAI_API_KEY` | (required for new runs) | xAI API key, read from `.env` |
| `FACTBASE_BUDGET_USD` | 300 | spend cap |
| `FACTBASE_ANSWER_EFFORT` | `low` | reasoning effort for answers |
| `FACTBASE_ANSWER_MODEL` | `grok-4.3` | answer-time model override |
| `FACTBASE_INGEST_WORKERS` | 16 | parallel extraction / digest calls |
| `FACTBASE_CACHE_SALT` | (none) | bypass the cache for repeat runs |
| `FACTBASE_CONTACT` | (none) | contact for data-API User-Agents |

---

## The research, phase by phase

### The test bench

The runner (`factbase/eval/run.py`) replays a dataset one simulated day at a time: ingest the day's items, run
end-of-day consolidation, then ask any questions scheduled for that day as of 23:59:59 UTC. A memory never sees an item
from after the question time. The same fact is re-asked months later, which gives retention curves.

Fairness rules, fixed before any run ([`docs/preregistration.md`](docs/preregistration.md)): every design sees the same
items in the same order and is asked the same questions with the same model; gold answers never come from any
memory; grading is blind to the design; a no-memory baseline is reported next to everything to expose what the model
already knows.

Grading (`factbase/eval/grade.py`) checks numbers deterministically to the precision the gold is written in, then uses a
strict LLM judge. The judge was validated on 480 adversarial test answers: 100% of correct answers with extra detail
accepted, 97.5% of vague answers and 99.2% of confident near misses rejected ([`docs/method.md`](docs/method.md)).

### Phase 0: survey

We surveyed long-term memory approaches for language-model agents: rolling summaries and context compaction,
extracted-fact stores with update/delete pipelines, temporal knowledge graphs with validity intervals, hierarchical
summaries, file- and search-based agents, and news-analytics practice (story deduplication, novelty, source
credibility). The recurring claims worth testing: raw evidence must be kept; facts need time; repeated summarisation
drifts; extraction loses information. These became the hypotheses.

### Phase 1: pre-registered comparison of twelve designs

Six real public streams, November 2024 to October 2026, about 361,000 items: daily market series, football results,
SEC filings, Federal Register sanctions documents, Wikipedia's daily current events with human-written news quizzes, and
339,000 GDELT headlines about Iran. About 1,500 questions per design.

| Design | Mean accuracy |
|---|---|
| closed book (no memory) | 10.4% |
| rolling summary (auto-compaction) | 27.7% |
| last ~30k tokens verbatim | 32.6% |
| frozen day/week/month summaries | 57.4% |
| extracted facts only | 67.8% |
| hybrid search over raw items, single shot | 81.5% |
| factbase v1 (facts + digests + search agent) | 87.9% |
| search agent over raw items | 89.1% |

Confirmed: compaction collapses with fact age; search over raw items beats searching extracted facts; designs that keep
raw items have flat retention. Refuted: the pre-registered "factbase v1" did not beat a plain search agent. Full tables:
[`docs/results.md`](docs/results.md); hypotheses and verdicts: [`docs/findings.md`](docs/findings.md).

### Phase 2: from searching to computing

Reading the failures showed one cause: counts, maxima, "first day above $90" and league tables need *every* matching
record, and search returns only the best matches. The fixes, each measured:

| Change | Mean accuracy |
|---|---|
| v1 search agent | 89.1% |
| v2: every raw item also a SQL row, sandboxed Python, schema card | 92.6% |
| v3: analytic questions must compute before answering | **94.2%** (aggregation 72% to 96%, as-of 80% to 96%) |
| without structured fields | -6.4 points (p < 1e-13), -14 on football |
| v3 + extracted facts and digests | 94.3% (tie with v3: 40 questions won each way) |

The full design and the lean one tied, so the extra layers were dropped for feeds. Two later rules (require two
searches before abstaining; answer when the event matches even if a detail is unconfirmed) gave no net gain. In one
shared ~361k-item memory the lean design held at 97.2%.

### Phase 3: trust testing

| Concern | Test | Result |
|---|---|---|
| noise | three cache-bypassed runs on 360 questions | ±1.1 points; ranking never changed |
| gold answers | agent audit of 240 questions, re-derived from raw data with no LLM calls | 0 wrong, 6 ambiguous |
| grader | 720 verdicts checked | 0 false passes; 27 false fails, so scores are lower bounds |
| overfitting | two datasets (USGS earthquakes, Open-Meteo weather) built blind by an agent that never saw the designs | 93.5% against 55.6% for the search agent and 12.5% for compaction |
| one model's quirk | same designs answered by grok-4.7 | same ranking: 97.5% against 89.6% |
| scale | search and SQL timed from 10k to 3M rows | vector 44 ms, BM25 164 ms at 3M; 99% of answer time is the model (median 12.6 s) |
| conversations | LongMemEval-S with a fixed dev/test split | 70.9%, then 78.7% with a unified answer policy, 82.3% adding facts from each speaker's turns |
| truth in social posts | PHEME rumour tweets | not run: with no memory the model already knew 9 of 12 outcomes |

Details: [`docs/trust.md`](docs/trust.md), [`docs/audit.md`](docs/audit.md),
[`docs/bench_retrieval.md`](docs/bench_retrieval.md).

### Phase 4: layered additions

Seven additions, each a switch, pre-registered in [`docs/preregistration_v7.md`](docs/preregistration_v7.md): typed and
prioritised facts with topics, a standing profile, non-destructive conflict resolution, topic threads, reversible
offload of the agent's working memory, a search budget, and drill-down with Markdown views. Chosen on the dev split,
tested once on 413 held-out questions, then attributed:

| Configuration | LongMemEval-S test |
|---|---|
| previous best (v6 + speaker facts) | 82.3% |
| v7 chosen on dev (profile, conflicts, typed ranking) | 86.4% (p = 0.019) |
| v7 extraction only (topic, type, priority per fact) | **87.2%** (p = 0.008) |

The gain came entirely from the richer extraction. The profile, conflict resolution and priority ranking added no
measurable accuracy; threads hurt on normal sessions and did not help on an interleaved channel (unrelated same-day
conversations mixed message by message, 89.1% either way); offload saved no tokens on agent loops of about three calls
and lowered the share of input served from the prompt cache from 38% to 30%. On
feeds no addition helped. Full report: [`docs/v7_results.md`](docs/v7_results.md).

---

## What we landed on

- **Never compress the evidence.** Keep every item verbatim and searchable; retention then stays flat with age.
- **Make the evidence queryable, not only searchable.** SQL rows over every item, structured fields captured as they
  arrive, and a sandboxed calculator. This was the largest measured gain.
- **A careful agent beats clever storage.** The rules that mattered are behavioural: compute before answering
  analytic questions, search twice before saying no, take the latest value.
- **Derived layers are optional.** Extracted facts pay off for conversations, where facts hide in long turns; on fact
  feeds, facts and summaries added nothing measurable. Profiles, conflict logs and thread views are for human review.
- **One memory can hold everything**, with a per-feed schema card so small feeds are not hidden by large ones.

---

## Latency and scaling

Measured on one laptop (Apple Silicon, 18 cores) with SQLite, brute-force NumPy vectors and local embeddings: no
search cluster, no GPU, no approximate index.

### Ingest: how fast a new item becomes searchable

| Step | Throughput |
|---|---|
| SQL row + keyword index (append-only) | ~550,000 items/s |
| Embedding, headline-length text (~100 chars), CPU | ~540 items/s |
| Embedding, long chat turn (~1,400 chars), CPU | ~50 items/s |
| Fact extraction (conversation configuration only) | one LLM call per day-batch of messages, off the answer path |

A burst of 10,000 headlines is findable by keyword immediately and by meaning within about 20 seconds on a single CPU.
Embedding is the only ingest step that needs scaling for a firehose (GPU or a batching service).

### Retrieval: time per lookup as the corpus grows

Median milliseconds, single thread ([`docs/bench_retrieval.md`](docs/bench_retrieval.md); rows beyond 339k are
synthetic copies of real headlines):

| Items | Vector search | Keyword (BM25) top-100 | SQL count by date | SQL full-text scan |
|---|---|---|---|---|
| 10,000 | 0.1 | 0.4 | 0.0 | 1.0 |
| 339,210 | 5.0 | 17.3 | 0.6 | 34.9 |
| 1,000,000 | 15.8 | 55.4 | 2.1 | 106.8 |
| 3,000,000 | 44.4 | 164.4 (p95 706) | 6.3 | 312.7 |

Everything grows roughly linearly and stays under a second at 3 million items.

### Answers: where the time goes

About 99% of answer time is model calls; search, SQL and Python together take about 0.1%. A typical answer uses three
model calls. Answer latency therefore does **not** grow with corpus size; it depends on the question:

| Dataset (agentic_sql_v3) | Items in memory | Median | p90 |
|---|---|---|---|
| fedreg | 783 | 14.1 s | 26.6 s |
| sec_filings | 958 | 17.0 s | 26.7 s |
| football (league tables computed in Python) | 2,114 | 24.9 s | 50.0 s |
| markets | 4,990 | 15.5 s | 26.9 s |
| world_quiz | 13,066 | 9.8 s | 22.7 s |
| iran_headlines | 339,210 | 16.5 s | 29.2 s |

By design (medians across six datasets): single-shot retrieval 8-10 s, search agents 13-16 s, the conversation
configuration 18.5 s. These were measured with many experiments sharing the API; a quieter repeat run gave a median of
12.6 s and p90 of 26.5 s.

### Scaling path

| Corpus | What changes |
|---|---|
| up to ~3M items | nothing: one machine, every lookup under a second |
| 3M-30M items | approximate nearest-neighbour vectors, tables partitioned by month, a dedicated keyword index |
| 30M+ items | a distributed search engine with hybrid search and hard filters, a partitioned SQL or columnar store for the rows, GPU embedding |

Answer latency is set by the number of agent steps and the model's speed. For sub-second reads, the next step is an
always-current fast path: state per entity and topic kept up to date in the background and pushed as alerts when it
changes, with the agent reserved for deep questions.

---

## Eval suites and results in this repository

- [`evals/`](evals/README.md): the quiz for each dataset (questions, gold answers, categories, ask times) and its dataset
  card. Item streams are rebuilt locally by the builders.
- [`results/`](results/README.md): graded outputs for every run the reports rely on (25 runs, compressed), run stats,
  per-run reports, tool traces for the final designs, the audit and the judge validation.

---

## Repository layout

```
factbase/
  llm.py            xAI chat-completions client over plain HTTP: request cache, call log, spend cap
  embed.py          local embeddings (bge-small-en-v1.5 via fastembed), cached
  index.py          hybrid BM25 (SQLite FTS5) + dense index with hard time filters
  paths.py          where data, eval suites and results live
  types.py          Item, Question, Answer
  memories/
    base.py         memory interface, answer policies, tool-using agent loop (compute rule, abstain rule, offload, budget)
    baselines.py    closed_book, recent_window, rolling_summary, raw_rag, agentic_raw
    structured.py   fact_memory, rollups, factbase v1-v6 (SQL rows, Python sandbox, schema card, supersession)
    layered.py      factbase v7 layers (typed extraction, profile, conflicts, threads, offload, budget, views)
    registry.py     every architecture name and ablation used in the reports
  datasets/         one builder per dataset, validate.py, combined/
  eval/
    run.py          replay on a simulated clock
    grade.py        blind grading (numeric check + strict judge)
    judge_check.py  adversarial validation of the grader
    analyze.py      cross-run tables, retention, McNemar tests, latency
    audit_summary.py, v7_report.py, longmemeval.py
scripts/            run_dataset.sh (all architectures on one dataset), bench_retrieval.py (latency to 3M rows)
evals/              eval suites and dataset cards
results/            graded outputs, stats, reports, audit
docs/               pre-registrations, method, results, findings, trust, layers, architecture
```

---

## Licence

Code: MIT ([`LICENSE`](LICENSE)). Eval suites and results derived from public data keep their sources' terms; see
[`DATA_LICENSES.md`](DATA_LICENSES.md).
