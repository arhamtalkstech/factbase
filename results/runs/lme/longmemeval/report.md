# LongMemEval-S results

Run `lme`. Official judge prompts, judge model grok-4.3 (the paper used gpt-4o).

| arch | knowledge-update | knowledge-update_abs | multi-session | multi-session_abs | single-session-assistant | single-session-preference | single-session-user | single-session-user_abs | temporal-reasoning | temporal-reasoning_abs | ALL | USD/q | latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 79.2% (72) | 100.0% (6) | 65.3% (121) | 91.7% (12) | 98.2% (56) | 16.7% (30) | 92.2% (64) | 100.0% (6) | 56.3% (126) | 100.0% (5) | 71.1% (498) | 0.0290 | 25.2 |
| raw_rag | 72.2% (72) | 100.0% (6) | 63.6% (121) | 91.7% (12) | 96.4% (56) | 30.0% (30) | 90.6% (64) | 100.0% (6) | 50.8% (126) | 100.0% (5) | 68.7% (498) | 0.0168 | 15.3 |
| agentic_raw | 72.2% (72) | 100.0% (6) | 60.3% (121) | 91.7% (12) | 98.2% (56) | 26.7% (30) | 93.8% (64) | 100.0% (6) | 50.8% (126) | 100.0% (5) | 68.3% (498) | 0.0156 | 9.2 |
