# world_quiz

General world news stream (Wikipedia Current Events Portal) quizzed with human-written weekly
news quizzes (RealTimeQA: CNN 5 Things quiz, The Week quiz of the week).

Build: `uv run python -m factbase.datasets.world_quiz.build` (all downloads and LLM calls cached;
code in `factbase/datasets/world_quiz/build.py`).

## Sources and terms

- **Stream: Wikipedia Current Events Portal (WCEP).** Raw wikitext of
  `Portal:Current_events/<YYYY>_<Month>_<D>` via `index.php?action=raw`, every day 2024-11-01..2026-10-31
  (730/730 pages fetched, cached in `data/raw/world_quiz/wcep/`). Text is CC BY-SA 4.0 (Wikipedia).
- **Quiz: RealTimeQA** (`github.com/realtimeqa/realtimeqa_public`, `past/2024` files from 20241101,
  `past/2025`, `past/2026`, `*_qa.jsonl` only; `_nota`/`_gcs` ignored). 103 files, 1,820 rows; 1,810 with
  `question_date` inside the window. Questions are human-written by CNN, The Week and DelawareOnline;
  used here for research evaluation only.

## Items (`items.jsonl`): 13,066

- One item per **leaf** bullet of a day page. `text` = `[<section> | <parent topic bullets>] <event sentence>`,
  e.g. `[Armed conflicts and attacks | Russian invasion of Ukraine | United States and the Russian invasion of Ukraine] U.S. President Donald Trump pauses all U.S. military aid to Ukraine with immediate effect.`
- Wiki markup stripped (links -> display text, a few templates such as `convert`/`ill`/`ship` rendered,
  refs and source links dropped). Source outlet names and URLs are kept in `meta.outlets` / `meta.source_urls`.
- `ts` = that day at 20:00:00Z; id = `world_quiz:<date>:<NNN>` (bullet order within the day).
- `meta`: `date`, `section`, `topics` (parent bullets), `outlets`, `source_urls`.
- 2026 days are denser (~25 items/day from March 2026) than 2025 (~13-15/day).

## Questions (`questions.jsonl`): 84 base questions, 265 instances

| category | instances | gold_source |
|---|---|---|
| point_recent | 76 | human_quiz |
| point_old | 167 | human_quiz |
| abstain | 22 (8 bases, 8.3%) | llm_from_source |

ask_at range 2024-11-08..2026-10-31, all 24 months covered (2026-10 holds 74 instances because every base is
re-asked on 2026-10-31). Instances per base: 4 (36 bases), 3 (31), 2 (11), 1 (6).
Quiz bases by outlet: CNN 50, The Week 26.

### How the human quiz questions were made

1. **Open-ended gold**: gold = text of the correct choice (`answer` index into `choices`), plus aliases
   suggested by the rewrite LLM (surname, abbreviations). The original question, choices and quiz URL are in
   `meta`.
2. **Answerability filter** (grok-4.3, effort low): for each `question_date`, the LLM saw ONLY the WCEP items
   dated `question_date-9 .. question_date`, plus up to 10 questions with their gold, and returned
   `supported`, `open_ended_ok` and the supporting item ids. 206/1,810 were supported, open-ended-askable and had
   valid in-window evidence ids.
3. **Rewrite**: each kept question rewritten to be self-contained with a code-computed time anchor
   ("In the week ending <question_date>" when all evidence is within 6 days, else "In the period from
   <first evidence date> to <question_date>"), without the options or the answer.
4. **Verification** (LLM sees the evidence items only): answerable, self-contained, faithful to the
   original, not leaking the answer -> 187 passed (13 rejected, 6 refused at rewrite).
5. **Window check** (LLM sees all items of the 10-day window): gold must be the unique answer, question
   specific, gold crisp -> 185 passed.
6. **Manual curation**: 4 vague/explanation-style questions excluded (`CURATOR_EXCLUDE` in build.py).
7. **Selection**: 76 bases chosen round-robin across months (seeded), skipping any question whose evidence
   items overlap an already chosen one (removes duplicate CNN/The Week questions about the same event).
   Per-question audit trail: `data/raw/world_quiz/filter_log.jsonl`.

`fact_time` = latest evidence item date. Ask schedule: `question_date` (point_recent), then the month-end
3 and 12 months after `fact_time`, then 2026-10-31, keeping only dates inside the window and at least
60 days after the previous ask (point_old). The +6 month re-ask was dropped to keep the instance count
near the 180-260 target; point_old ages still range from ~3 to ~23 months.

### Abstain questions

8 false-premise questions, one per evenly spaced candidate day (12 candidates). For each day the LLM picked
one significant WCEP item (Politics / International relations / Armed conflicts / Business sections) and
wrote a wh-question presupposing a changed detail (wrong judge outcome, wrong country, wrong venue, wrong
election date, etc.). A second LLM pass saw ALL WCEP items from 10 days before to 10 days after that day and
had to confirm the premise is not supported, is contradicted, and is phrased as a presupposition question.
10 candidates passed; 1 was removed manually (`ABSTAIN_EXCLUDE`: Iran vs Iraq drone origin too subtle, since
Iran had attacked the same pipeline earlier) and 1 dropped at random to fill 8 slots. gold = short note of what
the record says; evidence_item_ids = the contradicting item(s). Each is asked at the month-end after the event
(or 3 days after if that is sooner), ~6 months later, and on 2026-10-31.

## Validation and spot check

`uv run python -m factbase.datasets.validate world_quiz` -> OK. A manual spot-check of 11 random instances
against their evidence items found all golds supported.

## LLM cost

$7.34 total under tag `dataset:world_quiz` (all runs, including one trial batch and the re-runs after prompt
changes, which were mostly cache hits). Most of the spend was the answerability filter over 1,810 questions.

## Known issues / fairness notes

- **Survivorship bias**: only questions whose answer WCEP covers survive (~10%). The quiz therefore skews to
  hard news (conflicts, elections, disasters, major business/sports results); lifestyle/culture questions
  mostly fail the filter.
- **Closed-book leakage**: many 2024-2025 questions are famous events (Syria regime fall, DeepSeek, Charlie
  Kirk shooting) that grok-4.3 may know from pretraining; compare against A0 `closed_book`.
- **Weekly granularity**: questions are anchored to a week, not a day; the evidence may be up to 9 days before
  `question_date`. Some questions keep the quiz's original framing ("which country is reeling from ...").
- **Alias coverage**: aliases are LLM-suggested and not exhaustive (e.g. the Charlie Kirk question accepts
  "Utah" but not "Orem"); the grader should accept equivalent answers. A few human golds are partial where WCEP
  names several (Hurricane Melissa: Jamaica is gold; Cuba and Haiti were also hit).
- One human quiz question has slightly garbled wording kept from the source ("25% tariffs on imports of most
  US goods" = US tariffs on Mexican and Canadian imports).
- 45 questions judged supported and open-ended were discarded because the judge returned evidence ids
  without the `world_quiz:` prefix, which the strict id check rejected. They were not recovered, to stay within
  the LLM budget. The pool after filtering (181) was already larger than the 76 slots, so this only shrinks the
  candidate pool. It does not bias the gold.
- Answerability and abstain checks are LLM judgments on the raw items (independent of any memory
  architecture), not human review, apart from the curator exclusions listed above.
