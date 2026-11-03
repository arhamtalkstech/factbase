from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def fmt_day(d: datetime | date) -> str:
    """'Monday 3 March 2025' style, unambiguous for the model."""
    return d.strftime("%A %-d %B %Y")


@dataclass
class Item:
    id: str
    dataset: str
    ts: datetime
    title: str
    text: str
    source: str
    url: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, d: dict) -> "Item":
        return cls(
            id=d["id"],
            dataset=d["dataset"],
            ts=parse_ts(d["ts"]),
            title=d.get("title") or "",
            text=d["text"],
            source=d.get("source") or "",
            url=d.get("url") or "",
            meta=d.get("meta") or {},
        )

    def render(self) -> str:
        """How an item is shown to a model: date first, then text."""
        return f"[{self.id} | {self.ts.strftime('%Y-%m-%d %H:%M')} UTC | {self.source}] {self.text}"


@dataclass
class Question:
    qid: str
    base_id: str
    dataset: str
    ask_at: datetime
    question: str
    gold: list[str]
    answer_type: str
    category: str
    fact_time: str
    gold_source: str
    numeric_tolerance: float | None = None
    evidence_item_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, d: dict) -> "Question":
        return cls(
            qid=d["qid"],
            base_id=d["base_id"],
            dataset=d["dataset"],
            ask_at=parse_ts(d["ask_at"]),
            question=d["question"],
            gold=[str(g) for g in d["gold"]],
            answer_type=d["answer_type"],
            category=d["category"],
            fact_time=str(d["fact_time"]),
            gold_source=d["gold_source"],
            numeric_tolerance=d.get("numeric_tolerance"),
            evidence_item_ids=d.get("evidence_item_ids") or [],
        )


@dataclass
class Answer:
    answer: str
    abstain: bool
    citations: list[str] = field(default_factory=list)
    usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    trace: list[dict] = field(default_factory=list)
    error: str | None = None
    llm_s: float = 0.0
    tool_s: float = 0.0
