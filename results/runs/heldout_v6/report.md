# Results: run `heldout_v6`

### Accuracy by architecture and dataset

| arch | quakes | weather | all |
|---|---|---|---|
| agentic_sql_v6 | 99% (217) | 86% (215) | **92.6%** (432) |

### quakes: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (19) | 98% (58) | 100% (14) | 100% (15) | 96% (23) | 100% (26) | 100% (48) | 100% (14) | **99.1%** (217) |

### quakes: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (15) | 100% (14) | 100% (6) | 100% (15) | 100% (12) | **100.0%** (62) |

### weather: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (18) | 82% (56) | 78% (9) | 47% (19) | 84% (25) | 85% (27) | 100% (46) | 100% (15) | **86.0%** (215) |

### weather: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (15) | 100% (15) | 100% (7) | 100% (13) | 100% (11) | **100.0%** (61) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v6 | 0.0181 | 23.5 | 18128 |
