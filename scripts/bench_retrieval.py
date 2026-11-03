"""Retrieval and SQL latency versus corpus size (no LLM calls).

Uses real Iran headline items (up to 339k) and, beyond that, synthetic copies of them (text suffixed, vectors
re-normalised with small noise) to reach 1M and 3M rows. Reports median and p95 latency per operation.

uv run python scripts/bench_retrieval.py
"""

from __future__ import annotations

import json
import random
import sqlite3
import statistics
import time
from pathlib import Path

import numpy as np

from factbase import embed as E
from factbase.index import fts_query
from factbase.types import Item

ROOT = Path(__file__).resolve().parents[1]
QUERIES = [
    "Iran seizes tanker in the Strait of Hormuz",
    "US strikes Houthi targets in Yemen",
    "IAEA inspectors Natanz enrichment",
    "Brent crude oil price jumps after attack",
    "Araghchi talks in Oman with Witkoff",
    "Israel strikes Iranian nuclear facilities",
    "sanctions on Iranian oil exports",
    "Khamenei speech on negotiations",
]


def timeit(fn, reps=3):
    out = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return out


def main() -> None:
    items = [Item.from_json(json.loads(l)) for l in open(ROOT / "data" / "iran_headlines" / "items.jsonl")]
    texts = [i.render() for i in items]
    base_vecs = E.embed(texts)  # cached
    qv = [E.embed_query(q) for q in QUERIES]
    rng = np.random.default_rng(0)
    rows = []
    for n in (10_000, 100_000, 339_210, 1_000_000, 3_000_000):
        # vectors: real up to 339k, then noisy copies
        reps = -(-n // len(texts))
        V = np.vstack([base_vecs] * reps)[:n].astype(np.float32)
        if n > len(texts):
            V[len(texts):] += rng.normal(0, 0.02, V[len(texts):].shape).astype(np.float32)
            V[len(texts):] /= np.linalg.norm(V[len(texts):], axis=1, keepdims=True)
        ts = np.arange(n, dtype=np.float64)
        dense = []
        for q in qv:
            def f():
                sims = V @ q
                sims = np.where(ts <= n * 0.9, sims, -1e9)
                np.argpartition(-sims, 100)[:100]
            dense += timeit(f)
        V16 = V.astype(np.float16)
        dense16 = []
        for q in qv:
            q16 = q.astype(np.float16)
            dense16 += timeit(lambda: np.argpartition(-(V16 @ q16), 100)[:100])
        del V, V16
        # BM25 (FTS5) and SQL over the same number of rows
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE docs (rid INTEGER PRIMARY KEY, ts REAL, date TEXT, text TEXT)")
        db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='docs', content_rowid='rid', tokenize='porter unicode61')")
        batch = []
        for i in range(n):
            t = texts[i % len(texts)] + ("" if i < len(texts) else f" copy{i // len(texts)}")
            batch.append((i, float(i), items[i % len(items)].ts.date().isoformat(), t))
            if len(batch) == 50_000:
                db.executemany("INSERT INTO docs VALUES (?,?,?,?)", batch)
                db.executemany("INSERT INTO fts (rowid, text) VALUES (?,?)", [(b[0], b[3]) for b in batch])
                batch = []
        if batch:
            db.executemany("INSERT INTO docs VALUES (?,?,?,?)", batch)
            db.executemany("INSERT INTO fts (rowid, text) VALUES (?,?)", [(b[0], b[3]) for b in batch])
        db.execute("CREATE INDEX d_date ON docs(date)")
        bm = []
        for q in QUERIES:
            fq = fts_query(q)
            bm += timeit(lambda: db.execute(
                "SELECT d.rid FROM fts JOIN docs d ON d.rid=fts.rowid WHERE fts MATCH ? AND d.ts <= ? ORDER BY bm25(fts) LIMIT 100",
                (fq, n * 0.9)).fetchall())
        sql_count = timeit(lambda: db.execute("SELECT count(*) FROM docs WHERE date BETWEEN '2026-03-01' AND '2026-03-31'").fetchone(), 5)
        sql_like = timeit(lambda: db.execute("SELECT count(*) FROM docs WHERE date BETWEEN '2026-03-01' AND '2026-03-31' AND text LIKE '%hormuz%'").fetchone(), 5)
        sql_scan = timeit(lambda: db.execute("SELECT count(*) FROM docs WHERE text LIKE '%hormuz%'").fetchone(), 3)
        db.close()

        def ms(xs):
            xs = sorted(xs)
            return f"{1000 * statistics.median(xs):.1f} / {1000 * xs[int(0.95 * (len(xs) - 1))]:.1f}"

        row = {"rows": n, "dense_f32": ms(dense), "dense_f16": ms(dense16), "bm25": ms(bm), "sql_date_count": ms(sql_count),
               "sql_date_like": ms(sql_like), "sql_full_like": ms(sql_scan)}
        print(json.dumps(row), flush=True)
        rows.append(row)
    lines = ["| rows | dense f32 | dense f16 | BM25 top-100 | SQL count by date | SQL date + LIKE | SQL full-table LIKE |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['rows']:,} | {r['dense_f32']} | {r['dense_f16']} | {r['bm25']} | {r['sql_date_count']} | {r['sql_date_like']} | {r['sql_full_like']} |" for r in rows]
    out = ROOT / "docs" / "bench_retrieval.md"
    out.write_text("# Retrieval and SQL latency by corpus size\n\nMedian / p95 in milliseconds, single thread on an 18-core Apple Silicon laptop, "
                   "brute-force vectors (no ANN), SQLite FTS5. Rows beyond 339,210 are synthetic copies of real headlines.\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
