# Results: run `v7heldout`

### Accuracy by architecture and dataset

| arch | quakes | weather | all |
|---|---|---|---|
| agentic_sql_v7f | 99% (217) | 83% (215) | **91.0%** (432) |

### quakes: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 95% (19) | 100% (58) | 100% (14) | 100% (15) | 96% (23) | 100% (26) | 100% (48) | 100% (14) | **99.1%** (217) |

### quakes: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (15) | 100% (14) | 100% (6) | 100% (15) | 100% (12) | **100.0%** (62) |

### weather: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (18) | 70% (56) | 89% (9) | 53% (19) | 80% (25) | 81% (27) | 100% (46) | 100% (15) | **82.8%** (215) |

### weather: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (15) | 100% (15) | 100% (7) | 100% (13) | 100% (11) | **100.0%** (61) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v7f | 0.0180 | 21.4 | 17940 |
