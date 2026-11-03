# Pre-registration: what we expect before running anything

Written on 2026-11-02, before any architecture was run on any dataset. (Wording later edited to remove the names of
external systems the designs were compared to; the architectures, hypotheses and rules are unchanged.) The point of
this file is to stop the experiment from becoming a self-fulfilling prophecy: the
hypotheses and the comparison rules are fixed here, and the results file reports
against them, including the ones that turn out wrong.

## Question

Which memory architecture best lets a model answer questions about a long, continuous
stream of time-stamped information (news, market data, filings, results), at any later
point in time, over one to two years of simulated ingestion?

## Architectures under test

| ID | Name | One-line description |
|---|---|---|
| A0 | `closed_book` | No memory. Measures what the model already knows (leakage control). |
| A1 | `recent_window` | The most recent ~30k tokens of raw items in context. |
| A2 | `rolling_summary` | One bounded summary, rewritten every simulated day from yesterday's summary plus today's items. |
| A3 | `raw_rag` | Hybrid BM25 + dense retrieval over raw items, time-filtered, single shot. |
| A4 | `agentic_raw` | Tool-using search agent over raw items only (keyword, semantic, date listing, read). |
| A5 | `fact_memory` | Add-only atomic facts extracted by an LLM, hybrid retrieval over facts, single shot. |
| A7 | `rollups` | Frozen day → week → month summaries, retrieval over all levels, single shot. |
| A8 | `factbase` | Proposed design: evidence vault + temporal facts with supersession + frozen rollups + structured records + search agent over all of them. |

Ablations of A8: no agent (single shot), no raw evidence search, no mechanical
structured ingest (LLM extraction only).

## Hypotheses (directional, stated before results)

- **H1.** A2 `rolling_summary` (auto-compaction) degrades sharply with fact age and is
  the worst non-trivial memory on old point facts.
- **H2.** A3 `raw_rag` is a strong baseline on point lookups and beats A5 `fact_memory`
  on them (pre-processing loses information).
- **H3.** A3 `raw_rag` and A5 fail on aggregation and as-of-state questions (counts,
  standings, "latest value as of date"), where A8's structured records and SQL win
  by a large margin.
- **H4.** A4 `agentic_raw` closes much of the gap to A8 on point and change questions;
  A8's advantage over A4 is concentrated in aggregation, as-of state and knowledge
  updates.
- **H5.** A8 beats every other architecture overall, and removing raw evidence search
  from A8 lowers accuracy (raw evidence is a necessary layer).
- **H6.** Retention: A3, A4 and A8 show flat accuracy with fact age; A1 drops to near
  zero beyond its window; A2 declines steadily.

If A4 matches A8 overall, the conclusion is that the extra structure is not worth its
cost on these datasets, and the results file must say so.

## Fairness rules

1. Every architecture sees the same items in the same order and answers the same
   questions at the same simulated time, with no access to items after that time.
2. The same model (`grok-4.3`) and the same reasoning effort are used for every
   answer. Ingestion-time LLM calls use the same model.
3. Gold answers never come from any architecture's own memory. They come from human
   quizzes, structured source data, or an independent question writer that reads only
   the raw source, and are verified against the raw source.
4. Grading is blind to the architecture. The LLM judge is validated against
   deliberately vague wrong answers before use.
5. A0 `closed_book` is reported next to every result so knowledge the model already
   had from pretraining is visible.
6. All runs, costs and failures are logged. Nothing is dropped from results after the
   fact; any exclusion is listed with its reason.
