# Trust report: how far the results can be relied on

Second phase, run after [`results.md`](results.md) and [`findings.md`](findings.md). Each test below targets one way the
first-phase conclusions could have been wrong. Extra spend for this phase: about $262 (project total about $893).

## Summary

| Question a skeptic would ask | Test | Answer |
|---|---|---|
| Are the scores just noise? | 3 independent runs of the top 3 designs on 360 questions | No. Run-to-run SD about 1 point; ranking identical every run |
| Are the gold answers right? | Agent audit of 240 questions, re-derived from raw data | 0 wrong, 6 ambiguous (2.5%) |
| Is the grader fair? | Same audit, 720 grader verdicts | 0 false passes; 27 false fails, so scores are lower bounds |
| Did I fit the questions I studied? | 2 new datasets built by an agent that never saw the designs | No. Gap grew: 93.5% against 55.6% for the search agent |
| Is it one model's quirk? | Same designs answered by grok-4.7 | No. Same ranking, about 8-point gap on both models |
| Does it hold in one shared memory? | All six feeds in one ~361k-item memory | Yes, with a per-feed schema card (97.2%) |
| Does search slow down at scale? | Benchmark from 10k to 3M items | Negligible: 99% of answer time is the model |
| Does it work on conversations? | LongMemEval-S, dev/test split | 82.3% on the held-out test split after two generic fixes |
| Can it judge truth in noisy posts? | PHEME rumour tweets | Not testable: the model already knows the outcomes |

## 1. Run-to-run variance

The same 360 stratified questions (60 per dataset) were answered three times by each design, bypassing the cache.

| Design | Run 1 | Run 2 | Run 3 | Mean ± SD | Answers that changed |
|---|---|---|---|---|---|
| agentic_sql_v3 | 94.7% | 96.9% | 95.8% | 95.8 ± 1.1 | 20/360 (5.6%) |
| factbase_v3 | 94.4% | 95.8% | 95.6% | 95.3 ± 0.7 | 22/360 (6.1%) |
| agentic_raw | 89.7% | 90.6% | 90.0% | 90.1 ± 0.4 | 30/360 (8.3%) |

Single answers change in about 6% of cases, mostly on noisy news. Dataset-level scores move by 1-3 points and the
ranking never changes.

## 2. Independent audit of gold answers and grading

`docs/audit.md` has the detail. An auditing agent with no LLM calls re-derived 40 base questions per dataset from the raw
data (recomputing league tables, maxima, counts and filing values in code) and judged each of the three designs' answers.

- Gold answers: 234 correct, 6 ambiguous, 0 wrong, 0 unanswerable.
- Grader: 0 false passes in 720 verdicts. 27 false fails: 6 on fedreg, 6 on world_quiz, 15 on iran_headlines, all
  correct answers phrased differently from the gold ("British envoy" for "chargé d'affaires", "strikes" for "airstrikes").
- Corrected estimates: agentic_sql_v3 94.2% graded becomes about 96.6%; on iran_headlines about 77% becomes about 88%.
  These rest on small audited counts and are rough.

## 3. Held-out datasets nobody tuned on

An agent built two new datasets without reading the memory code, prompts or results, with deliberately new compound
question types: USGS earthquakes (16,259 events, 217 questions) and Open-Meteo daily weather for 12 cities (8,760 items,
215 questions). The frozen designs ran unchanged.

| Design | quakes | weather | mean |
|---|---|---|---|
| agentic_sql_v3 | 99.1% | 87.9% | **93.5%** |
| factbase_v3 | 95.4% | 86.0% | 90.7% |
| agentic_raw | 51.6% | 59.5% | 55.6% |
| raw_rag | 41.9% | 41.9% | 41.9% |
| rolling_summary | 11.1% | 14.0% | 12.5% |
| closed_book | 8.8% | 8.4% | 8.6% |

The gap between SQL-plus-compute and search is larger on fresh compute-heavy questions (38 points) than on the studied
datasets (5 points). Auto-compaction collapses again. The weakest area is weather "change" questions (year-over-year
differences of monthly averages): 58% for agentic_sql_v3.

## 4. A second model

The same 240 sampled questions (football, fedreg, world_quiz, iran_headlines) answered with grok-4.7 instead of grok-4.3.

| Design | grok-4.3 (mean of 3 runs) | grok-4.7 |
|---|---|---|
| agentic_sql_v3 | 93.8% | 97.5% |
| agentic_raw | 87.5% | 89.6% |

The first grok-4.7 pass exposed a harness bug: grok-4.7 often answers in plain text and never calls `final_answer`, so
up to 22 of 60 answers per dataset hit the step limit. A generic fallback (a second plain-text reply is taken as the
answer) fixed it; the table uses the fixed harness. The API reports $0 for grok-4.7 calls, so they are not in the spend.

## 5. One shared memory

All six feeds in one ~361k-item memory, 319 valid questions (iran_headlines excluded, see `results.md`).

| Configuration | Accuracy |
|---|---|
| agentic_sql_v3, no feed column | 97.2% |
| agentic_sql_v3, feed column | 93.1% |
| agentic_sql_v6, feed column | 96.2% |
| agentic_sql_v6 with per-feed schema card | **97.2%** |

