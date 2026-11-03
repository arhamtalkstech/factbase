# Results

Every graded answer from every run the reports rely on. Pilots and superseded attempts are not included.

## Files

| Path | What it is |
|---|---|
| `runs/<run>/<dataset>/<architecture>.graded.jsonl.gz` | One row per question: qid, category, fact age bucket, the model's answer, abstained or not, correct or not, the grader's reason, cost (USD), input tokens, latency, number of agent steps |
| `runs/<run>/<dataset>/<architecture>.stats.json` | Run metadata: items, questions, wall time, memory statistics (facts, supersessions, digests, threads, ...) |
| `runs/<run>/<dataset>/<architecture>.answers.jsonl.gz` | Full answers with the agent's tool trace (tool, arguments, output size). Included for the final designs only: `v3/*/agentic_sql_v3` and `lme_v7test/longmemeval/factbase_v7u_extract_only` |
| `runs/<run>/report.md` | The per-run report written by `factbase.eval.grade` |
| `audit/sample_<dataset>.jsonl`, `audit/audit_<dataset>.jsonl` | The independent audit: 40 sampled questions per dataset, the answer re-derived from raw data, and each verdict checked |
| `judge_check.json` | Adversarial validation of the grader (correct, verbose-correct, vague and near-miss test answers) |
| `cost_ledger.jsonl.gz` | Every paid LLM call: time, tag, input / cached / output tokens, USD. No prompts, no keys |

`world_quiz` rows keep ids, categories, verdicts and costs but no question, gold or answer text: the quiz source declares
no licence (see `DATA_LICENSES.md`).

## Run map

| Run | Phase | What it compares |
|---|---|---|
| `v1` | 1. Pre-registered comparison | 12 architectures (closed book, recent window, rolling summary, raw RAG, search agent, fact memory, rollups, factbase v1 and 4 ablations) on 6 datasets |
| `v2` | 2. Iteration | factbase v2 (raw items as SQL rows + Python + schema card), the `agentic_sql` control, v2 without structured fields |
| `v3` | 2. Iteration | v3: analytic questions must compute before answering |
| `v4` | 2. Scale | All six feeds in one ~361k-item memory |
| `v5` | 2. Iteration | v4: two searches required before abstaining |
| `v6` | 2. Iteration (exploratory) | calibrated answer rules (agentic_sql_v5) on news datasets |
| `rep1`, `rep2` | 3. Trust | Repeat runs with the cache bypassed, 60 sampled questions per dataset |
| `m47` | 3. Trust | Second model (grok-4.7) on the same sample |
| `heldout` | 3. Trust | Two new datasets built blind (quakes, weather) |
| `feedcol`, `feedcard` | 3. Trust | Combined stream with a feed column, then with a per-feed schema card |
| `heldout_v6`, `v6facts` | 3. Trust | The v6 answer policy on held-out and on the 360-question sample |
| `lme`, `lme_v6dev`, `lme_v6test`, `lme_v6udev`, `lme_v6utest` | 3. Conversations | LongMemEval-S: first designs, the v6 policy, and v6 + speaker facts, on fixed dev and test splits |
| `lme_v7dev`, `lme_v7test` | 4. v7 layers | Leave-one-out on dev, the pre-registered test run, and test-split attribution |
| `lme_inter` | 4. v7 layers | Interleaved channel: same-day sessions mixed message by message |
| `v7feeds`, `v7heldout`, `v7news` | 4. v7 layers | v7 additions on feeds, held-out feeds and news storylines |

## Regenerating the reports from these files

No API key or downloads needed:

```bash
uv run python -m factbase.eval.analyze --runs v1,v2,v3,v4,v5,v6 --out docs/results.md
uv run python -m factbase.eval.audit_summary
uv run python -m factbase.eval.v7_report
```
