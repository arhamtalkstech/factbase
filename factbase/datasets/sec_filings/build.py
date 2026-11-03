"""Build the sec_filings dataset: 10-Q / 10-K / 8-K filings of ~30 large US companies.

Run: uv run python -m factbase.datasets.sec_filings.build
Gold is computed in code from SEC EDGAR structured data (gold_source = "structured"); no LLM calls.
"""

from __future__ import annotations

import calendar
import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from factbase.datasets.sec_filings.fetch import COMPANIES, RAW, fetch_all

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sec_filings"
DS = "sec_filings"
WIN_START, WIN_END = "2024-11-01", "2026-10-31"
PERIODIC = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
CURRENT = {"8-K", "8-K/A", "8-K12B"}

NAMES = {
    "XOM": "Exxon Mobil Corporation", "CVX": "Chevron Corporation", "COP": "ConocoPhillips",
    "LMT": "Lockheed Martin Corporation", "RTX": "RTX Corporation", "NOC": "Northrop Grumman Corporation",
    "GD": "General Dynamics Corporation", "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation", "AMZN": "Amazon.com, Inc.", "GOOGL": "Alphabet Inc.",
    "META": "Meta Platforms, Inc.", "JPM": "JPMorgan Chase & Co.", "BAC": "Bank of America Corporation",
    "WMT": "Walmart Inc.", "KO": "The Coca-Cola Company", "PFE": "Pfizer Inc.", "JNJ": "Johnson & Johnson",
    "UNH": "UnitedHealth Group Incorporated", "BA": "The Boeing Company", "CAT": "Caterpillar Inc.",
    "GE": "General Electric Company, doing business as GE Aerospace", "F": "Ford Motor Company", "GM": "General Motors Company",
    "TSLA": "Tesla, Inc.", "INTC": "Intel Corporation", "DIS": "The Walt Disney Company",
    "NFLX": "Netflix, Inc.", "ORCL": "Oracle Corporation",
}
# Names used in questions (short, unambiguous).
QNAMES = {**NAMES, "XOM": "ExxonMobil", "GE": "GE Aerospace", "KO": "Coca-Cola", "BA": "Boeing",
          "DIS": "Walt Disney", "UNH": "UnitedHealth Group", "BAC": "Bank of America"}
XOM_HOLDCO = ("ExxonMobil Holdings Corp", "2026-07-01")  # new registrant/parent from this date

# Revenue concept chain (first concept with a fact for the filing wins) and the caption it represents.
REV_CHAIN = ["Revenues", "RevenuesNetOfInterestExpense", "RevenueFromContractWithCustomerExcludingAssessedTax"]
REV_CAPTION = {
    "XOM": "total revenues and other income", "CVX": "total revenues and other income",
    "COP": "total revenues and other income", "JPM": "total net revenue",
    "BAC": "total revenue, net of interest expense", "GM": "total net sales and revenue",
}
NI_CHAIN = ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"]
EPS_CHAIN = ["EarningsPerShareDiluted", "IncomeLossFromContinuingOperationsPerDilutedShare"]
ITEM_NAMES = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.04": "Mine Safety - Reporting of Shutdowns and Patterns of Violations",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation or an Obligation under an Off-Balance Sheet Arrangement",
    "2.04": "Triggering Events That Accelerate or Increase a Direct Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements or a Related Audit Report",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; Compensatory Arrangements of Certain Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year",
    "5.04": "Temporary Suspension of Trading Under Registrant's Employee Benefit Plans",
    "5.05": "Amendments to the Registrant's Code of Ethics, or Waiver of a Provision of the Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "5.08": "Shareholder Director Nominations",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}
FP_WORD = {"Q1": "first", "Q2": "second", "Q3": "third", "FY": "full"}


# ---------------------------------------------------------------- helpers

def d(s: str) -> date:
    return date.fromisoformat(s)


def ndays(a: str, b: str) -> int:
    return (d(b) - d(a)).days + 1


def fmt_date(s: str) -> str:
    x = d(s)
    return f"{x.day} {calendar.month_name[x.month]} {x.year}"


def kind(n: int) -> str | None:
    if 80 <= n <= 100:
        return "3M"
    if 170 <= n <= 195:
        return "6M"
    if 260 <= n <= 285:
        return "9M"
    if 350 <= n <= 380:
        return "12M"
    return None


def money(v: float) -> str:
    """Human-readable USD amount; billions with two decimals, else millions."""
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.2f} billion"
    return f"{sign}${a / 1e6:,.0f} million"


def money_q(v: float) -> tuple[str, str]:
    """(gold string, unit phrase) consistent with money()."""
    if abs(v) >= 1e9:
        return f"{v / 1e9:.2f}", "in billions of USD, two decimals"
    return f"{v / 1e6:.0f}", "in millions of USD"


def month_end(x: date) -> date:
    return date(x.year, x.month, calendar.monthrange(x.year, x.month)[1])


def add_months(x: date, k: int) -> date:
    m = x.month - 1 + k
    y = x.year + m // 12
    m = m % 12 + 1
    return month_end(date(y, m, 1))


def reask_dates(fact: str, offsets=(0, 3, 6, 12), final=True) -> list[str]:
    base = month_end(d(fact))
    out = [add_months(base, k) for k in offsets]
    if final:
        out.append(d(WIN_END))
    res = sorted({x.isoformat() for x in out if x <= d(WIN_END) and x.isoformat() >= fact})
    return res


def ts(day: str) -> str:
    return f"{day}T21:00:00Z"


# ---------------------------------------------------------------- load

@dataclass
class Filing:
    tk: str
    form: str
    filed: str
    report: str
    accn: str
    cik: int
    items: str = ""
    filer: str = ""
    desc: str = ""


