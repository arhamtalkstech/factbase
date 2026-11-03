# v7 results

Evaluation of the layered additions, as pre-registered in [`preregistration_v7.md`](preregistration_v7.md).
Layers and switches are described in [`layers.md`](layers.md). All answers by grok-4.3 at reasoning effort low.

## Summary

| Pre-registered hypothesis | Result |
|---|---|
| H7.1 v7u beats v6u on the interleaved channel, and removing threads hurts | v7u 89.2% against 84.2% (+8/-2, p = 0.11, not significant). Removing threads costs one question (88.3%). **Threads are not the reason.** Interleaving barely hurts any design: v6u 85.7% to 84.0%, v7u_best 89.1% to 89.1% on the same questions. |
| H7.2 the profile helps preference questions | Dev: 8/10 against 5/10 without it. Test: 15/20 with or without it. **Not confirmed**; the dev effect was small-sample noise. |
| H7.3 conflict resolution helps knowledge updates | Test: 55/61 with, 55/61 without. **Not confirmed.** |
| H7.4 offload cuts input tokens by 15%+ at most 1 point lost | Tokens +3%, cost +24%, prompt-cache share 38% to 30%. **Refuted**: agent loops are about 3 calls, too short to benefit, and rewriting history breaks caching. |
| H7.5 a search budget of 6 cuts cost and latency | The budget almost never bound. **No effect.** |
| H7.6 typed priority ranking is within 2 points | **Confirmed** (no measurable effect). |
| H7.7 v7u is at least as accurate as v6u on the test split | **Confirmed**: 86.4% against 82.3% (+32/-15, p = 0.019), and cheaper. |

What actually improved the system: asking the extractor for a topic, a memory type and a priority for every fact (extraction v2). With nothing else changed, LongMemEval-S test accuracy rose from 82.3% to 87.2% (p = 0.008) at lower cost per question. The other layers stay available as switches for auditability and human review, where accuracy was not the goal: the conflict log records every supersession decision, and the profile and thread views are readable Markdown with fact ids. On fact and market feeds no v7 layer helped; the v6 design stays the recommendation there.

## Conversations (LongMemEval-S)

### Dev split, leave-one-out (attribution only, small n)

| variant | all | knowledge-update | multi-session | temporal-reasoning | ss-preference | ss-user | ss-assistant | abstain | vs baseline | in tok/q | USD/q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factbase_v6u (baseline) | **89.4%** | 10/11 | 15/18 | 24/26 | 7/10 | 10/10 | 8/8 | 2/2 | – | 37633 | 0.0320 |
| factbase_v7u (all layers) | **87.1%** | 10/11 | 14/18 | 22/26 | 8/10 | 10/10 | 8/8 | 2/2 | +2 / -4 (p = 0.69) | 38971 | 0.0423 |
| v7u without threads | **92.9%** | 11/11 | 16/18 | 24/26 | 8/10 | 10/10 | 8/8 | 2/2 | +3 / -0 (p = 0.25) | 35403 | 0.0330 |
| v7u without offload | **90.6%** | 11/11 | 16/18 | 22/26 | 8/10 | 10/10 | 8/8 | 2/2 | +3 / -2 (p = 1) | 39125 | 0.0365 |
| v7u without profile | **84.7%** | 11/11 | 15/18 | 21/26 | 5/10 | 10/10 | 8/8 | 2/2 | +3 / -7 (p = 0.34) | 38540 | 0.0381 |
| v7u without conflicts | **87.1%** | 10/11 | 16/18 | 21/26 | 8/10 | 10/10 | 7/8 | 2/2 | +3 / -5 (p = 0.73) | 38055 | 0.0405 |
| v7u without typed | **87.1%** | 11/11 | 14/18 | 22/26 | 7/10 | 10/10 | 8/8 | 2/2 | +2 / -4 (p = 0.69) | 38427 | 0.0400 |
| v7u without budget | **87.1%** | 10/11 | 14/18 | 22/26 | 8/10 | 10/10 | 8/8 | 2/2 | +2 / -4 (p = 0.69) | 38834 | 0.0423 |

n = 85 questions.

### Test split (run once, configuration fixed on dev)

| variant | all | knowledge-update | multi-session | temporal-reasoning | ss-preference | ss-user | ss-assistant | abstain | vs baseline | in tok/q | USD/q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factbase_v6u (baseline) | **82.3%** | 56/61 | 75/103 | 73/100 | 16/20 | 50/54 | 46/48 | 24/27 | – | 37942 | 0.0371 |
| factbase_v7u_best (chosen on dev) | **86.4%** | 55/61 | 82/103 | 82/100 | 15/20 | 51/54 | 47/48 | 25/27 | +32 / -15 (p = 0.019) | 38596 | 0.0317 |

