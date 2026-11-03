"""iran_headlines: hourly GDELT English headlines about Iran + a WCEP-derived quiz.

The stream was meant to come from the GDELT DOC 2.0 API, but the API rejected most requests with its
rate-limit message (about one success every few minutes), so the stream is built from the raw GDELT GKG 2.0
15-minute files instead (one file per hour, same crawl, same URLs/titles/timestamps). See evals/iran_headlines/README.md.

Usage (from the factbase folder):
  uv run python -m factbase.datasets.iran_headlines.build            # wcep + gkg + items + quiz + stats (cached)
  uv run python -m factbase.datasets.iran_headlines.build gkg        # download hourly GKG snapshots
  uv run python -m factbase.datasets.iran_headlines.build wcep       # download WCEP day pages
  uv run python -m factbase.datasets.iran_headlines.build items      # write items.jsonl from the cache
  uv run python -m factbase.datasets.iran_headlines.build quiz       # build questions.jsonl
  uv run python -m factbase.datasets.iran_headlines.build stats      # coverage table
  uv run python -m factbase.datasets.iran_headlines.build gdelt      # DOC API download (slow; comparison only)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
NAME = "iran_headlines"
RAW = ROOT / "data" / "raw" / NAME
OUT = ROOT / "data" / NAME
GDELT_DIR = RAW / "gdelt"
WCEP_DIR = RAW / "wcep"
START = date(2024, 11, 1)
END = date(2026, 10, 31)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "(iran OR iranian OR tehran OR hormuz OR irgc) sourcelang:english"
from ...paths import user_agent

UA = user_agent()


def log(*a) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def days(a: date = START, b: date = END):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


# ---------------------------------------------------------------- GDELT stream


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S")


def _window_path(s: datetime, e: datetime) -> Path:
    return GDELT_DIR / s.strftime("%Y-%m") / f"{_fmt(s)}_{_fmt(e)}.json"


def _fetch_window(client: httpx.Client, s: datetime, e: datetime, state: dict) -> dict | None:
    """Fetch one window, respecting GDELT's one-request-per-5s rule. Returns parsed JSON or None."""
    p = _window_path(s, e)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            p.unlink()
    params = {
        "query": GDELT_QUERY,
        "mode": "artlist",
        "maxrecords": "250",
        "format": "json",
        "sort": "hybridrel",
        "startdatetime": _fmt(s),
        "enddatetime": _fmt(e),
    }
    backoff = 20.0
    for attempt in range(40):
        wait = state["next_ok"] - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            r = client.get(GDELT_URL, params=params, timeout=90)
            body = r.text
            status = r.status_code
        except httpx.HTTPError as ex:
            body, status = f"ERR {ex!r}", 0
        state["next_ok"] = time.time() + 6.5
        state["requests"] += 1
        stripped = body.strip()
        if status == 200 and (stripped.startswith("{") or stripped == ""):
            try:
                data = json.loads(stripped) if stripped else {}
            except json.JSONDecodeError:
                # GDELT occasionally emits invalid escapes or control chars in titles
                data = _lenient_parse(stripped)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False))
            return data
        state["rejected"] = state.get("rejected", 0) + 1
        if status != 429 or attempt % 5 == 4:
            log(f"  window {_fmt(s)} status={status} attempt={attempt} body={stripped[:70]!r}")
        state["next_ok"] = time.time() + backoff
        backoff = min(backoff * 1.3, 120)
    log(f"  giving up on window {_fmt(s)}-{_fmt(e)} for now")
    return None


def _lenient_parse(text: str) -> dict:
    """Parse GDELT JSON that contains stray control chars or bad escapes."""
    import re

    cleaned = re.sub(r"[\x00-\x1f]", " ", text)
    cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"articles": [], "_unparsed": True}


def base_windows():
    for d in days():
        s = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        yield s, s + timedelta(hours=12) - timedelta(seconds=1)
        yield s + timedelta(hours=12), s + timedelta(hours=24) - timedelta(seconds=1)