@dataclass
class Periodic:
    f: Filing
    fy: int | None = None
    fp: str | None = None
    vals: dict = field(default_factory=dict)  # (metric, kind) -> (value, start, end, concept, derived)
    assets: float | None = None
    concepts: dict = field(default_factory=dict)


def load_filings() -> tuple[dict[str, list[Filing]], dict[str, list[dict]]]:
    filings: dict[str, list[Filing]] = defaultdict(list)
    facts: dict[str, list[dict]] = defaultdict(list)
    for tk, ciks in COMPANIES.items():
        seen = set()
        for cik in ciks:
            p = f"{cik:010d}"
            sub = json.loads((RAW / f"sub_{p}.json").read_text())
            blocks = [sub["filings"]["recent"]]
            for extra in sub["filings"].get("files", []):
                fp = RAW / extra["name"]
                if fp.exists():
                    blocks.append(json.loads(fp.read_text()))
            for b in blocks:
                for row in zip(*[b[k] for k in b]):
                    r = dict(zip(b.keys(), row))
                    if not (WIN_START <= r["filingDate"] <= WIN_END):
                        continue
                    if r["form"] not in PERIODIC | CURRENT or r["accessionNumber"] in seen:
                        continue
                    seen.add(r["accessionNumber"])
                    filings[tk].append(Filing(tk, r["form"], r["filingDate"], r.get("reportDate") or "",
                                              r["accessionNumber"], cik, r.get("items") or "", sub["name"],
                                              r.get("primaryDocDescription") or ""))
            fpath = RAW / f"facts_{p}.json"
            if fpath.exists():
                facts[tk].append(json.loads(fpath.read_text())["facts"])
        filings[tk].sort(key=lambda f: (f.filed, f.accn))
    return filings, facts


def concept_facts(fs: list[dict], concept: str, unit_prefix: str = "USD") -> list[dict]:
    out = []
    for f in fs:
        c = f.get("us-gaap", {}).get(concept)
        if not c:
            continue
        for u, v in c["units"].items():
            if u == unit_prefix:
                out.extend(v)
    return out


def build_periodic(tk: str, f: Filing, fs: list[dict]) -> Periodic:
    p = Periodic(f)
    end = f.report
    for metric, chain, unit in (("rev", REV_CHAIN, "USD"), ("ni", NI_CHAIN, "USD"), ("eps", EPS_CHAIN, "USD/shares"),
                                ("ocf", ["NetCashProvidedByUsedInOperatingActivities"], "USD")):
        for concept in chain:
            hits = [x for x in concept_facts(fs, concept, unit) if x["accn"] == f.accn and x.get("end") == end and "start" in x]
            if not hits:
                continue
            p.concepts[metric] = concept
            for x in hits:
                k = kind(ndays(x["start"], x["end"]))
                if k and (metric, k) not in p.vals:
                    p.vals[(metric, k)] = (x["val"], x["start"], x["end"], concept, False)
                p.fy, p.fp = x.get("fy"), x.get("fp")
            break
    # Fiscal year from the fiscal-year start (companyfacts "fy" is occasionally wrong, e.g. Oracle's FY2027 Q1).
    ytd = [v for (m, k), v in p.vals.items() if m in ("rev", "ni") and k in ("3M", "6M", "9M", "12M")]
    if ytd and p.fp:
        fy_start = min(v[1] for v in ytd)
        fy_end = d(fy_start) + timedelta(days=364)
        fy = fy_end.year - (1 if fy_end.month == 1 and fy_end.day <= 7 else 0)
        if fy != p.fy:
            print(f"note: {tk} {f.accn} companyfacts fy={p.fy} -> {fy}")
        p.fy = fy
    a = [x for x in concept_facts(fs, "Assets") if x["accn"] == f.accn and x.get("end") == end]
    if a:
        p.assets = a[0]["val"]
    # Fourth quarter implied by a 10-K: annual minus the nine-month YTD originally reported in the Q3 10-Q.
    if f.form == "10-K":
        for metric in ("rev", "ni"):
            if (metric, "12M") not in p.vals or (metric, "3M") in p.vals:
                continue
            val, start, _, concept, _ = p.vals[(metric, "12M")]
            chain = {"rev": REV_CHAIN, "ni": NI_CHAIN}[metric]
            nine = []
            # Same concept first; another chain concept only if the 10-K tags the same annual value with it.
            for c in [concept] + [c for c in chain if c != concept]:
                if c != concept and not any(x["accn"] == f.accn and x.get("start") == start and x.get("end") == end
                                            and x["val"] == val for x in concept_facts(fs, c)):
                    continue
                nine = [x for x in concept_facts(fs, c) if x.get("start") == start and x.get("form") == "10-Q"
                        and "end" in x and kind(ndays(x["start"], x["end"])) == "9M"]
                if nine:
                    break
            if not nine:
                continue
            nine.sort(key=lambda x: x["filed"])
            x9 = nine[0]
            q4_start = (d(x9["end"]) + timedelta(days=1)).isoformat()
            p.vals[(metric, "3M")] = (val - x9["val"], q4_start, end, concept, True)
            p.vals[(metric, "9M_ref")] = (x9["val"], x9["start"], x9["end"], concept, x9["accn"])
    return p


# ---------------------------------------------------------------- items

def filer_name(f: Filing) -> str:
    if f.tk == "XOM" and f.filed >= XOM_HOLDCO[1]:
        if f.cik == 2115436 or f.form.startswith("10-"):
            return f"{XOM_HOLDCO[0]} (XOM; new registrant, SEC CIK 2115436)"
        return "Exxon Mobil Corporation (XOM; SEC CIK 34088)"
    return f"{NAMES[f.tk]} ({f.tk})"


