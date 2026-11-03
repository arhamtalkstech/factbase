"""Structured quiz for fedreg: gold computed in code from Federal Register API metadata."""

from __future__ import annotations

import calendar
import re
from collections import Counter
from datetime import date, timedelta

DS = "fedreg"
WIN_END = date(2026, 10, 31)


def month_end(y: int, m: int) -> date:
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return date(y, m, calendar.monthrange(y, m)[1])


def reask_dates(fact: date) -> list[date]:
    """First month-end on/after the fact, then about +3, +6, +12 months, and the window end."""
    out = [month_end(fact.year, fact.month + k) for k in (0, 3, 6, 12)] + [WIN_END]
    return sorted({d for d in out if d <= WIN_END})


def d_(s: str) -> date:
    return date.fromisoformat(s)


def long_date(d: date | str) -> str:
    d = d_(d) if isinstance(d, str) else d
    return f"{d.day} {calendar.month_name[d.month]} {d.year}"


def point_category(ask: date, fact: date) -> str:
    return "point_recent" if (ask - fact).days <= 30 else "point_old"


def date_gold(s: str) -> list[str]:
    d = d_(s)
    return [s, long_date(d), f"{calendar.month_name[d.month]} {d.day}, {d.year}"]


class Builder:
    def __init__(self, items: list[dict]):
        self.items = items
        self.by_doc = {it["meta"]["document_number"]: it for it in items}
        self.qs: list[dict] = []
        self.n = 0

    def new_base(self, prefix: str = "q") -> str:
        self.n += 1
        return f"{DS}:{prefix}{self.n:04d}"

    def emit(self, base_id, ask: date, question, gold, answer_type, category, fact_time, evidence,
             gold_source="structured", tol=None, note=None):
        q = {
            "qid": f"{base_id}@{ask.isoformat()}",
            "base_id": base_id,
            "dataset": DS,
            "ask_at": f"{ask.isoformat()}T23:59:59Z",
            "question": question,
            "gold": gold,
            "answer_type": answer_type,
            "numeric_tolerance": tol,
            "category": category,
            "fact_time": fact_time if isinstance(fact_time, str) else fact_time.isoformat(),
            "evidence_item_ids": evidence,
            "gold_source": gold_source,
        }
        if note:
            q["note"] = note
        self.qs.append(q)

    def point(self, question, gold, answer_type, fact: date, evidence, asks=None, gold_source="structured", tol=None):
        b = self.new_base()
        for a in asks or reask_dates(fact):
            self.emit(b, a, question, gold, answer_type, point_category(a, fact), fact, evidence, gold_source, tol)
        return b

    def doc(self, dn: str) -> dict:
        return self.by_doc[dn]


def find(items, pred):
    return [it for it in items if pred(it["meta"])]


def eo(items, n: str) -> dict:
    r = [it for it in items if str(it["meta"].get("executive_order_number")) == n]
    return sorted(r, key=lambda it: it["ts"])[0]


def proc(items, n: str) -> dict:
    r = [it for it in items if str(it["meta"].get("proclamation_number")) == n]
    return sorted(r, key=lambda it: it["ts"])[0]


def unique_title(items, title: str) -> bool:
    return sum(1 for it in items if it["meta"]["title"] == title) == 1


KIND = {"Rule": "final rule", "Notice": "notice", "Proposed Rule": "proposed rule"}
AG = {"foreign-assets-control-office": "OFAC", "industry-and-security-bureau": "BIS",
      "state-department": "State Department", "executive-office-of-the-president": "President"}


def who(m: dict) -> str:
    for s in m["agencies"]:
        if s in AG:
            return AG[s]
    return "agency"


def describe(m: dict) -> str:
    """Short reference like: the BIS final rule "Relaxing Export Controls for Syria"."""
    if m["type"] == "Presidential Document":
        st = (m.get("subtype") or "document").lower()
        return f'the presidential {st} "{m["title"]}"'
    return f'the {who(m)} {KIND.get(m["type"], m["type"].lower())} "{m["title"]}"'


