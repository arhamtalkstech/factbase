# Recommended memory architecture

This is the design the experiments support. Every claim below points at a measured result in
[`results.md`](results.md). Where the evidence is thin or only from one dataset, it says so.

## Current recommendation (after the trust phase)

- **Fact and market feeds:** `agentic_sql_v6f`. Raw items as SQL rows plus BM25 and vector entries, search + SQL +
  sandboxed Python, a per-feed schema card, enforced compute for analytic questions, two searches before abstaining,
  and the v6 answer policy. 93.5% on two held-out datasets, 97.2% on the combined six-feed memory.
- **Conversations:** the same plus atomic facts extracted from each speaker's own turns, with every fact also given a
  topic, a memory type and a priority (`factbase_v7c`). 87.2% on the LongMemEval-S held-out test split, and it holds when
  unrelated conversations arrive interleaved in one channel. Optional switches add a standing profile, a non-destructive
  conflict log and thread views for human review ([`layers.md`](layers.md), [`v7_results.md`](v7_results.md)).

The evidence for both is in [`trust.md`](trust.md). The sections below describe the parts.

## The short version

**Keep everything, make it queryable three ways, and put a careful agent with a calculator in front of it.**

```
                 ┌──────────────────────────────────────────────────────────────┐
 feeds ────────► │  EVIDENCE VAULT (append-only, never edited)                   │
 (news, prices,  │   one SQL row per item: id, ts, date, source, title, text,    │
  filings, ...)  │   meta JSON (structured fields captured mechanically)         │
                 │   + BM25 keyword index  + vector index   (all time-filtered)  │
                 └──────────────────────────────────────────────────────────────┘
                                   ▲            ▲              ▲
                                   │            │              │
                 ┌─────────────────┴────────────┴──────────────┴───────────────┐
 question ─────► │  QUERY AGENT                                                 │
                 │   tools: search_records, list_records, sql (read-only),      │
                 │          python (sandboxed, stdlib + sql helper)             │
                 │   schema card in the prompt (tables, fields, example values) │
                 │   routing: single facts -> search + verify;                  │
                 │            counts / max / first / as-of / tables -> compute  │
                 │   analytic questions must run sql/python before answering    │
                 └──────────────────────────────────────────────────────────────┘
 optional ─────► extracted facts with supersession, frozen day/week/month digests
```

## What each part is for, and the evidence

### 1. Evidence vault: keep every item, verbatim, forever

Every architecture that kept raw items and searched them at question time held point-fact
accuracy flat with the age of the fact: `agentic_sql_v3` scored 91.6% on facts under a month old and
92.0% on facts over 14 months old. Auto-compaction fell from 56% to 4% over the same range, and a
30k-token recent window from 79% to 0%. Removing raw evidence from v1 factbase cost 7.4 points
(p < 1e-15). See the retention table in `results.md`.

Storage is cheap compared with LLM calls. The vault is also the only layer that stays correct when
models, prompts or schemas change: everything else can be rebuilt from it.

### 2. Make the vault queryable as SQL rows, not only as a search index

This was the single biggest improvement found in the experiments. In v1 the agent could only search,
and it failed whenever the answer needed every matching record (how many OFAC notices in a month, the
first day Brent closed above $90, a league table on a date). Search returns the top matches, never all
of them. In v2 every raw item is also a SQL row, and the agent can count, filter and sort exhaustively.
Aggregation accuracy went from 72% (search agent) to 96% (`agentic_sql_v3`); as-of questions from 80% to 96%.

Give every row a `feed` column. In the combined stream (all six feeds in one memory) the agent had to tell
feeds apart by `source` and field names. The lean design still held (97.2% against 97.5% per feed), but
the full design lost 2.6 points, mostly on structured feeds.

### 3. Capture structured fields mechanically when a feed has them

Prices, filings and match results arrive structured. Storing those fields as they arrive (the
`meta` JSON) let the agent compute standings, highs, lows and crossings exactly. Removing them
(`factbase_v2_nostruct`) cost 6.4 points overall (p < 1e-13) and 14 points on football, where answers
depend on aggregating many small records.

### 4. A query agent with search, SQL and a sandboxed calculator

Single-shot retrieval (top-k into one prompt) is fine for point facts but fails on aggregation,
ordering and as-of questions. The agent needs:

- hybrid search with date filters, for finding things;
- read-only SQL, for exhaustive filters and counts;
- a Python sandbox with an `sql()` helper, for anything multi-step (league tables, streaks, crossings);
- a schema card in its prompt, so it knows which fields exist without spending a step to look;
- a rule that analytic questions (counts, maxima, first/last, as-of, standings) must be computed,
  enforced by refusing the first `final_answer` until it has run `sql` or `python` once (v2 to v3:
  92.6% to 94.2%, p = 0.007).

Single-shot retrieval scored 81.5%; the search agent 89.1% (p < 1e-20); the agent with SQL rows,
Python and enforced compute 94.2% (p < 1e-10 against the search agent).

### 5. Optional layers: extracted facts and frozen digests

On these quizzes, the extracted-facts layer (temporal facts with supersession) and the digest
layer (day/week/month summaries) added nothing measurable over the raw vault plus compute:
`factbase_v3` and `agentic_sql_v3` both scored 94.2%, 40 questions won each (p = 1.0). They cost about
$100 to build across the six datasets and make each answer about 60% more expensive. They are worth adding
only for needs the quizzes did not test well:

- entity histories in unstructured news ("how did X's position change?");
- overviews of a period ("what happened in March 2026?");
- a browsable, human-reviewable layer for analysts.

### What not to use as memory

- **Auto-compaction (a rolling summary):** accuracy collapses on anything older than the last few
  compactions. Good for keeping one session running, not for retention.
- **A long recent window:** perfect inside the window, near zero outside it.
- **Single-shot top-k RAG alone:** good on point facts, poor on anything that needs all the matches.

## Open issue: when to abstain on news

On 339k Iran headlines the best designs scored 77-81%. Search found the evidence (top-50 recall 86%);
the misses were mostly abstentions when a question named a detail the headline did not carry. Two
rules tried to fix this (more searches before abstaining; answer when the event matches and flag the
unconfirmed detail) and neither gave a significant gain. The answer policy for partial matches is the
main thing to tune with the analysts who will use the system, on their own questions.

## Production mapping

The experiment ran on SQLite FTS5, local `bge-small` embeddings and NumPy. For production at the
production scale:

| Experiment | Production |
|---|---|
| SQLite rows + JSON meta | Postgres (partitioned by month) or a columnar store for numeric feeds |
| SQLite FTS5 (BM25) | OpenSearch / Elasticsearch, or Vespa for keyword + vector + filters in one engine |
| NumPy vectors | pgvector, Vespa, or a vector DB with a hard time filter |
| `sandbox-exec` Python | a container or Firecracker sandbox with read-only DB credentials |
| Time filter `ts <= now` | the same filter on every tool, enforced server-side |
