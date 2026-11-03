"""LongMemEval-S: long multi-session chat histories (about 50 sessions, ~120k tokens, mostly unrelated filler) per question.

Each question gets its own memory built from its own history: one item per round (a user turn plus the assistant reply),
time-stamped with the session date, ingested in time order, then the question is asked at the question's date with the
same answer rules as every other experiment. Grading uses the benchmark's official yes/no judge prompts (from its public
evaluation script), with grok-4.3 as the judge model.

uv run python -m factbase.eval.longmemeval --arch agentic_sql_v3 --run lme
uv run python -m factbase.eval.longmemeval --grade --run lme
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import llm
from ..memories import registry
from ..paths import DATA_DIR, RUNS_DIR, read_jsonl
from ..types import Item, Question

ROOT = Path(__file__).resolve().parents[2]
DATA = DATA_DIR / "raw" / "longmemeval" / "longmemeval_s_cleaned.json"
DATA_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json"


def _dt(s: str) -> datetime:
    # '2023/05/20 (Sat) 02:21'
    d, _, t = s.split(" ")
    return datetime.strptime(f"{d} {t}", "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)


def build_items(e: dict) -> list[Item]:
    items = []
    sessions = sorted(zip(e["haystack_dates"], e["haystack_session_ids"], e["haystack_sessions"]), key=lambda x: _dt(x[0]))
    for date_s, sid, turns in sessions:
        base = _dt(date_s)
        rnd, i = 0, 0
        while i < len(turns):
            user = turns[i]["content"] if turns[i]["role"] == "user" else ""
            asst = ""
            if turns[i]["role"] == "user" and i + 1 < len(turns) and turns[i + 1]["role"] == "assistant":
                asst = turns[i + 1]["content"]
                i += 2
            else:
                asst = turns[i]["content"] if turns[i]["role"] == "assistant" else ""
                i += 1
            text = (f"User: {user}\n" if user else "") + (f"Assistant: {asst}" if asst else "")
            items.append(
                Item(id=f"{sid}:r{rnd}", dataset="longmemeval", ts=base + timedelta(minutes=rnd), title="", text=text.strip(),
                     source=f"chat session {sid}", meta={})
            )
            rnd += 1
    return items


def build_items_interleaved(e: dict) -> list[Item]:
    """One shared channel: all sessions held on the same calendar day are interleaved message by message (random order,
    fixed seed per question), with no session labels. Each message keeps its true date; times within a day are reassigned
    one minute apart from the day's first session time."""
    import random

    rng = random.Random(e["question_id"])
    by_day: dict = defaultdict(list)
    for date_s, sid, turns in zip(e["haystack_dates"], e["haystack_session_ids"], e["haystack_sessions"]):
        by_day[_dt(date_s).date()].append((_dt(date_s), [t for t in turns if t.get("content")]))
    items, n = [], 0
    for day in sorted(by_day):
        sess = sorted(by_day[day], key=lambda x: x[0])
        base = sess[0][0]
        queues = [list(t) for _, t in sess]
        k = 0
        while any(queues):
            q = rng.choice([i for i, qu in enumerate(queues) if qu])
            t = queues[q].pop(0)
            role = "User" if t["role"] == "user" else "Assistant"
            items.append(Item(id=f"msg{n}", dataset="longmemeval", ts=base + timedelta(minutes=k), title="",
                              text=f"{role}: {t['content']}", source="chat channel", meta={}))
            n += 1
            k += 1
    return items


def to_question(e: dict) -> Question:
    abst = "_abs" in e["question_id"]
    return Question(
        qid=e["question_id"], base_id=e["question_id"], dataset="longmemeval", ask_at=_dt(e["question_date"]),
        question=e["question"], gold=[str(e["answer"])], answer_type="abstain" if abst else "text",
        category=e["question_type"] + ("_abs" if abst else ""), fact_time="", gold_source="human_quiz",
    )


def answer_one(e: dict, arch: str, work: Path, interleave: bool = False) -> dict:
    items = build_items_interleaved(e) if interleave else build_items(e)
    q = to_question(e)
    wd = work / e["question_id"]
    mem = registry.build(arch, "longmemeval", wd)
    t0 = time.time()
    mem.prepare(items)
    by_day: dict = defaultdict(list)
    for it in items:
        by_day[it.ts.date()].append(it)
    for day in sorted(by_day):
        now = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        mem.ingest(by_day[day], min(now, q.ask_at))
        mem.end_of_day(day, min(now, q.ask_at))
    t_ingest = time.time() - t0
    t1 = time.time()
    try:
        a = mem.answer(q, q.ask_at)
        err = a.error
    except llm.BudgetExceeded:
        raise
    except Exception as ex:  # keep going; recorded as an error
        from ..types import Answer

        a, err = Answer("", True), f"{type(ex).__name__}: {ex}"
    shutil.rmtree(wd, ignore_errors=True)
    return {"qid": q.qid, "arch": arch, "question_type": e["question_type"], "abst": "_abs" in q.qid, "items": len(items),
            "ingest_s": round(t_ingest, 1), "latency_s": round(time.time() - t1, 2), **{**asdict(a), "error": err}}


def split_of(qid: str) -> str:
    """Fixed dev/test split: 20% dev by hash of the question id (stable, independent of any result)."""
    import hashlib

    return "dev" if int(hashlib.sha1(qid.encode()).hexdigest(), 16) % 5 == 0 else "test"


