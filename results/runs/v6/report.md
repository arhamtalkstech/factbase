# Results: run `v6`

### Accuracy by architecture and dataset

| arch | iran_headlines | world_quiz | all |
|---|---|---|---|
| agentic_sql_v5 | 79% (257) | 94% (265) | **86.6%** (522) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_sql_v5 | 100% (26) | 100% (22) | 100% (2) | 67% (6) | 81% (16) | 73% (140) | 76% (45) | **79.0%** (257) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v5 | 77% (47) | 74% (43) | 63% (19) | 77% (43) | 70% (33) | **73.5%** (185) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v5 | 100% (22) | 94% (167) | 92% (76) | **94.0%** (265) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v5 | 92% (76) | 96% (70) | 92% (36) | 100% (9) | 92% (52) | **93.4%** (243) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v5 | 0.0097 | 12.5 | 9583 |
