# Results: run `rep2`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 97% (60) | 100% (60) | 82% (60) | 100% (60) | 100% (60) | 97% (60) | **95.8%** (360) |
| factbase_v3 | 97% (60) | 95% (60) | 82% (60) | 100% (60) | 100% (60) | 100% (60) | **95.6%** (360) |
| agentic_raw | 85% (60) | 80% (60) | 88% (60) | 90% (60) | 98% (60) | 98% (60) | **90.0%** (360) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 75% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **96.7%** (60) |
| factbase_v3 | 100% (8) | 75% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **96.7%** (60) |
| agentic_raw | 100% (8) | 0% (8) | 100% (8) | 88% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **85.0%** (60) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |
| factbase_v3 | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| factbase_v3 | 100% (8) | 75% (8) | 100% (8) | 100% (8) | 100% (7) | 86% (7) | 100% (7) | 100% (7) | **95.0%** (60) |
| agentic_raw | 100% (8) | 62% (8) | 62% (8) | 38% (8) | 100% (7) | 86% (7) | 100% (7) | 100% (7) | **80.0%** (60) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |
| factbase_v3 | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_raw | 100% (11) | 100% (11) | 100% (2) | 50% (6) | 90% (10) | 70% (10) | 100% (10) | **88.3%** (60) |
| agentic_sql_v3 | 100% (11) | 100% (11) | 50% (2) | 50% (6) | 80% (10) | 70% (10) | 80% (10) | **81.7%** (60) |
| factbase_v3 | 100% (11) | 100% (11) | 100% (2) | 33% (6) | 100% (10) | 50% (10) | 80% (10) | **81.7%** (60) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_raw | 100% (10) | 40% (5) | 100% (1) | 100% (2) | 100% (2) | **85.0%** (20) |
| agentic_sql_v3 | 80% (10) | 40% (5) | 100% (1) | 100% (2) | 100% (2) | **75.0%** (20) |
| factbase_v3 | 80% (10) | 20% (5) | 100% (1) | 50% (2) | 100% (2) | **65.0%** (20) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| factbase_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_raw | 100% (8) | 88% (8) | 88% (8) | 100% (8) | 100% (7) | 43% (7) | 100% (7) | 100% (7) | **90.0%** (60) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |
| factbase_v3 | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| factbase_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_raw | 100% (8) | 88% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **98.3%** (60) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |
| factbase_v3 | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| factbase_v3 | 100% (20) | 100% (20) | 100% (20) | **100.0%** (60) |
| agentic_raw | 100% (20) | 95% (20) | 100% (20) | **98.3%** (60) |
| agentic_sql_v3 | 100% (20) | 100% (20) | 90% (20) | **96.7%** (60) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| factbase_v3 | 100% (20) | 100% (10) | 100% (3) | 100% (7) | **100.0%** (40) |
| agentic_raw | 100% (20) | 90% (10) | 100% (3) | 100% (7) | **97.5%** (40) |
| agentic_sql_v3 | 90% (20) | 100% (10) | 100% (3) | 100% (7) | **95.0%** (40) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_raw | 0.0108 | 13.8 | 10621 |
| agentic_sql_v3 | 0.0179 | 15.5 | 20401 |
| factbase_v3 | 0.0274 | 15.5 | 31152 |
