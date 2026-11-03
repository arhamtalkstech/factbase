# Results: run `feedcol`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| factbase_v3 | 93% (60) | 88% (60) | 100% (59) | 100% (61) | 100% (63) | 95% (75) | **96.0%** (378) |
| agentic_sql_v3 | 87% (60) | 82% (60) | 97% (59) | 98% (61) | 98% (63) | 99% (75) | **93.7%** (378) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (5) | 80% (10) | 83% (6) | 100% (10) | 100% (6) | 100% (9) | 91% (11) | 100% (3) | **93.3%** (60) |
| agentic_sql_v3 | 100% (5) | 70% (10) | 83% (6) | 90% (10) | 100% (6) | 100% (9) | 82% (11) | 67% (3) | **86.7%** (60) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v3 | 100% (3) | 67% (3) | 100% (2) | 100% (3) | 100% (3) | **92.9%** (14) |
| agentic_sql_v3 | 67% (3) | 100% (3) | 100% (2) | 67% (3) | 67% (3) | **78.6%** (14) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (11) | 100% (9) | 75% (8) | 75% (8) | 100% (6) | 50% (6) | 100% (9) | 100% (3) | **88.3%** (60) |
| agentic_sql_v3 | 100% (11) | 44% (9) | 62% (8) | 62% (8) | 100% (6) | 100% (6) | 100% (9) | 100% (3) | **81.7%** (60) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |
| factbase_v3 | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (7) | 100% (10) | 100% (2) | 100% (6) | 100% (10) | 100% (20) | 100% (4) | **100.0%** (59) |
| agentic_sql_v3 | 100% (7) | 100% (10) | 100% (2) | 83% (6) | 90% (10) | 100% (20) | 100% (4) | **96.6%** (59) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (6) | 100% (5) | 100% (2) | 100% (7) | 100% (4) | **100.0%** (24) |
| factbase_v3 | 100% (6) | 100% (5) | 100% (2) | 100% (7) | 100% (4) | **100.0%** (24) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (5) | 100% (12) | 100% (4) | 100% (11) | 100% (10) | 100% (7) | 100% (9) | 100% (3) | **100.0%** (61) |
| agentic_sql_v3 | 100% (5) | 92% (12) | 100% (4) | 100% (11) | 100% (10) | 100% (7) | 100% (9) | 100% (3) | **98.4%** (61) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |
| factbase_v3 | 100% (3) | 100% (3) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (12) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (8) | 100% (10) | 100% (9) | 100% (8) | 100% (7) | 100% (9) | 100% (9) | 100% (3) | **100.0%** (63) |
| agentic_sql_v3 | 100% (8) | 90% (10) | 100% (9) | 100% (8) | 100% (7) | 100% (9) | 100% (9) | 100% (3) | **98.4%** (63) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (3) | 100% (3) | 100% (1) | 100% (3) | 100% (2) | **100.0%** (12) |
| factbase_v3 | 100% (3) | 100% (3) | 100% (1) | 100% (3) | 100% (2) | **100.0%** (12) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v3 | 100% (22) | 100% (36) | 94% (17) | **98.7%** (75) |
| factbase_v3 | 100% (22) | 94% (36) | 88% (17) | **94.7%** (75) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 94% (17) | 100% (15) | 100% (8) | 100% (1) | 100% (12) | **98.1%** (53) |
| factbase_v3 | 88% (17) | 100% (15) | 100% (8) | 100% (1) | 83% (12) | **92.5%** (53) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v3 | 0.0196 | 15.7 | 21620 |
| factbase_v3 | 0.0403 | 26.9 | 38652 |
