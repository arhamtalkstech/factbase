# LongMemEval-S results

Run `lme_v7test`. Official judge prompts, judge model grok-4.3.

| arch | knowledge-update | knowledge-update_abs | multi-session | multi-session_abs | single-session-assistant | single-session-preference | single-session-user | single-session-user_abs | temporal-reasoning | temporal-reasoning_abs | ALL | USD/q | latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factbase_v7u_extract_only | 91.8% (61) | 83.3% (6) | 82.5% (103) | 81.8% (11) | 95.8% (48) | 80.0% (20) | 92.6% (54) | 100.0% (5) | 83.0% (100) | 100.0% (5) | 87.2% (413) | 0.0257 | 24.2 |
| factbase_v7u_best_no_conflicts | 90.2% (61) | 83.3% (6) | 81.6% (103) | 81.8% (11) | 97.9% (48) | 75.0% (20) | 96.3% (54) | 100.0% (5) | 82.0% (100) | 100.0% (5) | 86.9% (413) | 0.0310 | 5.7 |
| factbase_v7u_best_no_profile | 93.4% (61) | 83.3% (6) | 83.5% (103) | 63.6% (11) | 97.9% (48) | 75.0% (20) | 92.6% (54) | 100.0% (5) | 81.0% (100) | 100.0% (5) | 86.7% (413) | 0.0252 | 24.1 |
| factbase_v7u_best | 90.2% (61) | 83.3% (6) | 79.6% (103) | 90.9% (11) | 97.9% (48) | 75.0% (20) | 94.4% (54) | 100.0% (5) | 82.0% (100) | 100.0% (5) | 86.4% (413) | 0.0317 | 19.5 |