def download_gdelt() -> None:
    state = {"next_ok": 0.0, "requests": 0}
    wins = list(base_windows())
    # one window per day first (alternating AM/PM), then the other half: a partial download
    # still covers every day of the range
    order = sorted(range(len(wins)), key=lambda i: ((i % 2) != ((i // 2) % 2), i))
    todo = [wins[i] for i in order if not _window_path(*wins[i]).exists()]
    log(f"GDELT base pass: {len(wins)} windows, {len(todo)} to fetch")
    with httpx.Client(headers={"User-Agent": UA}) as client:
        for i, (s, e) in enumerate(todo):
            data = _fetch_window(client, s, e, state)
            n = len((data or {}).get("articles", []))
            if i % 20 == 0 or data is None:
                log(f"[{i + 1}/{len(todo)}] {_fmt(s)} -> {n} articles (requests={state['requests']}, rejected={state.get('rejected', 0)})")


def refine_gdelt(min_hours: int = 6) -> None:
    """Split base windows that hit the 250 cap into halves, down to `min_hours`."""
    state = {"next_ok": 0.0, "requests": 0}
    with httpx.Client(headers={"User-Agent": UA}) as client:
        frontier = list(base_windows())
        level = 12
        while level > min_hours:
            nxt = []
            for s, e in frontier:
                p = _window_path(s, e)
                if not p.exists():
                    continue
                if len(json.loads(p.read_text()).get("articles", [])) >= 250:
                    half = timedelta(hours=level // 2)
                    nxt += [(s, s + half - timedelta(seconds=1)), (s + half, e)]
            todo = [w for w in nxt if not _window_path(*w).exists()]
            log(f"refine to {level // 2}h: {len(nxt)} windows, {len(todo)} to fetch")
            for i, (s, e) in enumerate(todo):
                data = _fetch_window(client, s, e, state)
                if i % 20 == 0:
                    log(f"[{i + 1}/{len(todo)}] {_fmt(s)} -> {len((data or {}).get('articles', []))} articles")
            frontier = nxt
            level //= 2


# ---------------------------------------------------------------- GDELT GKG raw files (fallback stream)

GKG_DIR = RAW / "gkg"
GKG_URL = "https://data.gdeltproject.org/gdeltv2/{}.gkg.csv.zip"
# same terms as the DOC API query: (iran OR iranian OR tehran OR hormuz OR irgc)
STREAM_RE = re.compile(r"\b(iran|iranians?|tehran|hormuz|irgc)\b", re.I)


def gkg_slots():
    """One 15-minute GKG file per hour, rotating the quarter so every quarter-hour is sampled."""
    t = datetime(START.year, START.month, START.day, tzinfo=timezone.utc)
    end = datetime(END.year, END.month, END.day, tzinfo=timezone.utc) + timedelta(days=1)
    k = 0
    while t < end:
        yield t + timedelta(minutes=15 * (k % 4))
        t += timedelta(hours=1)
        k += 1


def _gkg_path(t: datetime) -> Path:
    return GKG_DIR / t.strftime("%Y-%m") / f"{t:%Y%m%d%H%M%S}.json"


def _parse_gkg(blob: bytes) -> list[dict]:
    import html
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(blob))
    data = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    rows = []
    for line in data.splitlines():
        f = line.split("\t")
        if len(f) < 27 or f[2] != "1":  # 1 = web articles
            continue
        mt = re.search(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", f[26], re.S)
        title = " ".join(html.unescape(mt.group(1)).split()) if mt else ""
        in_title = bool(STREAM_RE.search(title))
        # body match: counts, themes, locations, persons, organisations, quotations and names that GKG
        # extracted from the full article text (URL and image links excluded)
        rest = "\t".join(f[5:15] + f[22:24])
        if not in_title and not STREAM_RE.search(rest):
            continue
        rows.append({"date": f[1], "domain": f[3], "url": f[4], "title": title, "in_title": in_title})
    return rows


def _fetch_gkg(client: httpx.Client, slot: datetime) -> tuple[datetime, int]:
    p = _gkg_path(slot)
    if p.exists():
        return slot, -1
    # fall back to the other quarter-hours of the same hour if the sampled file is missing
    hour = slot.replace(minute=0)
    cands = [slot] + [hour + timedelta(minutes=m) for m in (0, 15, 30, 45) if hour + timedelta(minutes=m) != slot]
    for t in cands:
        for attempt in range(4):
            try:
                r = client.get(GKG_URL.format(f"{t:%Y%m%d%H%M%S}"), timeout=120)
            except httpx.HTTPError:
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code == 404:
                break
            if r.status_code != 200:
                time.sleep(3 * (attempt + 1))
                continue
            try:
                rows = _parse_gkg(r.content)
            except Exception as ex:  # corrupt zip: try the next quarter-hour
                log(f"  bad zip {t}: {ex!r}")
                break
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"file": f"{t:%Y%m%d%H%M%S}", "rows": rows}, ensure_ascii=False))
            return slot, len(rows)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"file": None, "rows": []}))
    return slot, 0


def download_gkg(workers: int = 8) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    slots = [s for s in gkg_slots() if not _gkg_path(s).exists()]
    log(f"GKG: {len(slots)} hourly files to fetch")
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        with ThreadPoolExecutor(workers) as ex:
            futs = [ex.submit(_fetch_gkg, client, s) for s in slots]
            for i, fu in enumerate(as_completed(futs)):
                s, n = fu.result()
                if i % 200 == 0:
                    log(f"GKG [{i + 1}/{len(slots)}] {s:%Y-%m-%d %H:%M} -> {n} rows")


# ---------------------------------------------------------------- WCEP pages


def _wcep_title(d: date) -> str:
    return f"Portal:Current_events/{d.year}_{d.strftime('%B')}_{d.day}"


def download_wcep() -> None:
    WCEP_DIR.mkdir(parents=True, exist_ok=True)
    todo = [d for d in days() if not (WCEP_DIR / f"{d}.txt").exists()]
    log(f"WCEP: {len(todo)} day pages to fetch")
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        for i, d in enumerate(todo):
            url = "https://en.wikipedia.org/w/index.php?" + urllib.parse.urlencode(
                {"title": _wcep_title(d), "action": "raw"}
            )
            for attempt in range(5):
                try:
                    r = client.get(url, timeout=60)
                except httpx.HTTPError:
                    time.sleep(5 * (attempt + 1))
                    continue
                if r.status_code == 200:
                    (WCEP_DIR / f"{d}.txt").write_text(r.text)
                    break
                if r.status_code == 404:
                    (WCEP_DIR / f"{d}.txt").write_text("")
                    break
                time.sleep(5 * (attempt + 1))
            time.sleep(0.4)
            if i % 50 == 0:
                log(f"WCEP [{i + 1}/{len(todo)}] {d}")


# ---------------------------------------------------------------- items


BODY_ONLY_CAP = 5  # body-only matches kept per hourly GKG snapshot (title matches are all kept)


def build_items() -> list[dict]:
    """Stream = GKG rows from the hourly snapshots whose headline or extracted article entities match the query."""
    OUT.mkdir(parents=True, exist_ok=True)
    by_url: dict[str, dict] = {}
    n_files = n_missing = n_raw = n_body_dropped = 0
    for p in sorted(GKG_DIR.rglob("*.json")):
        n_files += 1
        snap = json.loads(p.read_text())
        if not snap.get("file"):
            n_missing += 1
            continue
        rows = [r for r in snap["rows"] if r["title"] and r["url"]]
        n_raw += len(rows)
        body = sorted((r for r in rows if not r["in_title"]), key=lambda r: hashlib.sha1(r["url"].encode()).hexdigest())
        n_body_dropped += max(0, len(body) - BODY_ONLY_CAP)
        keep = [r for r in rows if r["in_title"]] + body[:BODY_ONLY_CAP]
        for r in keep:
            url = r["url"].strip()
            title = r["title"]
            if title.startswith("{"):  # a few AP alerts wrap the headline in braces
                title = title.strip("{}").strip()
            ts = datetime.strptime(r["date"], "%Y%m%d%H%M%S").strftime("%Y-%m-%dT%H:%M:%SZ")
            if not (START.isoformat() <= ts[:10] <= END.isoformat()):
                continue
            prev = by_url.get(url)
            if prev is not None and prev["ts"] <= ts:
                continue
            domain = r["domain"] or urllib.parse.urlparse(url).netloc
            by_url[url] = {
                "id": f"{NAME}:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
                "dataset": NAME,
                "ts": ts,
                "title": title,
                "text": f"{title} ({domain}, English)",
                "source": "GDELT GKG 2.0",
                "url": url,
                "meta": {
                    "domain": domain,
                    "language": "English",
                    "gkg_file": snap["file"],
                    "match": "headline" if r["in_title"] else "article_body",
                },
            }
    items = sorted(by_url.values(), key=lambda x: (x["ts"], x["id"]))
    with open(OUT / "items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    log(
        f"items: {n_files} hourly snapshots ({n_missing} missing), {n_raw} matching rows, "
        f"{n_body_dropped} body-only rows over cap, {len(items)} unique-URL items"
    )
    return items


