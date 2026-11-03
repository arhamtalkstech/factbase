"""world_quiz: Wikipedia Current Events Portal stream + RealTimeQA human news quizzes.

Run: uv run python -m factbase.datasets.world_quiz.build

Stages (all cached, safe to rerun):
1. Download WCEP daily wikitext (data/raw/world_quiz/wcep/) and RealTimeQA *_qa.jsonl
   files (data/raw/world_quiz/rtqa/).
2. Parse WCEP leaf bullets into items.jsonl.
3. Answerability filter: an LLM sees only the WCEP items from question_date-9..question_date
   plus the question and its human gold, and returns supporting item ids.
4. Rewrite kept questions to be self-contained with an explicit time anchor, then verify
   each rewrite against its evidence items only.
5. Select 60-90 base questions spread over the window, add false-premise abstain
   questions (verified against the WCEP items of that period), expand re-asks.
"""

from __future__ import annotations

import calendar
import html
import json
import random
import re
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import httpx

from factbase import llm

DS = "world_quiz"
TAG = f"dataset:{DS}"
ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / DS
OUT = ROOT / "data" / DS
START, END = date(2024, 11, 1), date(2026, 10, 31)
from ...paths import user_agent

UA = user_agent()
WCEP_SOURCE = "Wikipedia Current Events Portal"
TARGET_BASE = 76
SEED = 20261102
# Manual review after the automatic filters: vague or explanation-style answers that are hard to grade.
CURATOR_EXCLUDE = {
    "20250502_7": "explanation answer (how a jet ended up in the Red Sea)",
    "20251003_0": "explanation answer (why the US government shut down)",
    "20251031_0": "vague: 'which region did Trump visit' (Asia)",
    "20260327_5": "vague: 'NASA revealed a timeline for which future project'",
}
# Abstain candidates (keyed by source day) rejected in manual review.
ABSTAIN_EXCLUDE = {
    "2026-09-11": "premise twist (drones 'from Iran' vs 'from Iraq') is too subtle: Iran had attacked the same pipeline in April 2026",
}


# ---------------------------------------------------------------- download

def page_title(d: date) -> str:
    return f"Portal:Current_events/{d.year}_{d.strftime('%B')}_{d.day}"


def fetch_wcep() -> None:
    out = RAW / "wcep"
    out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    d = START
    while d <= END:
        p = out / f"{d}.wiki"
        if not p.exists():
            for attempt in range(5):
                r = client.get("https://en.wikipedia.org/w/index.php", params={"title": page_title(d), "action": "raw"})
                if r.status_code == 200:
                    p.write_text(r.text)
                    break
                if r.status_code == 404:
                    print("WCEP page missing:", d)
                    break
                time.sleep(2**attempt)
            time.sleep(0.25)  # stay well under 5 req/s
        d += timedelta(days=1)


def fetch_rtqa() -> None:
    out = RAW / "rtqa"
    out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers={"User-Agent": UA}, timeout=30)
    for y in (2024, 2025, 2026):
        lp = out / f"listing_{y}.json"
        if not lp.exists():
            r = client.get(f"https://api.github.com/repos/realtimeqa/realtimeqa_public/contents/past/{y}")
            r.raise_for_status()
            lp.write_text(r.text)
        for x in json.loads(lp.read_text()):
            n = x["name"]
            if not n.endswith("_qa.jsonl") or n < "20241101":
                continue
            p = out / n
            if not p.exists():
                r = client.get(f"https://raw.githubusercontent.com/realtimeqa/realtimeqa_public/main/past/{y}/{n}")
                r.raise_for_status()
                p.write_text(r.text)


# ---------------------------------------------------------------- wikitext -> text

