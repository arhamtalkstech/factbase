# Results: run `v6facts`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 95% (60) | 97% (60) | 87% (60) | 100% (60) | 100% (60) | 100% (60) | **96.4%** (360) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (8) | 62% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **95.0%** (60) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (8) | 100% (8) | 88% (8) | 88% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **96.7%** (60) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (11) | 100% (11) | 100% (2) | 50% (6) | 80% (10) | 80% (10) | 90% (10) | **86.7%** (60) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 90% (10) | 60% (5) | 100% (1) | 100% (2) | 100% (2) | **85.0%** (20) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v6 | 100% (20) | 100% (20) | 100% (20) | **100.0%** (60) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (20) | 100% (10) | 100% (3) | 100% (7) | **100.0%** (40) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v6 | 0.0199 | 15.0 | 22627 |