def subset(data: list[dict], n: int) -> list[dict]:
    """Stratified (by question type) fixed subset of n questions, chosen by hash order (independent of any result)."""
    import hashlib

    by: dict = defaultdict(list)
    for e in sorted(data, key=lambda e: hashlib.sha1(("subset:" + e["question_id"]).encode()).hexdigest()):
        by[e["question_type"]].append(e)
    out, i = [], 0
    while len(out) < n and any(by.values()):
        for t in sorted(by):
            if by[t] and len(out) < n:
                out.append(by[t].pop(0))
    return out


def run(arch: str, run_id: str, limit: int = 0, workers: int = 6, split: str = "", interleave: bool = False, n_subset: int = 0) -> Path:
    data = json.load(open(DATA))
    if split:
        data = [e for e in data if split_of(e["question_id"]) == split]
    if n_subset:
        data = subset(data, n_subset)
    if limit:
        data = data[:limit]
    out_dir = RUNS_DIR / run_id / "longmemeval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{arch}.answers.jsonl"
    done = {json.loads(l)["qid"] for l in open(out)} if out.exists() else set()
    todo = [e for e in data if e["question_id"] not in done]
    print(f"{arch}: {len(todo)} to do ({len(done)} done)", flush=True)
    work = out_dir / f"{arch}.work"
    n = 0
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with open(out, "a") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(answer_one, e, arch, work, interleave) for e in todo]
        for fu in as_completed(futs):
            try:
                res = fu.result()
            except llm.BudgetExceeded:
                raise
            except Exception as err:
                print("error", err, flush=True)
                continue
            f.write(json.dumps(res) + "\n")
            f.flush()
            n += 1
            if n % 25 == 0:
                print(f"{arch}: {n}/{len(todo)} spend {llm.spent_usd(force=True):.2f}", flush=True)
    return out


def anscheck_prompt(task: str, question: str, answer: str, response: str, abstention: bool) -> str:
    """Verbatim from LongMemEval src/evaluation/evaluate_qa.py (get_anscheck_prompt)."""
    if not abstention:
        if task in ["single-session-user", "single-session-assistant", "multi-session"]:
            t = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
        elif task == "temporal-reasoning":
            t = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
        elif task == "knowledge-update":
            t = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
        elif task == "single-session-preference":
            t = "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
        else:
            raise NotImplementedError(task)
    else:
        t = "I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the model correctly identifies the question as unanswerable. The model could say that the information is incomplete, or some other information is given but the asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\nModel Response: {}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only."
    return t.format(question, answer, response)


def grade(run_id: str, split: str = "") -> str:
    data = {e["question_id"]: e for e in json.load(open(DATA))}
    out_dir = RUNS_DIR / run_id / "longmemeval"
    lines = ["# LongMemEval-S results", "", f"Run `{run_id}`. Official judge prompts, judge model grok-4.3.", ""]
    table = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    cost = {}
    for f in sorted(out_dir.glob("*.answers.jsonl")):
        rows = [json.loads(l) for l in open(f)]
        if split:
            rows = [r for r in rows if split_of(r["qid"]) == split]

        def g(r):
            e = data[r["qid"]]
            resp = r["answer"] if not r["abstain"] else f"I don't know / not in memory. {r['answer']}"
            p = anscheck_prompt(e["question_type"], e["question"], str(e["answer"]), resp, "_abs" in r["qid"])
            out = llm.chat([{"role": "user", "content": p}], tag="judge:lme")
            ok = "yes" in (out["content"] or "").strip().lower()[:5]
            return {**r, "correct": ok}

        graded = [x for x in llm.pmap(g, rows, workers=16) if isinstance(x, dict)]
        with open(f.with_name(f.name.replace(".answers.", ".graded.")), "w") as fo:
            for x in graded:
                fo.write(json.dumps(x) + "\n")
        arch = f.name.split(".")[0]
        for x in graded:
            cat = x["question_type"] + ("_abs" if x["abst"] else "")
            table[arch][cat][0] += int(x["correct"])
            table[arch][cat][1] += 1
            table[arch]["ALL"][0] += int(x["correct"])
            table[arch]["ALL"][1] += 1
        cost[arch] = (sum(x["usd"] for x in graded) / len(graded), sum(x["latency_s"] for x in graded) / len(graded))
    cats = sorted({c for a in table.values() for c in a if c != "ALL"}) + ["ALL"]
    lines += ["| arch | " + " | ".join(cats) + " | USD/q | latency s |", "|---" * (len(cats) + 3) + "|"]
    for arch, t in sorted(table.items(), key=lambda kv: -kv[1]["ALL"][0] / max(1, kv[1]["ALL"][1])):
        lines.append(f"| {arch} | " + " | ".join(f"{100 * t[c][0] / t[c][1]:.1f}% ({t[c][1]})" if t[c][1] else "–" for c in cats)
                     + f" | {cost[arch][0]:.4f} | {cost[arch][1]:.1f} |")
    md = "\n".join(lines) + "\n"
    (out_dir / "report.md").write_text(md)
    return md


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--arch", default="")
    p.add_argument("--run", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--grade", action="store_true")
    p.add_argument("--split", default="", help="dev | test (fixed 20/80 split by question-id hash)")
    p.add_argument("--interleave", action="store_true", help="interleave same-day sessions into one unlabeled channel")
    p.add_argument("--subset", type=int, default=0, help="stratified fixed subset of N questions")
    a = p.parse_args()
    if a.grade:
        print(grade(a.run, a.split))
        return
    for arch in a.arch.split(","):
        run(arch, a.run, a.limit, a.workers, a.split, a.interleave, a.subset)


if __name__ == "__main__":
    main()
