# Results: run `v7feeds`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 92% (60) | 100% (60) | 87% (60) | 100% (60) | 100% (60) | 98% (60) | **96.1%** (360) |
| agentic_sql_v7f_no_budget | 92% (60) | – | 87% (60) | 100% (60) | 100% (60) | 98% (60) | **95.3%** (300) |
| agentic_sql_v7f_no_offload | 98% (60) | 98% (45) | 73% (60) | 100% (60) | 100% (60) | 98% (60) | **94.5%** (345) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f_no_offload | 100% (8) | 88% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **98.3%** (60) |
| agentic_sql_v7f | 100% (8) | 50% (8) | 100% (8) | 100% (8) | 83% (6) | 100% (8) | 100% (7) | 100% (7) | **91.7%** (60) |
| agentic_sql_v7f_no_budget | 100% (8) | 50% (8) | 100% (8) | 100% (8) | 83% (6) | 100% (8) | 100% (7) | 100% (7) | **91.7%** (60) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_sql_v7f_no_budget | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_sql_v7f_no_offload | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_sql_v7f_no_offload | 100% (7) | 100% (4) | 100% (6) | 88% (8) | 100% (3) | 100% (6) | 100% (5) | 100% (6) | **97.8%** (45) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |
| agentic_sql_v7f_no_offload | 100% (6) | 100% (2) | – | 100% (2) | 100% (1) | **100.0%** (11) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (11) | 91% (11) | 50% (2) | 33% (6) | 90% (10) | 100% (10) | 90% (10) | **86.7%** (60) |
| agentic_sql_v7f_no_budget | 100% (11) | 91% (11) | 50% (2) | 33% (6) | 90% (10) | 100% (10) | 90% (10) | **86.7%** (60) |
| agentic_sql_v7f_no_offload | 100% (11) | 100% (11) | 0% (2) | 33% (6) | 70% (10) | 60% (10) | 70% (10) | **73.3%** (60) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v7f | 90% (10) | 100% (5) | 100% (1) | 100% (2) | 100% (2) | **95.0%** (20) |
| agentic_sql_v7f_no_budget | 90% (10) | 100% (5) | 100% (1) | 100% (2) | 100% (2) | **95.0%** (20) |
| agentic_sql_v7f_no_offload | 70% (10) | 40% (5) | 100% (1) | 100% (2) | 50% (2) | **65.0%** (20) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_sql_v7f_no_budget | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_sql_v7f_no_offload | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |
| agentic_sql_v7f_no_budget | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |
| agentic_sql_v7f_no_offload | 100% (7) | 100% (1) | 100% (2) | 100% (1) | 100% (3) | **100.0%** (14) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_sql_v7f_no_budget | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_sql_v7f_no_offload | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_sql_v7f_no_budget | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_sql_v7f_no_offload | 100% (7) | 100% (3) | 100% (2) | 100% (2) | **100.0%** (14) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v7f | 100% (20) | 95% (20) | 100% (20) | **98.3%** (60) |
| agentic_sql_v7f_no_budget | 100% (20) | 95% (20) | 100% (20) | **98.3%** (60) |
| agentic_sql_v7f_no_offload | 100% (20) | 95% (20) | 100% (20) | **98.3%** (60) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v7f | 100% (20) | 90% (10) | 100% (3) | 100% (7) | **97.5%** (40) |
| agentic_sql_v7f_no_budget | 100% (20) | 90% (10) | 100% (3) | 100% (7) | **97.5%** (40) |
| agentic_sql_v7f_no_offload | 100% (20) | 90% (10) | 100% (3) | 100% (7) | **97.5%** (40) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v7f | 0.0246 | 16.0 | 23325 |
| agentic_sql_v7f_no_budget | 0.0234 | 0.2 | 22420 |
| agentic_sql_v7f_no_offload | 0.0247 | 21.1 | 24799 |