def _template(body: str) -> str:
    parts = [p.strip() for p in body.split("|")]
    name = parts[0].strip().lower()
    pos = [p for p in parts[1:] if "=" not in p]
    named = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
    if name in ("convert", "cvt", "conv") and len(pos) >= 2:
        return f"{pos[0]} {pos[1]}"
    if name == "ill":
        return named.get("lt", "").strip() or (pos[0] if pos else "")
    if name in ("lang", "transl", "transliteration") and pos:
        return pos[-1]
    if name in ("nowrap", "nobr", "small", "nowrap begin") and pos:
        return pos[0]
    if name == "m" and pos and pos[0].lower() == "ww":
        return "Mw"
    if name == "ship" and len(pos) >= 2:
        return f"{pos[0]} {pos[1]}" + (f" ({pos[2]})" if len(pos) > 2 and pos[2] else "")
    if name in ("uss", "hms", "hmas", "ins", "hmcs", "rfs", "jds") and pos:
        return f"{parts[0].strip()} {pos[0]}"
    if name in ("nbsp", "snd", "spaced ndash", "ndash"):
        return {"nbsp": " ", "snd": " – ", "spaced ndash": " – ", "ndash": "–"}[name]
    if name in ("us$", "usd") and pos:
        return f"US${pos[0]}"
    return pos[0] if len(pos) == 1 and name not in ("pp-protected", "citation needed", "cn") else ""


def _link(m: re.Match) -> str:
    inner = m.group(1)
    if re.match(r"\s*(file|image|category):", inner, re.I):
        return ""
    target, _, label = inner.partition("|")
    return (label or target).lstrip(":").strip()


EXT_LINK = re.compile(r"\[(https?://[^\s\]]+)(?:\s+([^\]]*))?\]")


