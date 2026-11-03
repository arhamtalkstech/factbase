"""Baseline memories: A0 closed_book, A1 recent_window, A2 rolling_summary, A3 raw_rag, A4 agentic_raw."""

from __future__ import annotations

import json
from collections import deque
from datetime import date, datetime, timedelta, timezone

from .. import llm
from ..index import HybridIndex
from ..types import Answer, Item, Question, fmt_day
from .base import ANSWER_EFFORT, ANSWER_MODEL, ANSWER_RULES, CACHE_SALT, ANSWER_SCHEMA, Memory, answer_from_context, run_agent, tool

CHARS_PER_TOKEN = 4


def _day_bounds(s: str | None, end: bool) -> float | None:
    if not s:
        return None
    d = datetime.fromisoformat(s[:10]).replace(tzinfo=timezone.utc)
    if end:
        d += timedelta(days=1) - timedelta(seconds=1)
    return d.timestamp()


# ---------------------------------------------------------------- A0


class ClosedBook(Memory):
    name = "closed_book"

    def ingest(self, items, now):
        pass

    def answer(self, q: Question, now: datetime) -> Answer:
        system = (
            "Answer the question from your own knowledge. Today is "
            + fmt_day(now)
            + ". Give a short exact answer. If you do not know, or the premise is false, or it asks about the future, set abstain=true."
        )
        r = llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": q.question}],
            schema=ANSWER_SCHEMA,
            tag=self.tag,
            effort=ANSWER_EFFORT,
            model=ANSWER_MODEL,
            salt=CACHE_SALT,
        )
        c = r["content"] if isinstance(r["content"], dict) else {}
        return Answer(str(c.get("answer", "")), bool(c.get("abstain", False)), [], r["usage"]["usd"], r["usage"]["in"], r["usage"]["out"], 0 if r["cached"] else 1)


# ---------------------------------------------------------------- A1


class RecentWindow(Memory):
    """The most recent N tokens of raw items, verbatim. 'Just use a long context window.'"""

    name = "recent_window"

    def __init__(self, dataset, workdir, window_tokens: int = 30000, **cfg):
        super().__init__(dataset, workdir, **cfg)
        self.budget = window_tokens * CHARS_PER_TOKEN
        self.buf: deque[str] = deque()
        self.chars = 0

    def ingest(self, items, now):
        for it in items:
            s = it.render()
            self.buf.append(s)
            self.chars += len(s) + 1
            while self.chars > self.budget and self.buf:
                self.chars -= len(self.buf.popleft()) + 1

    def answer(self, q, now):
        return answer_from_context("\n".join(self.buf) or "(empty)", q, now, self.tag)

    def stats(self):
        return {"window_items": len(self.buf)}


# ---------------------------------------------------------------- A2

COMPACT_SYSTEM = """You maintain the long-term memory of an assistant that is continuously reading a stream of time-stamped records
(news, market data, filings, results). The memory is a single document that you rewrite each time new records arrive.
The assistant will later be asked arbitrary questions about anything in the stream, including old details, so the memory
must preserve as much specific, checkable information as possible: names, exact numbers, exact dates, scores, values,
who did what, what changed and when, and the current state of ongoing situations.

Write the updated memory by merging the NEW RECORDS into the CURRENT MEMORY. Organise it by topic/entity with dated bullets.
Hard limit: about {words} words. When space runs out, compress older and less important details first, but keep dates
and numbers attached to what you keep. Output only the memory document."""


class RollingSummary(Memory):
    """Auto-compaction: raw records accumulate in a buffer; when the buffer passes a threshold, one LLM call rewrites a
    bounded summary from (previous summary + buffer). Answers see summary + current buffer (the usual auto-compaction pattern)."""

    name = "rolling_summary"

    def __init__(self, dataset, workdir, buffer_tokens: int = 12000, summary_words: int = 3000, **cfg):
        super().__init__(dataset, workdir, **cfg)
        self.threshold = buffer_tokens * CHARS_PER_TOKEN
        self.words = summary_words
        self.summary = ""
        self.buf: list[str] = []
        self.buf_chars = 0
        self.compactions = 0
        self.usd = 0.0

    def ingest(self, items, now):
        for it in items:
            s = it.render()
            self.buf.append(s)
            self.buf_chars += len(s) + 1

    def end_of_day(self, day, now):
        if self.buf_chars >= self.threshold:
            self._compact(now)

    def _compact(self, now):
        user = f"TODAY: {fmt_day(now)}\n\nCURRENT MEMORY:\n{self.summary or '(empty)'}\n\nNEW RECORDS:\n" + "\n".join(self.buf)
        r = llm.chat(
            [{"role": "system", "content": COMPACT_SYSTEM.format(words=self.words)}, {"role": "user", "content": user}],
            tag=self.tag + ":compact",
            max_tokens=int(self.words * 2.2),
        )
        self.usd += r["usage"]["usd"]
        if r["content"]:
            self.summary = r["content"]
        self.buf, self.buf_chars = [], 0
        self.compactions += 1

    def answer(self, q, now):
        ctx = f"SUMMARY OF OLDER RECORDS:\n{self.summary or '(empty)'}\n\nRECENT RECORDS (verbatim):\n" + "\n".join(self.buf)
        return answer_from_context(ctx, q, now, self.tag)

    def stats(self):
        return {"compactions": self.compactions, "summary_words": len(self.summary.split()), "ingest_usd": self.usd}


