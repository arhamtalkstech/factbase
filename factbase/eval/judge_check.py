"""Adversarial check of the grader before trusting it.

For a sample of questions, build three answers per question and check the grader's verdicts:
- paraphrase of the gold (should be CORRECT)
- vague but on-topic answer (should be INCORRECT)
- near miss: a plausible wrong value (should be INCORRECT); for numbers, gold +/- 3%

uv run python -m factbase.eval.judge_check --datasets markets,football,sec_filings --n 25
"""

from __future__ import annotations

import argparse
import json
import random

from .. import llm
from ..types import Question
from ..paths import RESULTS_DIR, questions_path
from .grade import grade_one

VARIANT_SYSTEM = """You help test an automatic grader. Given a quiz question and its gold answer, write:
- paraphrase: the correct answer phrased differently (different wording/format, same information, still exact).
- vague: an answer that is on-topic and sounds plausible but is less specific than the gold, so it should be graded wrong.
- near_miss: a specific, confident answer that is wrong (e.g. a neighbouring date, a different team or company, a different number).
- verbose: the correct answer plus extra plausible detail (an alias, a citation, units, context), still clearly stating the gold."""
VARIANT_SCHEMA = {
    "type": "object",
    "properties": {"paraphrase": {"type": "string"}, "vague": {"type": "string"}, "near_miss": {"type": "string"}, "verbose": {"type": "string"}},
    "required": ["paraphrase", "vague", "near_miss", "verbose"],
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--datasets", required=True)
    p.add_argument("--n", type=int, default=25)
    a = p.parse_args()
    rng = random.Random(7)
    sample: list[Question] = []
    for ds in a.datasets.split(","):
        qs = [Question.from_json(json.loads(l)) for l in open(questions_path(ds))]
        qs = [q for q in qs if q.answer_type != "abstain"]
        sample += rng.sample(qs, min(a.n, len(qs)))

    def check(q: Question):
        v = llm.ask_json(VARIANT_SYSTEM, f"QUESTION: {q.question}\nGOLD: {q.gold}", VARIANT_SCHEMA, tag="judgecheck")
        out = []
        for kind, ans, want in (("paraphrase", v.get("paraphrase", ""), True), ("vague", v.get("vague", ""), False), ("near_miss", v.get("near_miss", ""), False), ("verbose", v.get("verbose", ""), True)):
            ok, why = grade_one(q, {"answer": ans, "abstain": False})
            out.append({"qid": q.qid, "kind": kind, "answer": ans, "want": want, "got": ok, "why": why, "gold": q.gold, "question": q.question})
        return out

    rows = [r for res in llm.pmap(check, sample, workers=12) if isinstance(res, list) for r in res]
    by = {}
    for r in rows:
        k = r["kind"]
        by.setdefault(k, [0, 0])
        by[k][0] += int(r["got"] == r["want"])
        by[k][1] += 1
    print("grader agreement with intended label:")
    for k, (ok, n) in by.items():
        print(f"  {k}: {ok}/{n} = {100 * ok / n:.1f}%")
    bad = [r for r in rows if r["got"] != r["want"]]
    print(f"\n{len(bad)} disagreements:")
    for r in bad:
        print(f"- [{r['kind']}] Q: {r['question'][:110]}\n  gold={r['gold'][:2]} answer={r['answer'][:110]!r}\n  grader: {r['got']} ({r['why'][:150]})")
    (RESULTS_DIR / "judge_check.json").write_text(json.dumps({"summary": by, "disagreements": bad}, indent=2))


if __name__ == "__main__":
    main()
