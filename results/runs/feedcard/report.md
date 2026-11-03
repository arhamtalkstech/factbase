# Results: run `feedcard`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| agentic_sql_v6f | 95% (60) | 95% (60) | 93% (59) | 100% (61) | 100% (63) | 96% (75) | **96.6%** (378) |
| agentic_sql_v6 | 92% (60) | 93% (60) | 93% (59) | 100% (61) | 98% (63) | 97% (75) | **95.8%** (378) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (5) | 70% (10) | 100% (6) | 100% (10) | 100% (6) | 100% (9) | 100% (11) | 100% (3) | **95.0%** (60) |
| agentic_sql_v6 | 100% (5) | 70% (10) | 83% (6) | 100% (10) | 100% (6) | 100% (9) | 100% (11) | 67% (3) | **91.7%** (60) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (3) | 100% (3) | 100% (2) | 100% (3) | 100% (3) | **100.0%** (14) |
| agentic_sql_v6 | 67% (3) | 100% (3) | 100% (2) | 100% (3) | 100% (3) | **92.9%** (14) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (11) | 89% (9) | 100% (8) | 75% (8) | 100% (6) | 100% (6) | 100% (9) | 100% (3) | **95.0%** (60) |
| agentic_sql_v6 | 100% (11) | 89% (9) | 75% (8) | 88% (8) | 100% (6) | 100% (6) | 100% (9) | 100% (3) | **93.3%** (60) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |
| agentic_sql_v6 | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (7) | 100% (10) | 100% (2) | 83% (6) | 80% (10) | 95% (20) | 100% (4) | **93.2%** (59) |
| agentic_sql_v6 | 100% (7) | 100% (10) | 100% (2) | 67% (6) | 80% (10) | 100% (20) | 100% (4) | **93.2%** (59) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 100% (6) | 100% (5) | 100% (2) | 100% (7) | 100% (4) | **100.0%** (24) |
| agentic_sql_v6f | 100% (6) | 80% (5) | 100% (2) | 100% (7) | 100% (4) | **95.8%** (24) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (5) | 100% (12) | 100% (4) | 100% (11) | 100% (10) | 100% (7) | 100% (9) | 100% (3) | **100.0%** (61) |
| agentic_sql_v6 | 100% (5) | 100% (12) | 100% (4) | 100% (11) | 100% (10) | 100% (7) | 100% (9) | 100% (3) | **100.0%** (61) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |
| agentic_sql_v6 | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (8) | 100% (10) | 100% (9) | 100% (8) | 100% (7) | 100% (9) | 100% (9) | 100% (3) | **100.0%** (63) |
| agentic_sql_v6 | 88% (8) | 100% (10) | 100% (9) | 100% (8) | 100% (7) | 100% (9) | 100% (9) | 100% (3) | **98.4%** (63) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6f | 100% (3) | 100% (3) | 100% (1) | 100% (3) | 100% (2) | **100.0%** (12) |
| agentic_sql_v6 | 100% (3) | 100% (3) | 100% (1) | 100% (3) | 100% (2) | **100.0%** (12) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v6 | 100% (22) | 97% (36) | 94% (17) | **97.3%** (75) |
| agentic_sql_v6f | 100% (22) | 97% (36) | 88% (17) | **96.0%** (75) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v6 | 94% (17) | 100% (15) | 100% (8) | 100% (1) | 92% (12) | **96.2%** (53) |
| agentic_sql_v6f | 88% (17) | 100% (15) | 100% (8) | 100% (1) | 92% (12) | **94.3%** (53) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v6 | 0.0243 | 21.5 | 26203 |
| agentic_sql_v6f | 0.0269 | 15.8 | 32827 |