def period_label(p: Periodic) -> str:
    if p.fp == "FY":
        return f"fiscal year {p.fy}"
    return f"the {FP_WORD.get(p.fp, p.fp)} quarter of fiscal year {p.fy}"


def periodic_text(p: Periodic) -> tuple[str, str, dict]:
    f = p.f
    who = filer_name(f)
    cap = REV_CAPTION.get(f.tk)
    revname = f"revenue ({cap})" if cap else "revenue"
    end = fmt_date(f.report)
    meta = {"ticker": f.tk, "company": NAMES[f.tk], "cik": f.cik, "form": f.form, "accession": f.accn,
            "filed": f.filed, "period_end": f.report, "fiscal_year": p.fy, "fiscal_period": p.fp,
            "concepts": p.concepts, "values": {}}
    for (m, k), v in p.vals.items():
        if k == "9M_ref":
            continue
        meta["values"][f"{m}_{k}"] = {"value": v[0], "start": v[1], "end": v[2], "derived": bool(v[4])}
    if p.assets is not None:
        meta["values"]["assets"] = {"value": p.assets, "instant": f.report}

    if f.form.endswith("/A") and not p.vals:
        title = f"{NAMES[f.tk]} files {f.form} amendment for period ended {end}"
        orig = "annual report on Form 10-K" if f.form == "10-K/A" else "quarterly report on Form 10-Q"
        text = (f"On {fmt_date(f.filed)} {who} filed a Form {f.form}, an amendment to its {orig} for the period "
                f"ended {end} (accession {f.accn}). The amendment's XBRL financial data contains no income-statement or "
                f"balance-sheet figures, so it does not report new or restated revenue, net income or EPS.")
        return title, text, meta

    parts = []
    if f.form.startswith("10-K"):
        title = f"{NAMES[f.tk]} files {f.form} for fiscal year {p.fy}"
        lead = (f"On {fmt_date(f.filed)} {who} filed its Form {f.form} annual report for fiscal year {p.fy} "
                f"(fiscal year ended {end}; accession {f.accn}).")
        r = p.vals.get(("rev", "12M"))
        ni = p.vals.get(("ni", "12M"))
        eps = p.vals.get(("eps", "12M"))
        span = f"fiscal year {p.fy} ({fmt_date(r[1]) if r else ''} to {end})"
        bits = []
        if r:
            bits.append(f"annual {revname} of {money(r[0])}")
        if ni:
            bits.append(f"net income of {money(ni[0])}")
        if eps:
            bits.append(f"diluted earnings per share of ${eps[0]:.2f}")
        if bits:
            parts.append(f"For {span} it reported " + ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1] + ".")
        q = [(m, p.vals[(m, "3M")]) for m in ("rev", "ni") if (m, "3M") in p.vals]
        if q:
            derived = q[0][1][4]
            qbits = [f"{'revenue' if m == 'rev' else 'net income'} of {money(v[0])}" for m, v in q]
            qs = f"the three months ended {end} (fourth quarter of fiscal year {p.fy}, {fmt_date(q[0][1][1])} to {end})"
            if derived:
                parts.append(f"Implied fourth-quarter figures for {qs}, computed as the annual amount minus the "
                             f"nine-month year-to-date amount reported in the company's third-quarter Form 10-Q, are "
                             + " and ".join(qbits) + "; the 10-K itself does not report fourth-quarter EPS.")
            else:
                parts.append(f"For {qs} it reported " + " and ".join(qbits) + ".")
    else:
        title = f"{NAMES[f.tk]} files {f.form} for {period_label(p).replace('the ', '', 1)}"
        lead = (f"On {fmt_date(f.filed)} {who} filed its Form {f.form} quarterly report for {period_label(p)} "
                f"(fiscal quarter ended {end}; accession {f.accn}).")
        r, ni, eps = (p.vals.get((m, "3M")) for m in ("rev", "ni", "eps"))
        bits = []
        if r:
            bits.append(f"quarterly {revname} of {money(r[0])}")
        if ni:
            bits.append(f"net income of {money(ni[0])}")
        if eps:
            bits.append(f"diluted earnings per share of ${eps[0]:.2f}")
        start3 = (r or ni or eps)[1] if (r or ni or eps) else None
        if bits:
            parts.append(f"For the three months ended {end} ({fmt_date(start3)} to {end}) it reported "
                         + ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1] + ".")
        for k, word in (("6M", "six"), ("9M", "nine")):
            yr, yni, yeps = (p.vals.get((m, k)) for m in ("rev", "ni", "eps"))
            if yr or yni:
                yb = []
                if yr:
                    yb.append(f"revenue was {money(yr[0])}")
                if yni:
                    yb.append(f"net income {money(yni[0])}")
                if yeps:
                    yb.append(f"diluted EPS ${yeps[0]:.2f}")
                parts.append(f"For the {word} months ended {end} (fiscal year to date, from {fmt_date((yr or yni)[1])}) "
                             + ", ".join(yb) + ".")
    tail = []
    if p.assets is not None:
        tail.append(f"total assets were {money(p.assets)} at {end}")
    ocf = next((p.vals[("ocf", k)] for k in ("12M", "9M", "6M", "3M") if ("ocf", k) in p.vals), None)
    if ocf:
        tail.append(f"net cash provided by operating activities was {money(ocf[0])} for the period "
                    f"{fmt_date(ocf[1])} to {end} (year to date)")
    if tail:
        parts.append(tail[0][0].upper() + "; ".join(tail)[1:] + ".")
    if not parts:
        parts.append("Its key financial values were not available in the SEC XBRL company facts data.")
    return title, lead + " " + " ".join(parts), meta