def strip_markup(s: str) -> tuple[str, list[str], list[str]]:
    """Return (plain text, source outlet names, source urls)."""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>/]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    outlets, urls = [], []
    for m in EXT_LINK.finditer(s):
        urls.append(m.group(1))
        label = re.sub(r"'{2,}", "", (m.group(2) or "")).strip().strip("()").strip()
        if label:
            outlets.append(label)
    s = EXT_LINK.sub("", s)
    for _ in range(5):
        s2 = re.sub(r"\{\{([^{}]*)\}\}", lambda m: _template(m.group(1)), s)
        if s2 == s:
            break
        s = s2
    for _ in range(3):
        s = re.sub(r"\[\[([^\[\]]*)\]\]", _link, s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s, outlets, urls


SECTION_FIX = {"attacks and armed conflicts": "Armed conflicts and attacks", "disaster and accidents": "Disasters and accidents"}


def parse_day(raw: str, d: date) -> list[dict]:
    a = raw.find("All news items below this line")
    b = raw.find("All news items above this line")
    body = raw[a:b] if a >= 0 and b > a else raw
    bullets = []  # (depth, raw line, section)
    section = None
    for line in body.splitlines()[1:] if a >= 0 else body.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.fullmatch(r"'''(.+?)'''\s*", s)
        if m or (s.startswith(";") and not s.startswith(";;")):
            section = strip_markup(m.group(1) if m else s.lstrip(";"))[0]
            section = SECTION_FIX.get(section.lower(), section[:1].upper() + section[1:].lower())
            continue
        if s.startswith("*"):
            depth = len(s) - len(s.lstrip("*"))
            bullets.append((depth, s.lstrip("*").strip(), section))
    items = []
    stack: list[tuple[int, str]] = []
    for i, (depth, line, section) in enumerate(bullets):
        while stack and stack[-1][0] >= depth:
            stack.pop()
        text, outlets, urls = strip_markup(line)
        is_leaf = i + 1 >= len(bullets) or bullets[i + 1][1] == "" or bullets[i + 1][0] <= depth
        if is_leaf and len(text) >= 15:
            topics = [t for _, t in stack if t]
            ctx = [c for c in [section, *topics] if c]
            n = len(items) + 1
            items.append({
                "id": f"{DS}:{d}:{n:03d}",
                "dataset": DS,
                "ts": f"{d}T20:00:00Z",
                "title": text if len(text) <= 120 else text[:117].rsplit(" ", 1)[0] + "...",
                "text": (f"[{' | '.join(ctx)}] " if ctx else "") + text,
                "source": WCEP_SOURCE,
                "url": f"https://en.wikipedia.org/wiki/{page_title(d)}",
                "meta": {"date": str(d), "section": section, "topics": topics, "outlets": outlets, "source_urls": urls},
            })
        stack.append((depth, text))
    return items


def build_items() -> list[dict]:
    items = []
    d = START
    while d <= END:
        p = RAW / "wcep" / f"{d}.wiki"
        if p.exists():
            items.extend(parse_day(p.read_text(), d))
        d += timedelta(days=1)
    items.sort(key=lambda x: (x["ts"], x["id"]))
    with open(OUT / "items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return items


# ---------------------------------------------------------------- quiz

def load_quiz() -> list[dict]:
    import ast

    rows = []
    for p in sorted((RAW / "rtqa").glob("*_qa.jsonl")):
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            qd = date.fromisoformat(r["question_date"].replace("/", "-"))
            if not (START <= qd <= END):
                continue
            choices = r["choices"] if isinstance(r["choices"], list) else ast.literal_eval(r["choices"])
            ans = r["answer"] if isinstance(r["answer"], list) else ast.literal_eval(r["answer"])
            if len(ans) != 1:
                continue
            rows.append({
                "rtqa_id": r["question_id"], "qdate": qd, "source": r["question_source"], "url": r.get("question_url"),
                "question": r["question_sentence"].strip(), "choices": [str(c).strip() for c in choices],
                "gold": str(choices[int(ans[0])]).strip(),
            })
    return rows


def fmt_items(items: list[dict]) -> str:
    return "\n".join(f"{it['id']} | {it['meta']['date']} | {it['text']}" for it in items)


JUDGE_SYS = """You audit whether human-written weekly news quiz questions can be answered from a fixed set of news items.
You get ONLY a list of news items (id | date | text) from the ten days up to the quiz date, then quiz questions with their correct answer.
For each question decide:
- supported: true only if the items CLEARLY state the fact needed so that a reader of these items alone would arrive at the given correct answer. General knowledge, guesses or loose topical overlap do not count. If the item only mentions the topic but not the asked detail, it is NOT supported. Minor descriptive details in the question (e.g. who exactly did something) need not all appear, as long as the items clearly describe the same event and the asked detail (the answer) is explicit in them.
- open_ended_ok: true if the question still has a single clear answer when asked WITHOUT the multiple-choice options (false for "which of these", "which of the following is NOT", true/false style, or questions whose answer only makes sense relative to the options).
- evidence: the minimal list of item ids that together support the answer (empty if not supported). Copy ids exactly.
Be strict: when in doubt, supported=false."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {
        "qid": {"type": "string"}, "supported": {"type": "boolean"}, "open_ended_ok": {"type": "boolean"},
        "evidence": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
        "required": ["qid", "supported", "open_ended_ok", "evidence", "reason"], "additionalProperties": False}}},
    "required": ["results"], "additionalProperties": False,
}


def window_items(by_date: dict, end: date, days: int = 9) -> list[dict]:
    out = []
    for k in range(days, -1, -1):
        out.extend(by_date.get(end - timedelta(days=k), []))
    return out


def judge(rows: list[dict], by_date: dict, ids: set) -> dict:
    groups = defaultdict(list)
    for r in rows:
        groups[r["qdate"]].append(r)
    batches = []
    for qd, rs in sorted(groups.items()):
        for i in range(0, len(rs), 10):
            batches.append((qd, rs[i:i + 10]))

    def run(batch):
        qd, rs = batch
        items = window_items(by_date, qd)
        qs = "\n".join(
            f"- qid: {r['rtqa_id']}\n  question: {r['question']}\n  options: {r['choices']}\n  correct answer: {r['gold']}" for r in rs)
        user = f"NEWS ITEMS (quiz date {qd}):\n{fmt_items(items)}\n\nQUIZ QUESTIONS:\n{qs}"
        return llm.ask_json(JUDGE_SYS, user, JUDGE_SCHEMA, tag=TAG, effort="low")

    res = llm.pmap(run, batches, workers=8)
    out = {}
    for (qd, rs), r in zip(batches, res):
        if isinstance(r, Exception) or "results" not in r:
            print("judge batch failed", qd, r if isinstance(r, Exception) else "")
            continue
        allowed = {it["id"] for it in window_items(by_date, qd)}
        for x in r["results"]:
            x["evidence"] = [e for e in x["evidence"] if e in ids and e in allowed]
            out[x["qid"]] = x
    return out


REWRITE_SYS = """You turn a human-written multiple-choice news quiz question into a self-contained open-ended question for a memory benchmark.
Rules:
- Keep the meaning and the correct answer exactly the same. Do not add facts that are not in the original question or the evidence items.
- The question must be self-contained: replace "this week", "recently", "last week" etc. with the explicit time anchor given to you, and include it in the question (e.g. "In the week ending 7 March 2025, ...").
- Do NOT include the answer or the answer options in the question, and do not give hints that make the answer trivial.
- Name people, countries and organisations explicitly where the original relies on context.
- gold_aliases: other natural ways to write the same correct answer (short forms, surname only for a person, common abbreviations). Do not include the original answer text itself. Empty list if none.
Also report ok=false if the question cannot be rewritten as a clear open-ended question with a single answer supported by the evidence items."""

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}, "gold_aliases": {"type": "array", "items": {"type": "string"}},
                   "ok": {"type": "boolean"}, "note": {"type": "string"}},
    "required": ["question", "gold_aliases", "ok", "note"], "additionalProperties": False,
}

VERIFY_SYS = """You verify a benchmark question against its evidence. You get news items (id | date | text), a question and a proposed gold answer.
Return:
- answerable: true only if a reader of these items alone would give the gold answer to this question, with no other answer equally consistent with the items.
- self_contained: true if the question has an explicit date anchor and no vague references like "this week".
- leaks_answer: true if the question text itself contains or gives away the gold answer.
- faithful: true if the question asks the same thing as the original quiz question (shown for reference) and the gold is still correct for it."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"answerable": {"type": "boolean"}, "self_contained": {"type": "boolean"},
                   "leaks_answer": {"type": "boolean"}, "faithful": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["answerable", "self_contained", "leaks_answer", "faithful", "reason"], "additionalProperties": False,
}


def fmt_d(d: date) -> str:
    return f"{d.day} {d.strftime('%B')} {d.year}"


def time_anchor(qd: date, ev_dates: list[date]) -> str:
    if min(ev_dates) >= qd - timedelta(days=6):
        return f"In the week ending {fmt_d(qd)}"
    return f"In the period from {fmt_d(min(ev_dates))} to {fmt_d(qd)}"


def rewrite_and_verify(kept: list[dict], item_by_id: dict) -> list[dict]:
    def run(r):
        ev = [item_by_id[e] for e in r["evidence"]]
        ev_dates = [date.fromisoformat(it["meta"]["date"]) for it in ev]
        anchor = time_anchor(r["qdate"], ev_dates)
        user = (f"Quiz date: {r['qdate']}\nTime anchor to use: \"{anchor}\"\n"
                f"Original question: {r['question']}\nOptions: {r['choices']}\nCorrect answer: {r['gold']}\n\n"
                f"Evidence items:\n{fmt_items(ev)}")
        rw = llm.ask_json(REWRITE_SYS, user, REWRITE_SCHEMA, tag=TAG, effort="low")
        if not rw.get("ok") or not rw.get("question"):
            return {**r, "status": "rewrite_rejected", "why": rw.get("note")}
        vuser = (f"Evidence items:\n{fmt_items(ev)}\n\nOriginal quiz question (reference): {r['question']}\n"
                 f"Question: {rw['question']}\nGold answer: {r['gold']}")
        v = llm.ask_json(VERIFY_SYS, vuser, VERIFY_SCHEMA, tag=TAG, effort="low")
        good = v.get("answerable") and v.get("self_contained") and v.get("faithful") and not v.get("leaks_answer")
        aliases = [a for a in rw["gold_aliases"] if a.strip() and a.strip().lower() != r["gold"].lower()]
        return {**r, "status": "ok" if good else "verify_rejected", "why": v.get("reason"),
                "new_question": rw["question"], "aliases": aliases,
                "fact_time": max(ev_dates)}

    res = llm.pmap(run, kept, workers=8)
    out = []
    for r, x in zip(kept, res):
        if isinstance(x, Exception):
            print("rewrite failed", r["rtqa_id"], x)
            continue
        out.append(x)
    return out


UNIQUE_SYS = """You check open-ended benchmark questions against ALL news items (id | date | text) published in the ten days up to a quiz date.
For each question (with its proposed gold answer) return:
- unique: true if, given these items, the gold is the only reasonable answer (no other item points to a different answer).
- specific: true if the question pins down one particular event or entity; false for vague questions like "What happened in space?" or "Which region did X visit?" that many different answers could satisfy.
- crisp: true if the gold is a short, checkable answer (a name, place, number, date or short phrase), false if it is an explanation or description that would be hard to grade.
- reason: one short sentence."""

UNIQUE_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {
        "qid": {"type": "string"}, "unique": {"type": "boolean"}, "specific": {"type": "boolean"},
        "crisp": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["qid", "unique", "specific", "crisp", "reason"], "additionalProperties": False}}},
    "required": ["results"], "additionalProperties": False,
}


