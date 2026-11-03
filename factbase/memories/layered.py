"""Factbase v7: layered memory additions on top of the v6 design.

Every addition is a switch, so the evaluation can measure each one on its own:

  extract_v2   facts carry a topic label, a memory type and a 0-100 priority (one extraction call, as before)
  threads      topic labels are merged, in time order, into persistent threads (storylines / conversation topics);
               tools list_threads and get_thread; relevant threads are shown in the initial context
  typed        fact search ranks by relevance first and priority second; nothing is ever dropped for low priority
  profile      a standing profile rebuilt from current preference/instruction/state/plan facts (never rewritten from its
               own previous version), every bullet citing fact ids, placed in the stable part of the prompt
  conflicts    non-destructive conflict resolution: each new state-like fact is compared with similar existing facts and
               marked duplicate / updates / contradicts; replaced facts are marked superseded, never deleted
  offload      reversible offload of the agent's working memory: older tool outputs become stubs, open_ref restores them
  budget       maximum number of search calls per question
  read_records drill-down tool: exact raw records by id, so every derived statement can be traced to its evidence

export_views() writes the derived layers as readable Markdown (profile, one file per thread) for human review.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np

from .. import embed as E
from .. import llm
from ..types import Item, Question, fmt_day
from .base import ANSWER_RULES_V6, run_agent, tool
from .baselines import _day_bounds
from .structured import (
    ANALYTIC,
    DIGEST_LINE,
    EXTRACT_SYSTEM,
    FACTBASE_V2_SYSTEM,
    INGEST_WORKERS,
    Factbase,
    _epoch,
    day_chunks,
    norm,
    speaker_view,
)

# ---------------------------------------------------------------- extraction v2

EXTRACT_SYSTEM_V2 = EXTRACT_SYSTEM + """

Also give each fact:
- topic: a short, stable label (3-8 words) for the ongoing thread, storyline or subject the fact belongs to, e.g. "Kitchen
  renovation", "Strait of Hormuz shipping", "Arsenal 2025-26 season". Unrelated conversations or storylines may be interleaved
  in the records: give each its own topic, and reuse exactly the same label for the same thread.
- mem_type: "preference" (likes, dislikes, habits, values), "instruction" (a standing request about how to behave or answer),
  "plan" (an intention or a scheduled future event), "state" (a current value or status that a later value replaces), or
  "event" (something that happened).
- priority: 0-100, how likely the fact matters for later questions (identity, health, money, major events and decisions
  80-100; ordinary facts 40-70; trivia 0-30). Never leave a fact out because of low priority."""

_FACT_PROPS_V2 = {
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
    "topic": {"type": "string"},
    "mem_type": {"type": "string", "enum": ["preference", "instruction", "plan", "state", "event"]},
    "priority": {"type": "integer"},
}
FACT_SCHEMA_V2 = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": _FACT_PROPS_V2, "required": list(_FACT_PROPS_V2)}}},
    "required": ["facts"],
}


def extract_chunk_v2(chunk: list[Item], tag: str) -> list[dict]:
    recs = "\n".join(it.render()[:16000] for it in chunk)
    try:
        r = llm.ask_json(EXTRACT_SYSTEM_V2, f"RECORDS:\n{recs}", FACT_SCHEMA_V2, tag=tag, schema_name="facts", timeout=420, max_attempts=2)
    except Exception:
        try:
            r = llm.ask_json(EXTRACT_SYSTEM_V2, f"RECORDS:\n{recs}", FACT_SCHEMA_V2, tag=tag, schema_name="facts", timeout=420, max_attempts=2, max_tokens=12000)
        except Exception:
            return []
    ids = {it.id for it in chunk}
    out = []
    for f in r.get("facts") or []:
        if not isinstance(f, dict) or not f.get("statement"):
            continue
        f["source_ids"] = [s for s in (f.get("source_ids") or []) if s in ids] or [chunk[0].id]
        ed = str(f.get("event_date") or "")[:10]
        try:
            date.fromisoformat(ed)
        except ValueError:
            ed = chunk[0].ts.date().isoformat()
        f["event_date"] = ed
        try:
            f["priority"] = max(0, min(100, int(f.get("priority") or 50)))
        except (TypeError, ValueError):
            f["priority"] = 50
        f["topic"] = (f.get("topic") or "").strip()[:80] or "general"
        if f.get("mem_type") not in ("preference", "instruction", "plan", "state", "event"):
            f["mem_type"] = "state" if f.get("kind") == "state" else "event"
        out.append(f)
    return out


# ---------------------------------------------------------------- conflict resolution and profile prompts

CONFLICT_SYSTEM = """You maintain a long-term memory that never deletes anything. For each NEW fact, compare it with the
EXISTING facts listed under it and choose one relation:
- "new": it adds information that is not already in the existing facts.
- "duplicate": it says the same thing as an existing fact, with nothing new. Give that fact's id.
- "updates": same subject and property with a newer or corrected value (a new count, a changed plan, a new address, a revised
  figure). Give the ids of the facts it replaces.