def items_text(codes: list[str]) -> str:
    return "; ".join(f"Item {c} {ITEM_NAMES.get(c, '(unlisted item)')}" for c in codes)


def current_text(f: Filing) -> tuple[str, str, dict]:
    codes = [c for c in f.items.split(",") if c]
    who = filer_name(f)
    kindtxt = {"8-K": "a Form 8-K current report", "8-K/A": "a Form 8-K/A (amendment to a previously filed Form 8-K)",
               "8-K12B": "a Form 8-K12B (current report registering securities of a successor issuer)"}[f.form]
    ev = f" (event date {fmt_date(f.report)})" if f.report else ""
    body = items_text(codes) if codes else "no item codes listed"
    text = f"On {fmt_date(f.filed)} {who} filed {kindtxt}{ev}, accession {f.accn}, reporting: {body}."
    short = ", ".join(codes) if codes else "no items"
    title = f"{NAMES[f.tk]} files {f.form} (Items {short})"
    meta = {"ticker": f.tk, "company": NAMES[f.tk], "cik": f.cik, "form": f.form, "accession": f.accn,
            "filed": f.filed, "event_date": f.report or None, "items": codes}
    return title, text, meta


def item_id(f: Filing) -> str:
    return f"{DS}:{f.tk}:{f.form.replace('/', '')}:{f.accn}"


# ---------------------------------------------------------------- questions

class Q:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.n = 0

    def add(self, category: str | None, question: str, gold: list[str], answer_type: str, fact_time: str,
            evidence: list[str], ask_dates: list[str], tol: float | None = None, fact_ts: str | None = None,
            note: str | None = None) -> None:
        self.n += 1
        base = f"{DS}:q{self.n:04d}"
        for a in ask_dates:
            cat = category
            if cat is None:  # point fact: recent vs old by age at ask time
                cat = "point_recent" if (d(a) - d(fact_ts or fact_time)).days <= 30 else "point_old"
            row = {"qid": f"{base}@{a}", "base_id": base, "dataset": DS, "ask_at": f"{a}T23:59:59Z",
                   "question": question, "gold": gold, "answer_type": answer_type,
                   "numeric_tolerance": tol if answer_type == "number" else None, "category": cat,
                   "fact_time": fact_time, "evidence_item_ids": evidence, "gold_source": "structured"}
            if note:
                row["note"] = note
            self.rows.append(row)


def date_golds(s: str) -> list[str]:
    x = d(s)
    return [s, fmt_date(s), f"{calendar.month_name[x.month]} {x.day}, {x.year}"]


def quarter_bounds(y: int, q: int) -> tuple[str, str]:
    s = date(y, 3 * q - 2, 1)
    e = month_end(date(y, 3 * q, 1))
    return s.isoformat(), e.isoformat()


