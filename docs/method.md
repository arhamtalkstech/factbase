# How the experiment works

## The replay

Each dataset is a stream of time-stamped items plus a quiz. For every architecture, the runner
(`factbase/eval/run.py`) replays the stream one simulated day at a time:

1. Ingest every item published that day (`Memory.ingest`).
2. Run the end-of-day hook (`Memory.end_of_day`), where consolidation happens: compaction for
   `rolling_summary`, releasing digests for periods that just closed, and so on.
3. If any questions are scheduled for that day, ask them as of 23:59:59 UTC (`Memory.answer`).

A memory never sees an item from after the question's `ask_at`. The same question is asked again
months later (shared `base_id`), which is how retention is measured.

### Precomputing item-local work

Fact extraction looks at one day's items, and a digest looks at one closed period. Neither uses
anything outside its own day or period, so the runner may compute them up front in parallel
(`Memory.prepare`) and reveal each result only when the simulated clock reaches it. The output is
identical to computing them in streaming order, and much faster. Anything that depends on earlier
state (supersession, compaction, entity history) runs in time order inside `ingest`/`end_of_day`.

## Models

- Every LLM call uses `grok-4.3`.
- Answer-time calls (single-shot answers and every agent step) use reasoning effort `low` for every
  architecture. A pilot at effort `none` produced misreads of correct context (for example picking the
  next day's VIX close), which would have measured the reader rather than the memory.
- Ingestion-time calls (fact extraction, digests, compaction) use effort `none`.
- Embeddings: local `BAAI/bge-small-en-v1.5` (384 dimensions) via fastembed, because xAI has no
  embeddings endpoint. Keyword search: SQLite FTS5 with BM25 and Porter stemming. Hybrid search fuses
  the two with reciprocal rank fusion.
- All LLM calls are cached by request hash in `data/cache/llm.sqlite`, so reruns are deterministic and
  free. Every paid call is logged with its cost in `data/cache/ledger.jsonl`; a numbers-only export of that ledger is
  committed as `results/cost_ledger.jsonl.gz`.

## Grading

`factbase/eval/grade.py` grades each answer without knowing which architecture produced it.

- Abstain questions: correct if the memory declined or said the premise is false or not in the record.
- Answerable questions: an abstention is wrong.
- Numbers: a deterministic check first. The answer must match the gold within half a unit of the
  gold's last written decimal place (and within the dataset's relative tolerance if that is tighter).
  "About" or "approximately" answers never pass this check. A number of the same magnitude that misses
  is marked wrong without consulting the judge.
- Everything else goes to an LLM judge with a strict rubric (`JUDGE_SYSTEM`).

### Judge validation

Before any results were read, `factbase/eval/judge_check.py` built test answers for random questions
and checked the grader's verdicts. The first round (75 questions, three datasets) found that "about 170
billion" passed for a gold of 169.59 because one dataset allowed 1% error; the numeric check was tightened.
A later round found the judge rejected correct answers that carried extra detail ("a.k.a." aliases, an EO
number); the rubric was changed to judge meaning, a fourth test type was added, and every run was regraded.

Final validation, 120 questions across all six datasets, four test answers each:

| Test answer | Graded as intended |
|---|---|
| Correct answer with extra detail (should pass) | 120/120 (100%) |
| Near miss: confident, specific, wrong (should fail) | 119/120 (99.2%) |
| Vague but on-topic (should fail) | 117/120 (97.5%) |
| Correct paraphrase (should pass) | 116/120 (96.7%) |

Most paraphrase "failures" were faulty test answers (the generator restated the question, or chose a
broader term such as "leafy greens" for "lettuce"). All reported results use this final grader.

## Leakage control

`closed_book` answers with no memory at all. Its score is what the model knows from pretraining
(or can guess), and it is reported next to every other result.
