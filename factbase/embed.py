"""Local text embeddings (bge-small-en-v1.5 via fastembed), cached on disk by text hash.

xAI has no embeddings endpoint, so every architecture uses the same local model.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "emb.sqlite"
CACHE.parent.mkdir(parents=True, exist_ok=True)
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None
_lock = threading.Lock()
_local = threading.local()


def _db() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(CACHE, timeout=120)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")
        _local.c = c
    return c


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(MODEL_NAME)
    return _model


def _key(t: str) -> str:
    return hashlib.sha1(t.encode()).hexdigest()


def embed(texts: list[str], batch: int = 256) -> np.ndarray:
    """Return L2-normalised float32 vectors, shape (n, DIM)."""
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    keys = [_key(t) for t in texts]
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    db = _db()
    missing: dict[str, list[int]] = {}
    for i in range(0, len(keys), 900):
        chunk = keys[i : i + 900]
        rows = db.execute(f"SELECT k, v FROM emb WHERE k IN ({','.join('?' * len(chunk))})", chunk).fetchall()
        found = {k: v for k, v in rows}
        for j, k in enumerate(chunk):
            if k in found:
                out[i + j] = np.frombuffer(found[k], dtype=np.float16).astype(np.float32)
            else:
                missing.setdefault(k, []).append(i + j)
    if missing:
        todo_keys = list(missing)
        todo_texts = [texts[missing[k][0]] for k in todo_keys]
        with _lock:
            vecs = np.array(list(_get_model().embed(todo_texts, batch_size=batch)), dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        db.executemany(
            "INSERT OR REPLACE INTO emb (k, v) VALUES (?, ?)",
            [(k, vecs[n].astype(np.float16).tobytes()) for n, k in enumerate(todo_keys)],
        )
        db.commit()
        for n, k in enumerate(todo_keys):
            for idx in missing[k]:
                out[idx] = vecs[n]
    return out


def embed_query(q: str) -> np.ndarray:
    return embed([QUERY_PREFIX + q])[0]