A bare feed column hurt: with 94% of rows from one feed, the schema card's sample hid the small feeds' fields and the
agent guessed field names. A card with one section per feed, sampled from that feed, fixed it.

## 6. Latency and scale

[`bench_retrieval.md`](bench_retrieval.md) has the full table. Single-thread latency on a laptop with brute-force
vectors, in milliseconds:

| rows | vector search | BM25 top-100 (median / p95) | SQL count by date | SQL full-table LIKE |
|---|---|---|---|---|
| 339k | 5 | 17 / 77 | 0.6 | 35 |
| 1M | 16 | 55 / 229 | 2.1 | 107 |
| 3M | 44 | 164 / 706 | 6.3 | 313 |

Measured on 360 real answers: median latency 12.6 s, p90 26.5 s, about 3 model calls per answer. **99% of that time is
model time; search, SQL and Python together are 0.1%.** Retrieval scales linearly and stays under a second to about 3M
items. Beyond roughly 30M items, a proper engine (approximate vector search, OpenSearch or Vespa) keeps it in milliseconds.
Answer latency is set by the model and the number of agent steps, not by corpus size.

## 7. Conversations: LongMemEval-S

500 questions, each with its own history of about 50 chat sessions (~120k tokens, mostly unrelated filler), covering
recall, multi-session aggregation, knowledge updates, temporal reasoning, preferences and abstention. Graded with the
benchmark's official judge prompts, using grok-4.3 as judge. A fixed 20/80 dev/test split by hash
of the question id was made before any change. Both fixes were designed on the 85 dev questions only.

| Design | test split (413) |
|---|---|
| raw_rag | 69.5% |
| agentic_raw | 69.5% |
| agentic_sql_v3 (best design on fact feeds) | 70.9% |
| **v6 answer policy** (agentic_sql_v6) | 78.7% |
| **v6 + facts extracted from the user's own turns** (factbase_v6u) | **82.3%** |

| Question type | v3 | v6 | v6 + speaker facts |
|---|---|---|---|
| knowledge-update (61) | 77.0% | 86.9% | 91.8% |
| multi-session (103) | 64.1% | 70.9% | 72.8% |
| temporal-reasoning (100) | 53.0% | 61.0% | 73.0% |
| single-session-preference (20) | 25.0% | 75.0% | 80.0% |
| single-session-user (54) | 90.7% | 94.4% | 92.6% |
| single-session-assistant (48) | 97.9% | 100.0% | 95.8% |
| abstention (27) | 96.3% | 88.9% | 88.9% |

What changed and why:

- **v6 answer policy.** v3 failed mostly by abstaining: 48 of 55 wrong temporal answers, often without a single search.
  v6 answers advice questions using what it remembers, turns "two weeks ago" into dates, takes the latest of conflicting
  values, lists instances before counting, and must search twice before abstaining. On the six fact datasets it scored
  96.4% against 95.8% for v3 (360 questions), so it did not trade facts for conversations.
- **Speaker facts.** Extracting atomic facts from only the user's turns raised the test split from 78.7% to 82.3% (31
  questions won, 16 lost, p = 0.04). This reverses the first-phase finding for this data type: extracted facts add
  nothing on self-contained fact feeds, but they help on conversations, where a fact is buried in long chat turns. Cost:
  about $0.04 of extraction per 120k-token history plus $0.037 per answer.

For context, published LongMemEval-S scores (self-reported, different reader and judge models, not re-verified here) run
from about 61% for a strong model reading the full history, through about 71% for an early graph-memory system, to about
85-95% for the best systems reported in 2026. This system is in the upper-middle of that range. Weakest: counting across
sessions (73%) and temporal reasoning (73%).

Not covered: multi-party channels with interleaved threads (LongMemEval is one user and one assistant).

## 8. Truth in noisy social posts: not testable with public data

PHEME (CC BY 4.0) has about 6,400 rumour and non-rumour tweet threads from 2014-15 breaking news, with true/false labels.
The plan was to replay the tweets in time order and score the memory's calibration at each point. A probe of 12 claims
with no memory at all came back 9/12 correct: the model already knows how these famous events turned out, so the test
would measure pretraining knowledge, not the memory. It was not run.

A valid test needs social posts from after the model's training cutoff, with outcomes labelled later. For example, X posts
on 2026 events, labelled against what wires and official sources later confirmed or denied. The replay harness already
enforces point-in-time answers, so only the labelled dataset is missing.

## Recommended configuration after this phase

- **Fact and market feeds:** `agentic_sql_v6f`. Every item stored as a SQL row plus BM25 and vector entries; agent with
  search, SQL and a Python sandbox; per-feed schema card; analytic questions must compute; two searches before
  abstaining; the v6 answer policy.
- **Conversations:** the same, plus atomic facts extracted from each speaker's own turns (`factbase_v6u`).
- **Do not use as memory:** auto-compaction, a recent window, or single-shot top-k retrieval alone.

## What remains unproven

- Judging truth in noisy, possibly false social posts (section 8).
- Multi-party conversations with interleaved threads.
- Very large scale (above ~3M items) and live ingestion latency, beyond the projections above.
- Weather-style "change" questions (58-68%) and LongMemEval counting/temporal questions (about 73%) are the weakest
  measured areas.
