"""Extraction-based memories: A5 fact_memory, A7 rollups, A8 factbase (+ ablation variants).

Item-local and period-local LLM work (fact extraction per day, digests per closed period) is computed up front in
parallel in prepare() and only *revealed* to the memory when the simulated clock reaches it. That is equivalent to
doing the work in streaming order, because no call uses information from outside its own day or period.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .. import llm
from ..index import HybridIndex
from ..types import Answer, Item, Question, fmt_day
from .base import ANSWER_RULES, ANSWER_RULES_CALIBRATED, ANSWER_RULES_V6, Memory, answer_from_context, run_agent, tool
from .baselines import _day_bounds

# ---------------------------------------------------------------- extraction

EXTRACT_SYSTEM = """You turn time-stamped records into atomic facts for a long-term memory that must answer arbitrary future
questions (including exact numbers, dates, names, counts and how things changed over time).

For each distinct piece of checkable information, output one fact:
- statement: a self-contained sentence with absolute dates and full names (never "today", "yesterday", "this week").
- subject: the main entity, full canonical name (e.g. "Brent crude oil spot price", "Arsenal FC", "Apple Inc.", "Iran").
- attribute: short snake_case relation or property (e.g. closing_price, fed_funds_target_range, match_result, quarterly_revenue,
  ceo, seized_vessel, sanctions_designation, statement, attack, agreement). Use the same attribute name for the same kind of fact.
