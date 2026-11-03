"""Combined stream: every item from all six datasets in one memory, quizzed on a stratified sample of their questions.

This is the closest test to pouring every feed into one memory. Items and questions keep their
original ids and `dataset` field (the feed), so per-feed results can be compared with the single-dataset runs.

uv run python -m factbase.datasets.combined.build
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from ...paths import questions_path

ROOT = Path(__file__).resolve().parents[3]
FEEDS = ["markets", "football", "sec_filings", "fedreg", "world_quiz", "iran_headlines"]
BASES_PER_FEED = 25


def main() -> None:
    rng = random.Random(42)
    out = ROOT / "data" / "combined"
    out.mkdir(parents=True, exist_ok=True)
    items = []
    for f in FEEDS:
        items += [json.loads(l) for l in open(ROOT / "data" / f / "items.jsonl")]
    # stable sort on time only: ties keep each feed's original order, so per-feed extraction chunks match the
    # single-dataset runs exactly (same LLM cache keys)
    items.sort(key=lambda d: d["ts"])
    with open(out / "items.jsonl", "w") as fo:
        for d in items:
            fo.write(json.dumps(d) + "\n")

    questions = []
    counts = {}
    for f in FEEDS:
        qs = [json.loads(l) for l in open(questions_path(f))]
        by_base = defaultdict(list)
        for q in qs:
            by_base[q["base_id"]].append(q)
        # stratify base questions by the category of their first instance
        by_cat = defaultdict(list)
        for b, inst in sorted(by_base.items()):
            by_cat[min(inst, key=lambda q: q["ask_at"])["category"]].append(b)
        for c in by_cat.values():
            rng.shuffle(c)
        chosen = []
        while len(chosen) < BASES_PER_FEED and any(by_cat.values()):
            for c in sorted(by_cat):
                if by_cat[c] and len(chosen) < BASES_PER_FEED:
                    chosen.append(by_cat[c].pop())
        for b in chosen:
            questions += by_base[b]
        counts[f] = (len(chosen), sum(len(by_base[b]) for b in chosen))
    questions.sort(key=lambda q: (q["ask_at"], q["qid"]))
    with open(out / "questions.jsonl", "w") as fo:
        for q in questions:
            fo.write(json.dumps(q) + "\n")
    lines = [
        "# combined",
        "",
        "All items from the six datasets merged into one time-ordered stream, quizzed on a stratified sample of each",
        f"dataset's base questions ({BASES_PER_FEED} per feed, stratified by category, seed 42) with all their re-asks.",
        "Items and questions keep their original ids and `dataset` (feed) field.",
        "",
        f"Items: {len(items)}. Questions: {len(questions)}.",
        "",
        "| feed | base questions | instances |",
        "|---|---|---|",
    ] + [f"| {f} | {b} | {n} |" for f, (b, n) in counts.items()]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