def build_questions(per: dict[str, list[Periodic]], cur: dict[str, list[Filing]]) -> list[dict]:
    rng = random.Random(20261102)
    Qs = Q()
    E = item_id

    tks = list(NAMES)
    q10 = {tk: [p for p in per[tk] if p.f.form == "10-Q" and ("rev", "3M") in p.vals] for tk in tks}
    k10 = {tk: [p for p in per[tk] if p.f.form == "10-K" and ("rev", "12M") in p.vals] for tk in tks}
    aligned = {tk for tk in tks if all(abs((d(p.f.report) - month_end(d(p.f.report))).days) <= 0
                                       and d(p.f.report).month % 3 == 0 for p in q10[tk])}

    def rev_unit(v):
        return money_q(v)

    def revdesc(tk):
        return f"revenue ({REV_CAPTION[tk]})" if tk in REV_CAPTION else "revenue"

    # ---- point lookups: quarterly revenue / net income / EPS
    pool = [p for tk in tks for p in q10[tk]]
    rng.shuffle(pool)
    pool.sort(key=lambda p: p.f.filed)
    # spread choices over the window: pick from evenly spaced positions
    def spread(lst, k, offset=0):
        if not lst:
            return []
        step = len(lst) / k
        return [lst[min(len(lst) - 1, int(i * step + offset) % len(lst))] for i in range(k)]

    used = set()
    for i, p in enumerate(spread(pool, 6, 1)):
        g, unit = rev_unit(p.vals[("rev", "3M")][0])
        used.add(p.f.accn)
        Qs.add(None, f"What quarterly {revdesc(p.f.tk)} did {QNAMES[p.f.tk]} report in its Form 10-Q for the three "
                     f"months ended {fmt_date(p.f.report)}? Answer {unit}.", [g], "number", p.f.filed,
               [E(p.f)], reask_dates(p.f.filed), 0.01)
    rest = [p for p in pool if p.f.accn not in used]
    for p in spread(rest, 4, 3):
        v = p.vals.get(("ni", "3M"))
        if not v:
            continue
        g, unit = money_q(v[0])
        used.add(p.f.accn)
        Qs.add(None, f"What net income did {QNAMES[p.f.tk]} report for the three months ended {fmt_date(p.f.report)} "
                     f"in its Form 10-Q? Answer {unit} (negative for a loss).", [g], "number", p.f.filed,
               [E(p.f)], reask_dates(p.f.filed), 0.01)
    rest = [p for p in pool if p.f.accn not in used]
    for p in spread(rest, 4, 2):
        v = p.vals.get(("eps", "3M"))
        if not v:
            continue
        used.add(p.f.accn)
        Qs.add(None, f"What diluted earnings per share did {QNAMES[p.f.tk]} report for the three months ended "
                     f"{fmt_date(p.f.report)} in its Form 10-Q? Answer in USD per share, two decimals.",
               [f"{v[0]:.2f}"], "number", p.f.filed, [E(p.f)], reask_dates(p.f.filed), 0.01)
    # YTD vs quarter distinction
    ytd_pool = [p for p in pool if p.f.accn not in used and ("rev", "9M") in p.vals]
    for p in spread(ytd_pool, 2, 1):
        v = p.vals[("rev", "9M")]
        g, unit = money_q(v[0])
        used.add(p.f.accn)
        Qs.add(None, f"What year-to-date {revdesc(p.f.tk)} did {QNAMES[p.f.tk]} report for the nine months ended "
                     f"{fmt_date(p.f.report)} (not the three-month figure)? Answer {unit}.", [g], "number",
               p.f.filed, [E(p.f)], reask_dates(p.f.filed), 0.01)
    # annual from 10-K
    kpool = sorted([p for tk in tks for p in k10[tk]], key=lambda p: (p.f.filed, p.f.tk))
    rng.shuffle(kpool)
    kpool = sorted(kpool[:12], key=lambda p: p.f.filed)
    for p in spread(kpool, 3):
        g, unit = money_q(p.vals[("rev", "12M")][0])
        Qs.add(None, f"What annual {revdesc(p.f.tk)} did {QNAMES[p.f.tk]} report in its Form 10-K for fiscal year "
                     f"{p.fy} (fiscal year ended {fmt_date(p.f.report)})? Answer {unit}.", [g], "number", p.f.filed,
               [E(p.f)], reask_dates(p.f.filed), 0.01)
    # implied Q4 (derived and stated in the 10-K item)
    q4pool = [p for p in kpool if ("rev", "3M") in p.vals and p.vals[("rev", "3M")][4]]
    for p in spread(q4pool, 2, 1):
        g, unit = money_q(p.vals[("rev", "3M")][0])
        Qs.add(None, f"Based on its Form 10-K for fiscal year {p.fy}, what was {QNAMES[p.f.tk]}'s implied fourth-quarter "
                     f"{revdesc(p.f.tk)} for the three months ended {fmt_date(p.f.report)} (annual minus nine-month "
                     f"year to date)? Answer {unit}.", [g], "number", p.f.filed, [E(p.f)], reask_dates(p.f.filed), 0.01)
    # total assets
    ap = [p for p in pool if p.assets and p.f.accn not in used]
    for p in spread(ap, 1, 5):
        g, unit = money_q(p.assets)
        Qs.add(None, f"What total assets did {QNAMES[p.f.tk]} report as of {fmt_date(p.f.report)} in its Form 10-Q? "
                     f"Answer {unit}.", [g], "number", p.f.filed, [E(p.f)], reask_dates(p.f.filed), 0.01)
    # amendments
    for tk in tks:
        for p in per[tk]:
            if p.f.form == "10-K/A":
                fy = p.f.report[:4]
                Qs.add(None, f"On what date did {QNAMES[tk]} file a Form 10-K/A amending its annual report for the "
                             f"fiscal year ended {fmt_date(p.f.report)}?", date_golds(p.f.filed), "date", p.f.filed,
                       [E(p.f)], reask_dates(p.f.filed, (0, 6)), None)
    # 8-K point: date of a 5.02 8-K that is the only 5.02 filing by that company in its month
    by_month = defaultdict(list)
    for tk in tks:
        for f in cur[tk]:
            if f.form == "8-K" and "5.02" in f.items.split(","):
                by_month[(tk, f.filed[:7])].append(f)
    uniq = sorted([v[0] for v in by_month.values() if len(v) == 1], key=lambda f: f.filed)
    rng.shuffle(uniq)
    picks = sorted(uniq[:3], key=lambda f: f.filed)
    for f in picks:
        x = d(f.filed)
        Qs.add(None, f"On what date in {calendar.month_name[x.month]} {x.year} did {QNAMES[f.tk]} file a Form 8-K "
                     f"reporting Item 5.02 (departure or appointment of directors or certain officers)?",
               date_golds(f.filed), "date", f.filed, [E(f)], reask_dates(f.filed), None)
    # 8-K point: which item codes
    multi = [f for tk in tks for f in cur[tk] if f.form == "8-K" and len(f.items.split(",")) >= 3
             and sum(1 for g in cur[tk] if g.filed == f.filed and g.form == "8-K") == 1]
    rng.shuffle(multi)
    for f in sorted(multi[:2], key=lambda f: f.filed):
        codes = f.items.split(",")
        Qs.add(None, f"Which 8-K item numbers did the Form 8-K filed by {QNAMES[f.tk]} on {fmt_date(f.filed)} report? "
                     f"List all item numbers.", [", ".join(codes), " and ".join(codes)], "text", f.filed, [E(f)],
               reask_dates(f.filed, (0, 6)), None)

    # ---- as_of_state
    def latest(tk, asof, forms=("10-Q",)):
        c = [p for p in per[tk] if p.f.form in forms and p.f.filed <= asof and ("rev", "3M" if forms == ("10-Q",) else "12M") in p.vals]
        return max(c, key=lambda p: (p.f.report, p.f.filed)) if c else None

    asof_dates = ["2024-12-31", "2025-04-30", "2025-08-31", "2025-12-31", "2026-02-28", "2026-05-31",
                  "2026-08-31", "2026-10-31"]
    tk_cycle = tks[:]
    rng.shuffle(tk_cycle)
    j = 0
    for a in asof_dates:
        for _ in range(20):
            tk = tk_cycle[j % len(tk_cycle)]
            j += 1
            p = latest(tk, a)
            if p:
                break
        g, unit = money_q(p.vals[("rev", "3M")][0])
        Qs.add("as_of_state", f"As of {fmt_date(a)}, according to the most recent Form 10-Q that {QNAMES[tk]} had filed, "
                              f"what was its quarterly {revdesc(tk)} for the three months covered by that report? "
                              f"Answer {unit}.", [g], "number", p.f.filed, [E(p.f)],
               sorted({x for x in [a, add_months(d(a), 3).isoformat() if a < "2025-06-30" else a, WIN_END]
                       if a <= x <= WIN_END}), 0.01)
    # most recent 10-Q period end (date answer)
    for a in ["2025-03-15", "2025-09-15", "2026-03-15"]:
        tk = tk_cycle[j % len(tk_cycle)]
        j += 1
        p = latest(tk, a)
        if not p:
            continue
        Qs.add("as_of_state", f"As of {fmt_date(a)}, what was the period end date of the most recent fiscal quarter for "
                              f"which {QNAMES[tk]} had filed a Form 10-Q?", date_golds(p.f.report), "date", p.f.filed,
               [E(p.f)], [x for x in [a, WIN_END] if x <= WIN_END])
    # latest annual revenue as of a date
    for a, tk in [("2025-01-31", "LMT"), ("2025-12-31", "AAPL"), ("2026-09-30", "MSFT")]:
        p = latest(tk, a, ("10-K",))
        g, unit = money_q(p.vals[("rev", "12M")][0])
        Qs.add("as_of_state", f"As of {fmt_date(a)}, what annual {revdesc(tk)} had {QNAMES[tk]} reported in its most "
                              f"recent Form 10-K, and for which fiscal year? Give the revenue {unit}.", [g], "number",
               p.f.filed, [E(p.f)], [x for x in [a, WIN_END] if x <= WIN_END], 0.01)
    # most recent officer-change 8-K as of date
    for a, tk in [("2025-06-30", None), ("2026-01-31", None), ("2026-07-31", None)]:
        cands = []
        for t in tks:
            fl = [f for f in cur[t] if f.form == "8-K" and "5.02" in f.items.split(",") and f.filed <= a]
            if len(fl) >= 2:
                cands.append((t, fl[-1]))
        t, f = cands[rng.randrange(len(cands))]
        # require a unique filing date for that company
        Qs.add("as_of_state", f"As of {fmt_date(a)}, on what date had {QNAMES[t]} most recently filed a Form 8-K "
                              f"reporting Item 5.02 (departure or appointment of directors or certain officers)?",
               date_golds(f.filed), "date", f.filed, [E(f)], [x for x in [a, WIN_END] if x <= WIN_END])

    # ---- change: YoY quarterly revenue / QoQ net income
    def by_end(tk):
        return {p.f.report: p for p in q10[tk]}
    yoy = []
    for tk in tks:
        m = by_end(tk)
        for e, p in m.items():
            prev = [q for q in q10[tk] if 350 <= (d(e) - d(q.f.report)).days <= 380]
            if prev:
                yoy.append((p, prev[0]))
    rng.shuffle(yoy)
    for p, q in sorted(yoy[:6], key=lambda x: x[0].f.filed):
        tk = p.f.tk
        # Difference of the two-decimal billion figures shown in the item texts.
        diff = round(p.vals[("rev", "3M")][0] / 1e9, 2) - round(q.vals[("rev", "3M")][0] / 1e9, 2)
        g, unit = f"{diff:.2f}", "in billions of USD, two decimals"
        tol = max(0.01, 0.011 / max(abs(diff), 1e-9))
        Qs.add("change", f"By how much did {QNAMES[tk]}'s quarterly {revdesc(tk)} for the three months ended "
                         f"{fmt_date(p.f.report)} differ from the three months ended {fmt_date(q.f.report)}, as reported in "
                         f"its Form 10-Q filings? Answer {unit} (positive for an increase, negative for a decrease).",
               [g], "number", p.f.filed, [E(q.f), E(p.f)], reask_dates(p.f.filed, (0, 6)), round(tol, 4))
    qoq = []
    for tk in tks:
        ql = sorted(q10[tk], key=lambda p: p.f.report)
        for a, b in zip(ql, ql[1:]):
            if 80 <= (d(b.f.report) - d(a.f.report)).days <= 100 and ("eps", "3M") in a.vals and ("eps", "3M") in b.vals:
                qoq.append((b, a))
    rng.shuffle(qoq)
    for p, q in sorted(qoq[:3], key=lambda x: x[0].f.filed):
        diff = round(p.vals[("eps", "3M")][0], 2) - round(q.vals[("eps", "3M")][0], 2)
        Qs.add("change", f"How did {QNAMES[p.f.tk]}'s diluted EPS change from the quarter ended {fmt_date(q.f.report)} "
                         f"to the quarter ended {fmt_date(p.f.report)}? Give the change in USD per share, two decimals "
                         f"(negative for a decrease).", [f"{diff:.2f}"], "number", p.f.filed, [E(q.f), E(p.f)],
               reask_dates(p.f.filed, (0, 6)), round(max(0.01, 0.005 / max(abs(diff), 1e-9)), 4))

    # ---- aggregate: highest revenue among named calendar-aligned companies in a calendar quarter
    al = sorted(aligned)
    quarters = [(2025, 1), (2025, 3), (2025, 4), (2026, 2), (2026, 3)]
    for y, qn in quarters:
        _, qe = quarter_bounds(y, qn)
        def qrec(tk):
            return next((p for p in per[tk] if p.f.report == qe and p.f.form in ("10-Q", "10-K")
                         and ("rev", "3M") in p.vals), None)
        have = [tk for tk in al if qrec(tk)]
        if len(have) < 4:
            continue
        group = rng.sample(have, rng.choice([3, 4, 5]))
        recs = {tk: qrec(tk) for tk in group}
        top = max(group, key=lambda tk: recs[tk].vals[("rev", "3M")][0])
        last = max(p.f.filed for p in recs.values())
        src = ("its Form 10-Q" if qn != 4 else
               "the fourth-quarter figure given with its Form 10-K, reported or implied as annual minus nine-month year to date")
        Qs.add("aggregate", f"Among {', '.join(QNAMES[t] for t in group[:-1])} and {QNAMES[group[-1]]}, which company "
                            f"had the highest quarterly revenue ({src}) for the three months "
                            f"ended {fmt_date(qe)}?", [QNAMES[top], top, NAMES[top]], "text", last,
               [E(recs[t].f) for t in group], reask_dates(last, (0, 6)))
    # aggregate: count 8-Ks in a calendar quarter
    for y, qn in [(2025, 1), (2025, 4), (2026, 2), (2026, 3)]:
        qs, qe = quarter_bounds(y, qn)
        tk = rng.choice([t for t in tks if t != "XOM"])
        fl = [f for f in cur[tk] if f.form == "8-K" and qs <= f.filed <= qe]
        Qs.add("aggregate", f"How many Form 8-K current reports (original 8-K filings, not 8-K/A amendments) did "
                            f"{QNAMES[tk]} file between {fmt_date(qs)} and {fmt_date(qe)} inclusive?", [str(len(fl))],
               "number", qe, [E(f) for f in fl], reask_dates(qe, (0, 6)), 0.0)
    # aggregate: count of officer-change 8-Ks in calendar 2025
    for tk in rng.sample([t for t in tks if t != "XOM"], 2):
        fl = [f for f in cur[tk] if f.form in ("8-K", "8-K/A") and "5.02" in f.items.split(",") and f.filed[:4] == "2025"]
        Qs.add("aggregate", f"How many Form 8-K or 8-K/A filings reporting Item 5.02 (departure or appointment of directors "
                            f"or certain officers) did {QNAMES[tk]} file during calendar year 2025?", [str(len(fl))],
               "number", "2025-12-31", [E(f) for f in fl], ["2025-12-31", "2026-06-30", WIN_END], 0.0)

    # ---- ordering: who filed the 10-K for a fiscal year first
    cal_k = {tk: {p.f.report[:4]: p for p in k10[tk] if p.f.report.endswith("12-31")} for tk in tks}
    for yr in ("2024", "2025", "2024", "2025", "2025"):
        cands = [tk for tk in tks if yr in cal_k[tk]]
        for _ in range(50):
            a, b = rng.sample(cands, 2)
            if cal_k[a][yr].f.filed != cal_k[b][yr].f.filed:
                break
        pa, pb = cal_k[a][yr], cal_k[b][yr]
        first = a if pa.f.filed < pb.f.filed else b
        last = max(pa.f.filed, pb.f.filed)
        Qs.add("ordering", f"Which company filed its Form 10-K for fiscal year {yr} (year ended 31 December {yr}) first: "
                           f"{QNAMES[a]} or {QNAMES[b]}?", [QNAMES[first], first, NAMES[first]], "text", last,
               [E(pa.f), E(pb.f)], reask_dates(last, (0, 6)))
    # ordering: days between two filings of the same company
    for tk in rng.sample(tks, 2):
        ks = sorted(k10[tk], key=lambda p: p.f.filed)
        if len(ks) < 2:
            continue
        a, b = ks[0], ks[1]
        gap = (d(b.f.filed) - d(a.f.filed)).days
        Qs.add("ordering", f"How many days passed between {QNAMES[tk]}'s Form 10-K filing for the fiscal year ended "
                           f"{fmt_date(a.f.report)} and its Form 10-K filing for the fiscal year ended {fmt_date(b.f.report)}?",
               [str(gap)], "number", b.f.filed, [E(a.f), E(b.f)], reask_dates(b.f.filed, (0, 6)), 0.0)

    # ---- multi_hop
    for y, qn in [(2025, 2), (2026, 1), (2026, 3)]:
        _, qe = quarter_bounds(y, qn)
        have = [tk for tk in al if any(p.f.report == qe and ("ni", "3M") in p.vals for p in q10[tk])]
        group = rng.sample(have, 4)
        recs = {tk: next(p for p in q10[tk] if p.f.report == qe) for tk in group}
        top = max(group, key=lambda tk: recs[tk].vals[("rev", "3M")][0])
        last = max(p.f.filed for p in recs.values())
        g, unit = money_q(recs[top].vals[("ni", "3M")][0])
        Qs.add("multi_hop", f"Of {', '.join(QNAMES[t] for t in group[:-1])} and {QNAMES[group[-1]]}, take the company "
                            f"that reported the highest quarterly revenue for the three months ended {fmt_date(qe)}. What "
                            f"net income did that company report for the same quarter? Answer {unit}.", [g], "number",
               last, [E(recs[t].f) for t in group], reask_dates(last, (0, 6)), 0.01)
    # 8-K officer change -> latest 10-Q revenue at that time
    officer = [f for tk in tks for f in cur[tk] if f.form == "8-K" and "5.02" in f.items.split(",")
               and "2.02" not in f.items.split(",") and len([g for g in cur[tk] if g.filed == f.filed]) == 1]
    rng.shuffle(officer)
    k = 0
    for f in officer:
        if k == 3:
            break
        p = latest(f.tk, f.filed)
        if not p or p.f.filed == f.filed:
            continue
        k += 1
        g, unit = money_q(p.vals[("rev", "3M")][0])
        Qs.add("multi_hop", f"{QNAMES[f.tk]} filed a Form 8-K reporting Item 5.02 (officer/director changes) on "
                            f"{fmt_date(f.filed)}. At that date, what quarterly {revdesc(f.tk)} had {QNAMES[f.tk]} reported "
                            f"in its most recent Form 10-Q? Answer {unit}.", [g], "number", f.filed, [E(f), E(p.f)],
               reask_dates(f.filed, (0, 6)), 0.01)
    # first 10-K filer -> its annual net income
    for yr in ("2025",):
        group = rng.sample([tk for tk in tks if yr in cal_k[tk] and ("ni", "12M") in cal_k[tk][yr].vals], 3)
        ps = {t: cal_k[t][yr] for t in group}
        if len({p.f.filed for p in ps.values()}) == 3:
            first = min(group, key=lambda t: ps[t].f.filed)
            last = max(p.f.filed for p in ps.values())
            g, unit = money_q(ps[first].vals[("ni", "12M")][0])
            Qs.add("multi_hop", f"Of {QNAMES[group[0]]}, {QNAMES[group[1]]} and {QNAMES[group[2]]}, which filed its Form "
                                f"10-K for fiscal year {yr} first, and what annual net income did that company report? "
                                f"Give the net income {unit}.", [g], "number", last, [E(p.f) for p in ps.values()],
                   reask_dates(last, (0, 6)), 0.01)

    # ---- abstain
    # (a) quarter not yet reported at ask time
    nr = [p for p in pool if d(p.f.filed).day > 3 and month_end(d(p.f.report)) < d(p.f.filed)]
    rng.shuffle(nr)
    k = 0
    for p in nr:
        ask = (d(p.f.filed) - timedelta(days=d(p.f.filed).day)).isoformat()  # previous month-end
        if ask <= p.f.report or k >= 7:
            continue
        k += 1
        Qs.add("abstain", f"What quarterly revenue did {QNAMES[p.f.tk]} report in its Form 10-Q for the three months "
                          f"ended {fmt_date(p.f.report)}?",
               [f"Not yet reported as of {fmt_date(ask)}: the Form 10-Q for that quarter was filed on {fmt_date(p.f.filed)}."],
               "abstain", ask, [], [ask])
    # (b) filings that do not exist (checked against the data)
    aapl_sep = [p for p in per["AAPL"] if p.f.form == "10-K"]
    for p in aapl_sep[-1:]:
        Qs.add("abstain", f"What quarterly revenue did Apple Inc. report in a Form 10-Q for the three months ended "
                          f"{fmt_date(p.f.report)}?",
               ["False premise: Apple filed no 10-Q for that quarter; it is the fourth fiscal quarter, covered by the "
                "annual Form 10-K."], "abstain", p.f.filed, [], reask_dates(p.f.filed, (1, 6)))
    for tk, yr in (("MSFT", "2025"), ("NVDA", "2025")):
        assert not any(p.f.form == "10-K/A" for p in per[tk])
        a = reask_dates(f"{yr}-12-31", (0, 6))
        Qs.add("abstain", f"On what date did {QNAMES[tk]} file a Form 10-K/A amending its annual report during "
                          f"calendar year {yr}?", [f"False premise: {QNAMES[tk]} filed no Form 10-K/A in the record."],
               "abstain", f"{yr}-12-31", [], a)
    for tk in ("BA", "INTC"):
        assert not any("1.03" in f.items.split(",") for f in cur[tk])
        Qs.add("abstain", f"On what date in 2025 did {QNAMES[tk]} file a Form 8-K reporting Item 1.03 "
                          f"(Bankruptcy or Receivership)?", [f"False premise: {QNAMES[tk]} filed no 8-K with Item 1.03."],
               "abstain", "2025-12-31", [], ["2025-12-31", WIN_END])
    # (c) change question whose later quarter is not yet reported at window end
    for tk in ("JPM", "CAT"):
        later = [p for p in q10[tk] if p.f.report == "2026-09-30"]
        assert not later
        Qs.add("abstain", f"By how much did {QNAMES[tk]}'s quarterly revenue for the three months ended 30 September 2026 "
                          f"differ from the three months ended 30 September 2025?",
               [f"Not yet reported as of 31 October 2026: {QNAMES[tk]} had not filed its 10-Q for the quarter ended "
                f"30 September 2026."], "abstain", WIN_END, [], [WIN_END])
    return Qs.rows


