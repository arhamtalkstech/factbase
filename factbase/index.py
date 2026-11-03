"""Hybrid search index: SQLite FTS5 (BM25) + dense vectors, with hard time filters.

Used by every retrieval-based architecture over whatever unit it stores (raw items,
facts, rollups). Documents are added incrementally as the simulated clock advances.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass

import numpy as np

from . import embed as E

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*")
STOP = set(
    "a an the of in on at to for from by with and or is was were be been are what which who whom whose when where why how "
    "did does do as that this these those it its into than then there their they he she his her not no yes about after before "
    "during between over under up down out per vs most more least many much any all each".split()
)


def fts_query(q: str) -> str:
    toks = []
    for w in _WORD.findall(q):
        w = w.strip(".'-").lower()
        if len(w) < 2 or w in STOP:
            continue
        toks.append('"' + w.replace('"', "") + '"')
    return " OR ".join(dict.fromkeys(toks))


@dataclass
class Hit:
    doc_id: str
    text: str
    ts: float
    kind: str
    score: float


class HybridIndex:
    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("CREATE TABLE docs (rid INTEGER PRIMARY KEY, doc_id TEXT UNIQUE, ts REAL, kind TEXT, text TEXT, active INTEGER DEFAULT 1)")
        self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='docs', content_rowid='rid', tokenize='porter unicode61')")
        self.db.execute("CREATE INDEX docs_ts ON docs(ts)")
        self.lock = threading.RLock()
        self._cap = 1024
        self.vecs = np.zeros((self._cap, E.DIM), dtype=np.float32)
        self.ts = np.zeros((self._cap,), dtype=np.float64)
        self.active = np.zeros((self._cap,), dtype=bool)
        self.kinds: list[str] = []
        self.ids: list[str] = []
        self.texts: list[str] = []
        self.rid_of: dict[str, int] = {}
        self.kind_arr = np.zeros((self._cap,), dtype=np.int16)
        self.kind_codes: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self.ids)

    def add(self, docs: list[tuple[str, float, str, str]], embed_texts: list[str] | None = None) -> None:
        """docs: (doc_id, ts_epoch, kind, text). Optional separate text to embed."""
        if not docs:
            return
        with self.lock:
            keep = [n for n, d in enumerate(docs) if d[0] not in self.rid_of]
            if not keep:
                return
            new = [docs[n] for n in keep]
            vecs = E.embed([embed_texts[n] for n in keep] if embed_texts else [d[3] for d in new])
            start = len(self.ids)
            need = start + len(new)
            if need > self._cap:
                while self._cap < need:
                    self._cap *= 2
                for name in ("vecs", "ts", "active", "kind_arr"):
                    old = getattr(self, name)
                    grown = np.zeros((self._cap,) + old.shape[1:], dtype=old.dtype)
                    grown[: len(self.ids)] = old[: len(self.ids)]
                    setattr(self, name, grown)
            rows = []
            for n, (doc_id, ts, kind, text) in enumerate(new):
                rid = start + n
                rows.append((rid, doc_id, ts, kind, text))
                self.ids.append(doc_id)
                self.texts.append(text)
                self.kinds.append(kind)
                self.rid_of[doc_id] = rid
                self.kind_arr[rid] = self.kind_codes.setdefault(kind, len(self.kind_codes))
            self.db.executemany("INSERT INTO docs (rid, doc_id, ts, kind, text) VALUES (?,?,?,?,?)", rows)
            self.db.executemany("INSERT INTO fts (rowid, text) VALUES (?, ?)", [(r[0], r[4]) for r in rows])
            self.vecs[start:need] = vecs
            self.ts[start:need] = [d[1] for d in new]
            self.active[start:need] = True

    def deactivate(self, doc_id: str) -> None:
        with self.lock:
            rid = self.rid_of.get(doc_id)
            if rid is None:
                return
            self.active[rid] = False
            self.db.execute("UPDATE docs SET active=0 WHERE rid=?", (rid,))

    def search(
        self,
        query: str,
        k: int = 20,
        t_min: float | None = None,
        t_max: float | None = None,
        kinds: list[str] | None = None,
        include_inactive: bool = True,
        mode: str = "hybrid",
        pool: int = 100,
    ) -> list[Hit]:
        if not self.ids:
            return []
        lo = -1e18 if t_min is None else t_min
        hi = 1e18 if t_max is None else t_max
        ranks: dict[int, float] = {}
        if mode in ("hybrid", "bm25"):
            fq = fts_query(query)
            if fq:
                sql = "SELECT d.rid FROM fts JOIN docs d ON d.rid = fts.rowid WHERE fts MATCH ? AND d.ts >= ? AND d.ts <= ?"
                args: list = [fq, lo, hi]
                if kinds:
                    sql += f" AND d.kind IN ({','.join('?' * len(kinds))})"
                    args += kinds
                if not include_inactive:
                    sql += " AND d.active = 1"
                sql += " ORDER BY bm25(fts) LIMIT ?"
                args.append(pool)
                with self.lock:
                    rows = self.db.execute(sql, args).fetchall()
                for r, (rid,) in enumerate(rows):
                    ranks[rid] = ranks.get(rid, 0.0) + 1.0 / (60 + r)
        if mode in ("hybrid", "dense"):
            qv = E.embed_query(query)
            with self.lock:
                n = len(self.ids)
                mask = (self.ts[:n] >= lo) & (self.ts[:n] <= hi)
                if kinds:
                    codes = [self.kind_codes[k] for k in kinds if k in self.kind_codes]
                    mask &= np.isin(self.kind_arr[:n], codes)
                if not include_inactive:
                    mask &= self.active[:n]
                sims = self.vecs[:n] @ qv
            sims = np.where(mask, sims, -1e9)
            top = np.argsort(-sims)[:pool]
            for r, rid in enumerate(top):
                if sims[rid] <= -1e8:
                    break
                ranks[int(rid)] = ranks.get(int(rid), 0.0) + 1.0 / (60 + r)
        best = sorted(ranks.items(), key=lambda x: -x[1])[:k]
        return [Hit(self.ids[r], self.texts[r], float(self.ts[r]), self.kinds[r], s) for r, s in best]

    def by_time(self, t_min: float, t_max: float, kinds: list[str] | None = None, limit: int = 200) -> list[Hit]:
        sql = "SELECT rid FROM docs WHERE ts >= ? AND ts <= ?"
        args: list = [t_min, t_max]
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args += kinds
        sql += " ORDER BY ts LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        return [Hit(self.ids[r], self.texts[r], float(self.ts[r]), self.kinds[r], 0.0) for (r,) in rows]

    def count(self, t_min: float, t_max: float) -> int:
        with self.lock:
            return self.db.execute("SELECT count(*) FROM docs WHERE ts >= ? AND ts <= ?", (t_min, t_max)).fetchone()[0]

    def get(self, doc_id: str) -> Hit | None:
        with self.lock:
            row = self.db.execute("SELECT rid FROM docs WHERE doc_id=?", (doc_id,)).fetchone()
        if not row:
            return None
        r = row[0]
        return Hit(self.ids[r], self.texts[r], float(self.ts[r]), self.kinds[r], 0.0)
