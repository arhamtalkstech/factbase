"""Replay one dataset through one memory architecture on a simulated clock and record answers.

uv run python -m factbase.eval.run --dataset markets --arch raw_rag --run pilot --until 2025-01-31
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import llm
from ..memories import registry
from ..paths import DATA_DIR, RUNS_DIR, questions_path
from ..types import Item, Question

ROOT = Path(__file__).resolve().parents[2]


def load(dataset: str, until: str | None = None, since_q: str | None = None) -> tuple[list[Item], list[Question]]:
    items = [Item.from_json(json.loads(l)) for l in open(DATA_DIR / dataset / "items.jsonl")]
    qs = [Question.from_json(json.loads(l)) for l in open(questions_path(dataset))]
    if until:
        cut = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) + timedelta(days=1)
        items = [i for i in items if i.ts < cut]
        qs = [q for q in qs if q.ask_at < cut]
    if since_q:
        lo = datetime.fromisoformat(since_q).replace(tzinfo=timezone.utc)
        qs = [q for q in qs if q.ask_at >= lo]
    items.sort(key=lambda i: i.ts)
    return items, qs


def sample_questions(qs: list[Question], n: int, seed: int = 0) -> list[Question]:
    """Stratified sample of n question instances (round-robin over categories, fixed seed)."""
    import random

    rng = random.Random(seed)
    by_cat: dict = defaultdict(list)
    for q in sorted(qs, key=lambda q: q.qid):
        by_cat[q.category].append(q)
    for v in by_cat.values():
        rng.shuffle(v)
    out: list[Question] = []
    while len(out) < n and any(by_cat.values()):
        for c in sorted(by_cat):
            if by_cat[c] and len(out) < n:
                out.append(by_cat[c].pop())
    return out


def run(dataset: str, arch: str, run_id: str, until: str | None = None, workers: int = 8, cfg: dict | None = None, sample: int = 0) -> Path:
    items, qs = load(dataset, until)
    if sample:
        qs = sample_questions(qs, sample)
    out_dir = RUNS_DIR / run_id / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{arch}.answers.jsonl"
    log = open(out_dir / f"{arch}.log", "a")

    def say(msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    mem = registry.build(arch, dataset, RUNS_DIR / run_id / dataset / f"{arch}.work", **(cfg or {}))
    spend0 = llm.spent_usd(force=True)
    t0 = time.time()
    say(f"start {dataset}/{arch}: {len(items)} items, {len(qs)} questions")
    mem.prepare(items)
    say(f"prepared in {time.time() - t0:.0f}s")

    by_day: dict = defaultdict(list)
    for it in items:
        by_day[it.ts.date()].append(it)
    q_by_day: dict = defaultdict(list)
    for q in qs:
        q_by_day[q.ask_at.date()].append(q)
    first = min(by_day) if by_day else min(q_by_day)
    last = max(max(by_day), max(q_by_day)) if q_by_day else max(by_day)

    n_done = 0
    with open(out, "w") as f:
        day = first
        while day <= last:
            now = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
            batch = by_day.get(day, [])
            if batch:
                mem.ingest(batch, now)
            mem.end_of_day(day, now)
            todo = q_by_day.get(day, [])
            if todo:
                def one(q: Question):
                    t = time.time()
                    try:
                        a = mem.answer(q, now)
                    except llm.BudgetExceeded:
                        raise
                    except Exception as e:
                        from ..types import Answer

                        a = Answer("", True, error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}")
                    return q, a, time.time() - t

                for res in llm.pmap(one, todo, workers=workers):
                    if isinstance(res, Exception):
                        raise res
                    q, a, dt = res
                    row = {"qid": q.qid, "arch": arch, "dataset": dataset, "run": run_id, "latency_s": round(dt, 2), **asdict(a)}
                    f.write(json.dumps(row) + "\n")
                n_done += len(todo)
                f.flush()
                say(f"{day} answered {len(todo)} (total {n_done}/{len(qs)}), spend so far {llm.spent_usd(force=True) - spend0:.2f} USD")
            day += timedelta(days=1)
    stats = {
        "dataset": dataset,
        "arch": arch,
        "run": run_id,
        "items": len(items),
        "questions": len(qs),
        "seconds": round(time.time() - t0, 1),
        "spend_usd_this_process": round(llm.spent_usd(force=True) - spend0, 4),
        "memory": mem.stats(),
        "cfg": cfg or {},
    }
    (out_dir / f"{arch}.stats.json").write_text(json.dumps(stats, indent=2))
    say(f"done {json.dumps(stats)}")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--arch", required=True, help="comma-separated")
    p.add_argument("--run", required=True)
    p.add_argument("--until", default=None, help="YYYY-MM-DD: only items/questions up to this day (pilot)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--cfg", default="{}", help="JSON config passed to the memory")
    p.add_argument("--sample", type=int, default=0, help="stratified sample of N question instances (seed 0)")
    a = p.parse_args()
    for arch in a.arch.split(","):
        run(a.dataset, arch, a.run, a.until, a.workers, json.loads(a.cfg), a.sample)


if __name__ == "__main__":
    main()