# ---------------------------------------------------------------- main

def main() -> None:
    fetch_all()
    filings, facts = load_filings()
    OUT.mkdir(parents=True, exist_ok=True)
    items, per, cur = [], defaultdict(list), defaultdict(list)
    for tk in NAMES:
        for f in filings[tk]:
            if f.form in PERIODIC:
                p = build_periodic(tk, f, facts[tk])
                per[tk].append(p)
                title, text, meta = periodic_text(p)
            else:
                cur[tk].append(f)
                title, text, meta = current_text(f)
            items.append({"id": item_id(f), "dataset": DS, "ts": ts(f.filed), "title": title, "text": text,
                          "source": "SEC EDGAR",
                          "url": f"https://www.sec.gov/Archives/edgar/data/{f.cik}/{f.accn.replace('-', '')}/",
                          "meta": meta})
    items.sort(key=lambda x: (x["ts"], x["id"]))
    with open(OUT / "items.jsonl", "w") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    qs = build_questions(per, cur)
    qs.sort(key=lambda q: (q["base_id"], q["ask_at"]))
    with open(OUT / "questions.jsonl", "w") as fh:
        for q in qs:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")
    # sanity table for fiscal labels
    for tk in NAMES:
        for p in per[tk]:
            if p.fp and p.fp != "FY" and p.f.form == "10-K":
                print("WARN fp mismatch", tk, p.f.accn, p.fp)
            if p.f.form == "10-Q" and ("rev", "3M") not in p.vals:
                print("WARN no quarterly revenue", tk, p.f.accn, p.f.report)
    print(f"{len(items)} items, {len(qs)} question instances, {len({q['base_id'] for q in qs})} base")


if __name__ == "__main__":
    main()
