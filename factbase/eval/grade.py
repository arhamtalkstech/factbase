"""Grade answers against gold, blind to architecture, then build report tables.

uv run python -m factbase.eval.grade --run pilot
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from .. import llm
from ..paths import RUNS_DIR, questions_path, read_jsonl
from ..types import Question, parse_ts

ROOT = Path(__file__).resolve().parents[2]

JUDGE_SYSTEM = """You grade a model's answer to a quiz question against the gold answer(s). Be strict and literal.

If ANSWER TYPE is "abstain": the question has a false premise or asks about something not in the record / in the future.
  CORRECT only if the model declined, said it does not know, said the record does not contain it, or said the premise is false
  or the event has not happened. INCORRECT if it gave a substantive answer that accepts the premise.
Otherwise:
  CORRECT only if the model's answer states the gold answer (or one of the listed aliases / an unambiguous equivalent, e.g.
  "Sept 18, 2025" = "2025-09-18", "Man Utd" = "Manchester United FC"). Numbers must match within the stated allowed
  absolute error after unit conversion (e.g. "$169,590 million" = "169.59 billion").
  Judge meaning, not strings: capitalisation, punctuation, word order, added aliases ("a.k.a."), legal citations, units or
  other extra detail do NOT make an answer wrong, as long as the gold information is clearly stated and nothing contradicts it.
  INCORRECT if it abstains, gives a different value, is vaguer than the gold (e.g. "a European country" for "France"),
  or hedges between several candidates. If the gold has several parts (e.g. a value AND a period), all parts must be right."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"reason": {"type": "string"}, "correct": {"type": "boolean"}},
    "required": ["reason", "correct"],
}

