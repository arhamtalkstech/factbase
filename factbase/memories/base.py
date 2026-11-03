"""Memory interface, the shared answer prompt, and the shared tool-using agent loop."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .. import llm
import os
import re
import time

from ..types import Answer, Item, Question, fmt_day

# Reasoning effort for answer-time calls (all architectures share it). Ingestion calls use "none".
ANSWER_EFFORT = os.environ.get("FACTBASE_ANSWER_EFFORT", "low")
# Optional answer-time model override (second-model robustness check) and cache salt (repeat runs).
ANSWER_MODEL = os.environ.get("FACTBASE_ANSWER_MODEL") or None
CACHE_SALT = os.environ.get("FACTBASE_CACHE_SALT", "")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "Short, exact answer. Empty if abstaining."},
        "abstain": {"type": "boolean", "description": "True if the memory does not contain the answer or the premise is contradicted by the record."},
        "citations": {"type": "array", "items": {"type": "string"}, "description": "IDs of the records that support the answer."},
    },
    "required": ["answer", "abstain", "citations"],
}

ANSWER_RULES = """Rules:
- Today is {today}. You only know what is in the memory below; treat it as the complete record up to today.
- Answer with the short, exact answer (a name, number, date, or brief phrase). Include units when relevant.
- Use the dates on records to reason about time. "As of" a date means the latest information at or before that date.
- If the memory does not contain the information needed, or the question's premise is contradicted by the record, or it asks
  about something after today, set abstain=true and explain briefly in answer. Do not guess.
- Cite the IDs of the records you used."""


# v5 exploratory: distinguish "detail not confirmed" (answer, with a note) from "premise contradicted / no such event" (abstain)
ANSWER_RULES_CALIBRATED = """Rules:
- Today is {today}. You only know what is in the memory below; treat it as the complete record up to today.
- Answer with the short, exact answer (a name, number, date, or brief phrase). Include units when relevant.
- Use the dates on records to reason about time. "As of" a date means the latest information at or before that date.
- If the record clearly describes the event or fact the question is about, answer from the record even if it does not confirm
  every detail in the question (a place name, a more specific term, a date one or two days off from the report). Briefly
  note any unconfirmed detail after the answer.
- Set abstain=true only if the record has no matching event or fact, if it contradicts the question's premise, or if the
  question asks about something after today. Do not guess beyond the record.
- Cite the IDs of the records you used."""


# v6: one answer policy for facts and conversations (designed on the LongMemEval dev split, see eval/longmemeval.py)
ANSWER_RULES_V6 = """Rules:
- Today is {today}. You only know what is in the memory (records up to today).
- Give a direct answer. For factual questions: a short exact answer (name, number, date or phrase, with units). For requests
  for advice, recommendations or opinions: answer helpfully in one to three sentences, tailored to everything relevant the
  memory says about the person or topic (their preferences, situation, past experiences).
- Time: relative phrases ("two weeks ago", "last month", "recently") are relative to today's date; turn them into dates and
  search that window. "As of" a date means the latest information at or before that date.
- When the record holds several values for the same thing, the most recent one is the current answer.
- For counts and totals across many records, list each distinct matching instance (with its record id) before giving the
  number, and do not count the same instance twice.
- If the record clearly describes the event or fact asked about, answer even if a minor detail in the question is not
  confirmed, and note that detail briefly.
- Abstain (abstain=true) only after searching and finding no matching event or fact, if the record contradicts the premise,
  or if the question asks about something after today.
