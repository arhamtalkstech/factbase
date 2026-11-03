# Results: run `rep1`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 95% (60) | 100% (60) | 87% (60) | 100% (60) | 100% (60) | 100% (60) | **96.9%** (360) |
| factbase_v3 | 97% (60) | 97% (60) | 83% (60) | 100% (60) | 100% (60) | 98% (60) | **95.8%** (360) |
| agentic_raw | 85% (60) | 82% (60) | 88% (60) | 93% (60) | 98% (60) | 97% (60) | **90.6%** (360) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (8) | 75% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **96.7%** (60) |
| agentic_sql_v3 | 100% (8) | 62% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **95.0%** (60) |
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
| factbase_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 71% (7) | 100% (7) | 100% (7) | **96.7%** (60) |
| agentic_raw | 100% (8) | 62% (8) | 50% (8) | 62% (8) | 100% (7) | 86% (7) | 100% (7) | 100% (7) | **81.7%** (60) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |
| factbase_v3 | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_raw | 100% (11) | 100% (11) | 100% (2) | 33% (6) | 100% (10) | 80% (10) | 90% (10) | **88.3%** (60) |
| agentic_sql_v3 | 100% (11) | 100% (11) | 100% (2) | 67% (6) | 90% (10) | 80% (10) | 70% (10) | **86.7%** (60) |
| factbase_v3 | 100% (11) | 100% (11) | 100% (2) | 67% (6) | 80% (10) | 50% (10) | 90% (10) | **83.3%** (60) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_raw | 90% (10) | 60% (5) | 100% (1) | 100% (2) | 100% (2) | **85.0%** (20) |
| agentic_sql_v3 | 70% (10) | 60% (5) | 100% (1) | 100% (2) | 100% (2) | **75.0%** (20) |
| factbase_v3 | 90% (10) | 20% (5) | 100% (1) | 50% (2) | 100% (2) | **70.0%** (20) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| factbase_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_raw | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 43% (7) | 100% (7) | 100% (7) | **93.3%** (60) |

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
| agentic_sql_v3 | 100% (20) | 100% (20) | 100% (20) | **100.0%** (60) |
| factbase_v3 | 100% (20) | 100% (20) | 95% (20) | **98.3%** (60) |
| agentic_raw | 100% (20) | 90% (20) | 100% (20) | **96.7%** (60) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (20) | 100% (10) | 100% (3) | 100% (7) | **100.0%** (40) |
| factbase_v3 | 95% (20) | 100% (10) | 100% (3) | 100% (7) | **97.5%** (40) |
| agentic_raw | 100% (20) | 80% (10) | 100% (3) | 100% (7) | **95.0%** (40) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_raw | 0.0119 | 14.3 | 10867 |
| agentic_sql_v3 | 0.0189 | 14.6 | 20590 |
| factbase_v3 | 0.0267 | 14.8 | 31841 |
