"""Build the `markets` dataset: daily FRED market/macro series plus a programmatic quiz.

Usage: uv run python -m factbase.datasets.markets.build
"""

from __future__ import annotations

import calendar
import csv
import json
import random
from bisect import bisect_right
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "markets"
OUT = ROOT / "data" / "markets"
NAME = "markets"

WIN_START = date(2024, 11, 1)
WIN_END = date(2026, 10, 31)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2024-10-01&coed=2026-10-31"

# kind: price (pct change in text), yield (pp change), fx, index
SERIES = {
    "DCOILBRENTEU": dict(kind="price", dp=2, unit="USD/bbl", unit_text="USD per barrel",
                         subj="the Brent crude oil spot price", short="Brent crude spot",
                         q="closing Brent crude oil spot price (USD per barrel)"),
    "DCOILWTICO": dict(kind="price", dp=2, unit="USD/bbl", unit_text="USD per barrel",
                       subj="the WTI (West Texas Intermediate, Cushing) crude oil spot price", short="WTI crude spot",
                       q="closing WTI crude oil spot price (USD per barrel)"),
    "DHHNGSP": dict(kind="price", dp=2, unit="USD/MMBtu", unit_text="USD per million BTU",
                    subj="the Henry Hub natural gas spot price", short="Henry Hub gas spot",
                    q="Henry Hub natural gas spot price (USD per million BTU)"),
    "DGS10": dict(kind="yield", dp=2, unit="percent", unit_text="%",
                  subj="the 10-year US Treasury constant-maturity yield", short="10-year Treasury yield",
                  q="10-year US Treasury constant-maturity yield (percent)"),
    "DGS2": dict(kind="yield", dp=2, unit="percent", unit_text="%",
                 subj="the 2-year US Treasury constant-maturity yield", short="2-year Treasury yield",
                 q="2-year US Treasury constant-maturity yield (percent)"),
    "DEXUSEU": dict(kind="fx", dp=4, unit="USD per EUR", unit_text="US dollars per euro",
                    subj="the US dollar to euro exchange rate (noon buying rate in New York)", short="EUR/USD",
                    q="US dollar to euro exchange rate (US dollars per euro, noon buying rate in New York)"),
    "DEXJPUS": dict(kind="fx", dp=2, unit="JPY per USD", unit_text="Japanese yen per US dollar",
                    subj="the Japanese yen to US dollar exchange rate (noon buying rate in New York)", short="USD/JPY",
                    q="Japanese yen to US dollar exchange rate (yen per US dollar, noon buying rate in New York)"),
    "VIXCLS": dict(kind="index", dp=2, unit="index points", unit_text="",
                   subj="the CBOE Volatility Index (VIX)", short="VIX",
                   q="closing value of the CBOE Volatility Index (VIX)"),
    "SP500": dict(kind="index", dp=2, unit="index points", unit_text="points",
                  subj="the S&P 500 index", short="S&P 500",
                  q="closing value of the S&P 500 index"),
    "NASDAQCOM": dict(kind="index", dp=2, unit="index points", unit_text="points",
                      subj="the NASDAQ Composite index", short="NASDAQ Composite",
                      q="closing value of the NASDAQ Composite index"),
}
FED = ("DFEDTARL", "DFEDTARU")
FED_ID = "DFEDTAR"


# ---------------------------------------------------------------- helpers

def long_date(d: date) -> str:
    return f"{d.day} {calendar.month_name[d.month]} {d.year}"


def fmt(s: str, v: float) -> str:
    return f"{v:.{SERIES[s]['dp']}f}"