def build_structured(items: list[dict]) -> list[dict]:
    B = Builder(items)
    pub = lambda it: d_(it["meta"]["publication_date"])  # noqa: E731

    # A. Executive order numbers and signing dates.
    for n in ["14203", "14257", "14312", "14382"]:
        it = eo(items, n)
        m = it["meta"]
        assert unique_title(items, m["title"]) or n == "14388"
        B.point(f'What Executive Order number was assigned to the executive order titled "{m["title"]}", '
                f'signed on {long_date(m["signing_date"])}?',
                [n, f"EO {n}", f"Executive Order {n}", f"E.O. {n}"], "text", pub(it), [it["id"]])
    for n in ["14245", "14436"]:
        it = eo(items, n)
        m = it["meta"]
        B.point(f'On what date did the President sign Executive Order {n} ("{m["title"]}")?',
                date_gold(m["signing_date"]), "date", pub(it), [it["id"]])

    # B. Proclamation numbers.
    for n in ["10962", "11052"]:
        it = proc(items, n)
        m = it["meta"]
        assert unique_title(items, m["title"])
        B.point(f'What proclamation number was assigned to the presidential proclamation "{m["title"]}", '
                f'signed on {long_date(m["signing_date"])}?',
                [n, f"Proclamation {n}", f"Proclamation No. {n}"], "text", pub(it), [it["id"]])

    # C. Publication dates of named documents.
    for dn in ["2025-00636", "2025-12036", "2025-16724", "2026-18222"]:
        it = B.doc(dn)
        m = it["meta"]
        assert unique_title(items, m["title"]), m["title"]
        B.point(f"On what date was {describe(m)} published in the Federal Register?",
                date_gold(m["publication_date"]), "date", pub(it), [it["id"]])

    # D. Effective dates.
    for dn in ["2025-00592", "2025-16735", "2026-14942"]:
        it = B.doc(dn)
        m = it["meta"]
        assert m["effective_on"] and m["effective_on"] != m["publication_date"]
        B.point(f"What is the effective date of {describe(m)}, published in the Federal Register on "
                f"{long_date(m['publication_date'])}?",
                date_gold(m["effective_on"]), "date", pub(it), [it["id"]])

    # D2. Effective date fixed by a later correction document (knowledge update).
    pk, pkc = B.doc("2024-27648"), B.doc("C1-2024-27648")
    from datetime import datetime
    fixed = re.search(r'should read "([A-Z][a-z]+ \d{1,2}, \d{4})', pkc["text"]).group(1)
    fixed = datetime.strptime(fixed, "%B %d, %Y").date().isoformat()
    b = B.new_base()
    for a in [date(2024, 11, 30), date(2025, 5, 31), WIN_END]:
        B.emit(b, a, 'BIS published the final rule "Implementation of Additional Controls on Pakistan" on 26 November '
                     "2024, and a correction to its DATES section was published on 29 November 2024. After that "
                     "correction, what is the rule's effective date?",
               date_gold(fixed), "date", "change", pkc["meta"]["publication_date"],
               [pk["id"], pkc["id"]])

    # E. Aggregates.
    ofac = [it for it in items if "foreign-assets-control-office" in it["meta"]["agencies"]]
    by_month = Counter(it["meta"]["publication_date"][:7] for it in ofac)
    for ym in ["2024-12", "2025-02", "2025-07", "2026-03", "2026-09"]:
        y, mo = map(int, ym.split("-"))
        end = month_end(y, mo)
        b = B.new_base()
        ev = [it["id"] for it in ofac if it["meta"]["publication_date"].startswith(ym)]
        asks = sorted(x for x in {end, month_end(y, mo + 6), WIN_END} if x <= WIN_END)
        for a in asks:
            B.emit(b, a, f"How many documents from the Treasury Department's Office of Foreign Assets Control (OFAC) "
                         f"were published in the Federal Register in {calendar.month_name[mo]} {y}?",
                   [str(by_month[ym])], "number", "aggregate", end, ev, tol=0.0)

    ent = [it for it in items if "industry-and-security-bureau" in it["meta"]["agencies"]
           and it["meta"]["type"] == "Rule" and "Entity List" in it["meta"]["title"]]
    ent.sort(key=lambda it: (it["ts"], it["id"]))
    ent25 = [it for it in ent if it["meta"]["publication_date"].startswith("2025")]
    b = B.new_base()
    for a in [date(2025, 12, 31), WIN_END]:
        B.emit(b, a, "How many BIS final rules with \"Entity List\" in their title were published in the Federal "
                     "Register during calendar year 2025?", [str(len(ent25))], "number", "aggregate",
               "2025-12-31", [it["id"] for it in ent25], tol=0.0)

    itsr = [it for it in items if "Iranian Transactions and Sanctions Regulations" in it["meta"]["title"]]
    itsr.sort(key=lambda it: (it["ts"], it["id"]))
    itsr_exact = [it for it in itsr if it["meta"]["title"] == "Iranian Transactions and Sanctions Regulations"
                  and it["meta"]["type"] == "Rule" and "2026-08-01" <= it["meta"]["publication_date"] <= "2026-10-31"]
    b = B.new_base()
    B.emit(b, WIN_END, "Between 1 August 2026 and 31 October 2026, how many OFAC final rules titled exactly "
                       "\"Iranian Transactions and Sanctions Regulations\" were published in the Federal Register?",
           [str(len(itsr_exact))], "number", "aggregate", "2026-10-31", [it["id"] for it in itsr_exact], tol=0.0)

    cont25 = [it for it in items if it["meta"]["type"] == "Presidential Document"
              and it["meta"]["title"].startswith("Continuation of the National Emergenc")
              and it["meta"]["publication_date"].startswith("2025")]
    b = B.new_base()
    for a in [date(2025, 12, 31), WIN_END]:
        B.emit(b, a, "How many presidential notices titled \"Continuation of the National Emergency ...\" (continuing "
                     "a national emergency) were published in the Federal Register during calendar year 2025?",
               [str(len(cont25))], "number", "aggregate", "2025-12-31", [it["id"] for it in cont25], tol=0.0)

    # F. Ordering.
    pairs = [("2025-16724", "2025-18618"), (eo(items, "14312")["meta"]["document_number"], "2025-16324"),
             ("2025-16735", "2025-19001"), (proc(items, "11020")["meta"]["document_number"], "2026-09489"),
             ("2025-00636", eo(items, "14320")["meta"]["document_number"])]
    for a_dn, b_dn in pairs:
        A, Bd = B.doc(a_dn), B.doc(b_dn)
        ma, mb = A["meta"], Bd["meta"]
        assert ma["publication_date"] < mb["publication_date"], (a_dn, b_dn)
        first = ma
        later = max(pub(A), pub(Bd))
        refs = [describe(ma), describe(mb)]
        if a_dn < b_dn:  # deterministic but not always first-listed-is-earlier
            refs = refs[::-1]
        q = (f"Which was published in the Federal Register first: {refs[0]} or {refs[1]}? "
             f"Give the earlier one and its publication date.")
        b = B.new_base()
        for a in sorted({month_end(later.year, later.month), month_end(later.year, later.month + 6), WIN_END}):
            if a <= WIN_END:
                B.emit(b, a, q, [first["title"], f'{first["title"]} ({first["publication_date"]})'], "text",
                       "ordering", later, [A["id"], Bd["id"]])

    # G. As-of state (knowledge updates).
    def latest(series, asof: date):
        prior = [it for it in series if pub(it) <= asof]
        return prior[-1] if prior else None

    def as_of(series, asof: date, question: str, extra_asks=()):
        it = latest(series, asof)
        same_day = [x["id"] for x in series if x["meta"]["publication_date"] == it["meta"]["publication_date"]]
        b = B.new_base()
        for a in sorted({asof, *[x for x in extra_asks if x > asof]}):
            B.emit(b, a, question, date_gold(it["meta"]["publication_date"]), "date", "as_of_state",
                   it["meta"]["publication_date"], same_day)

    for asof in ["2025-06-30", "2025-12-31", "2026-06-30", "2026-09-20", "2026-10-31"]:
        a = d_(asof)
        as_of(itsr, a, f"As of {long_date(a)}, what was the most recent OFAC document published in the Federal "
                       f"Register whose title names the Iranian Transactions and Sanctions Regulations, and on what "
                       f"date was it published?", extra_asks=[WIN_END] if a <= date(2026, 6, 30) else [])
    for asof in ["2024-11-30", "2025-06-30", "2025-10-31", "2026-06-30", "2026-10-31"]:
        a = d_(asof)
        as_of(ent, a, f"As of {long_date(a)}, on what date had BIS most recently published a final rule amending the "
                      f"Entity List (a rule with \"Entity List\" in its title) in the Federal Register?",
              extra_asks=[WIN_END] if a <= date(2025, 6, 30) else [])

    gl13 = []
    for it in items:
        m = it["meta"]
        if "Russian Harmful Foreign Activities" in m["title"]:
            for v in re.findall(r"\b13([A-Z])\b", m["title"]):
                gl13.append((m["publication_date"], v, it))
    gl13.sort(key=lambda x: (x[0], x[1]))
    for asof in ["2025-10-31", "2026-03-31", "2026-10-31"]:
        a = d_(asof)
        prior = [x for x in gl13 if d_(x[0]) <= a]
        pd, v, it = prior[-1]
        b = B.new_base()
        B.emit(b, a, f"As of {long_date(a)}, what was the latest version of OFAC's Russian Harmful Foreign Activities "
                     f"Sanctions Regulations Web General License 13 (13 followed by a letter) published in the Federal "
                     f"Register?", [f"13{v}", f"General License 13{v}", f"GL 13{v}"], "text", "as_of_state", pd, [it["id"]])

    iran_ne = [it for it in items if it["meta"]["title"] == "Continuation of the National Emergency With Respect to Iran"]
    iran_ne.sort(key=lambda it: it["ts"])
    for asof in ["2025-06-30", "2026-01-31"]:
        a = d_(asof)
        as_of(iran_ne, a, f"As of {long_date(a)}, on what date had the most recent presidential notice titled "
                          f"\"Continuation of the National Emergency With Respect to Iran\" been published in the "
                          f"Federal Register?")

    # H. Change / supersession.
    after = [it for it in ent if pub(it) > date(2025, 3, 28)][0]
    b = B.new_base()
    for a in [month_end(pub(after).year, pub(after).month), date(2026, 3, 31), WIN_END]:
        B.emit(b, a, "After the two BIS Entity List rules published on 28 March 2025, when was the next BIS final rule "
                     "with \"Entity List\" in its title published in the Federal Register, and what was its title?",
               date_gold(after["meta"]["publication_date"]) + [after["meta"]["title"]], "date", "change",
               after["meta"]["publication_date"], [after["id"]])
    o_dn = [x for x in gl13 if x[1] == "O"][0]
    p_dn = [x for x in gl13 if x[1] == "P"][0]
    b = B.new_base()
    for a in [month_end(d_(p_dn[0]).year, d_(p_dn[0]).month), WIN_END]:
        B.emit(b, a, "OFAC's Russian Harmful Foreign Activities Sanctions Regulations Web General License 13O was "
                     f"published in the Federal Register on {long_date(o_dn[0])}. Which version of General License 13 "
                     "was published next, and on what date?",
               ["13P", f"13P ({p_dn[0]})", *date_gold(p_dn[0])], "text", "change", p_dn[0], [o_dn[2]["id"], p_dn[2]["id"]])
    b = B.new_base()
    diff = by_month["2026-09"] - by_month["2025-09"]
    for a in [date(2026, 9, 30), WIN_END]:
        B.emit(b, a, "How many more OFAC documents were published in the Federal Register in September 2026 than in "
                     "September 2025?", [str(diff)], "number", "change", "2026-09-30",
               [it["id"] for it in ofac if it["meta"]["publication_date"][:7] in ("2025-09", "2026-09")], tol=0.0)

    # I. Multi-hop.
    p52, poly = proc(items, "11052"), B.doc("2026-19537")
    days = (pub(poly) - pub(p52)).days
    b = B.new_base()
    for a in [date(2026, 9, 30), WIN_END]:
        B.emit(b, a, f"BIS published the final rule \"{poly['meta']['title']}\" in the Federal Register on "
                     f"{long_date(poly['meta']['publication_date'])}. How many days earlier had the proclamation it "
                     f"names been published in the Federal Register?", [str(days)], "number", "multi_hop",
               poly["meta"]["publication_date"], [p52["id"], poly["id"]], tol=0.0)
    e203, icc = eo(items, "14203"), B.doc("2025-12036")
    days = (pub(icc) - pub(e203)).days
    b = B.new_base()
    for a in [date(2025, 7, 31), date(2026, 1, 31), WIN_END]:
        B.emit(b, a, "How many days after Executive Order 14203 (\"Imposing Sanctions on the International Criminal "
                     "Court\") was published in the Federal Register did OFAC publish its final rule \"International "
                     "Criminal Court-Related Sanctions Regulations\"?", [str(days)], "number", "multi_hop",
               icc["meta"]["publication_date"], [e203["id"], icc["id"]], tol=0.0)
    p32, guid = proc(items, "11032"), B.doc("2026-20938")
    b = B.new_base()
    for a in [date(2026, 10, 31)]:
        B.emit(b, a, f"BIS published guidance to U.S. Customs and Border Protection on "
                     f"{long_date(guid['meta']['publication_date'])} about assessing \"U.S. content\" for tariffs under a "
                     f"June 2026 proclamation. What is the title of that proclamation, and when was it published in the "
                     f"Federal Register?", [p32["meta"]["title"], *date_gold(p32["meta"]["publication_date"])], "text",
               "multi_hop", guid["meta"]["publication_date"], [p32["id"], guid["id"]])

    # J. Abstain (false premise or not yet published at ask time).
    def abstain(question, asks, note, evidence=(), fact="2026-10-31"):
        b = B.new_base()
        for a in asks:
            B.emit(b, a, question, [note], "abstain", "abstain", fact, list(evidence))

    syr = B.doc("2025-16724")
    abstain(f'On what date was the BIS final rule "{syr["meta"]["title"]}" published in the Federal Register?',
            [date(2025, 6, 30), date(2025, 8, 31)], "Not in the record at this date; the rule was only published on 2025-09-02.",
            fact=syr["meta"]["publication_date"])
    g = eo(items, "14436")
    abstain(f'What Executive Order number was assigned to the executive order "{g["meta"]["title"]}"?',
            [date(2026, 1, 31), date(2026, 6, 30)],
            "Not in the record at this date; that order was signed 2026-10-16 and published 2026-10-21.",
            fact=g["meta"]["publication_date"])
    june = [it for it in ent if it["meta"]["publication_date"].startswith("2025-06")]
    assert not june
    abstain("On what date in June 2025 did BIS publish a final rule adding entities to the Entity List, and how many "
            "entities did it add?", [date(2025, 7, 31), WIN_END],
            "False premise: BIS published no Entity List rule in June 2025 (none between 28 March and 16 September 2025).",
            fact="2025-06-30")
    assert not [it for it in itsr if it["meta"]["publication_date"].startswith("2025-03")]
    abstain("What was the effective date of the OFAC final rule titled \"Iranian Transactions and Sanctions "
            "Regulations\" that was published in the Federal Register in March 2025?", [date(2025, 4, 30), WIN_END],
            "False premise: no OFAC rule with that title was published in March 2025 (the first came on 2026-08-26).",
            fact="2025-03-31")
    abstain("What is the title of Presidential Proclamation 11052?", [date(2026, 3, 31), date(2026, 7, 31)],
            "Not in the record at this date; Proclamation 11052 was signed 2026-08-06 and published 2026-08-11.",
            fact=p52["meta"]["publication_date"])
    drone = sorted([it for it in items if it["meta"]["title"] == "Streamlining Export Controls for Drone Exports"],
                   key=lambda it: it["ts"])[0]
    abstain("What is the effective date of the BIS final rule \"Streamlining Export Controls for Drone Exports\"?",
            [date(2025, 9, 30), date(2025, 12, 31)], "Not in the record at this date; the first such rule was published on "
            f"{drone['meta']['publication_date']}.", fact=drone["meta"]["publication_date"])
    cacr = [it for it in items if it["meta"]["title"] == "Cuban Assets Control Regulations"]
    assert cacr and all(not it["meta"]["publication_date"].startswith("2025") for it in cacr)
    abstain("On what date in 2025 did OFAC publish a final rule titled \"Cuban Assets Control Regulations\" in the "
            "Federal Register?", [date(2025, 12, 31), WIN_END],
            "False premise: no OFAC rule with that title was published in 2025 (the only one in the record is "
            "dated 2026-09-30).", fact="2025-12-31")
    assert not [it for it in iran_ne if it["meta"]["publication_date"].startswith("2025-07")]
    abstain("What did the presidential notice \"Continuation of the National Emergency With Respect to Iran\" "
            "published in the Federal Register in July 2025 continue, and for how long?", [date(2025, 8, 31)],
            "False premise: no notice with that title was published in July 2025 (they appeared on 2025-03-12 and "
            "2025-11-07).", fact="2025-07-31")
    return B.qs
