# Results: run `v5`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| factbase_v4 | 95% (259) | 97% (256) | – | 99% (242) | 100% (259) | 94% (265) | **97.0%** (1281) |
| agentic_sql_v4 | 94% (259) | 97% (256) | 78% (257) | 100% (242) | 100% (259) | 96% (265) | **94.3%** (1538) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v4 | 100% (21) | 95% (19) | 100% (20) | 90% (10) | 100% (6) | 93% (14) | 94% (126) | 95% (43) | **95.4%** (259) |
| agentic_sql_v4 | 100% (21) | 74% (19) | 100% (20) | 100% (10) | 100% (6) | 100% (14) | 94% (126) | 93% (43) | **94.2%** (259) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v4 | 95% (43) | 95% (38) | 100% (22) | 91% (35) | 94% (31) | **94.7%** (169) |
| agentic_sql_v4 | 93% (43) | 95% (38) | 100% (22) | 91% (35) | 94% (31) | **94.1%** (169) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v4 | 100% (23) | 89% (53) | 98% (40) | 100% (18) | 100% (16) | 100% (12) | 100% (72) | 100% (22) | **97.3%** (256) |
| factbase_v4 | 100% (23) | 92% (53) | 95% (40) | 94% (18) | 100% (16) | 92% (12) | 100% (72) | 100% (22) | **96.9%** (256) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v4 | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |
| agentic_sql_v4 | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_sql_v4 | 100% (26) | 100% (22) | 0% (2) | 33% (6) | 81% (16) | 75% (140) | 73% (45) | **78.2%** (257) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v4 | 72% (47) | 74% (43) | 63% (19) | 77% (43) | 82% (33) | **74.6%** (185) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v4 | 100% (21) | 100% (41) | 100% (13) | 100% (28) | 100% (29) | 100% (21) | 100% (67) | 100% (22) | **100.0%** (242) |
| factbase_v4 | 100% (21) | 100% (41) | 100% (13) | 100% (28) | 100% (29) | 86% (21) | 100% (67) | 100% (22) | **98.8%** (242) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v4 | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |
| agentic_sql_v4 | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v4 | 100% (22) | 100% (28) | 100% (35) | 100% (20) | 100% (18) | 100% (21) | 100% (86) | 100% (29) | **100.0%** (259) |
| agentic_sql_v4 | 100% (22) | 100% (28) | 100% (35) | 100% (20) | 100% (18) | 100% (21) | 100% (86) | 100% (29) | **100.0%** (259) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v4 | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |
| agentic_sql_v4 | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v4 | 100% (22) | 96% (167) | 95% (76) | **96.2%** (265) |
| factbase_v4 | 100% (22) | 93% (167) | 93% (76) | **94.0%** (265) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v4 | 95% (76) | 96% (70) | 97% (36) | 89% (9) | 98% (52) | **95.9%** (243) |
| factbase_v4 | 93% (76) | 94% (70) | 92% (36) | 100% (9) | 92% (52) | **93.4%** (243) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v4 | 0.0192 | 13.9 | 19028 |
| factbase_v4 | 0.0328 | 17.6 | 33011 |
