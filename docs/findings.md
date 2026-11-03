# What we learned

> **Third phase (v7):** [`v7_results.md`](v7_results.md) tests seven layered additions. Only one improved accuracy:
> asking the extractor for a topic, memory type and priority per fact (LongMemEval-S test 82.3% to 87.2%, p = 0.008, at
> lower cost). Interleaving unrelated conversations into one channel barely hurts (89.1% to 89.1%). Threads, offload, the
> profile and conflict resolution gave no measurable gain; offload raised cost by breaking the prompt cache.
>
> **Second phase:** [`trust.md`](trust.md) re-tests these findings: repeat runs, an independent audit, two new held-out
> datasets, a second model, latency at scale, and the LongMemEval conversation benchmark. The main conclusions held. One
> changed: extracted facts *do* help on conversations (LongMemEval 78.7% to 82.3%, p = 0.04), though not on fact feeds.

Six real data streams, one to two years each, about 361,000 items in total. Twenty memory designs. About 1,500
quiz questions per design, asked at many points in simulated time and re-asked months later. All numbers are in
[`results.md`](results.md); the design that follows from them is in [`architecture.md`](architecture.md).

## 1. Auto-compaction is not a memory

A single rolling summary, rewritten whenever new data arrives, is the usual way agent tools keep a long session going. As a
long-term memory it scored **27.7%**, the worst of every design that had any memory at all. It knew recent facts
(56% for facts under a month old) and almost nothing older (4% for facts over 14 months old). Keeping the last
~30k tokens verbatim did slightly better (32.6%) for the same reason: perfect inside the window, zero outside it.

Every design that kept the raw items and searched them at question time had **flat retention**: about the same
accuracy for a fact from last week as for one from 18 months ago.

**So:** keep every item forever. Use compaction only to keep a working session within its context window.

## 2. Pre-processing memory into facts or summaries loses information

Single-shot search over the raw items scored 81.5%. The same search over LLM-extracted facts only
scored 67.8%, and over frozen day/week/month summaries 57.4%. Extraction and summarising drop details that later
questions need: pre-processing has a cost that raw retrieval does not pay.

**So:** derived layers can help, but they can never replace the raw items.

## 3. The bottleneck is computing over many records, not finding one

Every search-based design was near its ceiling on single facts. The errors were in questions that need *all* the
matching records: counts, highs and lows, "the first day X happened", "the latest value as of a date", league
tables, streaks. A search returns the best matches, never all of them, so the agent counted search results and
got 17 when the answer was 21.

The fix was to make every raw item a SQL row as well as a search document, and to give the agent a sandboxed
Python tool:

| design | mean accuracy |
|---|---|
| search agent over raw items (v1) | 89.1% |
| + every item as a SQL row, + Python, + schema card (v2) | 92.6% |
| + analytic questions must run SQL/Python before answering (v3) | **94.2%** |

Aggregation questions went from 72% to 96%, and as-of questions from 80% to 96%. All differences in this table are
significant (McNemar p < 0.01).

## 4. Keep structured fields when a feed has them

Prices, filings and match results arrive structured. Storing those fields as they arrive, rather than only as text,
was worth 6.4 points overall (97.2% against 90.8%, p < 1e-13) and 14 points on football, where answers come from
aggregating hundreds of small results.

## 5. The extra layers were not worth their cost on these quizzes

The pre-registered design ("factbase": raw items plus extracted temporal facts, frozen digests and an agent) did
**not** beat a plain search agent in v1 (87.9% against 89.1%). After the v2/v3 changes, the full design and the
lean one (raw rows + SQL + Python, no extracted facts, no digests) tied exactly: 94.2% each, 40 questions won by
each side, p = 1.0.

Building the facts and digests cost about $100 of the $630 total, and make every answer about 60% more expensive
($0.031 against $0.019 per question). On noisy news (Iran headlines) the full design was 2.8 points ahead (22 questions won against 15), which is
not significant (p = 0.32).

**So:** start lean. Add extracted facts or digests only for needs these quizzes did not test: browsable entity
histories, period overviews, and an analyst-reviewable layer.

## 6. One memory for everything works

Pouring all six feeds into one memory of about 361k items barely hurt the lean design: 97.2% against 97.5% when
each feed had its own memory (five valid feeds, 319 questions). Single-shot search lost about 3 points from the
extra noise.

## 7. On noisy news, the limit was reading, not finding

On 339k GDELT headlines about Iran, the best designs scored 77-81%. Retrieval held up at that scale: the known
evidence headline was in the top 50 search results for 86% of questions. Most misses happened after that. The
agents found the right headline but refused to answer because the question named a detail the headline did not
carry ("in Seiyun", "for hashish smuggling", "Marshall Islands-flagged").

Two follow-up rules did not fix it:

- Requiring two differently phrased searches before abstaining: no change (p = 1.0).
- Telling the agent to answer when the event matches and only flag unconfirmed details: fewer wrong abstentions
  (33 to 26), but no net gain (p = 0.67).

Part of this gap is the dataset: the Iran questions were written from Wikipedia's curated event summaries, which
carry more detail than headlines. Treat the Iran scores as a lower bound.

## 8. What the pre-registered hypotheses said, and what happened

| hypothesis | result |
|---|---|
| H1 auto-compaction degrades sharply with age | **confirmed** (56% under a month, 4% over 14 months) |
| H2 raw search beats extracted facts on point lookups | **confirmed** (81.5% against 67.8% overall; p < 1e-30) |
| H3 raw RAG and fact memory fail on aggregates and as-of | **confirmed** (61% and 40% on aggregates) |
| H4 a raw search agent closes much of the gap to factbase | **confirmed, more than expected**: it matched v1 factbase |
| H5 factbase beats every other design | **refuted**: it tied the lean design; removing raw evidence did hurt (p < 1e-15) |
| H6 retrieval designs have flat retention | **confirmed** |

## Caveats

- Questions are about things that happened. None test opinions, forecasts or "why" questions.
- One model family (`grok-4.3`) for everything, at reasoning effort `low` when answering.
- v2-v5 were designed after reading failures, so they risk fitting the questions. v2 was checked on two held-out
  datasets (world_quiz and iran_headlines) and held its gains there. v5 was designed on Iran failures and is exploratory.
- The judge was validated on 480 adversarial test answers (100% of correct answers with extra detail accepted, 97.5% of
  vague answers rejected, 99.2% of near misses rejected), but it is still strict on paraphrased news answers.
