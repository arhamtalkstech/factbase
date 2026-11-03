# Results: run `v3`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 95% (259) | 97% (256) | 77% (257) | 100% (242) | 100% (259) | 96% (265) | **94.2%** (1538) |
| factbase_v3 | 96% (259) | 96% (256) | 80% (257) | 99% (242) | 100% (259) | 94% (265) | **94.2%** (1538) |
| closed_book | 8% (259) | 9% (256) | – | 9% (242) | 8% (259) | – | **8.7%** (1016) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (21) | 95% (19) | 95% (20) | 100% (10) | 100% (6) | 100% (14) | 94% (126) | 95% (43) | **95.8%** (259) |
| agentic_sql_v3 | 100% (21) | 84% (19) | 100% (20) | 100% (10) | 83% (6) | 100% (14) | 95% (126) | 95% (43) | **95.4%** (259) |
| closed_book | 100% (21) | 0% (19) | 0% (20) | 0% (10) | 0% (6) | 0% (14) | 1% (126) | 0% (43) | **8.5%** (259) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 95% (43) | 95% (38) | 100% (22) | 94% (35) | 94% (31) | **95.3%** (169) |
| factbase_v3 | 95% (43) | 95% (38) | 95% (22) | 91% (35) | 97% (31) | **94.7%** (169) |
| closed_book | 0% (43) | 0% (38) | 0% (22) | 0% (35) | 3% (31) | **0.6%** (169) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (23) | 94% (53) | 90% (40) | 94% (18) | 100% (16) | 100% (12) | 100% (72) | 100% (22) | **96.9%** (256) |
| factbase_v3 | 100% (23) | 94% (53) | 92% (40) | 89% (18) | 100% (16) | 92% (12) | 100% (72) | 100% (22) | **96.5%** (256) |
| closed_book | 100% (23) | 0% (53) | 0% (40) | 0% (18) | 0% (16) | 0% (12) | 0% (72) | 0% (22) | **9.0%** (256) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |
| factbase_v3 | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |
| closed_book | 0% (22) | 0% (20) | 0% (11) | 0% (23) | 0% (18) | **0.0%** (94) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| factbase_v3 | 100% (26) | 100% (22) | 100% (2) | 50% (6) | 100% (16) | 74% (140) | 73% (45) | **80.2%** (257) |
| agentic_sql_v3 | 100% (26) | 100% (22) | 0% (2) | 33% (6) | 81% (16) | 74% (140) | 71% (45) | **77.4%** (257) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v3 | 72% (47) | 74% (43) | 68% (19) | 77% (43) | 76% (33) | **74.1%** (185) |
| agentic_sql_v3 | 70% (47) | 74% (43) | 58% (19) | 77% (43) | 82% (33) | **73.5%** (185) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (21) | 98% (41) | 100% (13) | 100% (28) | 100% (29) | 100% (21) | 100% (67) | 100% (22) | **99.6%** (242) |
| factbase_v3 | 100% (21) | 100% (41) | 100% (13) | 100% (28) | 100% (29) | 90% (21) | 100% (67) | 100% (22) | **99.2%** (242) |
| closed_book | 100% (21) | 0% (41) | 0% (13) | 0% (28) | 0% (29) | 0% (21) | 0% (67) | 0% (22) | **8.7%** (242) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |
| factbase_v3 | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |
| closed_book | 0% (22) | 0% (21) | 0% (10) | 0% (21) | 0% (15) | **0.0%** (89) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (22) | 100% (28) | 100% (35) | 100% (20) | 100% (18) | 100% (21) | 100% (86) | 100% (29) | **100.0%** (259) |
| factbase_v3 | 100% (22) | 100% (28) | 100% (35) | 100% (20) | 100% (18) | 100% (21) | 100% (86) | 100% (29) | **100.0%** (259) |
| closed_book | 100% (22) | 0% (28) | 0% (35) | 0% (20) | 0% (18) | 0% (21) | 0% (86) | 0% (29) | **8.5%** (259) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |
| factbase_v3 | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |
| closed_book | 0% (29) | 0% (24) | 0% (15) | 0% (27) | 0% (20) | **0.0%** (115) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v3 | 100% (22) | 96% (167) | 95% (76) | **96.2%** (265) |
| factbase_v3 | 100% (22) | 93% (167) | 93% (76) | **94.0%** (265) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 95% (76) | 96% (70) | 97% (36) | 89% (9) | 98% (52) | **95.9%** (243) |
| factbase_v3 | 93% (76) | 94% (70) | 92% (36) | 100% (9) | 92% (52) | **93.4%** (243) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql_v3 | 0.0190 | 17.7 | 17900 |
| closed_book | 0.0012 | 0.0 | 389 |
| factbase_v3 | 0.0305 | 17.1 | 28729 |