- "contradicts": it conflicts with an existing fact and it is unclear which is right. Give the ids.
Use the dates: a later statement about the same thing usually updates an earlier one. Separate events that happened at
different times are "new", not updates."""

CONFLICT_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string"},
                    "relation": {"type": "string", "enum": ["new", "duplicate", "updates", "contradicts"]},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["fact_id", "relation", "target_ids"],
            },
        }
    },
    "required": ["decisions"],
}

PROFILE_SYSTEM = """Write a standing profile of {who} from the facts below: who they are, stable preferences and dislikes,
standing instructions, current situation, and plans. One bullet per point. When facts disagree, the newest wins. End every
bullet with the ids of the facts it rests on in brackets, e.g. [F12, F40]. At most 250 words. Use only the facts given."""

V7_THREADS = """- threads: facts grouped into persistent topics or storylines (list_threads, get_thread). Use them to separate
  interleaved conversations or storylines and to follow one thread over time.
"""
V7_TYPES = """- every fact has a memory type (preference / instruction / plan / state / event) and a priority; superseded, duplicate
  and disputed facts are kept and marked, never deleted.
"""
V7_DRILL = "- read_records returns raw records by id: use it to drill down from a fact, thread or profile bullet to its evidence.\n"

PROFILE_BLOCK = """
STANDING PROFILE (derived from facts; each bullet cites fact ids; verify details in facts or records before relying on them):
{profile}
"""


class FactbaseV7(Factbase):
    name = "factbase_v7"

    def __init__(
        self,
        dataset,
        workdir,
        extract_v2: bool = True,
        threads: bool = True,
        typed: bool = True,
        profile: bool = False,
        profile_subject: str = "the user",
        profile_every: int = 30,
        conflicts: bool = True,
        offload: bool = True,
        budget: int | None = 6,
        thread_sim: float = 0.75,
        context_budget_s: float = 2.0,
        **cfg,
    ):
        super().__init__(dataset, workdir, **cfg)
        self.extract_v2, self.use_threads, self.use_typed = extract_v2, threads, typed
        self.use_profile, self.profile_subject, self.profile_every = profile, profile_subject, profile_every
        self.use_conflicts, self.use_offload, self.budget = conflicts, offload, budget
        self.thread_sim, self.context_budget_s = thread_sim, context_budget_s
        self.db.executescript(
            """
            ALTER TABLE facts ADD COLUMN topic TEXT;
            ALTER TABLE facts ADD COLUMN mem_type TEXT;
            ALTER TABLE facts ADD COLUMN priority INTEGER;
            ALTER TABLE facts ADD COLUMN thread_id TEXT;
            ALTER TABLE facts ADD COLUMN duplicate_of TEXT;
            ALTER TABLE facts ADD COLUMN relation TEXT;
            CREATE INDEX facts_thread ON facts(thread_id);
            CREATE TABLE threads (thread_id TEXT PRIMARY KEY, label TEXT, feed TEXT, first_date TEXT, last_date TEXT, n_facts INTEGER);
            CREATE TABLE relations (fact_id TEXT, other_id TEXT, relation TEXT, decided_at TEXT);
            """
        )
        self.thread_keys: dict[str, str] = {}
        self.thread_vecs = np.zeros((0, E.DIM), dtype=np.float32)
        self.thread_ids: list[str] = []
        self.profile_text = ""
        self.profile_pending = 0
        self.profile_builds = 0
        self.relation_counts: dict[str, int] = {}
        self.ingest_usd = 0.0

    # -- ingestion

    def prepare(self, items):
        if not (self.use_facts and self.extract_v2):
            return super().prepare(items)
        src = speaker_view(items) if self.extract_speaker_only else items
        chunks = day_chunks(src)
        jobs = [(d, ch) for d, chs in chunks.items() for ch in chs]
        res = llm.pmap(lambda j: (j[0], extract_chunk_v2(j[1], tag=f"extract2:{self.dataset}")), jobs, workers=INGEST_WORKERS)
        for r in res:
            if isinstance(r, Exception):
                continue
            d, facts = r
            self.by_day.setdefault(d, []).extend(facts)
        if self.use_digests:
            from .structured import _Revealer, build_digests

            self.rev = _Revealer(build_digests(items, tag=f"rollup:{self.dataset}"))

    def _thread_for(self, label: str, feed: str, day: str) -> str:
        key = norm(label)
        tid = self.thread_keys.get(key)
        if tid is None and len(self.thread_ids):
            v = E.embed([label])[0]
            sims = self.thread_vecs @ v
            j = int(np.argmax(sims))
            if sims[j] >= self.thread_sim:
                tid = self.thread_ids[j]
                self.thread_keys[key] = tid
        if tid is None:
            tid = f"T{len(self.thread_ids) + 1}"
            self.thread_ids.append(tid)
            self.thread_vecs = np.vstack([self.thread_vecs, E.embed([label])])
            self.thread_keys[key] = tid
            self.db.execute("INSERT INTO threads VALUES (?,?,?,?,?,0)", (tid, label, feed, day, day))
        self.db.execute(
            "UPDATE threads SET n_facts = n_facts + 1, first_date = min(first_date, ?), last_date = max(last_date, ?) WHERE thread_id=?",
            (day, day, tid),
        )
        return tid

    def ingest(self, items, now):
        if not (self.use_facts and self.extract_v2):
            return super().ingest(items, now)
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
            n_before = len(self.facts_ix)
            new_ids, docs = [], []
            for f in facts:
                fid = f"F{self.n}"
                self.n += 1
                self._insert_fact(fid, f, items[0].ts.isoformat())
                tid = self._thread_for(f["topic"], items[0].dataset, f["event_date"]) if self.use_threads else None
                self.db.execute(
                    "UPDATE facts SET topic=?, mem_type=?, priority=?, thread_id=? WHERE fact_id=?",
                    (f["topic"], f["mem_type"], f["priority"], tid, fid),
                )
                new_ids.append(fid)
                docs.append((fid, _epoch(f["event_date"]), "fact", f["statement"]))
            if self.use_conflicts and n_before and new_ids:
                self._resolve_conflicts(new_ids, facts, n_before, now)
            self.facts_ix.add(docs)
            if self.use_profile:
                self.profile_pending += sum(1 for f in facts if f["mem_type"] in ("preference", "instruction", "state", "plan"))
                if self.profile_pending >= self.profile_every or (not self.profile_text and self.profile_pending >= 5):
                    self._build_profile(now)
            self.db.commit()

    def _resolve_conflicts(self, new_ids: list[str], facts: list[dict], n_before: int, now: datetime) -> None:
        cand_types = ("preference", "instruction", "plan", "state")
        pick = [(fid, f) for fid, f in zip(new_ids, facts) if f["mem_type"] in cand_types or f.get("kind") == "state"]
        if not pick:
            return
        old_vecs = self.facts_ix.vecs[:n_before]
        old_ids = self.facts_ix.ids[:n_before]
        q = E.embed([f["statement"] for _, f in pick])
        sims = q @ old_vecs.T
        blocks: list[str] = []
        known: set[str] = set()
        for i, (fid, f) in enumerate(pick):
            order = np.argsort(-sims[i])[:5]
            cands = [old_ids[j] for j in order if sims[i][j] >= 0.72]
            # structural candidates: same subject and attribute, earlier facts (cheap, catches paraphrased updates)
            sk, ak = norm(f["subject"]), norm(f["attribute"])
            cands += [r[0] for r in self.db.execute(
                "SELECT fact_id FROM facts WHERE subject_key=? AND attribute_key=? AND fact_id NOT IN (" + ",".join("?" * len(new_ids)) + ") "
                "ORDER BY event_date DESC LIMIT 3", (sk, ak, *new_ids))]
            cands = list(dict.fromkeys(cands))
            if not cands:
                continue
            rows = self.db.execute(
                f"SELECT fact_id, event_date, statement, status FROM facts WHERE fact_id IN ({','.join('?' * len(cands))}) "
                "AND status IN ('current','event') AND (duplicate_of IS NULL)",
                cands,
            ).fetchall()
            if not rows:
                continue
            known.update({r[0] for r in rows})
            blocks.append(f"NEW {fid} ({f['event_date']}): {f['statement']}\n" + "\n".join(f"  EXISTING {r[0]} ({r[1]}): {r[2]}" for r in rows))
        if not blocks:
            return
        for start in range(0, len(blocks), 25):
            r = llm.chat(
                [{"role": "system", "content": CONFLICT_SYSTEM}, {"role": "user", "content": "\n\n".join(blocks[start:start + 25])}],
                schema=CONFLICT_SCHEMA, tag=f"conflict:{self.dataset}", timeout=300, max_attempts=3,
            )
            self.ingest_usd += r["usage"]["usd"]
            dec = (r["content"] or {}).get("decisions", []) if isinstance(r["content"], dict) else []
            for x in dec:
                fid, rel = x.get("fact_id"), x.get("relation")
                # duplicates may point at another new fact of the same batch; updates/contradictions only at older facts
                allowed = known | (set(new_ids) - {fid}) if rel == "duplicate" else known
                targets = [t for t in (x.get("target_ids") or []) if t in allowed]
                if fid not in new_ids or rel not in ("duplicate", "updates", "contradicts") or not targets:
                    continue
                self.relation_counts[rel] = self.relation_counts.get(rel, 0) + 1
                ev = self.db.execute("SELECT event_date FROM facts WHERE fact_id=?", (fid,)).fetchone()[0]
                for t in targets:
                    self.db.execute("INSERT INTO relations VALUES (?,?,?,?)", (fid, t, rel, now.isoformat()))
                if rel == "duplicate":
                    self.db.execute("UPDATE facts SET duplicate_of=?, relation='duplicate' WHERE fact_id=?", (targets[0], fid))
                elif rel == "updates":
                    for t in targets:
                        self.db.execute(
                            "UPDATE facts SET status='superseded', valid_to=?, superseded_by=?, relation='updated' WHERE fact_id=? AND status IN ('current','event')",
                            (ev, fid, t),
                        )
                        self.supersessions += 1
                else:
                    self.db.execute("UPDATE facts SET relation='disputed' WHERE fact_id IN (?" + ",?" * len(targets) + ")", [fid, *targets])

    def _build_profile(self, now: datetime) -> None:
        rows = self.db.execute(
            "SELECT fact_id, event_date, statement FROM facts WHERE mem_type IN ('preference','instruction','state','plan') "
            "AND status IN ('current','event') AND duplicate_of IS NULL ORDER BY priority DESC, event_date DESC LIMIT 150"
        ).fetchall()
        if not rows:
            return
        rows.sort(key=lambda r: r[1])
        body = "\n".join(f"[{r[0]} | {r[1]}] {r[2]}" for r in rows)
        r = llm.chat(
            [{"role": "system", "content": PROFILE_SYSTEM.format(who=self.profile_subject)}, {"role": "user", "content": f"TODAY: {fmt_day(now)}\n\nFACTS:\n{body}"}],
            tag=f"profile:{self.dataset}", timeout=300, max_attempts=3,
        )
        self.ingest_usd += r["usage"]["usd"]
        if r["content"]:
            self.profile_text = r["content"].strip()
            self.profile_builds += 1
        self.profile_pending = 0

    # -- query side

    def _fact_rows(self, fids: list[str]) -> list[str]:
        if not (self.use_facts and self.extract_v2) or not fids:
            return super()._fact_rows(fids)
        c = self._ro()
        rows = c.execute(
            "SELECT f.fact_id, f.event_date, f.period, f.kind, f.status, f.valid_to, f.statement, f.source_ids, f.mem_type, f.priority, "
            "f.thread_id, t.label, f.relation, f.duplicate_of FROM facts f LEFT JOIN threads t ON t.thread_id = f.thread_id "
            f"WHERE f.fact_id IN ({','.join('?' * len(fids))})",
            fids,
        ).fetchall()
        c.close()
        order = {f: i for i, f in enumerate(fids)}
        rows.sort(key=lambda r: order.get(r[0], 0))
        out = []
        for fid, ed, per, kind, st, vt, stmt, src, mt, pr, tid, label, rel, dup in rows:
            tags = [f"event {ed}"]
            if per:
                tags.append(f"period {per}")
            tags.append(f"{mt} p{pr}")
            if kind == "state" or st == "superseded":
                tags.append(st + (f" until {vt}" if vt else ""))
            if rel in ("disputed",):
                tags.append("DISPUTED")
            if dup:
                tags.append(f"duplicate of {dup}")
            if tid and self.use_threads:
                tags.append(f"thread {tid}: {label}")
            tags.append("src " + ",".join(json.loads(src)[:3]))
            out.append(f"[{fid} | {' | '.join(tags)}] {stmt}")
        return out

    def search_facts(self, query: str, k: int, t_min=None, t_max=None, current_only=False) -> list[str]:
        if not (self.use_facts and self.extract_v2):
            return super().search_facts(query, k, t_min, t_max, current_only)
        hits = self.facts_ix.search(query, k=k * 2, t_min=t_min, t_max=t_max)
        if not hits:
            return []
        ids = [h.doc_id for h in hits]
        c = self._ro()
        meta = {
            r[0]: r[1:]
            for r in c.execute(
                f"SELECT fact_id, priority, status, duplicate_of FROM facts WHERE fact_id IN ({','.join('?' * len(ids))})", ids
            )
        }
        c.close()
        keep = []
        for rank, fid in enumerate(ids):
            pr, st, dup = meta.get(fid, (50, "current", None))
            if dup:
                continue  # duplicates stay stored and visible via get_thread / read_records, not in search results
            if current_only and st == "superseded":
                continue
            # relevance first; priority can lift a fact by up to four places
            score = rank - ((pr or 50) / 25.0 if self.use_typed else 0.0)
            keep.append((score, rank, fid))
        keep.sort()
        chosen = [fid for _, _, fid in keep[:k]]
        # show chosen facts in time order
        c = self._ro()
        dates = dict(c.execute(f"SELECT fact_id, event_date FROM facts WHERE fact_id IN ({','.join('?' * len(chosen))})", chosen).fetchall()) if chosen else {}
        c.close()
        chosen.sort(key=lambda f: dates.get(f, ""))
        return self._fact_rows(chosen)

    def _thread_search(self, query: str, k: int = 5) -> list[tuple]:
        if not self.thread_ids:
            return []
        v = E.embed_query(query)
        sims = self.thread_vecs @ v
        order = np.argsort(-sims)[:k]
        c = self._ro()
        out = []
        for j in order:
            tid = self.thread_ids[int(j)]
            r = c.execute("SELECT thread_id, label, first_date, last_date, n_facts FROM threads WHERE thread_id=?", (tid,)).fetchone()
            if r:
                out.append(r)
        c.close()
        return out

    def _initial_context(self, q: Question, now: datetime) -> str:
        t0 = time.time()
        ctx = super()._initial_context(q, now)
        if self.use_facts and self.use_threads and time.time() - t0 < self.context_budget_s:
            th = self._thread_search(q.question, k=4)
            if th:
                ctx = "RELEVANT THREADS (get_thread for the full thread):\n" + "\n".join(
                    f"{tid}: {label} ({a} .. {b}, {n} facts)" for tid, label, a, b, n in th
                ) + "\n\n" + ctx
        return ctx

    def _tools_v2(self, now: datetime):
        t = super()._tools_v2(now)
        t.append(tool("read_records", "Read raw records by id (exact original text), e.g. to verify a fact's source ids.",
                      {"ids": {"type": "array", "items": {"type": "string"}}}, ["ids"]))
        if self.use_facts and self.use_threads:
            t += [
                tool("list_threads", "Find threads (topics / storylines) relevant to a query, with date ranges and fact counts.",
                     {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"]),
                tool("get_thread", "All facts of one thread in time order, including superseded, duplicate and disputed ones.",
                     {"thread_id": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}}, ["thread_id"]),
            ]
        return t

    def _handlers(self, now: datetime):
        h = super()._handlers(now)
        nowt = now.timestamp()

        def read_records(a):
            out = []
            for rid in (a.get("ids") or [])[:20]:
                hit = self.raw_ix.get(str(rid))
                if hit and hit.ts <= nowt:
                    out.append(hit.text)
                else:
                    out.append(f"{rid}: not found")
            return "\n".join(out) or "no ids given"

        def list_threads(a):
            th = self._thread_search(a.get("query", ""), k=min(int(a.get("k") or 8), 20))
            return "\n".join(f"{tid}: {label} ({x} .. {y}, {n} facts)" for tid, label, x, y, n in th) or "no threads"

        def get_thread(a):
            sql = "SELECT fact_id FROM facts WHERE thread_id=?"
            args: list = [a.get("thread_id", "")]
            if a.get("start_date"):
                sql += " AND event_date >= ?"
                args.append(a["start_date"][:10])
            if a.get("end_date"):
                sql += " AND event_date <= ?"
                args.append(a["end_date"][:10])
            c = self._ro()
            ids = [r[0] for r in c.execute(sql + " ORDER BY event_date, fact_id LIMIT 200", args)]
            c.close()
            rows = self._fact_rows(ids)
            return "\n".join(rows) or "no facts in that thread"

        h.update({"read_records": read_records, "list_threads": list_threads, "get_thread": get_thread})
        return h

    def answer(self, q, now):
        ctx = self._initial_context(q, now)
        facts_line = ""
        if self.use_facts:
            facts_line = (
                "- facts: atomic facts extracted from records (subject, attribute, object, number, event_date, kind, status\n"
                "  current/superseded with valid_to). Numbers in facts are LLM-extracted, so prefer records for exact values.\n"
            )
            if self.extract_v2:
                facts_line += (V7_THREADS if self.use_threads else "") + V7_TYPES
        facts_line += V7_DRILL
        system = FACTBASE_V2_SYSTEM.format(
            rules=ANSWER_RULES_V6.format(today=fmt_day(now)),
            facts_line=facts_line,
            digest_line=DIGEST_LINE if self.use_digests else "",
            fact_tools=("search_facts / entity_history / list_threads / get_thread (facts and threads), " if self.use_facts and self.use_threads
                        else "search_facts / entity_history (extracted facts), " if self.use_facts else ""),
            card=self.schema_card(now),
        ).replace("Call final_answer once, with the short exact answer.", "Call final_answer once.")
        if self.use_profile and self.profile_text:
            system += PROFILE_BLOCK.format(profile=self.profile_text)
        user = f"INITIAL CONTEXT:\n{ctx}\n\nQUESTION: {q.question}"
        req = {"sql", "python"} if self.enforce_compute and ANALYTIC.search(q.question) else None
        return run_agent(
            system, user, self._tools(now), self._handlers(now), self.tag, max_steps=self.max_steps, require_one_of=req,
            abstain_guard="search_records" if self.abstain_guard else None,
            offload_keep=1 if self.use_offload else None, search_budget=self.budget,
        )

    # -- human-readable views

    def export_views(self, out_dir: Path) -> Path:
        """Write the derived layers as Markdown: index.md, profile.md, threads/<id>.md. Every line keeps its fact and
        source ids so a reader can drill down to the raw records."""
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "threads").mkdir(exist_ok=True)
        c = self._ro()
        th = c.execute("SELECT thread_id, label, first_date, last_date, n_facts FROM threads ORDER BY n_facts DESC").fetchall()
        idx = ["# Memory views", "", f"{self.n} facts, {len(th)} threads, profile builds: {self.profile_builds}.", "", "| thread | label | from | to | facts |", "|---|---|---|---|---|"]
        for tid, label, a, b, n in th:
            idx.append(f"| [{tid}](threads/{tid}.md) | {label} | {a} | {b} | {n} |")
            ids = [r[0] for r in c.execute("SELECT fact_id FROM facts WHERE thread_id=? ORDER BY event_date, fact_id", (tid,))]
            lines = [f"# {tid}: {label}", ""] + [f"- {r}" for r in self._fact_rows(ids)]
            (out_dir / "threads" / f"{tid}.md").write_text("\n".join(lines) + "\n")
        c.close()
        (out_dir / "index.md").write_text("\n".join(idx) + "\n")
        if self.profile_text:
            (out_dir / "profile.md").write_text("# Standing profile\n\n" + self.profile_text + "\n")
        return out_dir

    def stats(self):
        s = super().stats()
        s.update({
            "threads": len(self.thread_ids), "relations": self.relation_counts, "profile_builds": self.profile_builds,
            "ingest_usd_conflicts_profile": round(self.ingest_usd, 4),
        })
        return s


CLASSES = {"factbase_v7": FactbaseV7}