def window_check(ok: list[dict], by_date: dict) -> None:
    """Mark each rewritten question with a uniqueness/specificity verdict over the full item window."""
    groups = defaultdict(list)
    for r in ok:
        groups[r["qdate"]].append(r)

    def run(qd):
        qs = "\n".join(f"- qid: {r['rtqa_id']}\n  question: {r['new_question']}\n  gold: {r['gold']}" for r in groups[qd])
        user = f"NEWS ITEMS (quiz date {qd}):\n{fmt_items(window_items(by_date, qd))}\n\nQUESTIONS:\n{qs}"
        return llm.ask_json(UNIQUE_SYS, user, UNIQUE_SCHEMA, tag=TAG, effort="low")

    days = sorted(groups)
    verdicts = {}
    for qd, res in zip(days, llm.pmap(run, days, workers=8)):
        if isinstance(res, Exception):
            print("window check failed", qd, res)
            continue
        for x in res.get("results", []):
            verdicts[x["qid"]] = x
    for r in ok:
        v = verdicts.get(r["rtqa_id"], {})
        r["window_ok"] = bool(v.get("unique") and v.get("specific") and v.get("crisp"))
        r["window_reason"] = v.get("reason")


def clean_answer(s: str) -> str:
    return s.strip().strip("\"'“”‘’").strip()