def iid(s: str, d: date) -> str:
    return f"{NAME}:{d.isoformat()}:{s}"


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def add_months_end(d: date, k: int) -> date:
    m = d.month - 1 + k
    return month_end(date(d.year + m // 12, m % 12 + 1, 1))


def first_month_end_after(d: date) -> date:
    me = month_end(d)
    return me if d < me else add_months_end(d, 1)


def sched_point(d: date) -> list[date]:
    me1 = first_month_end_after(d)
    cands = [me1, add_months_end(me1, 3), add_months_end(me1, 6), add_months_end(me1, 12), WIN_END]
    return sorted({c for c in cands if c <= WIN_END})


def sched_other(d: date) -> list[date]:
    me1 = first_month_end_after(d)
    return sorted({c for c in (me1, add_months_end(me1, 6), WIN_END) if c <= WIN_END})


# ---------------------------------------------------------------- data

def load_csv(s: str) -> list[tuple[date, float]]:
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / f"{s}.csv"
    if not p.exists():
        r = httpx.get(FRED_CSV.format(s=s), timeout=60, follow_redirects=True)
        r.raise_for_status()
        p.write_text(r.text)
    rows = list(csv.reader(p.open()))[1:]
    return [(date.fromisoformat(d), float(v)) for d, v in rows if v.strip() not in ("", ".")]


class Data:
    def __init__(self) -> None:
        self.obs: dict[str, list[tuple[date, float]]] = {}
        dropped = []
        for s in SERIES:
            o = load_csv(s)
            if not o or o[-1][0] < date(2026, 10, 1):
                dropped.append(s)
                continue
            self.obs[s] = [(d, round(v, SERIES[s]["dp"])) for d, v in o]
        if dropped:
            raise SystemExit(f"series without late-2026 data: {dropped}")
        self.val = {s: dict(o) for s, o in self.obs.items()}
        self.win = {s: [(d, v) for d, v in o if WIN_START <= d <= WIN_END] for s, o in self.obs.items()}
        lo, hi = dict(load_csv(FED[0])), dict(load_csv(FED[1]))
        self.fed_daily = sorted((d, lo[d], hi[d]) for d in lo if d in hi)
        # (date, lower, upper, prev_lower, prev_upper); first row = window-start state
        _, l0, u0 = [r for r in self.fed_daily if r[0] <= WIN_START][-1]
        self.fed: list[tuple[date, float, float, float | None, float | None]] = [(WIN_START, l0, u0, None, None)]
        prev = (l0, u0)
        for d, l, u in self.fed_daily:
            if WIN_START < d <= WIN_END and (l, u) != prev:
                self.fed.append((d, l, u, *prev))
                prev = (l, u)

    def v(self, s: str, d: date) -> float | None:
        return self.val[s].get(d)

    def latest(self, s: str, d: date) -> tuple[date, float]:
        o = self.obs[s]
        i = bisect_right([x for x, _ in o], d)
        return o[i - 1]

    def period(self, s: str, a: date, b: date) -> list[tuple[date, float]]:
        return [(d, v) for d, v in self.win[s] if a <= d <= b]

    def first_above(self, s: str, x: float) -> tuple[date, float]:
        return next((d, v) for d, v in self.win[s] if v > x)

    def first_below(self, s: str, x: float) -> tuple[date, float]:
        return next((d, v) for d, v in self.win[s] if v < x)

    def fed_at(self, d: date):
        return [f for f in self.fed if f[0] <= d][-1]


def rng_str(l: float, u: float) -> str:
    return f"{l:.2f}-{u:.2f}%"


def rng_aliases(l: float, u: float) -> list[str]:
    return [rng_str(l, u), f"{l:.2f}% to {u:.2f}%", f"{l:g}-{u:g}%", f"{l:g}% to {u:g}%"]


# ---------------------------------------------------------------- items

def build_items(D: Data) -> list[dict]:
    items = []
    order = {s: i for i, s in enumerate(list(SERIES) + [FED_ID])}
    for s, meta in SERIES.items():
        o = D.obs[s]
        for i, (d, v) in enumerate(o):
            if not (WIN_START <= d <= WIN_END):
                continue
            pd_, pv = o[i - 1]
            diff = round(v - pv, meta["dp"])
            head = f"On {long_date(d)} ({calendar.day_name[d.weekday()]}), {meta['subj']}"
            if meta["kind"] == "yield":
                body = f"{head} closed at {fmt(s, v)}%"
                if diff == 0:
                    chg = f", unchanged from the previous close of {fmt(s, pv)}% on {long_date(pd_)}."
                else:
                    chg = (f", {'up' if diff > 0 else 'down'} {abs(diff):.2f} percentage points from the previous "
                           f"close of {fmt(s, pv)}% on {long_date(pd_)}.")
                title = f"{meta['short']} closes at {fmt(s, v)}%"
            else:
                verb = "was" if meta["kind"] == "fx" else "closed at"
                unit = f" {meta['unit_text']}" if meta["unit_text"] else ""
                body = f"{head} {verb} {fmt(s, v)}{unit}"
                pct = (v - pv) / pv * 100
                if diff == 0:
                    chg = f", unchanged from the previous close of {fmt(s, pv)} on {long_date(pd_)}."
                else:
                    chg = (f", {'up' if diff > 0 else 'down'} {abs(diff):.{meta['dp']}f} ({pct:+.1f}%) from the "
                           f"previous {'reading' if meta['kind'] == 'fx' else 'close'} of {fmt(s, pv)} on {long_date(pd_)}.")
                if meta["kind"] == "fx":
                    chg = chg.replace("previous close", "previous reading")
                title = f"{meta['short']} {'at' if meta['kind'] == 'fx' else 'closes at'} {fmt(s, v)}{unit} ({pct:+.1f}%)"
            items.append({
                "id": iid(s, d), "dataset": NAME, "ts": f"{d.isoformat()}T22:00:00Z", "title": title,
                "text": body + chg, "source": "FRED", "url": f"https://fred.stlouisfed.org/series/{s}",
                "meta": {"series": s, "date": d.isoformat(), "value": v, "unit": meta["unit"],
                         "prev_value": pv, "prev_date": pd_.isoformat()},
            })
    for d, l, u, pl, pu in D.fed:
        wd = calendar.day_name[d.weekday()]
        if pl is None:
            text = (f"As of {long_date(d)} ({wd}), the Federal Reserve's federal funds target range was "
                    f"{rng_str(l, u)} (lower limit {l:.2f}%, upper limit {u:.2f}%).")
            title = f"Fed funds target range stands at {rng_str(l, u)}"
        else:
            step = round(u - pu, 2)
            what = f"a {'cut' if step < 0 else 'hike'} of {abs(step):.2f} percentage points"
            text = (f"On {long_date(d)} ({wd}) the Federal Reserve's federal funds target range changed from "
                    f"{rng_str(pl, pu)} to {rng_str(l, u)}, {what} (effective date as recorded by FRED).")
            title = f"Fed {'cuts' if step < 0 else 'raises'} target range to {rng_str(l, u)}"
        items.append({
            "id": iid(FED_ID, d), "dataset": NAME, "ts": f"{d.isoformat()}T22:00:00Z", "title": title,
            "text": text, "source": "FRED", "url": "https://fred.stlouisfed.org/series/DFEDTARU",
            "meta": {"series": FED_ID, "date": d.isoformat(), "value": rng_str(l, u), "unit": "percent",
                     "prev_value": rng_str(pl, pu) if pl is not None else None,
                     "lower": l, "upper": u},
        })
    items.sort(key=lambda it: (it["ts"], order[it["meta"]["series"]]))
    return items


# ---------------------------------------------------------------- questions

class Quiz:
    def __init__(self) -> None:
        self.base: list[dict] = []

    def add(self, category: str, question: str, gold: list[str], answer_type: str, fact_time: date,
            evidence: list[str], asks: list[date], tol: float | None = None) -> None:
        self.base.append(dict(category=category, question=question, gold=gold, answer_type=answer_type,
                              fact_time=fact_time, evidence=evidence, asks=asks, tol=tol))

    def expand(self) -> list[dict]:
        out = []
        for n, b in enumerate(self.base, 1):
            base_id = f"{NAME}:q{n:04d}"
            for a in b["asks"]:
                assert WIN_START <= a <= WIN_END, (b["question"], a)
                cat = b["category"]
                if cat == "point":
                    cat = "point_recent" if (a - b["fact_time"]).days <= 30 else "point_old"
                if b["answer_type"] != "abstain":
                    assert a >= b["fact_time"], (b["question"], a)
                out.append({
                    "qid": f"{base_id}@{a.isoformat()}", "base_id": base_id, "dataset": NAME,
                    "ask_at": f"{a.isoformat()}T23:59:59Z", "question": b["question"], "gold": b["gold"],
                    "answer_type": b["answer_type"], "numeric_tolerance": b["tol"], "category": cat,
                    "fact_time": b["fact_time"].isoformat(), "evidence_item_ids": b["evidence"],
                    "gold_source": "structured",
                })
        return out


def exact_tol(s: str) -> float:
    return {"DEXUSEU": 0.0002, "DEXJPUS": 0.0005}.get(s, 0.001)


def date_gold(d: date) -> list[str]:
    return [d.isoformat(), long_date(d)]


def pct_gold(x: float) -> list[str]:
    return [f"{x:.1f}", f"{x:.2f}"]


def build_questions(D: Data) -> list[dict]:
    Q = Quiz()
    rnd = random.Random(20261102)

    # --- point lookups: 22 base, stratified over the window
    plan = (["DCOILBRENTEU"] * 3 + ["SP500"] * 3 + ["DCOILWTICO", "DHHNGSP", "DGS10", "DGS2", "DEXUSEU",
            "DEXJPUS", "VIXCLS", "NASDAQCOM"] * 2)
    rnd.shuffle(plan)
    span = (date(2026, 10, 20) - WIN_START).days
    for k, s in enumerate(plan):
        a = WIN_START + timedelta(days=span * k // len(plan))
        b = WIN_START + timedelta(days=span * (k + 1) // len(plan) - 1)
        d, v = rnd.choice(D.period(s, a, b))
        Q.add("point", f"What was the {SERIES[s]['q']} on {long_date(d)}?", [fmt(s, v)], "number", d,
              [iid(s, d)], sched_point(d), exact_tol(s))

    # --- as_of_state: latest value as of the ask date (some weekends/holidays), and Fed range
    for s, a in [("DCOILBRENTEU", date(2025, 1, 18)), ("SP500", date(2025, 4, 18)), ("DGS10", date(2025, 7, 4)),
                 ("VIXCLS", date(2025, 8, 29)), ("DEXUSEU", date(2025, 11, 27)), ("DHHNGSP", date(2026, 1, 25)),
                 ("NASDAQCOM", date(2026, 5, 13)), ("DCOILWTICO", date(2026, 8, 9)),
                 ("DEXJPUS", date(2026, 3, 7))]:
        d, v = D.latest(s, a)
        Q.add("as_of_state", f"As of {long_date(a)}, what was the most recent recorded {SERIES[s]['q']}?",
              [fmt(s, v)], "number", d, [iid(s, d)], [a], exact_tol(s))
    for a in [date(2025, 3, 15), date(2025, 10, 15), date(2026, 2, 28), date(2026, 10, 20)]:
        d, l, u, *_ = D.fed_at(a)
        Q.add("as_of_state", f"As of {long_date(a)}, what was the Federal Reserve's federal funds target range?",
              rng_aliases(l, u), "text", d, [iid(FED_ID, d)], [a])

    # --- aggregates
    def ext(s, a, b, label, fn, ask, extra=""):
        p = D.period(s, a, b)
        best = fn(v for _, v in p)
        ds = [d for d, v in p if v == best]
        assert len(ds) == 1, (s, label, ds)
        word = "highest" if fn is max else "lowest"
        if ask == "value":
            Q.add("aggregate", f"What was the {word} {SERIES[s]['q']} recorded in {label}?{extra}",
                  [fmt(s, best)], "number", b, [iid(s, ds[0])], sched_other(b), exact_tol(s))
        else:
            Q.add("aggregate", f"On what date in {label} did the {SERIES[s]['q']} record its {word} value?",
                  date_gold(ds[0]), "date", b, [iid(s, ds[0])], sched_other(b))

    ext("DCOILBRENTEU", date(2026, 4, 1), date(2026, 4, 30), "April 2026", max, "value")
    ext("DCOILBRENTEU", date(2026, 7, 1), date(2026, 9, 30), "Q3 2026 (1 July to 30 September 2026)", max, "date")
    ext("SP500", date(2025, 4, 1), date(2025, 6, 30), "Q2 2025 (1 April to 30 June 2025)", min, "value")
    ext("SP500", date(2025, 4, 1), date(2025, 6, 30), "Q2 2025 (1 April to 30 June 2025)", min, "date")
    ext("NASDAQCOM", date(2025, 7, 1), date(2025, 9, 30), "Q3 2025 (1 July to 30 September 2025)", max, "value")
    ext("VIXCLS", date(2025, 4, 1), date(2025, 6, 30), "Q2 2025 (1 April to 30 June 2025)", max, "value")
    ext("DHHNGSP", date(2026, 1, 1), date(2026, 1, 31), "January 2026", max, "date")
    ext("DGS10", date(2025, 7, 1), date(2025, 9, 30), "Q3 2025 (1 July to 30 September 2025)", min, "value")
    ext("DEXUSEU", date(2026, 1, 1), date(2026, 1, 31), "January 2026", max, "value")
    ext("DEXJPUS", date(2025, 4, 1), date(2025, 6, 30), "Q2 2025 (1 April to 30 June 2025)", min, "date")

    for a, b, label in [(date(2025, 4, 1), date(2025, 6, 30), "Q2 2025 (1 April to 30 June 2025)"),
                        (date(2025, 10, 1), date(2025, 12, 31), "Q4 2025 (1 October to 31 December 2025)"),
                        (date(2026, 1, 1), date(2026, 3, 31), "Q1 2026 (1 January to 31 March 2026)")]:
        hits = [d for d, v in D.period("VIXCLS", a, b) if v > 25]
        Q.add("aggregate", f"On how many days in {label} did the CBOE Volatility Index (VIX) close above 25?",
              [str(len(hits))], "number", b, [iid("VIXCLS", d) for d in hits], sched_other(b), 0.0)

    for s, y, m in [("DCOILBRENTEU", 2025, 3), ("DGS10", 2026, 6), ("DCOILWTICO", 2026, 9)]:
        a, b = date(y, m, 1), month_end(date(y, m, 1))
        p = D.period(s, a, b)
        avg = sum(v for _, v in p) / len(p)
        Q.add("aggregate", f"What was the average of the daily values of the {SERIES[s]['q']} recorded in "
              f"{calendar.month_name[m]} {y} ({len(p)} observations)? Round to two decimal places.",
              [f"{avg:.2f}"], "number", b, [iid(s, d) for d, _ in p], sched_other(b), 0.001)

    # --- change: percent change between two dated closes
    def pct_change(s, a, b):
        va, vb = D.v(s, a), D.v(s, b)
        assert va is not None and vb is not None, (s, a, b)
        x = (vb - va) / va * 100
        Q.add("change", f"By what percentage did the {SERIES[s]['q']} change from {long_date(a)} to "
              f"{long_date(b)}? Give the percent change rounded to one decimal place (negative for a decline).",
              pct_gold(x), "number", b, [iid(s, a), iid(s, b)], sched_other(b), 0.005)

    pct_change("SP500", date(2024, 12, 31), date(2025, 12, 31))
    pct_change("DCOILBRENTEU", date(2026, 1, 2), date(2026, 4, 30))
    pct_change("NASDAQCOM", date(2025, 4, 8), date(2025, 10, 8))
    pct_change("DEXUSEU", date(2025, 1, 2), date(2025, 6, 30))
    pct_change("DEXJPUS", date(2025, 1, 10), date(2025, 4, 21))

    def bp_change(s, a, b):
        va, vb = D.v(s, a), D.v(s, b)
        assert va is not None and vb is not None, (s, a, b)
        bp = round((vb - va) * 100)
        Q.add("change", f"By how many basis points did the {SERIES[s]['q']} change from {long_date(a)} to "
              f"{long_date(b)}? Answer as a signed whole number of basis points (negative for a decline).",
              [str(bp)], "number", b, [iid(s, a), iid(s, b)], sched_other(b), 0.0)

    bp_change("DGS10", date(2026, 6, 30), date(2026, 9, 30))
    bp_change("DGS2", date(2025, 1, 2), date(2025, 12, 31))

    for a, b in [(date(2024, 11, 1), date(2024, 12, 31)), (date(2025, 1, 1), date(2025, 8, 31)),
                 (date(2025, 1, 1), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 10, 31))]:
        ch = [f for f in D.fed if a <= f[0] <= b and f[3] is not None]
        cuts = sum(1 for f in ch if f[2] < f[4])
        hikes = len(ch) - cuts
        if not ch:
            gold = ["0 changes: the target range was not changed", "none", "no changes"]
        elif hikes == 0:
            gold = [f"{len(ch)} changes, all cuts" if len(ch) > 1 else "1 change, a cut", f"{len(ch)} cut" + ("s" if len(ch) > 1 else "")]
        elif cuts == 0:
            gold = [f"{len(ch)} changes, all hikes" if len(ch) > 1 else "1 change, a hike (increase)", f"{len(ch)} hike" + ("s" if len(ch) > 1 else "")]
        else:
            gold = [f"{len(ch)} changes: {cuts} cut(s) and {hikes} hike(s)"]
        ev = [iid(FED_ID, f[0]) for f in ch] or [iid(FED_ID, D.fed_at(a)[0])]
        Q.add("change", f"Between {long_date(a)} and {long_date(b)} (inclusive), how many times did the Federal "
              f"Reserve's federal funds target range change, and in which direction?",
              gold, "text", b, ev, sched_other(b))

    # --- ordering
    def first_date(s, x, below=False):
        return D.first_below(s, x) if below else D.first_above(s, x)

    def which_first(s1, x1, s2, x2, desc1, desc2, below2=False):
        d1, _ = first_date(s1, x1)
        d2, _ = first_date(s2, x2, below2)
        assert abs((d1 - d2).days) >= 3, (s1, s2, d1, d2)
        first, later = ((desc1, d1), (desc2, d2)) if d1 < d2 else ((desc2, d2), (desc1, d1))
        Q.add("ordering", f"Counting from 1 November 2024, which happened first: (a) {desc1} for the first time, or "
              f"(b) {desc2} for the first time?",
              [f"{first[0]} came first ({long_date(first[1])}, before {long_date(later[1])})",
               "(a)" if d1 < d2 else "(b)"], "text", max(d1, d2),
              [iid(s1, d1), iid(s2, d2)], sched_other(max(d1, d2)))

    def first_q(s, x, label, below=False):
        d, _ = first_date(s, x, below)
        Q.add("ordering", f"Counting from 1 November 2024, on what date did the {SERIES[s]['q']} first "
              f"{'fall below' if below else 'rise above'} {label}?",
              date_gold(d), "date", d, [iid(s, d)], sched_other(d))

    which_first("DCOILBRENTEU", 100, "DCOILWTICO", 100, "the Brent crude spot price closing above $100 per barrel",
                "the WTI crude spot price closing above $100 per barrel")
    which_first("NASDAQCOM", 25000, "SP500", 7500, "the NASDAQ Composite closing above 25,000",
                "the S&P 500 closing above 7,500")
    which_first("VIXCLS", 30, "DGS10", 4.0, "the VIX closing above 30",
                "the 10-year Treasury yield closing below 4.00%", below2=True)
    first_q("DCOILBRENTEU", 90, "$90 per barrel (a close strictly above 90.00)")
    first_q("SP500", 7000, "7,000 (a close strictly above 7,000)")
    first_q("DGS10", 5.0, "5.00% (a close strictly above 5.00%)")
    first_q("DEXUSEU", 1.15, "1.1500 US dollars per euro (a reading strictly above 1.1500)")

    f1 = next(f for f in D.fed if f[3] is not None and f[1] == 4.00 and f[2] == 4.25)
    f2 = D.fed[D.fed.index(f1) + 1]
    Q.add("ordering", "How many calendar days passed between the federal funds target range changing to 4.00-4.25% "
          "and the next change to the target range?", [str((f2[0] - f1[0]).days)], "number", f2[0],
          [iid(FED_ID, f1[0]), iid(FED_ID, f2[0])], sched_other(f2[0]), 0.0)

    # --- multi_hop
    for d in [date(2025, 6, 13), date(2026, 4, 14)]:
        b, w = D.v("DCOILBRENTEU", d), D.v("DCOILWTICO", d)
        assert b is not None and w is not None
        Q.add("multi_hop", f"On {long_date(d)}, by how many US dollars per barrel did the Brent crude spot price "
              f"exceed the WTI crude spot price (Brent minus WTI, two decimals)?", [f"{b - w:.2f}"], "number", d,
              [iid("DCOILBRENTEU", d), iid("DCOILWTICO", d)], sched_point(d), 0.005)
    for d in [date(2025, 2, 14), date(2026, 9, 24)]:
        t10, t2 = D.v("DGS10", d), D.v("DGS2", d)
        assert t10 is not None and t2 is not None
        Q.add("multi_hop", f"On {long_date(d)}, what was the spread between the 10-year and 2-year US Treasury "
              f"constant-maturity yields (10-year minus 2-year, in percentage points, two decimals)?",
              [f"{t10 - t2:.2f}"], "number", d, [iid("DGS10", d), iid("DGS2", d)], sched_point(d), 0.005)
    d = date(2025, 11, 20)
    eu, jp = D.v("DEXUSEU", d), D.v("DEXJPUS", d)
    Q.add("multi_hop", f"Using the noon buying rates recorded on {long_date(d)} (US dollars per euro and yen per "
          f"US dollar), what was the implied number of Japanese yen per euro? Round to two decimal places.",
          [f"{eu * jp:.2f}"], "number", d, [iid("DEXUSEU", d), iid("DEXJPUS", d)], sched_point(d), 0.001)
    d = f1[0]
    Q.add("multi_hop", "What was the closing value of the S&P 500 index on the day the federal funds target range "
          "changed to 4.00-4.25%?", [fmt("SP500", D.v("SP500", d))], "number", d,
          [iid(FED_ID, d), iid("SP500", d)], sched_point(d), 0.001)
    hike = next(f for f in D.fed if f[3] is not None and f[2] > f[4])
    bv = D.v("DCOILBRENTEU", hike[0])
    assert bv is not None
    Q.add("multi_hop", "What was the closing Brent crude oil spot price (USD per barrel) on the day the federal "
          "funds target range was first raised (rather than cut) in the period starting 1 November 2024?",
          [fmt("DCOILBRENTEU", bv)], "number", hike[0], [iid(FED_ID, hike[0]), iid("DCOILBRENTEU", hike[0])],
          sched_point(hike[0]), 0.001)
    p = D.period("VIXCLS", date(2025, 4, 1), date(2025, 6, 30))
    vd = max(p, key=lambda x: x[1])[0]
    Q.add("multi_hop", "What was the 2-year US Treasury constant-maturity yield (percent) on the day in Q2 2025 "
          "(1 April to 30 June 2025) when the VIX recorded its highest close of that quarter?",
          [fmt("DGS2", D.v("DGS2", vd))], "number", vd, [iid("VIXCLS", vd), iid("DGS2", vd)],
          sched_other(date(2025, 6, 30)), 0.001)

    # --- abstain
    for s, d, a in [("SP500", date(2025, 3, 14), date(2025, 2, 28)), ("DCOILBRENTEU", date(2025, 7, 15),
                    date(2025, 6, 30)), ("DGS10", date(2026, 2, 17), date(2026, 1, 31)),
                    ("DEXUSEU", date(2026, 8, 20), date(2026, 7, 31)), ("NASDAQCOM", date(2024, 12, 20),
                    date(2024, 11, 30)), ("VIXCLS", date(2025, 11, 3), date(2025, 10, 31))]:
        assert D.v(s, d) is not None
        Q.add("abstain", f"What was the {SERIES[s]['q']} on {long_date(d)}?",
              [f"Not known as of {long_date(a)}: {long_date(d)} is after the ask date, so no value is recorded yet."],
              "abstain", d, [], [a])
    d, a = date(2026, 10, 1), date(2026, 8, 31)
    Q.add("abstain", f"What was the Federal Reserve's federal funds target range on {long_date(d)}?",
          [f"Not known as of {long_date(a)}: {long_date(d)} is after the ask date."], "abstain", d, [], [a])
    for s, d, why in [("SP500", date(2025, 12, 25), "Christmas Day market holiday"),
                      ("DGS10", date(2025, 4, 18), "Good Friday, US bond market closed"),
                      ("DCOILBRENTEU", date(2025, 4, 21), "Easter Monday; FRED has no Brent spot price that day"),
                      ("DCOILWTICO", date(2026, 3, 14), "a Saturday")]:
        assert D.v(s, d) is None, (s, d)
        Q.add("abstain", f"What was the {SERIES[s]['q']} on {long_date(d)}?",
              [f"No value recorded for {long_date(d)} ({why}); the question presumes a close that does not exist."],
              "abstain", d, [], sched_other(d)[:2])
    for what, d in [("closing spot price of gold (USD per troy ounce)", date(2025, 5, 15)),
                    ("closing value of the Dow Jones Industrial Average", date(2026, 3, 2)),
                    ("30-year US Treasury constant-maturity yield (percent)", date(2025, 10, 1))]:
        Q.add("abstain", f"What was the {what} on {long_date(d)}?",
              ["Not in the record: this series is not tracked (only Brent, WTI, Henry Hub gas, 2- and 10-year "
               "Treasury yields, EUR/USD, USD/JPY, VIX, S&P 500, NASDAQ Composite and the fed funds target range)."],
              "abstain", d, [], sched_other(d)[:2])

    return Q.expand()


# ---------------------------------------------------------------- main

def main() -> None:
    D = Data()
    items = build_items(D)
    qs = build_questions(D)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    with open(OUT / "questions.jsonl", "w") as f:
        for q in qs:
            f.write(json.dumps(q) + "\n")
    print(f"items: {len(items)} {dict(Counter(it['meta']['series'] for it in items))}")
    print(f"questions: {len(qs)} base: {len({q['base_id'] for q in qs})}")
    print(" by category:", dict(Counter(q["category"] for q in qs)))
    print(" base by category:", dict(Counter(q["category"] for q in {q['base_id']: q for q in qs}.values())))
    print(" fed:", [(f[0].isoformat(), rng_str(f[1], f[2])) for f in D.fed])


if __name__ == "__main__":
    main()
