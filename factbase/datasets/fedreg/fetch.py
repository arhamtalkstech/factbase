"""Download Federal Register document lists and raw text (cached under data/raw/fedreg/)."""

from __future__ import annotations

import html
import json
import re
import time
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "fedreg"
API = "https://www.federalregister.gov/api/v1/documents.json"
START, END = "2024-11-01", "2026-10-31"

FIELDS = [
    "title", "type", "subtype", "abstract", "document_number", "publication_date", "effective_on",
    "agencies", "raw_text_url", "html_url", "executive_order_number", "proclamation_number",
    "presidential_document_number", "signing_date", "action", "dates", "cfr_references",
    "citation", "correction_of", "regulation_id_numbers", "toc_subject", "toc_doc",
]

# name -> extra query params
QUERIES = {
    "ofac": {"conditions[agencies][]": "foreign-assets-control-office"},
    "bis": {"conditions[agencies][]": "industry-and-security-bureau"},
    "presdocu": {"conditions[type][]": "PRESDOCU"},
    "state": {"conditions[agencies][]": "state-department"},
}

from ...paths import user_agent

HEADERS = {"User-Agent": user_agent()}


def _get(client: httpx.Client, url: str, params=None) -> httpx.Response:
    delay = 2.0
    for _ in range(8):
        try:
            r = client.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
        except httpx.HTTPError:
            pass
        time.sleep(delay)
        delay = min(delay * 2, 60)
    raise RuntimeError(f"failed GET {url}")


def fetch_lists() -> dict[str, list[dict]]:
    out = {}
    (RAW / "lists").mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for name, cond in QUERIES.items():
            path = RAW / "lists" / f"{name}.json"
            if path.exists():
                out[name] = json.loads(path.read_text())
                continue
            # Query month by month so no single result set comes near the API's paging cap.
            results: list[dict] = []
            y, m = 2024, 11
            while (y, m) <= (2026, 10):
                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                last_day = (date(ny, nm, 1) - timedelta(days=1)).day
                params = [(k, v) for k, v in cond.items()]
                params += [
                    ("conditions[publication_date][gte]", f"{y}-{m:02d}-01"),
                    ("conditions[publication_date][lte]", f"{y}-{m:02d}-{last_day:02d}"),
                    ("per_page", "1000"),
                    ("order", "oldest"),
                ]
                params += [("fields[]", f) for f in FIELDS]
                url, p = API, params
                while url:
                    d = _get(client, url, p).json()
                    results.extend(d.get("results", []))
                    url, p = d.get("next_page_url"), None
                y, m = ny, nm
            path.write_text(json.dumps(results))
            out[name] = results
            print(f"fetched {name}: {len(results)}")
    return out


def fetch_texts(docs: list[dict]) -> None:
    (RAW / "text").mkdir(parents=True, exist_ok=True)
    todo = [d for d in docs if d.get("raw_text_url") and not (RAW / "text" / f"{d['document_number']}.txt").exists()]
    if not todo:
        return
    print(f"fetching raw text for {len(todo)} documents")

    def one(d):
        with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
            r = _get(client, d["raw_text_url"])
            txt = r.text if r.status_code == 200 else ""
            (RAW / "text" / f"{d['document_number']}.txt").write_text(txt)
            time.sleep(0.2)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, todo))


def load_text(docnum: str) -> str:
    p = RAW / "text" / f"{docnum}.txt"
    if not p.exists():
        return ""
    t = p.read_text()
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)