# ---------------------------------------------------------------- abstain

ABSTAIN_SYS = """You write false-premise questions for a news-memory benchmark. You get the news items (id | date | text) of one day.
Pick ONE significant, concrete item (named country, person or organisation; not a minor local accident) and write a question whose premise contradicts that item by changing one key detail (wrong country, wrong person, wrong outcome) or that presupposes a related event that did not happen. A system with perfect memory of the news should notice the premise is false and say so.
It must be a wh-question (what/which/who/how/why/where) that PRESUPPOSES the false detail, e.g. "After X happened in <wrong country>, what did ...?". Never a yes/no question and never a statement.
Pick a fact that is stable (not one that later changed or was reversed), so the premise stays false afterwards.
The question must include an explicit date anchor (e.g. "On 3 March 2025, ..." or "In the week ending ..."), be natural, and not reveal that it is false.
Return the id of the item it contradicts, the question, and a short note stating what the record actually says (this is the gold note)."""

ABSTAIN_SCHEMA = {
    "type": "object",
    "properties": {"item_id": {"type": "string"}, "question": {"type": "string"}, "note": {"type": "string"}},
    "required": ["item_id", "question", "note"], "additionalProperties": False,
}

PREMISE_SYS = """You verify a false-premise benchmark question. You get ALL news items (id | date | text) from a period around the event, and a question.
Return:
- premise_supported: true if any item states or implies the question's premise is true.
- premise_contradicted: true if the items clearly show the premise is false (e.g. the event happened with a different country/person/outcome).
- presupposition_question: true if the text is a wh-question whose false premise is presupposed (not a yes/no question, not a statement).
- contradicting_ids: item ids that show the premise is false."""

