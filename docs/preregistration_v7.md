# Pre-registration: v7 layered additions

Written on 2026-11-02 before any v7 run. v7 adds seven switchable layers to the v6 design (`factbase/memories/layered.py`):
topic threads, typed and prioritised facts, a standing profile, non-destructive conflict resolution, reversible offload
of the agent's working memory, a per-question search budget, and a drill-down tool (`read_records`) with Markdown views.

## Baselines

- Conversations: `factbase_v6u` (82.3% on the LongMemEval-S test split).
- Feeds: `agentic_sql_v6f` (agentic_sql_v6 plus the per-feed schema card).

## Evaluation tracks

| Track | Data | Comparison | Used for |
|---|---|---|---|
| C-dev | LongMemEval-S dev split (85 questions) | v7u and seven leave-one-out variants | Attribution only (small n) |
| C-test | LongMemEval-S test split (413 questions) | v7u against v6u | Main conversation result |
| C-interleaved | 120 test-split questions (20 per type), same-day sessions interleaved message by message into one unlabeled channel | v7u, v7u without threads, v6u, agentic_sql_v6 | Interleaved conversations |
| F-sample | 360-question stratified sample of the six fact datasets | agentic_sql_v7f and two ablations against agentic_sql_v6 | Cost, tokens, accuracy on feeds |
| F-heldout | quakes and weather (432 questions) | agentic_sql_v7f against agentic_sql_v6 | Held-out feeds |
| F-news | world_quiz (265 questions) | factbase_v7f (facts with storyline threads) against agentic_sql_v6f | Storylines on news |

## Hypotheses

- **H7.1** On the interleaved channel, v7u beats v6u, and removing threads lowers v7u's accuracy.
- **H7.2** The standing profile raises accuracy on preference questions.
- **H7.3** Non-destructive conflict resolution raises accuracy on knowledge-update questions.
- **H7.4** Offload cuts input tokens per question on feeds by at least 15%, losing at most 1 point of accuracy.
- **H7.5** A search budget of 6 cuts cost and latency, losing at most 1 point of accuracy.
- **H7.6** Typed priority ranking has little effect (within ±2 points).
- **H7.7** Overall, v7u is at least as accurate as v6u on the LongMemEval-S test split.

## Rules

Leave-one-out results on the 85-question dev split are reported as indicative only. The test-split and interleaved
results are run once, after the configuration is fixed. Every result is reported, including any layer that does not help.