- object: the value or counterpart, as text.
- number / unit: the main numeric value and unit if there is one, else null.
- event_date: YYYY-MM-DD when it happened or applies (resolve relative dates against the record's date).
- period: the reporting period it refers to if any (e.g. "2025-Q3", "FY2025", "2025-03"), else "".
- kind: "state" if it is a current value/status of subject+attribute that a later value would replace (a price, a rank, a
  rate, a role holder, the latest reported figure); "event" if it is something that happened (does not replace earlier events).
- entities: other named entities involved.
- source_ids: ids of the records it came from.
Merge duplicates (the same fact reported by several records -> one fact listing all source ids). Do not invent anything that
is not in the records. Be exhaustive about specific facts; skip pure opinion and filler."""

FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "subject": {"type": "string"},
                    "attribute": {"type": "string"},
                    "object": {"type": "string"},
                    "number": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "event_date": {"type": "string"},
                    "period": {"type": "string"},
                    "kind": {"type": "string", "enum": ["state", "event"]},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["statement", "subject", "attribute", "object", "number", "unit", "event_date", "period", "kind", "entities", "source_ids"],
            },
        }
    },
    "required": ["facts"],
}

CHUNK_CHARS = 16000
# Parallel LLM calls for ingestion-time extraction and digests (item/period-local work).
INGEST_WORKERS = int(__import__("os").environ.get("FACTBASE_INGEST_WORKERS", "16"))


_TRAILING_ATTRIB = re.compile(r"\s*\([^()]{1,80}\)\s*$")


def _dup_key(it: Item) -> str:
    t = _TRAILING_ATTRIB.sub("", it.text)
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def collapse_duplicates(items: list[Item]) -> list[Item]:
    """Collapse items with the same text (ignoring a trailing source attribution such as "(reuters.com, English)") into
    one representative whose text records how many copies there were. Applied only to LLM extraction/digest input; the
    raw evidence store keeps every item. Copy counts are a corroboration signal, so they are kept, not dropped."""
    groups: dict[str, list[Item]] = {}
    for it in items:
        groups.setdefault(_dup_key(it), []).append(it)
    out = []
    for key, grp in groups.items():
        if len(grp) == 1:
            out.append(grp[0])
            continue
        rep = grp[0]
        out.append(
            Item(
                id=rep.id, dataset=rep.dataset, ts=rep.ts, title=rep.title, source=rep.source, url=rep.url, meta=rep.meta,
                text=f"{rep.text} [reported {len(grp)} times that day]",
            )
        )
    out.sort(key=lambda i: i.ts)
    return out


def day_chunks(items: list[Item]) -> dict[date, list[list[Item]]]:
    """Group items by UTC day and feed (item.dataset), split into chunks of at most CHUNK_CHARS rendered characters.
    Grouping by feed keeps a mixed stream's chunks identical to the single-feed runs (same extraction cache)."""
    by_day: dict[date, dict[str, list[Item]]] = defaultdict(lambda: defaultdict(list))
    for it in items:
        by_day[it.ts.date()][it.dataset].append(it)
    out: dict[date, list[list[Item]]] = {}
    for d, feeds in by_day.items():
        chunks = []
        for feed in sorted(feeds):
            cur, n = [], 0
            for it in collapse_duplicates(feeds[feed]):
                s = len(it.render())
                if cur and n + s > CHUNK_CHARS:
                    chunks.append(cur)
                    cur, n = [], 0
                cur.append(it)
                n += s
            if cur:
                chunks.append(cur)
        out[d] = chunks
    return out


def extract_chunk(chunk: list[Item], tag: str) -> list[dict]:
    recs = "\n".join(it.render()[:CHUNK_CHARS] for it in chunk)
    try:
        r = llm.ask_json(EXTRACT_SYSTEM, f"RECORDS:\n{recs}", FACT_SCHEMA, tag=tag, schema_name="facts", timeout=420, max_attempts=2)
    except Exception:
        # straggler (runaway generation): retry once with an output cap; the cap changes the cache key only for these
        try:
            r = llm.ask_json(EXTRACT_SYSTEM, f"RECORDS:\n{recs}", FACT_SCHEMA, tag=tag, schema_name="facts", timeout=420, max_attempts=2, max_tokens=12000)
        except Exception:
            return []
    facts = r.get("facts") or []
    ids = {it.id for it in chunk}
    fallback_ts = chunk[0].ts
    out = []
    for f in facts:
        if not isinstance(f, dict) or not f.get("statement"):
            continue
        src = [s for s in (f.get("source_ids") or []) if s in ids] or [chunk[0].id]
        ed = str(f.get("event_date") or "")[:10]
        try:
            date.fromisoformat(ed)
        except ValueError:
            ed = fallback_ts.date().isoformat()
        f["event_date"] = ed
        f["source_ids"] = src
        out.append(f)
    return out


def speaker_view(items: list[Item]) -> list[Item]:
    """Conversations: keep only what the person said (drop the assistant's replies) for fact extraction."""
    out = []
    for it in items:
        text = it.text.split("\nAssistant:")[0]
        if text.startswith("Assistant:"):
            continue
        out.append(Item(id=it.id, dataset=it.dataset, ts=it.ts, title=it.title, source=it.source, url=it.url, meta=it.meta, text=text))
    return out


def norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"[^a-z0-9%$\.\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _epoch(d: str) -> float:
    return datetime.fromisoformat(d[:10]).replace(tzinfo=timezone.utc, hour=12).timestamp()


# ---------------------------------------------------------------- digests (rollups)

DIGEST_SYSTEM = """You write a frozen {level} digest for a long-term memory of a stream of time-stamped records.
Period: {period}. Later, someone will ask arbitrary questions about this period, so keep specific, checkable details:
names, exact numbers, exact dates, scores/values, what changed. Organise by topic/entity, dated bullets, no filler.
Hard limit: about {words} words. Cite record or digest ids in brackets after each bullet."""

LEVEL_WORDS = {"day": 350, "week": 600, "month": 900}


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_digests(items: list[Item], tag: str, workers: int | None = None) -> list[dict]:
    """Day digests from items, week digests from day digests, month digests from week digests. Each is computed only from
    its own period's content. Returns digests with the time they become available (period end)."""
    workers = workers or INGEST_WORKERS
    chunks = day_chunks(items)
    days = sorted(chunks)

    def day_digest(d: date) -> dict:
        recs = "\n".join(it.render()[:3000] for ch in chunks[d] for it in ch)[:60000]
        r = llm.chat(
            [
                {"role": "system", "content": DIGEST_SYSTEM.format(level="daily", period=fmt_day(d), words=LEVEL_WORDS["day"])},
                {"role": "user", "content": f"RECORDS:\n{recs}"},
            ],
            tag=tag + ":digest",
            timeout=300,
            max_attempts=3,
        )
        return {"id": f"digest:day:{d}", "level": "day", "start": d.isoformat(), "end": d.isoformat(), "text": r["content"] or ""}

    day_d = [x for x in llm.pmap(day_digest, days, workers=workers) if isinstance(x, dict)]
    weeks: dict[date, list[dict]] = defaultdict(list)
    for x in day_d:
        weeks[_week_start(date.fromisoformat(x["start"]))].append(x)

    def week_digest(ws: date) -> dict:
        we = ws + timedelta(days=6)
        body = "\n\n".join(f"[{x['id']}]\n{x['text']}" for x in sorted(weeks[ws], key=lambda x: x["start"]))
        r = llm.chat(
            [
                {"role": "system", "content": DIGEST_SYSTEM.format(level="weekly", period=f"{fmt_day(ws)} to {fmt_day(we)}", words=LEVEL_WORDS["week"])},
                {"role": "user", "content": f"DAILY DIGESTS:\n{body}"},
            ],
            tag=tag + ":digest",
            timeout=300,
            max_attempts=3,
        )
        return {"id": f"digest:week:{ws}", "level": "week", "start": ws.isoformat(), "end": we.isoformat(), "text": r["content"] or ""}

    week_d = [x for x in llm.pmap(week_digest, sorted(weeks), workers=workers) if isinstance(x, dict)]
    months: dict[tuple, list[dict]] = defaultdict(list)
    for x in day_d:
        d = date.fromisoformat(x["start"])
        months[(d.year, d.month)].append(x)

    def month_digest(ym: tuple) -> dict:
        y, m = ym
        ms = date(y, m, 1)
        me = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        # weeks fully inside the month plus days of partial weeks at the edges
        wk = [w for w in week_d if date.fromisoformat(w["start"]) >= ms and date.fromisoformat(w["end"]) <= me]
        covered = {date.fromisoformat(w["start"]) + timedelta(days=i) for w in wk for i in range(7)}
        edge = [x for x in months[ym] if date.fromisoformat(x["start"]) not in covered]
        parts = sorted(wk + edge, key=lambda x: x["start"])
        body = "\n\n".join(f"[{x['id']}]\n{x['text']}" for x in parts)
        r = llm.chat(
            [
                {"role": "system", "content": DIGEST_SYSTEM.format(level="monthly", period=ms.strftime("%B %Y"), words=LEVEL_WORDS["month"])},
                {"role": "user", "content": f"WEEKLY AND DAILY DIGESTS:\n{body}"},
            ],
            tag=tag + ":digest",
            timeout=300,
            max_attempts=3,
        )
        return {"id": f"digest:month:{ms:%Y-%m}", "level": "month", "start": ms.isoformat(), "end": me.isoformat(), "text": r["content"] or ""}

    month_d = [x for x in llm.pmap(month_digest, sorted(months), workers=workers) if isinstance(x, dict)]
    return day_d + week_d + month_d


class _Revealer:
    """Holds precomputed digests and releases each one when its period has closed."""

    def __init__(self, digests: list[dict]):
        self.pending = sorted(digests, key=lambda x: x["end"])
        self.i = 0

    def due(self, day: date) -> list[dict]:
        out = []
        while self.i < len(self.pending) and date.fromisoformat(self.pending[self.i]["end"]) <= day:
            out.append(self.pending[self.i])
            self.i += 1
        return out


# ---------------------------------------------------------------- A5


class FactMemory(Memory):
    """Add-only atomic facts extracted by an LLM, hybrid retrieval over facts, single shot."""

    name = "fact_memory"

    def __init__(self, dataset, workdir, k: int = 40, **cfg):
        super().__init__(dataset, workdir, **cfg)
        self.k = k
        self.ix = HybridIndex()
        self.by_day: dict[date, list[dict]] = {}
        self.n = 0

    def prepare(self, items):
        chunks = day_chunks(items)
        jobs = [(d, ch) for d, chs in chunks.items() for ch in chs]
        res = llm.pmap(lambda j: (j[0], extract_chunk(j[1], tag=f"extract:{self.dataset}")), jobs, workers=INGEST_WORKERS)
        for r in res:
            if isinstance(r, Exception):
                continue
            d, facts = r
            self.by_day.setdefault(d, []).extend(facts)

    def _fact_text(self, f: dict, fid: str) -> str:
        per = f" period={f['period']}" if f.get("period") else ""
        return f"[{fid} | event {f['event_date']}{per} | src {','.join(f['source_ids'][:3])}] {f['statement']}"

    def ingest(self, items, now):
        d = items[0].ts.date()
        facts = self.by_day.pop(d, [])
        docs = []
        for f in facts:
            fid = f"F{self.n}"
            self.n += 1
            docs.append((fid, _epoch(f["event_date"]), "fact", self._fact_text(f, fid)))
        self.ix.add(docs)

    def answer(self, q, now):
        hits = self.ix.search(q.question, k=self.k)
        hits.sort(key=lambda h: h.ts)
        return answer_from_context("\n".join(h.text for h in hits) or "(no facts)", q, now, self.tag)

    def stats(self):
        return {"facts": self.n}


# ---------------------------------------------------------------- A7


class Rollups(Memory):
    """Frozen day -> week -> month digests (a time hierarchy of summaries), hybrid retrieval over all levels, single shot."""

    name = "rollups"

    def __init__(self, dataset, workdir, k: int = 12, **cfg):
        super().__init__(dataset, workdir, **cfg)
        self.k = k
        self.ix = HybridIndex()
        self.rev = _Revealer([])

    def prepare(self, items):
        self.rev = _Revealer(build_digests(items, tag=f"rollup:{self.dataset}"))

    def ingest(self, items, now):
        pass

    def end_of_day(self, day, now):
        new = self.rev.due(day)
        self.ix.add([(x["id"], _epoch(x["start"]), x["level"], f"[{x['id']} | {x['start']}..{x['end']}]\n{x['text']}") for x in new])

    def answer(self, q, now):
        hits = self.ix.search(q.question, k=self.k)
        hits.sort(key=lambda h: h.ts)
        return answer_from_context("\n\n".join(h.text for h in hits) or "(no digests yet)", q, now, self.tag)

    def stats(self):
        return {"digests": len(self.ix)}


# ---------------------------------------------------------------- A8

FACTBASE_SYSTEM = """You are the query agent of a long-term memory built from a continuous stream of time-stamped records.
{rules}

The memory has layers. Use whichever fits the question:
1. FACTS: atomic facts extracted from records, each with event date, kind (state/event) and status. For "state" facts the
   memory tracks supersession: status=current is the latest known value, status=superseded shows earlier values and the date
   they stopped being current (valid_to). Use entity_history to see how something changed over time.
2. RAW RECORDS: the original records, never edited. Use them to verify details, find things facts missed, or read exact wording.
3. DIGESTS: frozen day/week/month summaries for overviews and "what happened in period X" questions.
4. SQL: read-only SQL over tables {tables}. Use it for exact lookups, counts, sums, maxima, rankings, and "latest as of date"
   questions. Dates are ISO strings (YYYY-MM-DD), so string comparison works.

How to work:
- The initial context already shows the best facts, records and digests. If they answer the question, call final_answer.
- For counts/aggregates/as-of/ranking questions, prefer SQL (check the schema with describe_tables first), and make sure you
  covered every relevant record, not just the top search hits.
- Verify surprising or important answers against raw records. Stop when you have enough evidence. Call final_answer once."""


class Factbase(Memory):
    """Proposed design: evidence vault + temporal facts with supersession + frozen digests + structured records + agent."""

    name = "factbase"

    def __init__(
        self,
        dataset,
        workdir,
        agent: bool = True,
        raw: bool = True,
        struct: bool = True,
        digests: bool = True,
        facts: bool = True,
        compute: bool = False,
        records_all: bool = False,
        enforce_compute: bool = False,
        abstain_guard: bool = False,
        calibrated: bool = False,
        rules_v6: bool = False,
        per_feed_card: bool = False,
        extract_speaker_only: bool = False,
        max_steps: int = 8,
        k_facts: int = 25,
        k_raw: int = 12,
        k_digest: int = 3,
        **cfg,
    ):
        super().__init__(dataset, workdir, **cfg)
        self.use_agent, self.use_raw, self.use_struct, self.use_digests = agent, raw, struct, digests
        # v2 switches: facts=False drops the extracted-facts layer; compute=True adds the python tool, the schema card
        # and the v2 routing prompt; records_all=True makes every raw item a SQL row (not only items with meta).
        self.use_facts, self.use_compute, self.records_all = facts, compute, records_all
        # v3: analytic questions must run sql/python at least once before final_answer
        self.enforce_compute = enforce_compute
        # v4: an abstention is refused (once) until search_records has been run at least twice
        self.abstain_guard = abstain_guard
        # v5 (exploratory): calibrated answer rules, answer when the event matches even if a detail is unconfirmed
        self.calibrated = calibrated
        # v6: unified answer policy (advice answers, relative dates, latest value wins, enumerate before counting)
        self.rules_v6 = rules_v6
        self.per_feed_card = per_feed_card
        self.extract_speaker_only = extract_speaker_only
        self.max_steps, self.k_facts, self.k_raw, self.k_digest = max_steps, k_facts, k_raw, k_digest
        self.facts_ix = HybridIndex()
        self.raw_ix = HybridIndex()
        self.dig_ix = HybridIndex()
        self.rev = _Revealer([])
        self.by_day: dict[date, list[dict]] = {}
        self.n = 0
        self.lock = threading.Lock()
        self.db_path = workdir / "factbase.sqlite"
        if self.db_path.exists():
            self.db_path.unlink()
        for ext in ("-wal", "-shm"):
            p = workdir / f"factbase.sqlite{ext}"
            if p.exists():
                p.unlink()
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        # rollback journal (not WAL) so sandboxed read-only readers never need to write -shm files
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.executescript(
            """
            CREATE TABLE facts (fact_id TEXT PRIMARY KEY, subject TEXT, attribute TEXT, object TEXT, number REAL, unit TEXT,
              event_date TEXT, period TEXT, kind TEXT, status TEXT, valid_to TEXT, superseded_by TEXT, statement TEXT,
              entities TEXT, source_ids TEXT, reported_at TEXT, subject_key TEXT, attribute_key TEXT);
            CREATE INDEX facts_key ON facts(subject_key, attribute_key, period);
            CREATE INDEX facts_date ON facts(event_date);
            CREATE TABLE records (item_id TEXT PRIMARY KEY, date TEXT, ts TEXT, source TEXT, title TEXT, meta TEXT, text TEXT, feed TEXT);
            CREATE INDEX records_date ON records(date);
            """
        )
        self.supersessions = 0
        self.digests_seen: list[dict] = []
        self.feeds: set[str] = set()

    # -- ingestion

    def prepare(self, items):
        if self.use_facts:
            src = items
            if self.extract_speaker_only:
                src = speaker_view(items)
            chunks = day_chunks(src)
            jobs = [(d, ch) for d, chs in chunks.items() for ch in chs]
            res = llm.pmap(lambda j: (j[0], extract_chunk(j[1], tag=f"extract:{self.dataset}")), jobs, workers=INGEST_WORKERS)
            for r in res:
                if isinstance(r, Exception):
                    continue
                d, facts = r
                self.by_day.setdefault(d, []).extend(facts)
        if self.use_digests:
            self.rev = _Revealer(build_digests(items, tag=f"rollup:{self.dataset}"))

    def ingest(self, items, now):
        with self.lock:
            if self.use_raw:
                self.raw_ix.add([(it.id, it.ts.timestamp(), "item", it.render()) for it in items])
            rows = [
                (it.id, it.ts.date().isoformat(), it.ts.isoformat(), it.source, it.title, json.dumps(it.meta if self.use_struct else {}), it.text, it.dataset)
                for it in items
                if self.records_all or (self.use_struct and it.meta)
            ]
            if rows:
                self.db.executemany("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?)", rows)
                self.feeds.update(r[7] for r in rows)
            d = items[0].ts.date()
            facts = sorted(self.by_day.pop(d, []), key=lambda f: f["event_date"])
            docs = []
            for f in facts:
                fid = f"F{self.n}"
                self.n += 1
                self._insert_fact(fid, f, items[0].ts.isoformat())
                docs.append((fid, _epoch(f["event_date"]), "fact", f["statement"]))
            self.facts_ix.add(docs)
            self.db.commit()

    def _insert_fact(self, fid: str, f: dict, reported_at: str) -> None:
        sk, ak, per = norm(f["subject"]), norm(f["attribute"]), f.get("period") or ""
        status, valid_to, sup_by = "current", None, None
        if f.get("kind") == "state":
            prev = self.db.execute(
                "SELECT fact_id, event_date FROM facts WHERE subject_key=? AND attribute_key=? AND period=? AND kind='state' "
                "AND status='current'",
                (sk, ak, per),
            ).fetchall()
            for pid, ped in prev:
                if ped <= f["event_date"]:
                    # newer (or same-day) value replaces the old one
                    if norm(self._obj(pid)) != norm(str(f.get("object"))) or ped < f["event_date"]:
                        self.db.execute("UPDATE facts SET status='superseded', valid_to=?, superseded_by=? WHERE fact_id=?", (f["event_date"], fid, pid))
                        self.supersessions += 1
                else:
                    # late-arriving older value: store as historical
                    status, valid_to, sup_by = "superseded", ped, pid
        else:
            status = "event"
        self.db.execute(
            "INSERT INTO facts (fact_id, subject, attribute, object, number, unit, event_date, period, kind, status, valid_to, "
            "superseded_by, statement, entities, source_ids, reported_at, subject_key, attribute_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                fid, f["subject"], f["attribute"], str(f.get("object")), f.get("number"), f.get("unit"), f["event_date"], per,
                f.get("kind"), status, valid_to, sup_by, f["statement"], json.dumps(f.get("entities") or []),
                json.dumps(f["source_ids"]), reported_at, sk, ak,
            ),
        )

    def _obj(self, fid: str) -> str:
        r = self.db.execute("SELECT object FROM facts WHERE fact_id=?", (fid,)).fetchone()
        return r[0] if r else ""

    def end_of_day(self, day, now):
        if self.use_digests:
            new = self.rev.due(day)
            self.digests_seen.extend(new)
            self.dig_ix.add([(x["id"], _epoch(x["start"]), x["level"], f"[{x['id']} | {x['start']}..{x['end']}]\n{x['text']}") for x in new])

    # -- query helpers

    def _ro(self) -> sqlite3.Connection:
        c = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
        return c

    def _fact_rows(self, fids: list[str]) -> list[str]:
        if not fids:
            return []
        c = self._ro()
        rows = c.execute(
            f"SELECT fact_id, event_date, period, kind, status, valid_to, statement, source_ids FROM facts WHERE fact_id IN ({','.join('?' * len(fids))})",
            fids,
        ).fetchall()
        c.close()
        rows.sort(key=lambda r: r[1])
        out = []
        for fid, ed, per, kind, st, vt, stmt, src in rows:
            tags = [f"event {ed}"]
            if per:
                tags.append(f"period {per}")
            if kind == "state":
                tags.append(st + (f" until {vt}" if vt else ""))
            tags.append("src " + ",".join(json.loads(src)[:3]))
            out.append(f"[{fid} | {' | '.join(tags)}] {stmt}")
        return out

    def search_facts(self, query: str, k: int, t_min=None, t_max=None, current_only=False) -> list[str]:
        hits = self.facts_ix.search(query, k=k * 2 if current_only else k, t_min=t_min, t_max=t_max)
        rows = self._fact_rows([h.doc_id for h in hits])
        if current_only:
            rows = [r for r in rows if "superseded" not in r.split("]")[0]][:k]
        return rows

    def tables(self) -> str:
        if self.use_compute:
            # the feed column is only advertised when the memory holds several feeds, so single-feed prompts are unchanged
            feed = "feed, " if len(self.feeds) > 1 else ""
            t = [f"records(item_id, date, ts, {feed}source, title, text, meta JSON -- json_extract(meta,'$.field'))"]
            if self.use_facts:
                t.append("facts(fact_id, subject, attribute, object, number, unit, event_date, period, kind, status, valid_to, superseded_by, statement, entities, source_ids, reported_at)")
            return ", ".join(t)
        return "facts(fact_id, subject, attribute, object, number, unit, event_date, period, kind, status, valid_to, superseded_by, statement, entities, source_ids, reported_at)" + (
            ", records(item_id, date, ts, source, title, meta JSON -- use json_extract(meta,'$.field'))" if self.use_struct else ""
        )

    def _sql(self, q: str) -> str:
        s = q.strip().rstrip(";")
        if not re.match(r"(?is)^\s*(select|with)\b", s) or re.search(r"(?i)\b(insert|update|delete|drop|alter|attach|pragma|create)\b", s):
            return "only read-only SELECT queries are allowed"
        if not self.use_struct and re.search(r"(?i)\brecords\b", s):
            return "table records is not available"
        c = self._ro()
        try:
            cur = c.execute(s)
            cols = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(201)
        finally:
            c.close()
        more = len(rows) > 200
        rows = rows[:200]
        lines = [" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in r) for r in rows]
        return "\n".join(lines) + (f"\n... (truncated at 200 rows; use LIMIT/aggregates)" if more else f"\n({len(rows)} rows)")

    def _describe(self) -> str:
        c = self._ro()
        out = [self.tables()]
        out.append("facts: %d rows; top attributes: " % c.execute("select count(*) from facts").fetchone()[0])
        for a, n in c.execute("select attribute, count(*) n from facts group by attribute order by n desc limit 40"):
            out.append(f"  {a}: {n}")
        out.append("top subjects:")
        for s_, n in c.execute("select subject, count(*) n from facts group by subject order by n desc limit 40"):
            out.append(f"  {s_}: {n}")
        if self.use_struct:
            n = c.execute("select count(*) from records").fetchone()[0]
            out.append(f"records: {n} rows with structured meta. Example rows:")
            for r in c.execute("select item_id, date, source, title, meta from records order by random() limit 5"):
                out.append("  " + " | ".join(str(x) for x in r))
        c.close()
        return "\n".join(out)

    # -- answering

    def _initial_context(self, q: Question, now: datetime) -> str:
        parts = ["FACTS:\n" + ("\n".join(self.search_facts(q.question, self.k_facts)) or "none")] if self.use_facts else []
        if self.use_raw:
            hits = self.raw_ix.search(q.question, k=self.k_raw, t_max=now.timestamp())
            hits.sort(key=lambda h: h.ts)
            parts.append("RAW RECORDS:\n" + ("\n".join(h.text for h in hits) or "none"))
        if self.use_digests and self.k_digest:
            dh = self.dig_ix.search(q.question, k=self.k_digest)
            dh.sort(key=lambda h: h.ts)
            parts.append("DIGESTS:\n" + ("\n\n".join(h.text[:4000] for h in dh) or "none"))
        return "\n\n".join(parts)

    def _tools(self, now: datetime):
        if self.use_compute:
            return self._tools_v2(now)
        t = [
            tool(
                "search_facts",
                "Hybrid search over extracted facts. Dates filter on the fact's event date.",
                {
                    "query": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "current_only": {"type": "boolean", "description": "only current (non-superseded) state facts and events"},
                    "k": {"type": "integer"},
                },
                ["query"],
            ),
            tool(
                "entity_history",
                "All facts about an entity (subject or involved entity), oldest first, including superseded values.",
                {"entity": {"type": "string"}, "attribute_contains": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}},
                ["entity"],
            ),
            tool("describe_tables", "Show SQL table schemas, row counts, common attributes/subjects and example rows.", {}, []),
            tool("sql", "Run a read-only SQL SELECT over the memory tables. Max 200 rows returned.", {"query": {"type": "string"}}, ["query"]),
        ]
        if self.use_raw:
            t += [
                tool(
                    "search_records",
                    "Hybrid search over raw records (original text) up to today.",
                    {"query": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "k": {"type": "integer"}},
                    ["query"],
                ),
                tool(
                    "list_records",
                    "List raw records in a date range in time order, optionally filtered by keyword.",
                    {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "contains": {"type": "string"}, "limit": {"type": "integer"}},
                    ["start_date", "end_date"],
                ),
            ]
        if self.use_digests:
            t.append(
                tool(
                    "get_digests",
                    "Get frozen digests of a level (day, week, month) overlapping a date range.",
                    {"level": {"type": "string", "enum": ["day", "week", "month"]}, "start_date": {"type": "string"}, "end_date": {"type": "string"}},
                    ["level", "start_date", "end_date"],
                )
            )
        return t

    def _handlers(self, now: datetime):
        nowt = now.timestamp()

        def search_facts(a):
            rows = self.search_facts(
                a["query"], min(int(a.get("k") or 25), 60), _day_bounds(a.get("start_date"), False), _day_bounds(a.get("end_date"), True), bool(a.get("current_only"))
            )
            return "\n".join(rows) or "no facts"

        def entity_history(a):
            e = f"%{a['entity'].lower()}%"
            sql = "SELECT fact_id FROM facts WHERE (lower(subject) LIKE ? OR lower(entities) LIKE ?)"
            args = [e, e]
            if a.get("attribute_contains"):
                sql += " AND lower(attribute) LIKE ?"
                args.append(f"%{a['attribute_contains'].lower()}%")
            if a.get("start_date"):
                sql += " AND event_date >= ?"
                args.append(a["start_date"][:10])
            if a.get("end_date"):
                sql += " AND event_date <= ?"
                args.append(a["end_date"][:10])
            sql += " ORDER BY event_date LIMIT 150"
            c = self._ro()
            ids = [r[0] for r in c.execute(sql, args)]
            c.close()
            return "\n".join(self._fact_rows(ids)) or "no facts"

        def search_records(a):
            hits = self.raw_ix.search(
                a["query"], k=min(int(a.get("k") or 20), 50), t_min=_day_bounds(a.get("start_date"), False), t_max=min(_day_bounds(a.get("end_date"), True) or nowt, nowt)
            )
            hits.sort(key=lambda h: h.ts)
            return "\n".join(h.text for h in hits) or "no results"

        def list_records(a):
            lo = _day_bounds(a.get("start_date"), False) or 0
            hi = min(_day_bounds(a.get("end_date"), True) or nowt, nowt)
            limit = min(int(a.get("limit") or 100), 300)
            kw = (a.get("contains") or "").lower()
            hits = self.raw_ix.by_time(lo, hi, limit=100000 if kw else limit)
            if kw:
                hits = [h for h in hits if kw in h.text.lower()][:limit]
            return f"{len(hits)} shown (of {self.raw_ix.count(lo, hi)} records in range)\n" + "\n".join(h.text for h in hits)

        def get_digests(a):
            lvl = a.get("level", "week")
            lo, hi = (a.get("start_date") or "0000")[:10], (a.get("end_date") or "9999")[:10]
            sel = [x for x in self.digests_seen if x["level"] == lvl and x["end"] >= lo and x["start"] <= hi][:12]
            return "\n\n".join(f"[{x['id']} | {x['start']}..{x['end']}]\n{x['text']}" for x in sel) or "no digests for that range (digests appear only after a period closes)"

        return {
            "search_facts": search_facts,
            "entity_history": entity_history,
            "describe_tables": lambda a: self._describe(),
            "sql": lambda a: self._sql(a.get("query", "")),
            "search_records": search_records,
            "list_records": list_records,
            "get_digests": get_digests,
            "python": lambda a: self._python(a.get("code", ""), now),
        }

    # -- v2: schema card, python compute tool

    def schema_card(self, now: datetime) -> str:
        key = now.date().isoformat()
        cached = getattr(self, "_card", None)
        if cached and cached[0] == key:
            return cached[1]
        c = self._ro()
        out = []
        n, lo, hi = c.execute("select count(*), min(date), max(date) from records").fetchone()
        out.append(f"records: {n} rows, dates {lo} .. {hi}")
        if len(self.feeds) > 1:
            out.append("  feeds (filter with feed = '...'; meta fields differ by feed): " + ", ".join(
                f"{f_} ({k})" for f_, k in c.execute("select feed, count(*) k from records group by feed order by k desc")))
        out.append("  sources: " + ", ".join(f"{s_} ({k})" for s_, k in c.execute("select source, count(*) k from records group by source order by k desc limit 12")))
        # deterministic sample (every k-th row) so the prompt, and therefore the LLM cache key, is stable across runs
        total_meta = c.execute("select count(*) from records where meta != '{}'").fetchone()[0]
        step = max(1, total_meta // 800)
        sample = [json.loads(m) for (m,) in c.execute("select meta from records where meta != '{}' and rowid % ? = 0 limit 800", (step,))]
        keys: dict[str, set] = {}
        for m in sample:
            for k_, v in (m or {}).items():
                keys.setdefault(k_, set()).add(json.dumps(v)[:60])
        if len(self.feeds) > 1 and self.per_feed_card:
            # one section per feed, each sampled from its own rows, so small feeds are not drowned out by large ones
            for f_ in sorted(self.feeds):
                fn, flo, fhi = c.execute("select count(*), min(date), max(date) from records where feed=?", (f_,)).fetchone()
                fstep = max(1, fn // 300)
                fs = [json.loads(m) for (m,) in c.execute("select meta from records where feed=? and meta != '{}' and rowid % ? = 0 limit 300", (f_, fstep))]
                fk: dict[str, set] = {}
                for m in fs:
                    for k_, v in (m or {}).items():
                        fk.setdefault(k_, set()).add(json.dumps(v)[:50])
                out.append(f"  feed '{f_}': {fn} rows, {flo} .. {fhi}" + ("" if fk else " (no meta; use title/text)"))
                for k_, vals in fk.items():
                    vs = sorted(vals)
                    out.append(f"    meta.{k_}: " + ", ".join(vs[:12]) + (f", ... ({len(vs)}+ distinct)" if len(vs) > 12 else ""))
                ex1 = c.execute("select substr(text,1,160) from records where feed=? limit 1", (f_,)).fetchone()
                if ex1:
                    out.append(f"    example text: {ex1[0]}")
            keys = {}
        if keys:
            out.append("  meta fields (from a sample):")
            for k_, vals in keys.items():
                vs = sorted(vals)
                shown = ", ".join(vs[:25]) + (f", ... ({len(vs)}+ distinct)" if len(vs) > 25 else "")
                out.append(f"    {k_}: {shown}")
        else:
            out.append("  meta: empty for these records; use title/text with LIKE and the date column")
        ex = c.execute("select item_id, date, source, title, substr(text,1,200) from records where rowid % ? = 0 limit 3", (max(1, n // 3),)).fetchall()
        out.append("  example rows:")
        out += ["    " + " | ".join(str(x) for x in r) for r in ex]
        if self.use_facts:
            nf = c.execute("select count(*) from facts").fetchone()[0]
            out.append(f"facts: {nf} rows. top attributes: " + ", ".join(f"{a} ({k})" for a, k in c.execute("select attribute, count(*) k from facts group by attribute order by k desc limit 25")))
        c.close()
        card = "\n".join(out)
        self._card = (key, card)
        return card

    def _python(self, code: str, now: datetime) -> str:
        import subprocess
        import sys
        import tempfile

        prelude = PY_PRELUDE.format(uri=f"file:{self.db_path}?mode=ro", today=now.date().isoformat())
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(prelude + "\n" + code)
            path = f.name
        try:
            r = subprocess.run(
                ["sandbox-exec", "-p", SANDBOX, sys.executable, "-B", "-I", path],
                capture_output=True, text=True, timeout=60,
            )
            out = (r.stdout or "") + (("\nSTDERR:\n" + r.stderr[-3000:]) if r.returncode else "")
        except subprocess.TimeoutExpired:
            out = "timeout after 60s"
        finally:
            import os

            os.unlink(path)
        out = out.replace(path, "<code>")  # temp path is random; keep tool output (and the LLM cache key) deterministic
        return out.strip() or "(no output; print your result)"

    def _tools_v2(self, now: datetime):
        t = [
            tool(
                "search_records",
                "Hybrid keyword + semantic search over raw records up to today.",
                {"query": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "k": {"type": "integer"}},
                ["query"],
            ),
            tool(
                "list_records",
                "List raw records in a date range in time order, optionally filtered by keyword.",
                {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "contains": {"type": "string"}, "limit": {"type": "integer"}},
                ["start_date", "end_date"],
            ),
            tool("sql", "Read-only SQLite SELECT over the memory tables (max 200 rows shown).", {"query": {"type": "string"}}, ["query"]),
            tool(
                "python",
                "Run Python 3 (stdlib only, no network, no file writes) with helper sql(query, params=()) -> list of dicts and TODAY. Print results.",
                {"code": {"type": "string"}},
                ["code"],
            ),
        ]
        if self.use_facts:
            t += [
                tool(
                    "search_facts",
                    "Hybrid search over extracted facts. Dates filter on the fact's event date.",
                    {"query": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "current_only": {"type": "boolean"}, "k": {"type": "integer"}},
                    ["query"],
                ),
                tool(
                    "entity_history",
                    "All facts about an entity, oldest first, including superseded values.",
                    {"entity": {"type": "string"}, "attribute_contains": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}},
                    ["entity"],
                ),
            ]
        if self.use_digests:
            t.append(
                tool(
                    "get_digests",
                    "Get frozen digests of a level (day, week, month) overlapping a date range.",
                    {"level": {"type": "string", "enum": ["day", "week", "month"]}, "start_date": {"type": "string"}, "end_date": {"type": "string"}},
                    ["level", "start_date", "end_date"],
                )
            )
        return t

    def answer(self, q, now):
        ctx = self._initial_context(q, now)
        if not self.use_agent:
            return answer_from_context(ctx, q, now, self.tag)
        if self.use_compute:
            system = FACTBASE_V2_SYSTEM.format(
                rules=(ANSWER_RULES_V6 if self.rules_v6 else ANSWER_RULES_CALIBRATED if self.calibrated else ANSWER_RULES).format(today=fmt_day(now)),
                facts_line=FACTS_LINE if self.use_facts else "",
                digest_line=DIGEST_LINE if self.use_digests else "",
                fact_tools="search_facts / entity_history (extracted facts), " if self.use_facts else "",
                card=self.schema_card(now),
            )
            if self.rules_v6:
                system = system.replace("Call final_answer once, with the short exact answer.", "Call final_answer once.")
            user = f"INITIAL CONTEXT:\n{ctx}\n\nQUESTION: {q.question}"
            req = {"sql", "python"} if self.enforce_compute and ANALYTIC.search(q.question) else None
            return run_agent(
                system, user, self._tools(now), self._handlers(now), self.tag, max_steps=self.max_steps, require_one_of=req,
                abstain_guard="search_records" if self.abstain_guard else None,
            )
        system = FACTBASE_SYSTEM.format(rules=ANSWER_RULES.format(today=fmt_day(now)), tables=self.tables())
        user = f"INITIAL CONTEXT:\n{ctx}\n\nQUESTION: {q.question}"
        return run_agent(system, user, self._tools(now), self._handlers(now), self.tag, max_steps=self.max_steps)

    def stats(self):
        c = self._ro()
        st = dict(c.execute("select status, count(*) from facts group by status").fetchall())
        c.close()
        return {"facts": self.n, "status": st, "supersessions": self.supersessions, "raw": len(self.raw_ix), "digests": len(self.dig_ix)}


FACTBASE_V2_SYSTEM = """You are the query agent of a long-term memory built from a continuous stream of time-stamped records.
{rules}

What the memory holds (see the schema card at the end):
- records: every raw record ever received, one SQL row each (item_id, date, ts, source, title, text, meta JSON). Exhaustive and never edited.
{facts_line}{digest_line}
Tools: search_records / list_records (hybrid search and time listing over raw text), {fact_tools}sql (read-only SQLite), python
(stdlib Python 3 with a helper sql(query, params=()) -> list of dict rows; print what you need).

Routing:
- Single facts (a value, a date, who/what/where): use the initial context or search, then verify against the raw record text.
- Counts, totals, averages, maxima/minima, "first/last time", "latest as of <date>", rankings, league tables/standings, streaks and
  differences between dates: compute them exhaustively with sql or python over records (json_extract(meta,'$.field') for
  structured fields, the date column for time, LIKE on title/text for keywords). Never count or rank from search results, and never
  abstain just because no precomputed answer exists: compute it from the records.
- Check filters before trusting a number: print the match count and a few example rows. Mind inclusive date bounds, "strictly
  above", and that "as of D" means only records with date <= D.
Call final_answer once, with the short exact answer.

SCHEMA CARD:
{card}"""

FACTS_LINE = (
    "- facts: atomic facts extracted from records (subject, attribute, object, number, event_date, kind state/event, status\n"
    "  current/superseded with valid_to). Useful for entity histories and what replaced what; numbers in facts are LLM-extracted,\n"
    "  so prefer records for exact values.\n"
)
DIGEST_LINE = "- digests: frozen day/week/month summaries (get_digests) for overviews of a period.\n"

# Questions whose answer needs an exhaustive pass over many records (v3 compute enforcement). Generic wording only.
ANALYTIC = re.compile(
    r"(?i)\b(how many|number of|total|in total|highest|lowest|maximum|minimum|max|min|most recent|latest|first|last|"
    r"earlier|earliest|as of|top of the table|position|points|longest|average|mean|rank|streak|consecutive|"
    r"which .* (more|higher|lower|first)|count)\b"
)

PY_PRELUDE = """import sqlite3, json, re, math, statistics, collections, itertools, datetime
from collections import Counter, defaultdict
_DB = sqlite3.connect({uri!r}, uri=True)
def sql(query, params=()):
    cur = _DB.execute(query, params)
    cols = [d[0] for d in (cur.description or [])]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
TODAY = {today!r}
"""

SANDBOX = '(version 1)(allow default)(deny network*)(deny file-write*)(allow file-write* (literal "/dev/null"))'


CLASSES = {"fact_memory": FactMemory, "rollups": Rollups, "factbase": Factbase}
