# Independent audit of gold answers and grading

240 sampled base questions (40 per dataset), each re-derived from the raw data by an auditing agent that made no LLM
calls; 720 grader verdicts checked (three designs per question). The sample oversamples hard cases (designs disagree or
all fail), so raw counts overstate error rates; the corrected-accuracy column re-weights by the actual graded results.

## Gold answers

| dataset | correct | ambiguous | wrong | unanswerable |
|---|---|---|---|---|
| markets | 40 | 0 | 0 | 0 |
| football | 40 | 0 | 0 | 0 |
| sec_filings | 40 | 0 | 0 | 0 |
| fedreg | 39 | 1 | 0 | 0 |
| world_quiz | 38 | 2 | 0 | 0 |
| iran_headlines | 37 | 3 | 0 | 0 |

## Grader errors and corrected accuracy

FP = graded correct but actually wrong; FN = graded wrong but actually right (counts within the audited sample).

| design | dataset | FP / audited correct | FN / audited wrong | graded accuracy | corrected estimate |
|---|---|---|---|---|---|
| agentic_sql_v3 | markets | 0/39 | 0/1 | 99.6% | 99.6% |
| agentic_sql_v3 | football | 0/38 | 0/2 | 96.9% | 96.9% |
| agentic_sql_v3 | sec_filings | 0/40 | 0/0 | 100.0% | 100.0% |
| agentic_sql_v3 | fedreg | 0/37 | 2/3 | 95.4% | 98.5% |
| agentic_sql_v3 | world_quiz | 0/36 | 1/4 | 96.2% | 97.2% |
| agentic_sql_v3 | iran_headlines | 0/22 | 8/18 | 77.4% | 87.5% |
| **agentic_sql_v3** | mean of 6 | | | **94.2%** | **96.6%** |
| factbase_v3 | markets | 0/38 | 0/2 | 99.2% | 99.2% |
| factbase_v3 | football | 0/38 | 0/2 | 96.5% | 96.5% |
| factbase_v3 | sec_filings | 0/40 | 0/0 | 100.0% | 100.0% |
| factbase_v3 | fedreg | 0/38 | 2/2 | 95.8% | 100.0% |
| factbase_v3 | world_quiz | 0/35 | 2/5 | 94.0% | 96.4% |
| factbase_v3 | iran_headlines | 0/26 | 2/14 | 80.2% | 83.0% |
| **factbase_v3** | mean of 6 | | | **94.3%** | **95.8%** |
| agentic_raw | markets | 0/36 | 0/4 | 93.4% | 93.4% |
| agentic_raw | football | 0/26 | 0/14 | 75.0% | 75.0% |
| agentic_raw | sec_filings | 0/40 | 0/0 | 99.2% | 99.2% |
| agentic_raw | fedreg | 0/30 | 2/10 | 90.7% | 92.6% |
| agentic_raw | world_quiz | 0/35 | 3/5 | 95.5% | 98.2% |
| agentic_raw | iran_headlines | 0/27 | 5/13 | 80.9% | 88.3% |
| **agentic_raw** | mean of 6 | | | **89.1%** | **91.1%** |
