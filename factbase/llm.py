"""grok-4.3 client with a request cache, a cost ledger and a spend cap.

Every call is keyed by a hash of the full request. Re-running an experiment replays
cached responses, so reruns are free and deterministic. Spend is read from the API's
`cost_in_usd_ticks` (1 tick = 1e-10 USD) and appended to a ledger shared by all
processes; calls fail once the ledger total passes FACTBASE_BUDGET_USD.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "grok-4.3"
CACHE_DIR = ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = CACHE_DIR / "llm.sqlite"
LEDGER_PATH = CACHE_DIR / "ledger.jsonl"
BUDGET_FILE = CACHE_DIR / "budget_usd.txt"


def budget_usd() -> float:
    """Spend cap. data/cache/budget_usd.txt wins over the env var so a running experiment can be re-capped."""
    try:
        return float(BUDGET_FILE.read_text().strip())
    except (OSError, ValueError):
        return float(os.environ.get("FACTBASE_BUDGET_USD", "300"))


class BudgetExceeded(RuntimeError):
    pass


_local = threading.local()
_ledger_lock = threading.Lock()
_spent_cache = {"usd": None, "checked": 0.0}


def _db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(CACHE_PATH, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT)")
        _local.conn = conn
    return conn


API_BASE = "https://api.x.ai/v1"


class APIError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def _client() -> httpx.Client:
    """One plain HTTP client per thread for the xAI chat completions endpoint (no vendor SDK)."""
    c = getattr(_local, "client", None)
    if c is None:
        key = os.environ.get("XAI_API_KEY")
        if not key:
            raise RuntimeError("XAI_API_KEY is not set (put it in factbase/.env)")
        c = httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {key}"}, timeout=httpx.Timeout(600.0))
        _local.client = c
    return c


def _post(req: dict, timeout: float | None) -> dict:
    r = _client().post("/chat/completions", json=req, timeout=timeout or 600.0)
    if r.status_code >= 400:
        raise APIError(r.status_code, r.text)
    return r.json()


def spent_usd(force: bool = False) -> float:
    now = time.time()
    if not force and _spent_cache["usd"] is not None and now - _spent_cache["checked"] < 20:
        return _spent_cache["usd"]
    total = 0.0
    if LEDGER_PATH.exists():
        with open(LEDGER_PATH) as f:
            for line in f:
                try:
                    total += json.loads(line)["usd"]
                except Exception:
                    pass
    _spent_cache.update(usd=total, checked=now)
    return total


def _record(tag: str, usage: dict | None) -> None:
    if not usage:
        return
    usd = (usage.get("cost_in_usd_ticks") or 0) / 1e10
    row = {
        "t": time.time(),
        "tag": tag,
        "usd": usd,
        "in": usage.get("prompt_tokens", 0),
        "cached": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        "out": usage.get("completion_tokens", 0),
    }
    with _ledger_lock:
        with open(LEDGER_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")
        if _spent_cache["usd"] is not None:
            _spent_cache["usd"] += usd


def chat(
    messages: list[dict],
    *,
    schema: dict | None = None,
    schema_name: str = "out",
    tools: list[dict] | None = None,
    effort: str = "none",
    max_tokens: int | None = None,
    tag: str = "misc",
    use_cache: bool = True,
    timeout: float | None = None,
    max_attempts: int = 8,
    model: str | None = None,
    salt: str = "",
) -> dict:
    """Return the assistant message as a dict: {content, tool_calls, usage, cached}.

    With `schema`, `content` is parsed JSON.
    """
    req: dict[str, Any] = {"model": model or MODEL, "messages": messages, "reasoning_effort": effort}
    if schema is not None:
        req["response_format"] = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema}}
    if tools:
        req["tools"] = tools
    if max_tokens:
        req["max_tokens"] = max_tokens
    # salt (repeat runs) changes only the cache key, so a repeat run re-samples the model instead of replaying
    keyed = {**req, "_salt": salt} if salt else req
    key = hashlib.sha256(json.dumps(keyed, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    if use_cache:
        row = _db().execute("SELECT v FROM cache WHERE k=?", (key,)).fetchone()
        if row:
            out = json.loads(row[0])
            out["cached"] = True
            return out

    if spent_usd() > budget_usd():
        raise BudgetExceeded(f"spend {spent_usd():.2f} USD exceeds budget {budget_usd()}")

    delay = 2.0
    err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            data = _post(req, timeout)
            break
        except (httpx.TimeoutException, httpx.TransportError) as e:
            err = e
        except APIError as e:
            if e.status < 500 and e.status != 429:
                raise
            err = e
        time.sleep(delay + random.random() * delay)
        delay = min(delay * 2, 60)
    else:
        raise RuntimeError(f"LLM call failed after retries: {err}")

    msg = data["choices"][0]["message"]
    usage = data.get("usage")
    _record(tag, usage)
    content: Any = msg.get("content")
    if schema is not None and content:
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {"_unparsed": content}
    out = {
        "content": content,
        "tool_calls": [
            {"id": tc["id"], "name": tc["function"]["name"], "arguments": tc["function"].get("arguments") or "{}"}
            for tc in (msg.get("tool_calls") or [])
        ],
        "usage": {
            "in": (usage or {}).get("prompt_tokens", 0),
            "out": (usage or {}).get("completion_tokens", 0),
            "usd": ((usage or {}).get("cost_in_usd_ticks") or 0) / 1e10,
        },
        "cached": False,
    }
    if use_cache:
        _db().execute("INSERT OR REPLACE INTO cache (k, v) VALUES (?, ?)", (key, json.dumps(out)))
        _db().commit()
    return out


def ask_json(system: str, user: str, schema: dict, *, tag: str, effort: str = "none", **kw) -> dict:
    """Convenience: one system + one user message, parsed JSON back."""
    r = chat([{"role": "system", "content": system}, {"role": "user", "content": user}], schema=schema, tag=tag, effort=effort, **kw)
    c = r["content"]
    return c if isinstance(c, dict) else {"_unparsed": c}


def pmap(fn: Callable, items: Iterable, workers: int = 8) -> list:
    """Parallel map preserving order. Exceptions are returned in place of results."""
    items = list(items)

    def safe(x):
        try:
            return fn(x)
        except BudgetExceeded:
            raise
        except Exception as e:  # keep the batch going; caller decides
            return e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(safe, items))