PREMISE_SCHEMA = {
    "type": "object",
    "properties": {"premise_supported": {"type": "boolean"}, "premise_contradicted": {"type": "boolean"},
                   "presupposition_question": {"type": "boolean"}, "contradicting_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
    "required": ["premise_supported", "premise_contradicted", "presupposition_question", "contradicting_ids", "reason"], "additionalProperties": False,
}

ABSTAIN_SECTIONS = ("Politics and elections", "International relations", "Armed conflicts and attacks", "Business and economy")


def make_abstain(by_date: dict, item_by_id: dict, n: int) -> list[dict]:
    span = (END - START).days - 30
    # n + 4 evenly spaced candidate days, since some fail premise verification
    days = [START + timedelta(days=10 + int(span * (k + 0.5) / (n + 4))) for k in range(n + 4)]

    def run(d):
        cands = [it for it in by_date.get(d, []) if it["meta"]["section"] in ABSTAIN_SECTIONS] or by_date.get(d, [])
        a = llm.ask_json(ABSTAIN_SYS, f"Date: {d}\n\nItems:\n{fmt_items(cands)}", ABSTAIN_SCHEMA, tag=TAG, effort="low")
        if a.get("item_id") not in item_by_id:
            return None
        period = window_items(by_date, d + timedelta(days=10), days=20)
        v = llm.ask_json(PREMISE_SYS, f"Items:\n{fmt_items(period)}\n\nQuestion: {a['question']}", PREMISE_SCHEMA,
                         tag=TAG, effort="low")
        if v.get("premise_supported") or not v.get("premise_contradicted") or not v.get("presupposition_question"):
            return None
        if not a["question"].rstrip().endswith("?"):
            return None
        ev = [e for e in v["contradicting_ids"] if e in item_by_id] or [a["item_id"]]
        return {"date": d, "question": a["question"], "note": a["note"], "evidence": ev}

    res = [r for r in llm.pmap(run, days, workers=8)
           if r and not isinstance(r, Exception) and str(r["date"]) not in ABSTAIN_EXCLUDE]
    print(f"abstain: {len(res)} verified candidates for {n} slots")
    rng = random.Random(SEED)
    while len(res) > n:
        res.pop(rng.randrange(len(res)))
    return res


# ---------------------------------------------------------------- expansion

def month_end(y: int, m: int) -> date:
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, calendar.monthrange(y, m)[1])


def reask_dates(first: date, fact: date) -> list[date]:
    out = [first]
    for k in (3, 12):
        out.append(month_end(fact.year, fact.month + k))
    out.append(END)
    res = []
    for d in sorted(set(out)):
        if d > END or d < first:
            continue
        if res and (d - res[-1]).days < 60:
            continue
        res.append(d)
    return res


def select_bases(ok: list[dict], target: int) -> list[dict]:
    """Spread selection over months: round-robin across months, random within a month."""
    rng = random.Random(SEED)
    by_month = defaultdict(list)
    for r in ok:
        by_month[r["qdate"].strftime("%Y-%m")].append(r)
    for v in by_month.values():
        rng.shuffle(v)
    chosen, used = [], set()
    while len(chosen) < target and any(by_month.values()):
        for m in sorted(by_month):
            while by_month[m] and len(chosen) < target:
                r = by_month[m].pop()
                if used & set(r["evidence"]):
                    continue  # same event already asked about
                used |= set(r["evidence"])
                chosen.append(r)
                break
    return sorted(chosen, key=lambda r: (r["qdate"], r["rtqa_id"]))


