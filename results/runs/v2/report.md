# Results: run `v2`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | markets | sec_filings | world_quiz | all |
|---|---|---|---|---|---|---|---|
| factbase_v2 | 95% (259) | 95% (256) | 81% (257) | 99% (242) | 100% (259) | 95% (265) | **94.1%** (1538) |
| agentic_sql | 94% (259) | 93% (256) | 77% (257) | 98% (242) | 100% (259) | 94% (265) | **92.5%** (1538) |
| factbase_v2_nostruct | 90% (259) | 80% (256) | – | 94% (242) | 99% (259) | – | **90.8%** (1016) |
| closed_book | – | – | – | – | – | 18% (265) | **17.7%** (265) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v2 | 100% (21) | 95% (19) | 95% (20) | 100% (10) | 100% (6) | 100% (14) | 94% (126) | 95% (43) | **95.4%** (259) |
| agentic_sql | 100% (21) | 68% (19) | 100% (20) | 100% (10) | 100% (6) | 100% (14) | 94% (126) | 93% (43) | **93.8%** (259) |
| factbase_v2_nostruct | 100% (21) | 5% (19) | 95% (20) | 100% (10) | 100% (6) | 100% (14) | 95% (126) | 98% (43) | **90.0%** (259) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v2_nostruct | 98% (43) | 95% (38) | 100% (22) | 91% (35) | 97% (31) | **95.9%** (169) |
| factbase_v2 | 95% (43) | 95% (38) | 95% (22) | 91% (35) | 94% (31) | **94.1%** (169) |
| agentic_sql | 93% (43) | 97% (38) | 100% (22) | 94% (35) | 87% (31) | **94.1%** (169) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v2 | 100% (23) | 92% (53) | 90% (40) | 83% (18) | 100% (16) | 83% (12) | 100% (72) | 100% (22) | **94.9%** (256) |
| agentic_sql | 100% (23) | 89% (53) | 88% (40) | 78% (18) | 100% (16) | 83% (12) | 100% (72) | 100% (22) | **93.4%** (256) |
| factbase_v2_nostruct | 100% (23) | 55% (53) | 68% (40) | 44% (18) | 100% (16) | 75% (12) | 100% (72) | 100% (22) | **80.5%** (256) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v2 | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |
| factbase_v2_nostruct | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |
| agentic_sql | 100% (22) | 100% (20) | 100% (11) | 100% (23) | 100% (18) | **100.0%** (94) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| factbase_v2 | 100% (26) | 100% (22) | 100% (2) | 67% (6) | 100% (16) | 74% (140) | 76% (45) | **80.9%** (257) |
| agentic_sql | 100% (26) | 100% (22) | 50% (2) | 50% (6) | 88% (16) | 70% (140) | 73% (45) | **76.7%** (257) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v2 | 74% (47) | 74% (43) | 68% (19) | 77% (43) | 76% (33) | **74.6%** (185) |
| agentic_sql | 72% (47) | 77% (43) | 53% (19) | 74% (43) | 67% (33) | **70.8%** (185) |

### markets: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v2 | 100% (21) | 100% (41) | 100% (13) | 100% (28) | 100% (29) | 90% (21) | 100% (67) | 100% (22) | **99.2%** (242) |
| agentic_sql | 100% (21) | 90% (41) | 100% (13) | 100% (28) | 100% (29) | 95% (21) | 100% (67) | 100% (22) | **97.9%** (242) |
| factbase_v2_nostruct | 100% (21) | 93% (41) | 92% (13) | 100% (28) | 97% (29) | 57% (21) | 100% (67) | 100% (22) | **94.2%** (242) |

### markets: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v2 | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |
| factbase_v2_nostruct | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |
| agentic_sql | 100% (22) | 100% (21) | 100% (10) | 100% (21) | 100% (15) | **100.0%** (89) |

### sec_filings: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| factbase_v2 | 100% (22) | 96% (28) | 100% (35) | 100% (20) | 100% (18) | 100% (21) | 100% (86) | 100% (29) | **99.6%** (259) |
| agentic_sql | 100% (22) | 96% (28) | 100% (35) | 100% (20) | 100% (18) | 100% (21) | 100% (86) | 100% (29) | **99.6%** (259) |
| factbase_v2_nostruct | 100% (22) | 93% (28) | 100% (35) | 100% (20) | 94% (18) | 100% (21) | 100% (86) | 100% (29) | **98.8%** (259) |

### sec_filings: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v2 | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |
| factbase_v2_nostruct | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |
| agentic_sql | 100% (29) | 100% (24) | 100% (15) | 100% (27) | 100% (20) | **100.0%** (115) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| factbase_v2 | 100% (22) | 97% (167) | 89% (76) | **95.1%** (265) |
| agentic_sql | 100% (22) | 95% (167) | 91% (76) | **94.0%** (265) |
| closed_book | 100% (22) | 13% (167) | 4% (76) | **17.7%** (265) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| factbase_v2 | 89% (76) | 97% (70) | 97% (36) | 100% (9) | 96% (52) | **94.7%** (243) |
| agentic_sql | 91% (76) | 96% (70) | 89% (36) | 89% (9) | 98% (52) | **93.4%** (243) |
| closed_book | 4% (76) | 11% (70) | 19% (36) | 0% (9) | 13% (52) | **10.3%** (243) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_sql | 0.0154 | 17.5 | 13436 |
| closed_book | 0.0012 | 0.0 | 379 |
| factbase_v2 | 0.0239 | 20.0 | 21337 |
| factbase_v2_nostruct | 0.0250 | 21.0 | 22083 |
