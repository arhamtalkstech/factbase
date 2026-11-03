# Results: run `v7news`

### Accuracy by architecture and dataset

| arch | world_quiz | all |
|---|---|---|
| factbase_v7f | 96% (265) | **95.8%** (265) |
| agentic_sql_v6 | 95% (265) | **94.7%** (265) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| factbase_v7f | 100% (22) | 95% (167) | 96% (76) | **95.8%** (265) |
| agentic_sql_v6 | 100% (22) | 94% (167) | 95% (76) | **94.7%** (265) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v7f | 96% (76) | 94% (70) | 92% (36) | 100% (9) | 98% (52) | **95.5%** (243) |
| agentic_sql_v6 | 95% (76) | 96% (70) | 94% (36) | 89% (9) | 92% (52) | **94.2%** (243) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v6 | 0.0099 | 13.3 | 10073 |
| factbase_v7f | 0.0162 | 15.6 | 14999 |