def ledger_usd(since: float = 0.0) -> float:
    """Spend recorded under this dataset's tag (the ledger is shared with other builders)."""
    if not llm.LEDGER_PATH.exists():
        return 0.0
    total = 0.0
    for line in open(llm.LEDGER_PATH):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("tag") == TAG and r.get("t", 0) >= since:
            total += r["usd"]
    return total


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    fetch_wcep()
    fetch_rtqa()
    items = build_items()
    item_by_id = {it["id"]: it for it in items}
    by_date = defaultdict(list)
    for it in items:
        by_date[date.fromisoformat(it["meta"]["date"])].append(it)
    print(f"items: {len(items)} over {len(by_date)} days")

    rows = load_quiz()
    print(f"quiz rows in window: {len(rows)}")
    verdicts = judge(rows, by_date, set(item_by_id))
    kept = []
    for r in rows:
        v = verdicts.get(r["rtqa_id"])
        if v and v["supported"] and v["open_ended_ok"] and v["evidence"]:
            kept.append({**r, "evidence": v["evidence"]})
    print(f"judge: {len(verdicts)} judged, {len(kept)} supported+open-ended")

    done = rewrite_and_verify(kept, item_by_id)
    print("rewrite/verify:", dict(Counter(r["status"] for r in done)))
    window_check([r for r in done if r["status"] == "ok"], by_date)
    for r in done:
        if r["status"] == "ok" and not r["window_ok"]:
            r["status"], r["why"] = "window_rejected", r["window_reason"]
    for r in done:
        if r["status"] == "ok" and r["rtqa_id"] in CURATOR_EXCLUDE:
            r["status"], r["why"] = "curator_excluded", CURATOR_EXCLUDE[r["rtqa_id"]]
    ok = [r for r in done if r["status"] == "ok"]
    print("after window check and curator exclusions:", len(ok))

    with open(RAW / "filter_log.jsonl", "w") as f:
        for r in rows:
            v = verdicts.get(r["rtqa_id"], {})
            d = next((x for x in done if x["rtqa_id"] == r["rtqa_id"]), {})
            f.write(json.dumps({"rtqa_id": r["rtqa_id"], "qdate": str(r["qdate"]), "question": r["question"], "gold": r["gold"],
                                "supported": v.get("supported"), "open_ended_ok": v.get("open_ended_ok"),
                                "evidence": v.get("evidence"), "judge_reason": v.get("reason"),
                                "status": d.get("status", "filtered"), "new_question": d.get("new_question"),
                                "why": d.get("why")}, ensure_ascii=False) + "\n")

    bases = select_bases(ok, TARGET_BASE)
    n_abstain = max(1, round(len(bases) * 0.11))
    abstains = make_abstain(by_date, item_by_id, n_abstain)

    qs = []
    for i, r in enumerate(bases, 1):
        base_id = f"{DS}:q{i:04d}"
        for k, d in enumerate(reask_dates(r["qdate"], r["fact_time"])):
            age = (d - r["fact_time"]).days
            qs.append({
                "qid": f"{base_id}@{d}", "base_id": base_id, "dataset": DS, "ask_at": f"{d}T23:59:59Z",
                "question": r["new_question"], "gold": list(dict.fromkeys(clean_answer(g) for g in [r["gold"], *r["aliases"]])), "answer_type": "text",
                "numeric_tolerance": None, "category": "point_recent" if age <= 30 else "point_old",
                "fact_time": str(r["fact_time"]), "evidence_item_ids": r["evidence"], "gold_source": "human_quiz",
                "meta": {"rtqa_id": r["rtqa_id"], "quiz_source": r["source"], "quiz_url": r["url"],
                         "question_date": str(r["qdate"]), "original_question": r["question"], "choices": r["choices"]},
            })
    for j, a in enumerate(abstains, 1):
        base_id = f"{DS}:a{j:04d}"
        first = month_end(a["date"].year, a["date"].month)
        if (first - a["date"]).days < 3:
            first = a["date"] + timedelta(days=3)
        dates = [first]
        later = month_end(a["date"].year, a["date"].month + 6)
        if later <= END:
            dates.append(later)
        if (END - dates[-1]).days >= 45:
            dates.append(END)
        for d in dates:
            qs.append({
                "qid": f"{base_id}@{d}", "base_id": base_id, "dataset": DS, "ask_at": f"{d}T23:59:59Z",
                "question": a["question"], "gold": [a["note"]], "answer_type": "abstain", "numeric_tolerance": None,
                "category": "abstain", "fact_time": str(a["date"]), "evidence_item_ids": a["evidence"],
                "gold_source": "llm_from_source", "meta": {"kind": "false_premise"},
            })
    qs.sort(key=lambda q: (q["ask_at"], q["qid"]))
    with open(OUT / "questions.jsonl", "w") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    stats = {
        "items": len(items), "item_days": len(by_date), "quiz_rows": len(rows), "judged": len(verdicts),
        "supported": len(kept), "rewrite_verified": sum(1 for r in done if r["status"] in ("ok", "window_rejected", "curator_excluded")),
        "window_verified": sum(1 for r in done if r["status"] in ("ok", "curator_excluded")), "pool_after_curation": len(ok), "bases": len(bases), "abstain_bases": len(abstains),
        "instances": len(qs), "categories": dict(Counter(q["category"] for q in qs)),
        "quiz_sources_selected": dict(Counter(r["source"] for r in bases)),
        "llm_usd_this_run": round(ledger_usd(since=t0), 4),
        "llm_usd_all_runs": round(ledger_usd(), 4),
    }
    (RAW / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