_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _nums(s: str) -> list[float]:
    out = []
    for m in _NUM.findall(s or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _allowed_error(gold: str, tol: float | None) -> float | None:
    """Max absolute error for a numeric gold: half a unit of the gold's last written decimal place, and never more
    than the dataset's relative tolerance. '169.59' allows 0.005; '16.4' allows 0.05; '2' allows 0.5 but tol may cap it."""
    m = _NUM.search(gold or "")
    if not m:
        return None
    g = m.group(0).replace(",", "")
    dec = len(g.split(".")[1]) if "." in g else 0
    half_unit = 0.5 * 10 ** (-dec)
    val = abs(float(g))
    if tol is not None and val > 0:
        return min(half_unit, tol * val) + 1e-9
    return half_unit + 1e-9


def grade_one(q: Question, ans: dict) -> tuple[bool, str]:
    abstained = bool(ans.get("abstain"))
    text = (ans.get("answer") or "").strip()
    if ans.get("error") and not text:
        return False, f"error: {str(ans['error'])[:120]}"
    if q.answer_type == "abstain":
        if abstained:
            return True, "abstained"
    else:
        if abstained:
            return False, "abstained on answerable question"
        multi_part = re.search(r"(?i)\band (for |in )?(which|what|when|whose|who)\b", q.question)
        if q.answer_type == "number" and not multi_part and not re.search(r"(?i)\b(about|approx|approximately|around|roughly|~)", text):
            got = _nums(text)
            near = False
            for g in q.gold:
                gv, err = _nums(g), _allowed_error(g, q.numeric_tolerance)
                if not gv or err is None:
                    continue
                if any(abs(x - gv[0]) <= err for x in got):
                    return True, "numeric match"
                near |= any(abs(x - gv[0]) <= 0.2 * abs(gv[0]) for x in got)
            if near and len(got) == 1:
                return False, "numeric mismatch (same magnitude, outside allowed error)"
    user = (
        f"QUESTION: {q.question}\nANSWER TYPE: {q.answer_type}\n"
        f"GOLD (any of): {json.dumps(q.gold)}\n"
        f"ALLOWED ABSOLUTE ERROR FOR NUMBERS: {_allowed_error(q.gold[0], q.numeric_tolerance) if q.answer_type == 'number' else 'n/a'} "
        f"(i.e. the answer must round to the gold at the gold's precision; 'about'/'approximately' values are incorrect)\n"
        f"MODEL ANSWER: {text!r} (model abstained: {abstained})"
    )
    r = llm.ask_json(JUDGE_SYSTEM, user, JUDGE_SCHEMA, tag="judge")
    return bool(r.get("correct")), str(r.get("reason", ""))[:300]


def load_questions(dataset: str) -> dict[str, Question]:
    return {
        q.qid: q
        for q in (Question.from_json(json.loads(l)) for l in open(questions_path(dataset)))
    }


def age_bucket(q: Question) -> str:
    try:
        ft = date.fromisoformat(q.fact_time[:10])
    except ValueError:
        return "n/a"
    days = (q.ask_at.date() - ft).days
    if days <= 31:
        return "0-1m"
    if days <= 120:
        return "1-4m"
    if days <= 240:
        return "4-8m"
    if days <= 420:
        return "8-14m"
    return "14m+"


def grade_run(run_id: str, workers: int = 16) -> list[dict]:
    rows: list[dict] = []
    run_dir = RUNS_DIR / run_id
    for ds_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        qs = load_questions(ds_dir.name)
        for f in sorted(ds_dir.glob("*.answers.jsonl")):
            answers = [json.loads(l) for l in open(f)]
            jobs = [(qs[a["qid"]], a) for a in answers if a["qid"] in qs]

            def g(job):
                q, a = job
                ok, why = grade_one(q, a)
                return {
                    "run": run_id,
                    "stream": ds_dir.name,
                    "dataset": q.dataset,
                    "arch": a["arch"],
                    "qid": q.qid,
                    "base_id": q.base_id,
                    "category": q.category,
                    "answer_type": q.answer_type,
                    "gold_source": q.gold_source,
                    "age": age_bucket(q),
                    "ask_at": q.ask_at.date().isoformat(),
                    "question": q.question,
                    "gold": q.gold,
                    "answer": a.get("answer"),
                    "abstain": a.get("abstain"),
                    "correct": ok,
                    "why": why,
                    "usd": a.get("usd", 0),
                    "llm_calls": a.get("llm_calls", 0),
                    "tokens_in": a.get("tokens_in", 0),
                    "latency_s": a.get("latency_s", 0),
                    "steps": len(a.get("trace") or []),
                    "error": a.get("error"),
                }

            graded = [r for r in llm.pmap(g, jobs, workers=workers) if isinstance(r, dict)]
            out = f.with_name(f.name.replace(".answers.jsonl", ".graded.jsonl"))
            with open(out, "w") as fo:
                for r in graded:
                    fo.write(json.dumps(r) + "\n")
            rows += graded
    return rows


def table(rows: list[dict], row_key: str, col_key: str, title: str) -> str:
    cells: dict = defaultdict(lambda: [0, 0])
    rk, ck = set(), set()
    for r in rows:
        c = cells[(r[row_key], r[col_key])]
        c[0] += int(r["correct"])
        c[1] += 1
        rk.add(r[row_key])
        ck.add(r[col_key])
    cols = sorted(ck)
    lines = [f"### {title}", "", "| " + row_key + " | " + " | ".join(cols) + " | all |", "|---" * (len(cols) + 2) + "|"]
    for k in sorted(rk, key=lambda k: -sum(cells[(k, c)][0] for c in cols) / max(1, sum(cells[(k, c)][1] for c in cols))):
        parts = []
        tot = [0, 0]
        for c in cols:
            ok, n = cells[(k, c)]
            tot[0] += ok
            tot[1] += n
            parts.append(f"{100 * ok / n:.0f}% ({n})" if n else "–")
        lines.append(f"| {k} | " + " | ".join(parts) + f" | **{100 * tot[0] / max(1, tot[1]):.1f}%** ({tot[1]}) |")
    return "\n".join(lines) + "\n"


def report(rows: list[dict], run_id: str) -> str:
    out = [f"# Results: run `{run_id}`", ""]
    out.append(table(rows, "arch", "dataset", "Accuracy by architecture and dataset"))
    for ds in sorted({r["dataset"] for r in rows}):
        sub = [r for r in rows if r["dataset"] == ds]
        out.append(table(sub, "arch", "category", f"{ds}: accuracy by question category"))
        old = [r for r in sub if r["category"] in ("point_recent", "point_old")]
        if old:
            out.append(table(old, "arch", "age", f"{ds}: point-fact accuracy by fact age (retention)"))
    cost: dict = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for r in rows:
        c = cost[r["arch"]]
        c[0] += r["usd"] or 0
        c[1] += 1
        c[2] += r["latency_s"] or 0
        c[3] += r["tokens_in"] or 0
    out.append("### Answer-time cost and latency (per question)\n\n| arch | USD/q | mean latency s | input tokens/q |\n|---|---|---|---|")
    for k, (usd, n, lat, tin) in sorted(cost.items()):
        out.append(f"| {k} | {usd / n:.4f} | {lat / n:.1f} | {tin / n:.0f} |")
    return "\n".join(out) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    rows = grade_run(a.run)
    md = report(rows, a.run)
    (RUNS_DIR / a.run / "report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