def load_items() -> list[dict]:
    return [json.loads(l) for l in open(OUT / "items.jsonl")]


# ---------------------------------------------------------------- WCEP parsing

KW_RE = re.compile(
    r"\b(iran\w*|tehran|irgc|hormuz|khamenei|pezeshkian|araghchi|houthis?|hezbollah)\b", re.I
)


def _clean_wiki(s: str) -> str:
    s = re.sub(r"<ref[^>]*?/>", "", s)
    s = re.sub(r"<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"\[https?://\S+\s*([^\]]*)\]", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(s.split()).strip(" *")


def parse_wcep_day(d: date) -> list[dict]:
    """Return event bullets of one WCEP day page with their topic path."""
    p = WCEP_DIR / f"{d}.txt"
    if not p.exists():
        return []
    raw = p.read_text()
    m = re.search(r"All news items below this line -->(.*?)<!-- All news items above this line", raw, re.S)
    body = m.group(1) if m else raw
    out: list[dict] = []
    path: list[str] = []
    section = ""
    for line in body.splitlines():
        line = line.rstrip()
        sm = re.match(r"^'''(.+?)'''\s*$", line)
        if sm:
            section = _clean_wiki(sm.group(1))
            path = []
            continue
        bm = re.match(r"^(\*+)\s*(.*)$", line)
        if not bm:
            continue
        depth = len(bm.group(1))
        raw_text = bm.group(2)
        text = _clean_wiki(raw_text)
        path = path[: depth - 1]
        has_ref = "[http" in raw_text
        if not has_ref and len(text.split()) <= 12:
            path.append(text)  # topic header
            continue
        out.append(
            {
                "date": d.isoformat(),
                "section": section,
                "topics": [t for t in path if t],
                "text": text,
                "sources": re.findall(r"\[(https?://\S+)", raw_text),
            }
        )
    return out


def wcep_candidates() -> list[dict]:
    cands = []
    for d in days():
        for i, b in enumerate(parse_wcep_day(d)):
            ctx = " ".join(b["topics"]) + " " + b["text"]
            if KW_RE.search(ctx):
                b["bid"] = f"{b['date']}#{i}"
                b["kw_in_text"] = bool(KW_RE.search(b["text"]))
                cands.append(b)
    return cands


# ---------------------------------------------------------------- quiz

TAG = f"dataset:{NAME}"
QUIZ_CACHE = RAW / "quiz"
STOP = set(
    """a an the of in on at to for from by with and or but is are was were be been as that this these those it its
    into after before over under than then there their they he she his her who whom which what when where why how
    against during between about amid says said say new more most least least other some any all no not
    killed kills killing people least others including two three one four five six least near""".split()
)


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in STOP}


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _add_months(d: date, k: int) -> date:
    m = d.month - 1 + k
    return _month_end(date(d.year + m // 12, m % 12 + 1, 1))


def _human(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def reask_dates(first_ok: date) -> list[date]:
    """First month-end on/after first_ok, then +3, +6, +12 months, and the window end."""
    m0 = _month_end(first_ok)
    out = [m0] + [_add_months(m0, k) for k in (3, 6, 12)] + [END]
    return sorted({d for d in out if d <= END})


class Index:
    """Headlines grouped by UTC day for quick candidate retrieval."""

    def __init__(self, items: list[dict]):
        self.by_day: dict[str, list[dict]] = {}
        self.by_id = {it["id"]: it for it in items}
        for it in items:
            self.by_day.setdefault(it["ts"][:10], []).append(it)
        self.tok = {it["id"]: _tokens(it["title"]) for it in items}

    def window(self, d: date, before: int = 1, after: int = 2) -> list[dict]:
        out = []
        for k in range(-before, after + 1):
            out += self.by_day.get((d + timedelta(days=k)).isoformat(), [])
        return out

    def top(self, d: date, query_terms: set[str], k: int = 120, before: int = 1, after: int = 2) -> list[dict]:
        scored = []
        seen_titles = set()
        for it in self.window(d, before, after):
            sc = len(self.tok[it["id"]] & query_terms)
            if sc == 0:
                continue
            key = it["title"].lower()
            # one copy per identical headline in the prompt keeps it small; others stay as evidence
            if key in seen_titles:
                continue
            seen_titles.add(key)
            scored.append((sc, it["ts"], it))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [t[2] for t in scored[:k]]

    def same_title(self, item_ids: list[str], d: date, before: int = 1, after: int = 2) -> list[str]:
        titles = {self.by_id[i]["title"].lower() for i in item_ids}
        return [it["id"] for it in self.window(d, before, after) if it["title"].lower() in titles]


def my_spend() -> float:
    """USD spent under this dataset's tag (the ledger is shared with other builders)."""
    from factbase import llm

    total = 0.0
    if llm.LEDGER_PATH.exists():
        for line in open(llm.LEDGER_PATH):
            if f'"{TAG}"' in line:
                try:
                    total += json.loads(line)["usd"]
                except Exception:
                    pass
    return total


WRITE_SYS = """You write quiz questions for a news-memory benchmark. You see ONE curated news event bullet from the
Wikipedia Current Events Portal, with its date and topic path. Write exactly one factual question that is answerable
ONLY from this bullet, with a short exact gold answer (a name, place, organisation, number or short phrase, at most
6 words). Rules:
- The question must state the explicit date in the form "on 3 March 2025" (the bullet's date) and enough context
  to be unambiguous among all Iran/Middle East news of that period.
- Do not put the answer (or an obvious paraphrase of it) in the question.
- Prefer facts a news HEADLINE would carry: the main actor, the target, the place/facility/ship/country, the
  person appointed/killed/arrested, the decision taken. Never ask which agency or outlet reported something.
  Avoid fine-grained numbers like injured counts unless they are the core of the event.
- Gold: list of acceptable aliases (e.g. ["Abbas Araghchi", "Araghchi"]).
- keywords: 4-10 distinctive words likely to appear in headlines about this event (names, places, verbs).
- If the bullet has no fact suitable for such a question, set skip=true.
Return JSON."""

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "skip": {"type": "boolean"},
        "question": {"type": "string"},
        "gold": {"type": "array", "items": {"type": "string"}},
        "answer_type": {"type": "string", "enum": ["text", "number", "date"]},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["skip", "question", "gold", "answer_type", "keywords"],
    "additionalProperties": False,
}

VERIFY_SYS = """You check whether a quiz answer is supported by a set of news HEADLINES (titles only, with UTC
timestamps). You are given a question, its proposed gold answer, and numbered headlines.
- supported=true only if at least one headline, read on its own or together with others, clearly states the gold
  answer as the answer to the question (same event, same date range). Partial or vague support does not count.
- supporting: the numbers of ALL headlines that support the answer (each must carry the key fact).
- ambiguous=true if the headlines suggest a different or conflicting answer to the same question, or the question
  could reasonably have more than one answer in this period.
Return JSON."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "supporting": {"type": "array", "items": {"type": "integer"}},
        "ambiguous": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["supported", "supporting", "ambiguous", "note"],
    "additionalProperties": False,
}

BLIND_SYS = """Answer the question using ONLY the numbered news headlines given. Reply with a short exact answer
(at most 8 words). If the headlines do not contain the answer, answer "NOT FOUND"."""

BLIND_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

MATCH_SYS = """Decide if a candidate answer means the same as any of the gold answers for the question (same
entity/number/place; ignore wording, titles and minor spelling). Return JSON."""

MATCH_SCHEMA = {
    "type": "object",
    "properties": {"match": {"type": "boolean"}},
    "required": ["match"],
    "additionalProperties": False,
}


def _fmt_headlines(hs: list[dict]) -> str:
    return "\n".join(f"[{i}] {h['ts'][:16].replace('T', ' ')} | {h['text']}" for i, h in enumerate(hs))


def _llm(system: str, user: str, schema: dict, effort: str = "none") -> dict:
    from factbase import llm

    return llm.ask_json(system, user, schema, tag=TAG, effort=effort)


GUESS_SYS = """Answer the quiz question from its wording and generic common sense only. Do not use knowledge of
specific news events after 2023. Short answer (at most 6 words)."""


def _guessable(w: dict) -> bool:
    g = _llm(GUESS_SYS, w["question"], BLIND_SCHEMA)
    m = _llm(MATCH_SYS, f"Question: {w['question']}\nGold answers: {w['gold']}\nCandidate: {g.get('answer', '')}", MATCH_SCHEMA)
    return bool(m.get("match"))


def write_question(b: dict) -> dict:
    user = f"Date: {_human(_d(b['date']))}\nTopic path: {' > '.join(b['topics']) or '(none)'}\nBullet: {b['text']}"
    return _llm(WRITE_SYS, user, WRITE_SCHEMA)


def verify_against_stream(idx: Index, q: dict, d: date) -> dict:
    """Return {ok, evidence_ids, note}. Uses headlines from d-1..d+2."""
    terms = set()
    for k in q["keywords"] + q["gold"]:
        terms |= _tokens(k)
    terms |= _tokens(q["question"]) - {"iran", "iranian", "israel", "israeli"}
    hs = idx.top(d, terms, k=120)
    if not hs:
        return {"ok": False, "evidence_ids": [], "note": "no candidate headlines"}
    user = f"Question: {q['question']}\nProposed gold answer: {q['gold']}\n\nHeadlines:\n{_fmt_headlines(hs)}"
    v = _llm(VERIFY_SYS, user, VERIFY_SCHEMA, effort="low")
    sup = [hs[i] for i in v.get("supporting", []) if isinstance(i, int) and 0 <= i < len(hs)]
    if not v.get("supported") or v.get("ambiguous") or not sup:
        return {"ok": False, "evidence_ids": [], "note": v.get("note", "")}
    # independent blind pass: answer from the supporting headlines only, without seeing gold
    blind = _llm(BLIND_SYS, f"Question: {q['question']}\n\nHeadlines:\n{_fmt_headlines(sup)}", BLIND_SCHEMA)
    ans = blind.get("answer", "")
    m = _llm(MATCH_SYS, f"Question: {q['question']}\nGold answers: {q['gold']}\nCandidate: {ans}", MATCH_SCHEMA)
    if not m.get("match"):
        return {"ok": False, "evidence_ids": [], "note": f"blind answer mismatch: {ans}"}
    ev = idx.same_title([h["id"] for h in sup], d)
    return {"ok": True, "evidence_ids": ev, "blind_answer": ans, "note": v.get("note", "")}


STORY_TYPES = {"ordering", "change", "as_of_state", "multi_hop"}

STORY_SYS = """You build quiz questions for a news-memory benchmark from curated news event bullets on ONE storyline
(each with its date). The quiz is asked later to someone who has read every news headline up to the ask date, so
each question must be answerable from the news of those dates and must have exactly one correct answer.
Propose up to 4 questions, each using exactly TWO (or three) of the bullets, of these types:
- ordering: "Which happened first: <event X> or <event Y>?" Descriptions under 15 words, NO dates, and each must
  identify a ONE-OFF event (a named person appointed/killed/released, a named ship, a named agreement, a specific
  facility or city hit once). Never use recurring kinds of events ("Houthis fire a missile at Israel", "US strikes
  Yemen", "Iran launches drones") as they happened many times. gold = the first event's description.
- change: the same thing in two different states on two dates (status, figure, office holder, open/closed, in
  force/revoked). Ask "Between <date A> and <date B>, how did <thing> change?" with explicit dates like
  "3 March 2025". gold = short phrase with both states ("from closed to reopened").
- as_of_state: "As of <date of the LATER bullet>, what was <the latest state of a thing that changed>?" where the
  earlier bullet gave a different, now outdated state. gold = the later state.
- multi_hop: a question that needs facts from two bullets joined together (e.g. "The country whose embassy ... on
  <date A>: what did it do on <date B>?"). gold = short answer.
Use only the bullets. Gold answers: short (at most 8 words), list aliases. bullets = the indices used.
unique_events = true only if every event referenced is a one-off that cannot be confused with a similar event on
another date. Return JSON with a list of questions (may be empty)."""

STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["ordering", "change", "as_of_state", "multi_hop"]},
                    "question": {"type": "string"},
                    "gold": {"type": "array", "items": {"type": "string"}},
                    "bullets": {"type": "array", "items": {"type": "integer"}},
                    "unique_events": {"type": "boolean"},
                },
                "required": ["type", "question", "gold", "bullets", "unique_events"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

GLOBAL_SYS = {
    "state": """You build quiz questions for a news-memory benchmark from a dated list of curated news event bullets
about Iran and the wider Middle East conflict (Nov 2024 - Oct 2026). The quiz is asked later to someone who has read
every news headline up to the ask date, so each question needs exactly one correct answer.
Find up to 12 pairs of bullets where the SAME thing is reported in two different states on two different dates
(a status like open/closed, in force/revoked, detained/released; an office holder; a location; a figure), and write
for each either:
- type "change": "Between <date A> and <date B>, how did <thing> change?" with explicit dates like "3 March 2025";
  gold = short phrase with both states ("from closed to reopened"); or
- type "as_of_state": "As of <date of the later bullet>, what was <thing>?" where the earlier bullet gave a
  different, now outdated state; gold = the later state.
Only use genuine state changes of one specific thing stated in the bullets. bullets = the indices used.
unique_events = true only if the thing is specific enough that no other change of it could confuse the answer.
Gold answers: short (at most 8 words), list aliases. Return JSON.""",
    "multi_hop": """You build quiz questions for a news-memory benchmark from a dated list of curated news event bullets
about Iran and the wider Middle East conflict (Nov 2024 - Oct 2026). The quiz is asked later to someone who has read
every news headline up to the ask date, so each question needs exactly one correct answer.
Write up to 8 type "multi_hop" questions. Each must need two bullets on different dates joined by a shared
entity: the question names the entity only through its role in bullet A (with A's explicit date) and asks a fact
that only bullet B (with B's explicit date) gives, e.g. "The country that closed its embassy in Tehran on
16 January 2026: which ... did it ... on 3 March 2026?". Both bullets must mention the same specific entity
(person, country, ship, organisation, place). The answer must be a short exact fact from bullet B, not stated in
bullet A. bullets = the indices used [A, B]. unique_events = true only if the role in A identifies exactly one
entity. Gold answers: short (at most 8 words), list aliases. Return JSON.""",
}

FALSE_SYS = """You write a FALSE-PREMISE question for a news-memory benchmark. You get a curated news bullet (with
date) and a true question about it. Write a question that presupposes an event or state that the bullet clearly
contradicts, keeping the same explicit date. The false premise must be the CORE of the question, so that nobody can
answer it without accepting the falsehood: e.g. ask why/how something happened that did not happen, or ask about
the consequences of the opposite action ("Why did X release Y on <date>?" when X arrested Y). Do not merely swap
an adjective or attribution in an otherwise answerable question (bad: "Which Shia group claimed the attack?" when a
Sunni group did, because the questioner still expects the group's name). The premise must be contradicted by the
bullet itself, not merely absent. gold_note: one sentence saying why the premise is false (what actually
happened). Return JSON."""

FALSE_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}, "gold_note": {"type": "string"}, "keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["question", "gold_note", "keywords"],
    "additionalProperties": False,
}

FALSE_VERIFY_SYS = """You check a false-premise quiz question against news HEADLINES (titles with UTC timestamps).
contradicted=true only if at least one headline clearly shows the premise of the question is false.
supported=true if any headline supports the (false) premise. contradicting: numbers of the headlines that show
the premise is false. Return JSON."""

FALSE_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "contradicted": {"type": "boolean"},
        "supported": {"type": "boolean"},
        "contradicting": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["contradicted", "supported", "contradicting"],
    "additionalProperties": False,
}

# Generated questions dropped after manual review (event descriptions that recur in the stream, so the
# answer is not unique). Kept here so the exclusion is visible and reproducible.
EXCLUDE: set[str] = {
    # recurring events (Khamenei rejected talks, Munir visited Tehran, Houthi raids on UN offices, Hormuz closures,
    # Kuwait airspace reopenings, IRGC tanker strikes, Iranian summons of UK diplomats happened more than once)
    "Which happened first: U.S. reimposing maximum pressure on Iran or Khamenei rejecting negotiations?",
    "Which happened first: Khamenei rejecting U.S. negotiations or deploying B-2 bombers to Diego Garcia?",
    "Which happened first: American-Israeli airstrike kills Majid Khademi or Asim Munir visits Tehran?",
    "Which happened first: Houthi forces launch missiles at a U.S. fighter jet or raid United Nations offices in Sanaa?",
    "Which happened first: Houthis raid United Nations offices in Sanaa or capture the port city of Mokha?",
    "Which happened first: Kuwait reopens its airspace to commercial flights or United Arab Emirates suspends exchanges with Iran?",
    "Which happened first: Strait of Hormuz closed or Kuwait reopens its airspace to commercial flights?",
    "Which happened first: Strait of Hormuz closed or United Arab Emirates suspends exchanges with Iran?",
    "Which happened first: US launched Tomahawk strikes on Larak Island or IRGC struck two tankers?",
    "Which happened first: the Iranian foreign ministry summons the British chargé d'affaires or the United Kingdom "
    "designates Iran's Islamic Revolutionary Guards Corps as a terrorist organization?",
    # the 18 June 2026 bullet is a promise to reopen, not a reopening
    "Between 27 March 2026 and 18 June 2026, how did the status of the Strait of Hormuz change?",
    # Israel also struck South Pars on 14 June 2025; Iraq closed Iran border crossings more than once
    "Which happened first: U.S. strikes IRGC Navy drone carrier or Israel strikes South Pars gas field?",
    "Which happened first: the East–West Crude Oil Pipeline attack or Iraq closing three border crossings with Iran?",
    # vague or weak gold
    "What did Iran launch towards Israel on 13 June 2025?",
    "What happened to one person in the hydrogen capsule explosion at Tehran University laboratory on 2 October 2025?",
    # premise is only absent from the record, not contradicted
    "Why did Azerbaijan launch retaliatory strikes on Iranian territory following the 5 March 2026 drone attack on "
    "Nakhchivan International Airport?",
}

# Gold fixes after manual review: aliases that were really parts of one multi-part answer.
GOLD_OVERRIDE: dict[str, list[str]] = {
    "On 17 January 2025, which two presidents signed the Iranian–Russian Treaty on Comprehensive Strategic Partnership?": [
        "Masoud Pezeshkian and Vladimir Putin",
        "Pezeshkian and Putin",
    ],
    "On 14 September 2026, which two PLC-controlled Yemeni cities did Houthi forces advance towards amid heavy clashes?": [
        "Marib and Taiz",
        "Taiz and Marib",
    ],
}

GENERIC_TOPICS = {"Middle Eastern crisis", "Middle East crisis", "Middle Eastern crisis (2023–present)"}


def storyline(b: dict) -> str:
    ts = [t for t in b["topics"] if t not in GENERIC_TOPICS]
    return ts[0] if ts else (b["topics"][0] if b["topics"] else "-")


def _sample_candidates(cands: list[dict], per_month: int, seed: int = 7) -> list[dict]:
    import random

    rng = random.Random(seed)
    by_m: dict[str, list[dict]] = {}
    for b in cands:
        if b["kw_in_text"] and len(b["text"].split()) >= 8:
            by_m.setdefault(b["date"][:7], []).append(b)
    out = []
    for m in sorted(by_m):
        pool = by_m[m]
        out += pool if len(pool) <= per_month else rng.sample(pool, per_month)
    return sorted(out, key=lambda b: b["bid"])


def _instances(base: dict, dates: list[date], category_fn) -> list[dict]:
    out = []
    for d in dates:
        q = {k: v for k, v in base.items() if not k.startswith("_")}
        q["qid"] = f"{base['base_id']}@{d.isoformat()}"
        q["ask_at"] = f"{d.isoformat()}T23:59:59Z"
        q["category"] = category_fn(d)
        out.append(q)
    return out


def build_quiz(per_month: int = 14, n_points: int = 48, n_pairs: int = 20, n_false: int = 9, n_future: int = 8) -> None:
    import random

    from factbase import llm

    spent0 = my_spend()
    rng = random.Random(11)
    items = load_items()
    idx = Index(items)
    first_day = _d(items[0]["ts"])

    # 1) candidate WCEP bullets -> one question each (LLM reads only the bullet)
    cands = _sample_candidates(wcep_candidates(), per_month)
    log(f"quiz: {len(cands)} sampled WCEP bullets")
    written = llm.pmap(write_question, cands, workers=8)
    qs = []
    for b, w in zip(cands, written):
        if isinstance(w, Exception) or w.get("skip") or not w.get("gold") or not w.get("question"):
            continue
        qs.append({"b": b, "w": w})
    log(f"quiz: {len(qs)} questions written")

    # 2) verify each against the headline stream (d-1..d+2)
    ver = llm.pmap(lambda x: verify_against_stream(idx, x["w"], _d(x["b"]["date"])), qs, workers=8)
    verified = []
    for x, v in zip(qs, ver):
        if isinstance(v, Exception):
            log(f"  verify error {x['b']['bid']}: {v!r}")
            continue
        x["v"] = v
        if v["ok"]:
            verified.append(x)
    log(f"quiz: {len(verified)} verified against the stream ({my_spend() - spent0:.2f} USD so far)")
    (QUIZ_CACHE).mkdir(parents=True, exist_ok=True)
    (QUIZ_CACHE / "verified.json").write_text(json.dumps(verified, ensure_ascii=False, indent=1))
    (QUIZ_CACHE / "rejected.json").write_text(
        json.dumps([x for x in qs if not x.get("v", {}).get("ok")], ensure_ascii=False, indent=1, default=str)
    )

    out: list[dict] = []
    n_base = 0

    def new_base(**kw) -> dict:
        nonlocal n_base
        n_base += 1
        base = {"base_id": f"{NAME}:q{n_base:04d}", "dataset": NAME, "numeric_tolerance": None}
        base.update(kw)
        return base

    def ev_first_ok(ev: list[str]) -> date:
        return max(_d(idx.by_id[e]["ts"]) for e in ev)

    # 3) point questions, spread across months; questions guessable from their wording go last
    guesses = llm.pmap(lambda x: _guessable(x["w"]), verified, workers=8)
    for x, g in zip(verified, guesses):
        x["guessable"] = bool(g) if not isinstance(g, Exception) else False
    log(f"quiz: {sum(x['guessable'] for x in verified)} of {len(verified)} verified questions guessable from wording")
    by_m: dict[str, list[dict]] = {}
    for x in verified:
        by_m.setdefault(x["b"]["date"][:7], []).append(x)
    months = sorted(by_m)
    chosen: list[dict] = []
    quota = {m: 1 for m in months}
    left = n_points - len(months)
    while left > 0:
        progressed = False
        for m in sorted(months, key=lambda m: -len(by_m[m])):
            if left > 0 and quota[m] < len(by_m[m]):
                quota[m] += 1
                left -= 1
                progressed = True
        if not progressed:
            break
    for m in months:
        pool = sorted(by_m[m], key=lambda x: x["b"]["bid"])
        rng.shuffle(pool)
        pool.sort(key=lambda x: (x["guessable"], x["w"]["question"] in EXCLUDE))
        chosen += [x for x in pool[: quota[m]] if x["w"]["question"] not in EXCLUDE]
    chosen.sort(key=lambda x: x["b"]["bid"])
    point_bases = []
    for x in chosen:
        fd = _d(x["b"]["date"])
        ev = x["v"]["evidence_ids"]
        base = new_base(
            question=x["w"]["question"],
            gold=GOLD_OVERRIDE.get(x["w"]["question"], x["w"]["gold"]),
            answer_type=x["w"]["answer_type"],
            fact_time=fd.isoformat(),
            evidence_item_ids=ev,
            gold_source="curated_wcep",
            _wcep=x["b"],
        )
        point_bases.append((base, x))
        dates = reask_dates(max(ev_first_ok(ev), fd))
        out += _instances(base, dates, lambda d, fd=fd: "point_recent" if (d - fd).days <= 30 else "point_old")

    # 4) ordering / change / as_of_state / multi_hop questions from verified bullets on the same storyline
    by_story: dict[str, list[dict]] = {}
    for x in verified:
        st = storyline(x["b"])
        if st != "-":
            by_story.setdefault(st, []).append(x)
    groups = []
    for st, xs in sorted(by_story.items()):
        xs = sorted(xs, key=lambda x: x["b"]["bid"])
        for k in range(0, len(xs), 14):
            g = xs[k : k + 14]
            if len(g) >= 2:
                groups.append((st, g))

    def check_story_q(q: dict, xs: list[dict]) -> dict:
        # balanced: up to 60 distinct headlines, split across the bullets used
        per = max(1, 60 // len(xs))
        seen, hs = set(), []
        for x in xs:
            n = 0
            for h in sorted((idx.by_id[e] for e in x["v"]["evidence_ids"]), key=lambda h: h["ts"]):
                if n < per and h["title"].lower() not in seen:
                    seen.add(h["title"].lower())
                    hs.append(h)
                    n += 1
        hs.sort(key=lambda h: h["ts"])
        blind = _llm(BLIND_SYS, f"Question: {q['question']}\n\nHeadlines:\n{_fmt_headlines(hs)}", BLIND_SCHEMA, effort="low")
        m = _llm(MATCH_SYS, f"Question: {q['question']}\nGold answers: {q['gold']}\nCandidate: {blind.get('answer', '')}", MATCH_SCHEMA)
        return {"q": q, "bids": [x["b"]["bid"] for x in xs], "blind": blind.get("answer", ""), "ok": bool(m.get("match"))}

    def story_job(sg):
        st, g = sg
        lines = "\n".join(f"[{i}] {_human(_d(x['b']['date']))}: {x['b']['text']}" for i, x in enumerate(g))
        p = _llm(STORY_SYS, f"Storyline: {st}\n\nBullets:\n{lines}", STORY_SCHEMA, effort="low")
        res = []
        for q in p.get("questions", [])[:4]:
            ids = [i for i in q.get("bullets", []) if isinstance(i, int) and 0 <= i < len(g)]
            if len(set(ids)) < 2 or not q.get("unique_events", False) or q.get("type") not in ("ordering", "change"):
                continue
            res.append(check_story_q(q, [g[i] for i in sorted(set(ids))]))
        return res

    # one global pass over all verified bullets for change / as_of_state / multi_hop across storylines
    allv = sorted(verified, key=lambda x: x["b"]["bid"])

    def global_job(kind: str):
        lines = "\n".join(f"[{i}] {_human(_d(x['b']['date']))}: {x['b']['text']}" for i, x in enumerate(allv))
        p = _llm(GLOBAL_SYS[kind], f"Bullets:\n{lines}", STORY_SCHEMA, effort="low")
        res = []
        for q in p.get("questions", [])[:12]:
            ids = [i for i in q.get("bullets", []) if isinstance(i, int) and 0 <= i < len(allv)]
            if len(set(ids)) < 2 or not q.get("unique_events", False) or q.get("type") not in STORY_TYPES:
                continue
            res.append(check_story_q(q, [allv[i] for i in sorted(set(ids))]))
        return res

    groups += [("(global)", kind) for kind in GLOBAL_SYS]

    sres = llm.pmap(lambda sg: global_job(sg[1]) if sg[0] == "(global)" else story_job(sg), groups, workers=8)
    by_bid = {x["b"]["bid"]: x for x in verified}
    story_qs = []
    for (st, g), r in zip(groups, sres):
        if isinstance(r, Exception):
            log(f"  storyline error {st}: {r!r}")
            continue
        for k in r:
            k["storyline"] = st
            xs = [by_bid[b] for b in k["bids"]]
            if k["ok"] and k["q"]["type"] == "ordering":
                # the stream must show the same order as the bullets: compare first sightings
                firsts = sorted((min(idx.by_id[e]["ts"] for e in x["v"]["evidence_ids"]), x["b"]["date"]) for x in xs)
                if [d for _, d in firsts] != sorted(d for _, d in firsts) or len({d for _, d in firsts}) < len(firsts):
                    k["ok"] = False
            story_qs.append(k)
    (QUIZ_CACHE / "storyline_questions.json").write_text(json.dumps(story_qs, ensure_ascii=False, indent=1))
    caps = {"ordering": n_pairs // 2, "change": n_pairs // 2, "as_of_state": 6, "multi_hop": 6}
    counts = {t: 0 for t in caps}
    ok_qs = [k for k in story_qs if k["ok"]]
    rng.shuffle(ok_qs)
    ok_qs.sort(key=lambda k: counts.get(k["q"]["type"], 0))
    used_pairs: set[frozenset] = set()
    for k in ok_qs:
        t = k["q"]["type"]
        if counts[t] >= caps[t] or frozenset(k["bids"]) in used_pairs or k["q"]["question"] in EXCLUDE:
            continue
        used_pairs.add(frozenset(k["bids"]))
        xs = [by_bid[b] for b in k["bids"]]
        ev = sorted({e for x in xs for e in x["v"]["evidence_ids"]})
        fd = max(_d(x["b"]["date"]) for x in xs)
        first = max(ev_first_ok(ev), fd)
        base = new_base(
            question=k["q"]["question"],
            gold=k["q"]["gold"],
            answer_type="text",
            fact_time=fd.isoformat(),
            evidence_item_ids=ev,
            gold_source="curated_wcep",
        )
        out += _instances(base, sorted({_month_end(first), END}), lambda d, t=t: t)
        counts[t] += 1
    log(f"quiz: storyline questions {counts} (from {len(ok_qs)} verified of {len(story_qs)} proposed)")

    # 5) aggregates computed in code over the stream itself
    out += _aggregates(idx, items, new_base)

    # 6) abstain: false premise (verified against headlines) and questions about events after ask_at
    fp_pool = [x for x in verified if x not in [c for _, c in point_bases]] + [c for _, c in point_bases]
    fp_pool = fp_pool[:]
    rng.shuffle(fp_pool)

    def false_job(x):
        user = f"Date: {_human(_d(x['b']['date']))}\nBullet: {x['b']['text']}\nTrue question: {x['w']['question']} (answer: {x['w']['gold'][0]})"
        f = _llm(FALSE_SYS, user, FALSE_SCHEMA)
        terms = set()
        for k in f["keywords"] + x["w"]["keywords"]:
            terms |= _tokens(k)
        hs = idx.top(_d(x["b"]["date"]), terms, k=120)
        v = _llm(FALSE_VERIFY_SYS, f"Question: {f['question']}\n\nHeadlines:\n{_fmt_headlines(hs)}", FALSE_VERIFY_SCHEMA, effort="low")
        con = [hs[i]["id"] for i in v.get("contradicting", []) if isinstance(i, int) and 0 <= i < len(hs)]
        return {"f": f, "ok": bool(v.get("contradicted")) and not v.get("supported") and bool(con), "ev": con}

    fres = llm.pmap(false_job, fp_pool[: n_false + 14], workers=8)
    n_fp = 0
    for x, r in zip(fp_pool, fres):
        if isinstance(r, Exception) or not r["ok"] or n_fp >= n_false or r["f"]["question"] in EXCLUDE:
            continue
        fd = _d(x["b"]["date"])
        base = new_base(
            question=r["f"]["question"],
            gold=[f"False premise: {r['f']['gold_note']}"],
            answer_type="abstain",
            fact_time=fd.isoformat(),
            evidence_item_ids=r["ev"],
            gold_source="curated_wcep",
        )
        first = max(ev_first_ok(r["ev"]), fd)
        out += _instances(base, sorted({_month_end(first), END}), lambda d: "abstain")
        n_fp += 1
    future_pool = [(b, x) for b, x in point_bases if _d(b["fact_time"]) >= first_day + timedelta(days=75)]
    rng.shuffle(future_pool)
    for b, x in future_pool[:n_future]:
        fd = _d(b["fact_time"])
        ask = _month_end(fd - timedelta(days=rng.randint(45, 150)))
        ask = max(ask, _month_end(first_day))
        if ask >= fd:
            continue
        base = new_base(
            question=b["question"],
            gold=[f"Not in the record as of {_human(ask)}: the event is dated {_human(fd)}, after the ask date."],
            answer_type="abstain",
            fact_time=fd.isoformat(),
            evidence_item_ids=[],
            gold_source="curated_wcep",
        )
        out += _instances(base, [ask], lambda d: "abstain")
    log(f"quiz: {n_fp} false-premise, {min(n_future, len(future_pool))} future-event abstain bases")

    out.sort(key=lambda q: (q["ask_at"], q["qid"]))
    with open(OUT / "questions.jsonl", "w") as f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    log(f"quiz: wrote {len(out)} instances over {n_base} bases; LLM delta {my_spend() - spent0:.2f} USD")


AGG_TERMS = ["Fordow", "Natanz", "Isfahan", "Bandar Abbas", "Kharg", "Snapback", "Chabahar", "Bushehr", "Muscat", "Rising Lion", "Midnight Hammer"]


def _aggregates(idx: Index, items: list[dict], new_base) -> list[dict]:
    """Exactly checkable counts / first mentions over headline titles in the stream (case-insensitive)."""
    out = []
    by_term: dict[str, list[dict]] = {}
    for t in AGG_TERMS:
        rx = re.compile(r"\b" + re.escape(t) + r"\b", re.I)
        by_term[t] = [it for it in items if rx.search(it["title"])]
    # first appearance of a term that only enters the record mid-window
    for t, hits in by_term.items():
        if len(hits) < 15:
            continue
        first = _d(hits[0]["ts"])
        if first < START + timedelta(days=60):
            continue
        ev = [h["id"] for h in hits if h["ts"][:10] == hits[0]["ts"][:10]]
        base = new_base(
            question=f"On what date (UTC) did the term '{t}' first appear in a news headline in the record?",
            gold=[first.isoformat(), _human(first)],
            answer_type="date",
            fact_time=first.isoformat(),
            evidence_item_ids=ev,
            gold_source="structured",
        )
        out += _instances(base, sorted({_month_end(first), END}), lambda d: "aggregate")
    # busiest day for a term within one calendar month
    for t, hits in by_term.items():
        per_day: dict[str, int] = {}
        for h in hits:
            per_day[h["ts"][:10]] = per_day.get(h["ts"][:10], 0) + 1
        by_month: dict[str, list[tuple[int, str]]] = {}
        for dd, n in per_day.items():
            by_month.setdefault(dd[:7], []).append((n, dd))
        for m, lst in sorted(by_month.items()):
            lst.sort(reverse=True)
            total = sum(n for n, _ in lst)
            # require a clear winner so the answer is robust
            if total >= 25 and len(lst) >= 3 and lst[0][0] >= 2 * lst[1][0]:
                best = date.fromisoformat(lst[0][1])
                me = _month_end(best)
                ev = [h["id"] for h in hits if h["ts"][:10] == lst[0][1]]
                base = new_base(
                    question=(
                        f"In {best.strftime('%B %Y')}, on which date (UTC) did the most news headlines in the record "
                        f"mention '{t}'?"
                    ),
                    gold=[best.isoformat(), _human(best)],
                    answer_type="date",
                    fact_time=me.isoformat(),
                    evidence_item_ids=ev,
                    gold_source="structured",
                )
                out += _instances(base, sorted({me, END}), lambda d: "aggregate")
                break
    return out


def stats() -> None:
    """Coverage per month, and overlap with whatever DOC API windows were fetched."""
    items = load_items()
    per_m: dict[str, list[int]] = {}
    for it in items:
        per_m.setdefault(it["ts"][:7], [0, 0])
        per_m[it["ts"][:7]][0 if it["meta"]["match"] == "headline" else 1] += 1
    missing: dict[str, int] = {}
    for p in GKG_DIR.rglob("*.json"):
        if not json.loads(p.read_text()).get("file"):
            missing[p.parent.name] = missing.get(p.parent.name, 0) + 1
    print("| Month | Items | Items/day | Headline matches | Body-only matches | Missing hourly files |")
    print("|---|---|---|---|---|---|")
    for m in sorted(per_m):
        y, mo = map(int, m.split("-"))
        nd = (_month_end(date(y, mo, 1)) - date(y, mo, 1)).days + 1
        h, b = per_m[m]
        print(f"| {m} | {h + b} | {(h + b) / nd:.0f} | {h} | {b} | {missing.get(m, 0)} |")
    urls = {it["url"] for it in items}
    doc_urls, n_win = set(), 0
    for p in GDELT_DIR.rglob("*.json"):
        n_win += 1
        doc_urls |= {a["url"] for a in json.loads(p.read_text()).get("articles", [])}
    if doc_urls:
        print(f"DOC API windows fetched: {n_win}; DOC URLs: {len(doc_urls)}; also in stream: {len(doc_urls & urls)}")


def main(argv: list[str]) -> None:
    stage = argv[1] if len(argv) > 1 else "all"
    if stage == "gdelt":
        download_gdelt()  # DOC API; too rate-limited to complete, see README
    if stage == "refine":
        refine_gdelt()
    if stage in ("gkg", "all"):
        download_gkg()
    if stage in ("wcep", "all"):
        download_wcep()
    if stage in ("items", "all"):
        build_items()
    if stage in ("quiz", "all"):
        build_quiz()
    if stage in ("stats", "all"):
        stats()


if __name__ == "__main__":
    main(sys.argv)