- Cite the IDs of the records you used."""


def answer_from_context(context: str, q: Question, now: datetime, tag: str, header: str = "MEMORY") -> Answer:
    system = "You answer questions using a memory of time-stamped records.\n" + ANSWER_RULES.format(today=fmt_day(now))
    user = f"{header}:\n{context}\n\nQUESTION: {q.question}"
    t0 = time.time()
    r = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        schema=ANSWER_SCHEMA,
        tag=tag,
        effort=ANSWER_EFFORT,
        model=ANSWER_MODEL,
        salt=CACHE_SALT,
    )
    llm_s = time.time() - t0
    c = r["content"] if isinstance(r["content"], dict) else {}
    return Answer(
        answer=str(c.get("answer", "")),
        abstain=bool(c.get("abstain", False)),
        citations=[str(x) for x in c.get("citations", [])],
        usd=r["usage"]["usd"],
        tokens_in=r["usage"]["in"],
        tokens_out=r["usage"]["out"],
        llm_calls=0 if r["cached"] else 1,
        error=None if c else f"unparsed: {str(r['content'])[:200]}",
        llm_s=0.0 if r["cached"] else llm_s,
    )


class Memory:
    """Base class. The runner calls, in simulated time order:

    prepare(all_items)    optional precompute that may only use information local to one
                          item or one closed period, results revealed later by ingest/end_of_day
    ingest(items, now)    items published since the last call, all with ts <= now
    end_of_day(day, now)  consolidation hook after the day's items
    answer(q, now)        answer as of `now`; must not use anything ingested later
    """

    name = "base"

    def __init__(self, dataset: str, workdir: Path, **cfg) -> None:
        self.dataset = dataset
        self.workdir = workdir
        self.cfg = cfg
        workdir.mkdir(parents=True, exist_ok=True)

    @property
    def tag(self) -> str:
        return f"mem:{self.name}:{self.dataset}"

    def prepare(self, items: list[Item]) -> None:
        pass

    def ingest(self, items: list[Item], now: datetime) -> None:
        raise NotImplementedError

    def end_of_day(self, day: date, now: datetime) -> None:
        pass

    def answer(self, q: Question, now: datetime) -> Answer:
        raise NotImplementedError

    def stats(self) -> dict:
        return {}


# ---------------------------------------------------------------- agent loop

FINAL_TOOL = {
    "type": "function",
    "function": {
        "name": "final_answer",
        "description": "Give the final answer. Call exactly once when done.",
        "parameters": ANSWER_SCHEMA,
    },
}


OPEN_REF_TOOL = {
    "type": "function",
    "function": {
        "name": "open_ref",
        "description": "Re-open the full text of an earlier tool result that was offloaded to save context (e.g. 'R2').",
        "parameters": {"type": "object", "properties": {"ref_id": {"type": "string"}}, "required": ["ref_id"]},
    },
}

# tools that count against a per-question search budget
BUDGETED_TOOLS = {"search_records", "list_records", "search_facts", "entity_history", "list_threads", "get_thread", "read_records"}


def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def run_agent(
    system: str,
    user: str,
    tools: list[dict],
    handlers: dict[str, Callable[[dict], str]],
    tag: str,
    max_steps: int = 8,
    max_tool_chars: int = 12000,
    require_one_of: set[str] | None = None,
    abstain_guard: str | None = None,
    offload_keep: int | None = None,
    search_budget: int | None = None,
) -> Answer:
    """require_one_of: if set, a final_answer is refused (once) until one of these tools has been called.

    offload_keep: reversible offload of working memory. Tool outputs older than the last `offload_keep` tool rounds are
    replaced in the conversation by a short stub; the full text stays retrievable with the open_ref tool.
    search_budget: maximum number of search/list calls per question (computation and open_ref are not counted).
    """
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    ans = Answer(answer="", abstain=True)
    refs: dict[str, str] = {}
    tool_rounds: list[list[int]] = []  # message indices of tool outputs, per assistant round
    searches = 0
    all_tools = tools + [FINAL_TOOL] + ([OPEN_REF_TOOL] if offload_keep is not None else [])
    for step in range(max_steps):
        last = step == max_steps - 1
        if offload_keep is not None and len(tool_rounds) > offload_keep:
            for rnd in tool_rounds[: len(tool_rounds) - offload_keep]:
                for i in rnd:
                    m = messages[i]
                    if not m.get("_stub"):
                        m["content"] = m.pop("_stub_text")
                        m["_stub"] = True
        if last:
            messages.append({"role": "user", "content": "Step limit reached. Call final_answer now with your best supported answer, or abstain."})
        t0 = time.time()
        wire = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
        r = llm.chat(wire, tools=[FINAL_TOOL] if last else all_tools, tag=tag, effort=ANSWER_EFFORT, model=ANSWER_MODEL, salt=CACHE_SALT)
        if not r["cached"]:
            ans.llm_s += time.time() - t0
        ans.usd += r["usage"]["usd"]
        ans.tokens_in += r["usage"]["in"]
        ans.tokens_out += r["usage"]["out"]
        ans.llm_calls += 0 if r["cached"] else 1
        calls = r["tool_calls"]
        if not calls:
            text = (r["content"] or "").strip()
            if text and any(t.get("tool") == "text_reply" for t in ans.trace):
                # second plain-text reply in a row: accept it as the answer (some models ignore the final_answer tool)
                ans.answer = text[:2000]
                ans.abstain = bool(re.search(r"(?i)\b(not in (the )?(record|memory)|no record|don't know|do not know|cannot (determine|find)|not (found|available|mentioned))\b", text))
                ans.trace.append({"tool": "text_fallback"})
                return ans
            ans.trace.append({"tool": "text_reply"})
            # model answered in text; push it to use the final tool once
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "Use the final_answer tool to answer."})
            continue
        messages.append(
            {
                "role": "assistant",
                "content": r["content"] or "",
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls
                ],
            }
        )
        this_round: list[int] = []
        tool_rounds.append(this_round)
        for c in calls:
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            if c["name"] == "open_ref":
                rid = str(args.get("ref_id", ""))
                ans.trace.append({"tool": "open_ref", "args": args})
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": refs.get(rid, f"no such ref {rid}")[:max_tool_chars]})
                continue
            if search_budget is not None and c["name"] in BUDGETED_TOOLS:
                searches += 1
                if searches > search_budget:
                    ans.trace.append({"tool": "budget_refused", "args": {"tool": c["name"]}})
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": (
                        f"Search budget for this question is used up ({search_budget} searches). Answer from the evidence you "
                        "have, or use sql/python if a computation is needed.")})
                    continue
            if c["name"] == "final_answer" and require_one_of and not any(t.get("tool") in require_one_of for t in ans.trace) and not last:
                ans.trace.append({"tool": "final_answer_refused"})
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": (
                    "Not accepted yet: this question needs an exhaustive computation. Run "
                    + " or ".join(sorted(require_one_of))
                    + " over the records to compute or verify the answer, then call final_answer.")})
                require_one_of = None
                continue
            if (
                c["name"] == "final_answer" and abstain_guard and args.get("abstain") and not last
                and sum(1 for t in ans.trace if t.get("tool") == abstain_guard) < 2
            ):
                ans.trace.append({"tool": "abstain_refused"})
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": (
                    f"Not accepted yet: before concluding the record lacks this, run {abstain_guard} at least twice with different "
                    "phrasings (names, synonyms, spelling variants, key nouns only) and a date window a few days either side. "
                    "Exact-phrase SQL LIKE misses paraphrased headlines. Then call final_answer.")})
                abstain_guard = None
                continue
            if c["name"] == "final_answer":
                ans.answer = str(args.get("answer", ""))
                ans.abstain = bool(args.get("abstain", False))
                ans.citations = [str(x) for x in args.get("citations", [])]
                ans.trace.append({"tool": "final_answer"})
                return ans
            fn = handlers.get(c["name"])
            t1 = time.time()
            try:
                out = fn(args) if fn else f"unknown tool {c['name']}"
            except Exception as e:  # tool errors go back to the model
                out = f"tool error: {e}"
            ans.tool_s += time.time() - t1
            out = out[:max_tool_chars]
            ans.trace.append({"tool": c["name"], "args": args, "chars": len(out)})
            msg = {"role": "tool", "tool_call_id": c["id"], "content": out}
            if offload_keep is not None:
                rid = f"R{len(refs) + 1}"
                refs[rid] = out
                short_args = json.dumps(args, ensure_ascii=False)[:160]
                preview = " ".join(out.split())[:240]
                msg["_stub_text"] = (
                    f"[{rid} offloaded to save context: {c['name']}({short_args}) returned {len(out)} chars. "
                    f"Preview: {preview} ... Call open_ref('{rid}') to read it in full.]"
                )
                this_round.append(len(messages))
            messages.append(msg)
    ans.error = "no final answer"
    return ans
