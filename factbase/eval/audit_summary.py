"""Summarise the independent audit (results/audit/audit_<dataset>.jsonl) and estimate grader-corrected accuracy.

The audit re-derived the answer to 40 sampled base questions per dataset (oversampling questions where the top designs
disagree or all fail) and judged each design's answer on the merits. Every question a design got wrong (as graded) lies in
the "disagree" or "all_wrong" strata, so the audited share of graded-wrong answers that were actually right estimates the
grader's false-negative rate for that design; likewise for graded-correct answers and false positives.

corrected accuracy = graded_acc * (1 - FP rate among graded-correct) + (1 - graded_acc) * (FN rate among graded-wrong)

uv run python -m factbase.eval.audit_summary
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from ..paths import RESULTS_DIR, RUNS_DIR, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ["markets", "football", "sec_filings", "fedreg", "world_quiz", "iran_headlines"]
ARCHS = {"agentic_sql_v3": "v3", "factbase_v3": "v3", "agentic_raw": "v1"}


def main() -> None:
    L = ["# Independent audit of gold answers and grading", "",
         "240 sampled base questions (40 per dataset), each re-derived from the raw data by an auditing agent that made no LLM",
         "calls; 720 grader verdicts checked (three designs per question). The sample oversamples hard cases (designs disagree or",
         "all fail), so raw counts overstate error rates; the corrected-accuracy column re-weights by the actual graded results.", ""]
    L += ["## Gold answers", "", "| dataset | correct | ambiguous | wrong | unanswerable |", "|---|---|---|---|---|"]
    fp_fn = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # arch -> ds -> [gc_n, gc_fp, gw_n, gw_fn]
    for d in DATASETS:
        rows = list(read_jsonl(RESULTS_DIR / "audit" / f"audit_{d}.jsonl"))
        if not rows:
            continue
        c = Counter(r["gold_status"] for r in rows)
        L.append(f"| {d} | {c['correct']} | {c['ambiguous']} | {c['wrong']} | {c['unanswerable']} |")
        sample = {r["qid"]: r for r in read_jsonl(RESULTS_DIR / "audit" / f"sample_{d}.jsonl")}
        for r in rows:
            for a in ARCHS:
                graded = sample[r["qid"]]["answers"][a]["graded_correct"]
                truly = r["archs"][a]["truly_correct"]
                x = fp_fn[a][d]
                if graded:
                    x[0] += 1
                    x[1] += int(not truly)
                else:
                    x[2] += 1
                    x[3] += int(truly)
    L += ["", "## Grader errors and corrected accuracy", "",
          "FP = graded correct but actually wrong; FN = graded wrong but actually right (counts within the audited sample).", "",
          "| design | dataset | FP / audited correct | FN / audited wrong | graded accuracy | corrected estimate |", "|---|---|---|---|---|---|"]
    for a, run in ARCHS.items():
        tot_g, tot_c, tot_n = 0.0, 0.0, 0
        for d in DATASETS:
            x = fp_fn[a][d]
            rows = list(read_jsonl(RUNS_DIR / run / d / f"{a}.graded.jsonl"))
            if not rows or not (x[0] or x[2]):
                continue
            g = sum(r["correct"] for r in rows) / len(rows)
            fp = x[1] / x[0] if x[0] else 0.0
            fn = x[3] / x[2] if x[2] else 0.0
            corr = g * (1 - fp) + (1 - g) * fn
            tot_g += g
            tot_c += corr
            tot_n += 1
            L.append(f"| {a} | {d} | {x[1]}/{x[0]} | {x[3]}/{x[2]} | {100 * g:.1f}% | {100 * corr:.1f}% |")
        if tot_n:
            L.append(f"| **{a}** | mean of {tot_n} | | | **{100 * tot_g / tot_n:.1f}%** | **{100 * tot_c / tot_n:.1f}%** |")
    md = "\n".join(L) + "\n"
    (ROOT / "docs" / "audit.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
