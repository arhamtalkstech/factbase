# LongMemEval-S results

Run `lme_inter`. Official judge prompts, judge model grok-4.3.

| arch | knowledge-update | knowledge-update_abs | multi-session | multi-session_abs | single-session-assistant | single-session-preference | single-session-user | temporal-reasoning | temporal-reasoning_abs | ALL | USD/q | latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factbase_v7u | 88.9% (18) | 100.0% (2) | 84.2% (19) | 100.0% (1) | 95.0% (20) | 80.0% (20) | 95.0% (20) | 89.5% (19) | 100.0% (1) | 89.2% (120) | 0.0204 | 19.4 |
| factbase_v7u_best | 88.9% (18) | 100.0% (2) | 78.9% (19) | 100.0% (1) | 95.0% (20) | 80.0% (20) | 95.0% (20) | 94.7% (19) | 100.0% (1) | 89.2% (120) | 0.0185 | 18.7 |
| agentic_sql_v6 | 88.9% (18) | 100.0% (2) | 84.2% (19) | 100.0% (1) | 100.0% (20) | 80.0% (20) | 100.0% (20) | 73.7% (19) | 100.0% (1) | 88.3% (120) | 0.0187 | 24.1 |
| factbase_v7u_no_threads | 88.9% (18) | 100.0% (2) | 78.9% (19) | 100.0% (1) | 90.0% (20) | 85.0% (20) | 95.0% (20) | 89.5% (19) | 100.0% (1) | 88.3% (120) | 0.0187 | 19.8 |
| factbase_v6u | 88.9% (18) | 100.0% (2) | 78.9% (19) | 100.0% (1) | 95.0% (20) | 75.0% (20) | 85.0% (20) | 78.9% (19) | 100.0% (1) | 84.2% (120) | 0.0199 | 18.4 |