# ---------------------------------------------------------------- A3


class RawRAG(Memory):
    """Hybrid BM25 + dense over raw items, filtered to ts <= now, single shot."""

    name = "raw_rag"

    def __init__(self, dataset, workdir, k: int = 25, **cfg):
        super().__init__(dataset, workdir, **cfg)
        self.k = k
        self.ix = HybridIndex()
        self.items: dict[str, Item] = {}

    def ingest(self, items, now):
        for it in items:
            self.items[it.id] = it
        self.ix.add([(it.id, it.ts.timestamp(), "item", it.render()) for it in items])

    def retrieve(self, query: str, now: datetime, k: int | None = None, t_min=None, t_max=None) -> list:
        hi = now.timestamp() if t_max is None else min(t_max, now.timestamp())
        return self.ix.search(query, k=k or self.k, t_min=t_min, t_max=hi)

    def answer(self, q, now):
        hits = self.retrieve(q.question, now)
        hits.sort(key=lambda h: h.ts)
        return answer_from_context("\n".join(h.text for h in hits) or "(no matching records)", q, now, self.tag)

    def stats(self):
        return {"items": len(self.ix)}


# ---------------------------------------------------------------- A4

AGENT_SYSTEM = """You are a research agent answering a question from a memory of time-stamped records, using search tools.
{rules}

How to work:
- The first search results are already shown. If they answer the question, call final_answer right away.
- Otherwise search more: rephrase, use names and dates, narrow with start_date/end_date (YYYY-MM-DD), or list records in a date range.
- For counts, totals, maxima, rankings, or "as of" questions, gather all relevant records (list by date range) before answering.
- Stop as soon as you have enough evidence. Call final_answer exactly once."""


class AgenticRaw(RawRAG):
    """Tool-using agent over raw items only."""

    name = "agentic_raw"

    def __init__(self, dataset, workdir, k: int = 15, max_steps: int = 8, **cfg):
        super().__init__(dataset, workdir, k=k, **cfg)
        self.max_steps = max_steps

    def tools(self):
        return [
            tool(
                "search_records",
                "Hybrid keyword + semantic search over all records up to today. Returns records with ids and dates.",
                {
                    "query": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
                    "k": {"type": "integer", "description": "max results, default 20, max 50"},
                },
                ["query"],
            ),
            tool(
                "list_records",
                "List records in a date range in time order, optionally only those containing a keyword (case-insensitive).",
                {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "contains": {"type": "string", "description": "optional keyword filter"},
                    "limit": {"type": "integer", "description": "default 100, max 300"},
                },
                ["start_date", "end_date"],
            ),
        ]

    def handlers(self, now: datetime):
        def search(a):
            hits = self.retrieve(a["query"], now, k=min(int(a.get("k") or 20), 50), t_min=_day_bounds(a.get("start_date"), False), t_max=_day_bounds(a.get("end_date"), True))
            hits.sort(key=lambda h: h.ts)
            return "\n".join(h.text for h in hits) or "no results"

        def list_records(a):
            lo = _day_bounds(a.get("start_date"), False) or 0
            hi = min(_day_bounds(a.get("end_date"), True) or now.timestamp(), now.timestamp())
            limit = min(int(a.get("limit") or 100), 300)
            kw = (a.get("contains") or "").lower()
            hits = self.ix.by_time(lo, hi, limit=100000 if kw else limit)
            if kw:
                hits = [h for h in hits if kw in h.text.lower()][:limit]
            total = self.ix.count(lo, hi)
            return f"{len(hits)} shown (of {total} records in range{', before keyword filter' if kw else ''})\n" + "\n".join(h.text for h in hits)

        return {"search_records": search, "list_records": list_records}

    def answer(self, q, now):
        hits = self.retrieve(q.question, now)
        hits.sort(key=lambda h: h.ts)
        system = AGENT_SYSTEM.format(rules=ANSWER_RULES.format(today=fmt_day(now)))
        user = "INITIAL SEARCH RESULTS:\n" + ("\n".join(h.text for h in hits) or "none") + f"\n\nQUESTION: {q.question}"
        return run_agent(system, user, self.tools(), self.handlers(now), self.tag, max_steps=self.max_steps)
