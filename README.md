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
5. [Eval suites and results in this repository](#eval-suites-and-results-in-this-repository)
6. [Repository layout](#repository-layout)
7. [Limitations and open problems](#limitations-and-open-problems)
8. [Cost](#cost)
9. [Licence](#licence)

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
| `offload` | older tool outputs shrink to stubs that `open_ref` restores (raised cost: it breaks the prompt cache) |
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
and `combined`. `world_quiz`, `iran_headlines` and `fedreg` use a few dollars of LLM calls to write or verify questions.

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

| Configuration | LongMemEval-S test | USD per question |
|---|---|---|
| previous best (v6 + speaker facts) | 82.3% | 0.037 |
| v7 chosen on dev (profile, conflicts, typed ranking) | 86.4% (p = 0.019) | 0.032 |
| v7 extraction only (topic, type, priority per fact) | **87.2%** (p = 0.008) | **0.026** |

The gain came entirely from the richer extraction. The profile, conflict resolution and priority ranking added no
measurable accuracy; threads hurt on normal sessions and did not help on an interleaved channel (unrelated same-day
conversations mixed message by message, 89.1% either way); offload raised cost 24% by breaking the prompt cache. On
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

## Eval suites and results in this repository

- [`evals/`](evals/README.md): the quiz for each dataset (questions, gold answers, categories, ask times) and its dataset
  card. Item streams are rebuilt locally by the builders.
- [`results/`](results/README.md): graded outputs for every run the reports rely on (25 runs, compressed), run stats,
  per-run reports, tool traces for the final designs, the audit, the judge validation, and a numbers-only cost ledger.

---

## Repository layout

```
factbase/
  llm.py            xAI chat-completions client over plain HTTP: request cache, cost ledger, spend cap
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
    analyze.py      cross-run tables, retention, McNemar tests, cost
    audit_summary.py, v7_report.py, longmemeval.py
scripts/            run_dataset.sh (all architectures on one dataset), bench_retrieval.py (latency to 3M rows)
evals/              eval suites and dataset cards
results/            graded outputs, stats, reports, audit, cost ledger
docs/               pre-registrations, method, results, findings, trust, layers, architecture
```

---

## Limitations and open problems

- **Truth in noisy sources is not solved.** The memory finds and reasons over what was said; it does not yet weigh source
  reliability, count independent confirmations or track whether a claim was later confirmed. A fair test needs social
  posts from after the model's training cutoff with outcomes labelled later; the replay bench already supports it.
- **Prototype, not a service.** SQLite, NumPy and a local sandbox; no streaming ingestion, access control or always-current
  fast path. Answers take a median 12.6 seconds. [`docs/architecture.md`](docs/architecture.md) maps each part to
  production components.
- **Entity matching is basic** (normalised names only).
- **Weakest measured areas:** year-over-year "change" questions on weather (about 60-70%), counting across many
  conversations and temporal reasoning (about 83%), noisy headlines (about 80-88% after grading corrections).
- **Untested:** multi-party channels with interleaved threads; corpora beyond about 3M items.
- One model family answered everything (grok-4.3, replicated on grok-4.7 for a sample).

---

## Cost

The whole programme cost **$1,074.67** in API calls (140,139 calls): about $814 answering questions (including
rolling-summary compaction), $247 ingestion (fact extraction, digests, conflict checks, profiles), $11 dataset building
and $3 grading. Embeddings ran locally. The committed `results/cost_ledger.jsonl.gz` holds every call's tag, tokens and
cost.

---

## Licence

Code: MIT ([`LICENSE`](LICENSE)). Eval suites and results derived from public data keep their sources' terms; see
[`DATA_LICENSES.md`](DATA_LICENSES.md).
