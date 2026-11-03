# Results: run `m47`

### Accuracy by architecture and dataset

| arch | fedreg | football | iran_headlines | world_quiz | all |
|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (60) | 100% (60) | 92% (60) | 98% (60) | **97.5%** (240) |
| agentic_raw | 93% (60) | 88% (60) | 90% (60) | 87% (60) | **89.6%** (240) |

### fedreg: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_raw | 100% (8) | 50% (8) | 100% (8) | 100% (8) | 100% (6) | 100% (8) | 100% (7) | 100% (7) | **93.3%** (60) |

### fedreg: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (1) | 100% (2) | 100% (2) | 100% (2) | **100.0%** (14) |

### football: accuracy by question category

| arch | abstain | aggregate | as_of_state | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (8) | 100% (8) | 100% (8) | 100% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **100.0%** (60) |
| agentic_raw | 100% (8) | 62% (8) | 88% (8) | 62% (8) | 100% (7) | 100% (7) | 100% (7) | 100% (7) | **88.3%** (60) |

### football: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |
| agentic_raw | 100% (7) | 100% (3) | 100% (1) | 100% (2) | 100% (1) | **100.0%** (14) |

### iran_headlines: accuracy by question category

| arch | abstain | aggregate | change | multi_hop | ordering | point_old | point_recent | all |
|---|---|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (11) | 100% (11) | 100% (2) | 50% (6) | 100% (10) | 80% (10) | 100% (10) | **91.7%** (60) |
| agentic_raw | 100% (11) | 100% (11) | 100% (2) | 33% (6) | 100% (10) | 80% (10) | 100% (10) | **90.0%** (60) |

### iran_headlines: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 4-8m | 8-14m | all |
|---|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (10) | 60% (5) | 100% (1) | 100% (2) | 100% (2) | **90.0%** (20) |
| agentic_raw | 100% (10) | 60% (5) | 100% (1) | 100% (2) | 100% (2) | **90.0%** (20) |

### world_quiz: accuracy by question category

| arch | abstain | point_old | point_recent | all |
|---|---|---|---|---|
| agentic_sql_v3 | 100% (20) | 95% (20) | 100% (20) | **98.3%** (60) |
| agentic_raw | 75% (20) | 90% (20) | 95% (20) | **86.7%** (60) |

### world_quiz: point-fact accuracy by fact age (retention)

| arch | 0-1m | 1-4m | 14m+ | 8-14m | all |
|---|---|---|---|---|---|
| agentic_sql_v3 | 100% (20) | 90% (10) | 100% (3) | 100% (7) | **97.5%** (40) |
| agentic_raw | 95% (20) | 80% (10) | 100% (3) | 100% (7) | **92.5%** (40) |

### Answer-time cost and latency (per question)

| arch | USD/q | mean latency s | input tokens/q |
|---|---|---|---|
| agentic_raw | 0.0000 | 0.2 | 15639 |
| agentic_sql_v3 | 0.0000 | 0.2 | 15568 |
