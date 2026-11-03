"""Where everything lives.

  evals/<dataset>/questions.jsonl   committed eval suites (questions + gold), the canonical quiz for each dataset
  data/                             local only (gitignored): item streams, raw downloads, LLM and embedding caches
  results/runs/<run>/<dataset>/     committed graded outputs (.jsonl.gz), run stats and reports
  results/cost_ledger.jsonl.gz      committed per-call cost records (tag, tokens, USD; no prompts or keys)
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EVALS_DIR = ROOT / "evals"
RESULTS_DIR = ROOT / "results"
RUNS_DIR = Path(os.environ.get("FACTBASE_RUNS_DIR", str(RESULTS_DIR / "runs")))
LOCAL_LEDGER = DATA_DIR / "cache" / "ledger.jsonl"
COMMITTED_LEDGER = RESULTS_DIR / "cost_ledger.jsonl.gz"


def questions_path(dataset: str) -> Path:
    """The committed eval suite if there is one, else the locally built questions."""
    p = EVALS_DIR / dataset / "questions.jsonl"
    return p if p.exists() else DATA_DIR / dataset / "questions.jsonl"


def resolve(path: Path) -> Path | None:
    """`x.jsonl` or its compressed twin `x.jsonl.gz`, whichever exists."""
    if path.exists():
        return path
    gz = path.with_name(path.name + ".gz")
    return gz if gz.exists() else None


def read_jsonl(path: Path) -> Iterator[dict]:
    p = resolve(path)
    if p is None:
        return iter(())
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt") as f:
        return iter([json.loads(l) for l in f if l.strip()])


def ledger_rows() -> Iterator[dict]:
    """Cost records: the live local ledger when present, otherwise the committed export."""
    return read_jsonl(LOCAL_LEDGER) if LOCAL_LEDGER.exists() else read_jsonl(COMMITTED_LEDGER)


def user_agent() -> str:
    """Polite User-Agent for public data APIs. Set FACTBASE_CONTACT to an email or URL of your own."""
    return f"factbase-research/0.1 ({os.environ.get('FACTBASE_CONTACT', 'memory-architecture research')})"
