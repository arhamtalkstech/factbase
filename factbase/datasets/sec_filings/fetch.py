"""Download SEC EDGAR submissions and XBRL companyfacts JSON into data/raw/sec_filings/.

Cached: files already on disk are not re-downloaded.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "sec_filings"
from ...paths import user_agent

UA = user_agent()  # SEC requires a User-Agent with contact details: set FACTBASE_CONTACT

# ticker -> list of CIKs (ExxonMobil reorganised under a new holding-company CIK on 2026-07-01).
COMPANIES: dict[str, list[int]] = {
    "XOM": [34088, 2115436],
    "CVX": [93410],
    "COP": [1163165],
    "LMT": [936468],
    "RTX": [101829],
    "NOC": [1133421],
    "GD": [40533],
    "AAPL": [320193],
    "MSFT": [789019],
    "NVDA": [1045810],
    "AMZN": [1018724],
    "GOOGL": [1652044],
    "META": [1326801],
    "JPM": [19617],
    "BAC": [70858],
    "WMT": [104169],
    "KO": [21344],
    "PFE": [78003],
    "JNJ": [200406],
    "UNH": [731766],
    "BA": [12927],
    "CAT": [18230],
    "GE": [40545],
    "F": [37996],
    "GM": [1467858],
    "TSLA": [1318605],
    "INTC": [50863],
    "DIS": [1744489],
    "NFLX": [1065280],
    "ORCL": [1341439],
}

_last = [0.0]


def _get(client: httpx.Client, url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for attempt in range(5):
        wait = 0.15 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        r = client.get(url)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return dest
        if r.status_code == 404:
            raise FileNotFoundError(url)
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    return dest


def fetch_all() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}, timeout=60) as c:
        for tk, ciks in COMPANIES.items():
            for cik in ciks:
                p = f"{cik:010d}"
                sub = _get(c, f"https://data.sec.gov/submissions/CIK{p}.json", RAW / f"sub_{p}.json")
                d = json.loads(sub.read_text())
                for f in d["filings"].get("files", []):
                    # Older pages; only needed when the "recent" block does not reach back to the window start.
                    if f.get("filingTo", "") >= "2024-10-01":
                        _get(c, f"https://data.sec.gov/submissions/{f['name']}", RAW / f["name"])
                try:
                    _get(c, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{p}.json", RAW / f"facts_{p}.json")
                except FileNotFoundError:
                    print("no companyfacts for", tk, cik)
                print("ok", tk, cik)


if __name__ == "__main__":
    fetch_all()