n = 413 questions.

### Test split attribution (run after the pre-registered test result; selection among these is post hoc)

The gain comes from the richer extraction itself (topic, memory type and priority requested for every fact). The profile, conflict resolution and priority ranking add no measurable accuracy on 413 questions; the extraction-only variant is the cheapest and is not significantly different from v7u_best.

| variant | all | knowledge-update | multi-session | temporal-reasoning | ss-preference | ss-user | ss-assistant | abstain | vs baseline | in tok/q | USD/q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factbase_v6u (baseline) | **82.3%** | 56/61 | 75/103 | 73/100 | 16/20 | 50/54 | 46/48 | 24/27 | – | 37942 | 0.0371 |
| factbase_v7u_best | **86.4%** | 55/61 | 82/103 | 82/100 | 15/20 | 51/54 | 47/48 | 25/27 | +32 / -15 (p = 0.019) | 38596 | 0.0317 |
| v7u_best without profile | **86.7%** | 57/61 | 86/103 | 81/100 | 15/20 | 50/54 | 47/48 | 22/27 | +35 / -17 (p = 0.018) | 37648 | 0.0252 |
| v7u_best without conflicts | **86.9%** | 55/61 | 84/103 | 82/100 | 15/20 | 52/54 | 47/48 | 24/27 | +33 / -14 (p = 0.0079) | 38536 | 0.0310 |
| extraction v2 only (no profile, conflicts, typed ranking) | **87.2%** | 56/61 | 85/103 | 83/100 | 16/20 | 50/54 | 46/48 | 24/27 | +36 / -16 (p = 0.0078) | 38176 | 0.0257 |

n = 413 questions.

### Interleaved channel (120 test questions, same-day sessions mixed message by message, no session labels)

| variant | all | knowledge-update | multi-session | temporal-reasoning | ss-preference | ss-user | ss-assistant | abstain | vs baseline | in tok/q | USD/q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factbase_v6u (baseline) | **84.2%** | 16/18 | 15/19 | 15/19 | 15/20 | 17/20 | 19/20 | 4/4 | – | 20015 | 0.0199 |
| agentic_sql_v6 (no facts) | **88.3%** | 16/18 | 16/19 | 14/19 | 16/20 | 20/20 | 20/20 | 4/4 | +11 / -6 (p = 0.33) | 17404 | 0.0187 |
| factbase_v7u (all layers) | **89.2%** | 16/18 | 16/19 | 17/19 | 16/20 | 19/20 | 19/20 | 4/4 | +8 / -2 (p = 0.11) | 22437 | 0.0204 |
| v7u without threads | **88.3%** | 16/18 | 15/19 | 17/19 | 17/20 | 19/20 | 18/20 | 4/4 | +11 / -6 (p = 0.33) | 21347 | 0.0187 |
| factbase_v7u_best | **89.2%** | 16/18 | 15/19 | 18/19 | 16/20 | 19/20 | 19/20 | 4/4 | +11 / -5 (p = 0.21) | 21469 | 0.0185 |

n = 120 questions.

## Feeds

### 360-question stratified sample of the six fact datasets

| variant | accuracy | vs baseline | input tokens/q | USD/q |
|---|---|---|---|---|
| agentic_sql_v6 (baseline) | 96.4% | – | 22627 | 0.0199 |
| agentic_sql_v7f (offload + budget) | 96.1% | +8 / -9 (p = 1) | 23325 | 0.0246 |
| v7f without offload | 94.5% | +3 / -10 (p = 0.092) | 24799 | 0.0247 |
| v7f without budget | 95.3% | +6 / -9 (p = 0.61) | 22420 | 0.0234 |

Share of input tokens served from the prompt cache: agentic_sql_v6 38%, agentic_sql_v7f 30%. Offload rewrites earlier messages, which breaks the cached prefix.

### Held-out feeds

| dataset | agentic_sql_v6 | agentic_sql_v7f |
|---|---|---|
| quakes | 99.1% | 99.1% |
| weather | 86.0% | 82.8% |

### News storylines (world_quiz, 265 questions)

| variant | accuracy | vs agentic_sql_v6 |
|---|---|---|
| agentic_sql_v6 | 94.7% | – |
| factbase_v7f (facts with threads, types, conflicts) | 95.8% | +10 / -7 (p = 0.63) |

