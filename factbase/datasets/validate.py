"""Validate a built dataset against docs/datasets.md.

Usage: uv run python -m factbase.datasets.validate <name>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from ..paths import DATA_DIR, questions_path

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = {"point_recent", "point_old", "as_of_state", "change", "aggregate", "ordering", "abstain", "multi_hop"}
ANSWER_TYPES = {"text", "number", "date", "abstain"}
GOLD_SOURCES = {"human_quiz", "structured", "curated_wcep", "llm_from_source"}


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def validate(name: str) -> list[str]:
    errs: list[str] = []
    items_path = DATA_DIR / name / "items.jsonl"
    # without the locally built stream, check the eval suite on its own (schema, ids, dates)
    items = [json.loads(l) for l in open(items_path)] if items_path.exists() else []
    if not items:
        print(f"{name}: items.jsonl not built locally; checking the eval suite only")
    qs = [json.loads(l) for l in open(questions_path(name))]
    ids = set()
    last = None
    for i, it in enumerate(items):
        for k in ("id", "dataset", "ts", "title", "text", "source"):
            if not it.get(k) and k != "title":
                errs.append(f"item {i} missing {k}")
        if it["id"] in ids:
            errs.append(f"duplicate item id {it['id']}")
        ids.add(it["id"])
        t = parse_ts(it["ts"])
        if last and t < last:
            errs.append(f"items not sorted at {i}")
            break
        last = t
        if it["text"].lstrip().startswith("{"):
            errs.append(f"item {it['id']} text looks like JSON")
    first_ts = parse_ts(items[0]["ts"]) if items else None
    qids = set()
    for q in qs:
        for k in ("qid", "base_id", "dataset", "ask_at", "question", "gold", "answer_type", "category", "fact_time", "gold_source"):
            if k not in q:
                errs.append(f"q {q.get('qid')} missing {k}")
        if q["qid"] in qids:
            errs.append(f"duplicate qid {q['qid']}")
        qids.add(q["qid"])
        if not q["ask_at"].endswith("T23:59:59Z"):
            errs.append(f"q {q['qid']} ask_at not end of day")
        if q["category"] not in CATEGORIES:
            errs.append(f"q {q['qid']} bad category {q['category']}")
        if q["answer_type"] not in ANSWER_TYPES:
            errs.append(f"q {q['qid']} bad answer_type")
        if q["gold_source"] not in GOLD_SOURCES:
            errs.append(f"q {q['qid']} bad gold_source")
        if not isinstance(q["gold"], list) or not q["gold"]:
            errs.append(f"q {q['qid']} gold must be a non-empty list")
        ask = parse_ts(q["ask_at"])
        if first_ts and ask < first_ts:
            errs.append(f"q {q['qid']} asked before first item")
        for eid in q.get("evidence_item_ids") or []:
            if items and eid not in ids:
                errs.append(f"q {q['qid']} evidence {eid} not in items")
            else:
                pass
        if q["answer_type"] != "abstain":
            ev_ts = [parse_ts(it["ts"]) for it in items if it["id"] in set(q.get("evidence_item_ids") or [])]
            if ev_ts and max(ev_ts) > ask:
                errs.append(f"q {q['qid']} evidence published after ask_at")
    print(f"{name}: {len(items)} items, {len(qs)} questions, {len({q['base_id'] for q in qs})} base questions")
    print("  categories:", dict(Counter(q["category"] for q in qs)))
    print("  gold_source:", dict(Counter(q["gold_source"] for q in qs)))
    print("  ask months:", len({q["ask_at"][:7] for q in qs}))
    return errs


if __name__ == "__main__":
    errs = validate(sys.argv[1])
    for e in errs[:50]:
        print("ERROR", e)
    print("OK" if not errs else f"{len(errs)} errors")
    sys.exit(1 if errs else 0)
