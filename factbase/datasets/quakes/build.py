"""Build the `quakes` dataset: USGS M4.5+ earthquake catalogue plus a programmatic quiz.

Usage: uv run python -m factbase.datasets.quakes.build
"""

from __future__ import annotations

import calendar
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "quakes"
OUT = ROOT / "data" / "quakes"
NAME = "quakes"

WIN_START = date(2024, 11, 1)
WIN_END = date(2026, 10, 31)
LAG = timedelta(minutes=30)
API = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime={a}T00:00:00"
       "&endtime={b}T00:00:00&minmagnitude=4.5&orderby=time-asc")


# ---------------------------------------------------------------- helpers

def long_date(d: date) -> str:
    return f"{d.day} {calendar.month_name[d.month]} {d.year}"


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


def eod(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def date_gold(d: date) -> list[str]:
    return [d.isoformat(), long_date(d)]


def r1(x: float) -> str:
    """Round to one decimal, refusing values that sit on a rounding boundary."""
    f = abs(x * 10) % 1
    assert abs(f - 0.5) > 0.02, x
    return f"{round(x, 1):.1f}"


def mag_s(m: float) -> str:
    return f"{m:.2f}".rstrip("0").rstrip(".") if round(m, 1) != m else f"{m:.1f}"


# ---------------------------------------------------------------- data

def months() -> list[date]:
    out, d = [], WIN_START
    while d <= WIN_END:
        out.append(d)
        d = add_months_end(d, 0) + timedelta(days=1)
    return out


def fetch_month(m: date) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / f"{m:%Y-%m}.json"
    if p.exists():
        return json.loads(p.read_text())
    nxt = month_end(m) + timedelta(days=1)
    url = API.format(a=m.isoformat(), b=nxt.isoformat())
    for attempt in range(5):
        try:
            r = httpx.get(url, timeout=120)
            r.raise_for_status()
            break
        except httpx.HTTPError:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    data = r.json()
    assert data["metadata"]["count"] < 20000, m
    p.write_text(json.dumps(data))
    return data


@dataclass
class Ev:
    id: str
    t: datetime
    mag: float
    mt: str
    place: str
    region: str
    lat: float
    lon: float
    depth: float
    alert: str | None
    tsunami: int

    @property
    def d(self) -> date:
        return self.t.date()

    @property
    def ts(self) -> datetime:
        return self.t + LAG

    @property
    def iid(self) -> str:
        return f"{NAME}:{self.id}"


NAMED = re.compile(r"^(?:The )?\d{4} (.*) Earthquake$")


def core_place(place: str) -> str:
    """USGS named events ("2025 Mandalay, Burma (Myanmar) Earthquake") -> "Mandalay, Burma (Myanmar)"."""
    m = NAMED.match(place.strip())
    return m.group(1) if m else place.strip()


def region_of(place: str) -> str:
    c = core_place(place)
    return c.rsplit(",", 1)[-1].strip() if "," in c else c


class Data:
    def __init__(self) -> None:
        evs: dict[str, Ev] = {}
        self.skipped = Counter()
        for m in months():
            for f in fetch_month(m)["features"]:
                p = f["properties"]
                if p.get("type") != "earthquake":
                    self.skipped[p.get("type")] += 1
                    continue
                if p.get("mag") is None or not p.get("place"):
                    self.skipped["no mag/place"] += 1
                    continue
                t = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).replace(microsecond=0)
                if not (WIN_START <= t.date() <= WIN_END):
                    continue
                lon, lat, dep = f["geometry"]["coordinates"][:3]
                evs[f["id"]] = Ev(f["id"], t, round(float(p["mag"]), 2), p.get("magType") or "unknown",
                                  p["place"].strip(), region_of(p["place"]), round(lat, 3), round(lon, 3),
                                  round(float(dep), 1), p.get("alert"), int(p.get("tsunami") or 0))
        self.ev = sorted(evs.values(), key=lambda e: (e.t, e.id))
        self.by_id = {e.id: e for e in self.ev}

    def sel(self, a: date | None = None, b: date | None = None, mmin: float | None = None,
            where=None, visible_at: date | None = None) -> list[Ev]:
        out = []
        for e in self.ev:
            if a and e.d < a or b and e.d > b:
                continue
            if mmin is not None and e.mag < mmin:
                continue
            if visible_at and e.ts > eod(visible_at):
                continue
            if where and not where(e):
                continue
            out.append(e)
        return out


# ---------------------------------------------------------------- items

PREPS = ("south", "north", "east", "west", "southeast", "southwest", "northeast", "northwest", "southern",
         "northern", "eastern", "western", "central", "near", "off")


def where_phrase(place: str) -> str:
    if NAMED.match(place):
        return f"near {core_place(place)} (the event USGS catalogues as the \"{place}\")"
    first = place.split()[0]
    if first[0].isdigit() or first in PREPS:
        return place
    return f"in the {place}" if place.endswith("region") else f"in the {place} area"


def item_text(e: Ev) -> str:
    alert = e.alert if e.alert else "none"
    return (f"At {e.t:%H:%M} UTC on {long_date(e.d)} a magnitude {mag_s(e.mag)} ({e.mt}) earthquake struck "
            f"{where_phrase(e.place)}, at a depth of {e.depth:.1f} km (USGS event {e.id}). "
            f"Alert level: {alert}. Tsunami flag: {'yes' if e.tsunami else 'no'}.")


def build_items(D: Data) -> list[dict]:
    items = []
    for e in D.ev:
        items.append({
            "id": e.iid, "dataset": NAME, "ts": e.ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "title": f"M{mag_s(e.mag)} earthquake - {e.place}",
            "text": item_text(e), "source": "USGS",
            "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{e.id}",
            "meta": {"mag": e.mag, "magType": e.mt, "place": e.place, "region": e.region, "lat": e.lat,
                     "lon": e.lon, "depth_km": e.depth, "alert": e.alert, "tsunami": e.tsunami,
                     "usgs_id": e.id, "time": e.t.strftime("%Y-%m-%dT%H:%M:%SZ")},
        })
    items.sort(key=lambda it: (it["ts"], it["id"]))
    return items


# ---------------------------------------------------------------- questions

class Quiz:
    def __init__(self, D: Data) -> None:
        self.D = D
        self.base: list[dict] = []

    def add(self, category: str, question: str, gold: list[str], answer_type: str, fact_time: date,
            evidence: list[Ev], asks: list[date], tol: float | None = None) -> None:
        assert asks, question
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
                    for e in b["evidence"]:
                        assert e.ts <= eod(a), (b["question"], a, e.id)
                out.append({
                    "qid": f"{base_id}@{a.isoformat()}", "base_id": base_id, "dataset": NAME,
                    "ask_at": f"{a.isoformat()}T23:59:59Z", "question": b["question"], "gold": b["gold"],
                    "answer_type": b["answer_type"], "numeric_tolerance": b["tol"], "category": cat,
                    "fact_time": b["fact_time"].isoformat(), "evidence_item_ids": [e.iid for e in b["evidence"]],
                    "gold_source": "structured",
                })
        return out


def loc_gold(e: Ev) -> list[str]:
    g = [e.place, core_place(e.place)]
    if core_place(e.place)[0].isdigit() and " of " in core_place(e.place):
        g.append(core_place(e.place).split(" of ", 1)[1])
    g.append(e.region)
    if e.region == "Burma (Myanmar)":
        g += ["Myanmar", "Burma"]
    return list(dict.fromkeys(g))


def ev_gold(e: Ev) -> list[str]:
    """Identify an event: location and date (and magnitude)."""
    return [f"M{mag_s(e.mag)} {core_place(e.place)} on {long_date(e.d)}"] + loc_gold(e) + date_gold(e.d)


THE = {"Philippines", "Solomon Islands", "Northern Mariana Islands", "Cayman Islands", "Kuril Islands"}


def area_phrase(e: Ev) -> str:
    if "," not in core_place(e.place):
        return where_phrase(e.place)
    return f"in the {e.region}" if e.region in THE else f"in {e.region}"


def signed(n: int) -> list[str]:
    return list(dict.fromkeys([f"{n:+d}", str(n)]))


def in_(*names: str):
    return lambda e: any(n in e.place for n in names)


def loc_desc(name: str) -> str:
    return f"in or off {name} (any event whose USGS location names {name})"


def strict_top(evs: list[Ev], k: int, key=lambda e: e.mag, reverse=True) -> Ev:
    """k-th (1-based) event by key, asserting the top k+1 keys are distinct."""
    s = sorted(evs, key=key, reverse=reverse)
    ks = [key(e) for e in s[:k + 1]]
    assert len(set(ks)) == len(ks), ks
    return s[k - 1]


def unique_max(evs: list[Ev], key=lambda e: e.mag) -> Ev:
    return strict_top(evs, 1, key)


def period_s(a: date, b: date) -> str:
    return f"between {long_date(a)} and {long_date(b)} (inclusive, UTC dates)"


def build_questions(D: Data) -> list[dict]:
    Q = Quiz(D)
    JP = in_("Japan")

    # --- point lookups: one sizeable event every ~6 weeks, rotating the asked attribute
    templates = ["mag", "depth", "where", "time"]
    anchor, n = date(2024, 11, 10), 0
    used: set[str] = set()
    while anchor <= date(2026, 10, 15):
        cands = [e for e in D.sel(anchor, anchor + timedelta(days=20), 5.6)
                 if not NAMED.match(e.place) and e.id not in used]
        cands.sort(key=lambda e: (-e.mag, e.t))
        tmpl = templates[n % len(templates)]
        for e in cands:
            same_day = D.sel(e.d, e.d)
            if tmpl != "where" and sum(1 for x in same_day if x.region == e.region) != 1:
                continue
            if tmpl == "where" and sum(1 for x in same_day if x.mag == e.mag) != 1:
                continue
            break
        else:
            raise AssertionError(anchor)
        used.add(e.id)
        ds = long_date(e.d)
        if tmpl == "mag":
            Q.add("point", f"What was the magnitude of the earthquake that struck {where_phrase(e.place)} on {ds}?",
                  [mag_s(e.mag)], "number", e.d, [e], sched_point(e.d), 0.001)
        elif tmpl == "depth":
            Q.add("point", f"At what depth, in kilometres, did the magnitude {mag_s(e.mag)} earthquake {where_phrase(e.place)} "
                  f"on {ds} occur?", list(dict.fromkeys([f"{e.depth:.1f}", f"{e.depth:g}"])), "number", e.d, [e], sched_point(e.d), 0.002)
        elif tmpl == "where":
            Q.add("point", f"Where did the magnitude {mag_s(e.mag)} earthquake of {ds} strike, according to USGS?",
                  loc_gold(e), "text", e.d, [e], sched_point(e.d))
        else:
            Q.add("point", f"At what time (UTC, hours and minutes) did the earthquake {area_phrase(e)} on {ds} occur?",
                  [f"{e.t:%H:%M}", f"{e.t:%H:%M} UTC"], "text", e.d, [e], sched_point(e.d))
        n += 1
        anchor += timedelta(days=60)

    # point: alert level / tsunami flag / magnitude type of notable events
    e = next(x for x in D.ev if x.place == "8 km ESE of Calape, Philippines" and x.mag >= 6.5)
    Q.add("point", f"What PAGER alert level did USGS list for the magnitude {mag_s(e.mag)} earthquake near Calape, "
          f"Philippines on {long_date(e.d)}?", [e.alert], "text", e.d, [e], sched_point(e.d))
    e = next(x for x in D.ev if x.place == "0 km W of San Marcos, Mexico" and x.mag >= 6)
    Q.add("point", f"Did USGS set the tsunami flag for the magnitude {mag_s(e.mag)} earthquake {e.place} on "
          f"{long_date(e.d)}?", ["yes" if e.tsunami else "no"], "text", e.d, [e], sched_point(e.d))
    e = next(x for x in D.ev if x.place == "2025 Southern Tibetan Plateau Earthquake")
    Q.add("point", f"What magnitude type (for example mb or mww) did USGS report for the {e.place} of "
          f"{long_date(e.d)}?", [e.mt], "text", e.d, [e], sched_point(e.d))

    # --- as_of_state
    def most_recent(d: date, pred, mmin=None) -> Ev:
        evs = D.sel(None, d, mmin, pred, visible_at=d)
        late = [x for x in D.sel(d, d, mmin, pred) if x.ts > eod(d)]
        assert not late, (d, late)
        return evs[-1]

    for d in [date(2025, 6, 15), date(2026, 1, 20), date(2026, 9, 5)]:
        e = most_recent(d, None, 7.0)
        Q.add("as_of_state", f"As of the end of {long_date(d)} (UTC), where had the most recent earthquake of "
              f"magnitude 7.0 or greater struck, and when?", ev_gold(e), "text", d, [e], [d, add_months_end(d, 3)]
              if add_months_end(d, 3) <= WIN_END else [d])
    d = date(2025, 12, 31)
    e = most_recent(d, lambda x: x.tsunami == 1 and x.mag >= 6.0)
    Q.add("as_of_state", f"As of {long_date(d)}, on what date had the most recent magnitude 6.0+ earthquake with the "
          f"USGS tsunami flag set occurred?", date_gold(e.d), "date", d, [e], [d])
    for d in [date(2026, 3, 31), date(2026, 7, 31)]:
        evs = D.sel(date(2026, 1, 1), d, 5.0, visible_at=d)
        top = max(x.mag for x in evs)
        Q.add("as_of_state", f"As of {long_date(d)}, what was the largest earthquake magnitude recorded anywhere in "
              f"the world so far in calendar year 2026?", [mag_s(top)], "number", d,
              [x for x in evs if x.mag == top], [d], 0.001)
    d = date(2025, 10, 31)
    evs = D.sel(date(2025, 1, 1), d, 7.0, visible_at=d)
    Q.add("as_of_state", f"As of {long_date(d)}, how many earthquakes of magnitude 7.0 or greater had occurred "
          f"worldwide since 1 January 2025?", [str(len(evs))], "number", d, evs, [d, WIN_END], 0.0)
    d = date(2026, 2, 28)
    e = unique_max(D.sel(None, d, 6.0, visible_at=d), key=lambda x: x.depth)
    Q.add("as_of_state", f"As of {long_date(d)}, which magnitude 6.0+ earthquake since 1 November 2024 had the "
          f"greatest focal depth? Give its location and depth.", ev_gold(e) + [f"{e.depth:.1f} km"], "text", d, [e],
          [d, WIN_END])
    d = date(2026, 5, 31)
    e = most_recent(d, lambda x: x.alert in ("orange", "red"))
    Q.add("as_of_state", f"As of {long_date(d)}, what was the most recent earthquake to receive an orange or red "
          f"USGS PAGER alert?", ev_gold(e), "text", d, [e], [d])
    d = date(2026, 8, 20)
    e = most_recent(d, JP, 6.0)
    Q.add("as_of_state", f"As of {long_date(d)}, on what date had the most recent magnitude 6.0+ earthquake "
          f"{loc_desc('Japan')} occurred?", date_gold(e.d), "date", d, [e], [d])

    # --- aggregate
    def count_q(text, a, b, mmin, pred, asks=None, cat="aggregate"):
        evs = D.sel(a, b, mmin, pred)
        Q.add(cat, text, [str(len(evs))], "number", b, evs, asks or sched_other(b), 0.0)
        return evs

    evs = count_q(f"How many earthquakes of magnitude 5.0 or greater deeper than 70 km occurred {loc_desc('Japan')} "
                  f"in calendar year 2025?", date(2025, 1, 1), date(2025, 12, 31), 5.0,
                  lambda e: JP(e) and e.depth > 70)
    assert evs
    count_q(f"How many magnitude 5.0+ earthquakes shallower than 30 km struck {loc_desc('Indonesia')} in Q3 2025 "
            f"(1 July to 30 September 2025)?", date(2025, 7, 1), date(2025, 9, 30), 5.0,
            lambda e: "Indonesia" in e.place and e.depth < 30)
    count_q("How many earthquakes in the USGS M4.5+ catalogue had the tsunami flag set in calendar year 2025?",
            date(2025, 1, 1), date(2025, 12, 31), None, lambda e: e.tsunami == 1)
    count_q("How many magnitude 5.5+ deep-focus earthquakes (depth of 300 km or more) occurred worldwide in 2025?",
            date(2025, 1, 1), date(2025, 12, 31), 5.5, lambda e: e.depth >= 300)
    count_q("How many earthquakes of magnitude 7.0 or greater occurred worldwide in calendar year 2025?",
            date(2025, 1, 1), date(2025, 12, 31), 7.0, None)
    count_q(f"How many magnitude 4.5+ earthquakes were recorded {loc_desc('Greece')} in February 2025?",
            date(2025, 2, 1), date(2025, 2, 28), None, in_("Greece"))
    count_q("How many magnitude 6.5+ earthquakes with magnitude type mww occurred worldwide in the first half of "
            "2026 (1 January to 30 June)?", date(2026, 1, 1), date(2026, 6, 30), 6.5, lambda e: e.mt == "mww")
    count_q(f"How many earthquakes of magnitude 6.0 or greater struck {loc_desc('Vanuatu')} in December 2024?",
            date(2024, 12, 1), date(2024, 12, 31), 6.0, in_("Vanuatu"))
    b = date(2026, 9, 30)
    count_q(f"How many earthquakes received an orange or red USGS PAGER alert {period_s(WIN_START, b)}?",
            WIN_START, b, None, lambda e: e.alert in ("orange", "red"), [b, WIN_END])

    a, b = date(2025, 1, 1), date(2025, 12, 31)
    e = strict_top(D.sel(a, b, 7.0), 2)
    Q.add("aggregate", "What was the second-largest earthquake (by magnitude) of calendar year 2025? Give its "
          "magnitude and location.", ev_gold(e), "text", b, [e], sched_other(b))
    a2, b2 = date(2026, 1, 1), date(2026, 9, 30)
    e = strict_top(D.sel(a2, b2, 6.0, JP), 3)
    Q.add("aggregate", f"What was the magnitude of the third-largest earthquake {loc_desc('Japan')} between "
          f"1 January and 30 September 2026?", [mag_s(e.mag)], "number", b2, D.sel(a2, b2, e.mag, JP),
          sched_other(b2), 0.001)
    e = strict_top(D.sel(a, b, 6.0, in_("Philippines")), 2)
    Q.add("aggregate", f"In calendar year 2025, what was the second-highest magnitude among earthquakes "
          f"{loc_desc('the Philippines')}, and on what date did it occur?",
          [f"{mag_s(e.mag)} on {long_date(e.d)}", mag_s(e.mag)] + date_gold(e.d), "text", b, [e], sched_other(b))

    names = ["Indonesia", "Philippines", "Japan", "Papua New Guinea", "Tonga"]
    for (a, b, label, mmin) in [(date(2025, 1, 1), date(2025, 12, 31), "calendar year 2025", 5.0),
                                (date(2026, 1, 1), date(2026, 6, 30), "the first half of 2026 (January to June)", 5.0)]:
        cnt = {nm: len(D.sel(a, b, mmin, in_(nm))) for nm in names}
        assert len(set(cnt.values())) == len(cnt), cnt
        rk = sorted(names, key=lambda nm: -cnt[nm])
        Q.add("aggregate", f"Rank these five areas by the number of magnitude {mmin:.1f}+ earthquakes in {label}, "
              f"most first, counting any event whose USGS location names the area: {', '.join(names)}.",
              [" > ".join(rk), ", ".join(rk)], "text", b, D.sel(a, b, mmin, in_(*names)), sched_other(b))

    a, b = date(2025, 1, 1), date(2025, 12, 31)
    c = Counter(e.d.month for e in D.sel(a, b, 6.0))
    (m1, n1), (_, n2) = c.most_common(2)
    assert n1 > n2
    Q.add("aggregate", "Which calendar month of 2025 had the most earthquakes of magnitude 6.0 or greater worldwide, "
          "and how many were there?", [f"{calendar.month_name[m1]} 2025 ({n1})", calendar.month_name[m1]], "text",
          b, [e for e in D.sel(a, b, 6.0) if e.d.month == m1], sched_other(b))
    c = Counter(e.d for e in D.sel(a, b))
    (d1, n1), (_, n2) = c.most_common(2)
    assert n1 > n2
    Q.add("aggregate", "On which single UTC calendar day of 2025 did USGS record the largest number of magnitude "
          "4.5+ earthquakes worldwide?", date_gold(d1), "date", b, [e for e in D.sel(d1, d1)][:50], sched_other(b))
    a, b = date(2026, 3, 1), date(2026, 3, 31)
    c = Counter(e.region for e in D.sel(a, b))
    (r1_, n1), (_, n2) = c.most_common(2)
    assert n1 > n2
    Q.add("aggregate", "In March 2026, which country or sea region (the last part of the USGS location name) had the "
          "most magnitude 4.5+ earthquakes?", [r1_], "text", b, [e for e in D.sel(a, b) if e.region == r1_],
          sched_other(b))

    a, b = date(2025, 1, 1), date(2025, 12, 31)
    evs = D.sel(a, b, 5.0, in_("Chile"))
    avg = sum(e.depth for e in evs) / len(evs)
    Q.add("aggregate", f"What was the average focal depth, in km rounded to one decimal place, of magnitude 5.0+ "
          f"earthquakes {loc_desc('Chile')} in 2025?", [r1(avg)], "number", b, evs, sched_other(b), 0.005)
    a, b = date(2026, 1, 1), date(2026, 6, 30)
    e = unique_max(D.sel(a, b, 5.5), key=lambda x: x.depth)
    Q.add("aggregate", "Which magnitude 5.5+ earthquake in the first half of 2026 (January to June) was the deepest, "
          "and how deep was it (km)?", ev_gold(e) + [f"{e.depth:.1f} km"], "text", b, [e], sched_other(b))
    a, b = date(2025, 8, 1), date(2025, 8, 31)
    days = sorted({e.d for e in D.sel(a, b, 6.0)})
    Q.add("aggregate", "On how many distinct UTC calendar days in August 2025 was at least one earthquake of "
          "magnitude 6.0 or greater recorded worldwide?", [str(len(days))], "number", b, D.sel(a, b, 6.0),
          sched_other(b), 0.0)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    evs = D.sel(a, b, 6.0)
    pct = 100 * sum(e.tsunami for e in evs) / len(evs)
    assert abs(pct % 1 - 0.5) > 0.05
    Q.add("aggregate", "What percentage of magnitude 6.0+ earthquakes in 2025 had the USGS tsunami flag set? Round "
          "to the nearest whole percent.", [f"{round(pct)}", f"{round(pct)}%"], "number", b, evs, sched_other(b),
          0.0)
    e = unique_max(D.sel(WIN_START, date(2026, 10, 15), 5.5, in_("Alaska")))
    Q.add("aggregate", f"What was the largest earthquake {loc_desc('Alaska')} {period_s(WIN_START, date(2026, 10, 15))}? "
          f"Give magnitude and date.", [f"{mag_s(e.mag)} on {long_date(e.d)}"] + date_gold(e.d), "text",
          date(2026, 10, 15), [e], [WIN_END])
    e = strict_top(D.sel(date(2026, 1, 1), date(2026, 9, 30), 6.0, in_("Tonga")), 2)
    Q.add("aggregate", f"What was the second-highest earthquake magnitude {loc_desc('Tonga')} between 1 January and "
          f"30 September 2026?", [mag_s(e.mag)], "number", date(2026, 9, 30),
          D.sel(date(2026, 1, 1), date(2026, 9, 30), e.mag, in_("Tonga")), [WIN_END], 0.001)

    # --- change
    def cnt(a, b, mmin, pred=None):
        return D.sel(a, b, mmin, pred)

    q25, q26 = cnt(date(2025, 1, 1), date(2025, 3, 31), 5.0), cnt(date(2026, 1, 1), date(2026, 3, 31), 5.0)
    Q.add("change", "How did the worldwide number of magnitude 5.0+ earthquakes in Q1 2026 (January to March) "
          "compare with Q1 2025? Give the difference, 2026 count minus 2025 count.",
          signed(len(q26) - len(q25)), "number", date(2026, 3, 31), q25 + q26,
          sched_other(date(2026, 3, 31)), 0.0)
    h1, h2 = cnt(date(2025, 1, 1), date(2025, 6, 30), 5.0, in_("Russia")), cnt(date(2025, 7, 1), date(2025, 12, 31),
                                                                               5.0, in_("Russia"))
    Q.add("change", f"By how much did the number of magnitude 5.0+ earthquakes {loc_desc('Russia')} change from the "
          f"first half of 2025 (January to June) to the second half (July to December)? Give second-half count "
          f"minus first-half count.", signed(len(h2) - len(h1)), "number",
          date(2025, 12, 31), h1 + h2, sched_other(date(2025, 12, 31)), 0.0)
    m25, m26 = cnt(date(2025, 3, 1), date(2025, 3, 31), None, JP), cnt(date(2026, 3, 1), date(2026, 3, 31), None, JP)
    pc = 100 * (len(m26) - len(m25)) / len(m25)
    assert abs(pc % 1 - 0.5) > 0.05
    Q.add("change", f"By what percentage did the number of magnitude 4.5+ earthquakes {loc_desc('Japan')} change "
          f"from March 2025 to March 2026? Round to the nearest whole percent (negative for a decrease).",
          signed(round(pc)) + [f"{round(pc)}%"], "number", date(2026, 3, 31), m25 + m26,
          sched_other(date(2026, 3, 31)), 0.0)
    s25, s26 = cnt(date(2025, 9, 1), date(2025, 9, 30), 5.5), cnt(date(2026, 9, 1), date(2026, 9, 30), 5.5)
    Q.add("change", "How many more or fewer magnitude 5.5+ earthquakes were recorded worldwide in September 2026 "
          "than in September 2025? Give September 2026 count minus September 2025 count.",
          signed(len(s26) - len(s25)), "number", date(2026, 9, 30), s25 + s26,
          [WIN_END], 0.0)
    k = next(x for x in D.ev if x.mag >= 8.5)
    prev = unique_max(D.sel(date(2025, 1, 1), k.d - timedelta(days=1), 7.0))
    Q.add("change", f"The magnitude {mag_s(k.mag)} earthquake of {long_date(k.d)} became the largest earthquake of "
          f"2025. Which earthquake had been the largest of 2025 before it?", ev_gold(prev), "text", k.d, [prev, k],
          sched_other(k.d))
    p25 = unique_max(D.sel(date(2025, 1, 1), date(2025, 12, 31), 6.0, in_("Philippines")))
    p26 = unique_max(D.sel(date(2026, 1, 1), date(2026, 9, 30), 6.0, in_("Philippines")))
    Q.add("change", f"How much larger or smaller (in magnitude units, one decimal) was the strongest earthquake "
          f"{loc_desc('the Philippines')} in January-September 2026 than the strongest one in calendar year 2025? "
          f"Give 2026 minus 2025.", [f"{p26.mag - p25.mag:+.1f}", f"{p26.mag - p25.mag:.1f}"], "number",
          date(2026, 9, 30), [p25, p26], [date(2026, 9, 30), WIN_END], 0.001)
    t25, t26 = cnt(date(2025, 1, 1), date(2025, 6, 30), 5.0, in_("Tonga")), cnt(date(2026, 1, 1), date(2026, 6, 30),
                                                                                5.0, in_("Tonga"))
    a1, a2 = sum(e.depth for e in t25) / len(t25), sum(e.depth for e in t26) / len(t26)
    Q.add("change", f"Comparing magnitude 5.0+ earthquakes {loc_desc('Tonga')} in January-June 2025 with "
          f"January-June 2026, by how many kilometres did their average focal depth change (2026 minus 2025, one "
          f"decimal, using the depths as reported)?", [f"{float(r1(a2 - a1)):+.1f}", r1(a2 - a1)], "number",
          date(2026, 6, 30), t25 + t26, sched_other(date(2026, 6, 30)), 0.005)

    # --- ordering
    def first_after(a: date, pred, mmin) -> Ev:
        return D.sel(a, None, mmin, pred)[0]

    e = first_after(date(2025, 6, 1), in_("Chile"), 6.0)
    Q.add("ordering", f"What was the first earthquake of magnitude 6.0 or greater {loc_desc('Chile')} on or after "
          f"1 June 2025? Give its date and magnitude.", [f"{mag_s(e.mag)} on {long_date(e.d)}"] + date_gold(e.d),
          "text", e.d, [e], sched_other(e.d))
    e = first_after(date(2026, 1, 1), None, 7.0)
    Q.add("ordering", "What was the first earthquake of magnitude 7.0 or greater in 2026, and where did it strike?",
          ev_gold(e), "text", e.d, [e], sched_other(e.d))
    e = first_after(date(2026, 1, 1), lambda x: x.tsunami == 1 and x.mag >= 6.0, None)
    Q.add("ordering", "On what date in 2026 was a magnitude 6.0+ earthquake with the USGS tsunami flag first "
          "recorded?", date_gold(e.d), "date", e.d, [e], sched_other(e.d))
    i7 = first_after(date(2026, 1, 1), in_("Indonesia"), 7.0)
    j7 = first_after(date(2026, 1, 1), JP, 7.0)
    assert abs((i7.d - j7.d).days) >= 3
    first, later = (("Indonesia", i7), ("Japan", j7)) if i7.t < j7.t else (("Japan", j7), ("Indonesia", i7))
    Q.add("ordering", "Counting from 1 January 2026, which came first: the first magnitude 7.0+ earthquake located "
          "in or off Indonesia, or the first magnitude 7.0+ earthquake located in or off Japan?",
          [f"{first[0]} ({long_date(first[1].d)}, before {long_date(later[1].d)})", first[0]], "text",
          later[1].d, [i7, j7], sched_other(later[1].d))
    my = next(x for x in D.ev if x.place.startswith("2025 Mandalay"))
    Q.add("ordering", f"How many days passed between the magnitude {mag_s(my.mag)} Mandalay, Myanmar earthquake and "
          f"the magnitude {mag_s(k.mag)} Kamchatka Peninsula earthquake of 2025 (difference between UTC dates)?",
          [str((k.d - my.d).days)], "number", k.d, [my, k], sched_other(k.d), 0.0)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    big = D.sel(a, b, 7.0)
    gaps = sorted((((y.d - x.d).days, x, y) for x, y in zip(big, big[1:])), key=lambda g: g[0])
    assert gaps[-1][0] > gaps[-2][0]
    g, x, y = gaps[-1]
    Q.add("ordering", "In 2025, what was the longest gap, in days (difference between UTC dates), between two "
          "consecutive earthquakes of magnitude 7.0 or greater worldwide, and between which two events?",
          [f"{g} days ({long_date(x.d)} to {long_date(y.d)})", str(g)], "text", b, big, sched_other(b))
    trio = [next(x for x in D.ev if x.place == p) for p in
            ("2025 Hubbard Glacier Earthquake", "2025 Drake Passage Earthquake", "2025 Sand Point, Alaska Earthquake")]
    srt = sorted(trio, key=lambda x: x.t)
    Q.add("ordering", "Put these 2025 earthquakes in chronological order, earliest first: the Hubbard Glacier "
          "earthquake, the Drake Passage earthquake (magnitude 7.4), and the Sand Point, Alaska earthquake.",
          [" < ".join(core_place(x.place) for x in srt), ", ".join(core_place(x.place) for x in srt)], "text",
          srt[-1].d, trio, sched_other(srt[-1].d))
    e = D.sel(None, date(2025, 12, 31), 6.0)[-1]
    Q.add("ordering", "What was the last earthquake of magnitude 6.0 or greater of calendar year 2025 (UTC)? Give "
          "its location and date.", ev_gold(e), "text", date(2025, 12, 31), [e], sched_other(date(2025, 12, 31)))
    gr = first_after(WIN_START, in_("Greece"), 6.0)
    tu = first_after(WIN_START, in_("Turkey"), 6.0)
    assert abs((gr.d - tu.d).days) >= 3
    f_, l_ = (("Greece", gr), ("Turkey", tu)) if gr.t < tu.t else (("Turkey", tu), ("Greece", gr))
    Q.add("ordering", "Counting from 1 November 2024, which country first had an earthquake of magnitude 6.0 or "
          "greater in its USGS location: Greece or Turkey? How many days apart were the two first events?",
          [f"{f_[0]}, {(l_[1].d - f_[1].d).days} days earlier", f_[0]], "text", l_[1].d, [gr, tu],
          sched_other(l_[1].d))

    # --- multi_hop
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    e = unique_max(D.sel(a, b, 6.0, JP))
    Q.add("multi_hop", f"What was the focal depth (km) of the largest earthquake {loc_desc('Japan')} in 2025?",
          list(dict.fromkeys([f"{e.depth:.1f}", f"{e.depth:g}"])), "number", b, D.sel(a, b, 6.0, JP), sched_other(b), 0.002)
    after = [x for x in D.sel(k.d, k.d + timedelta(days=7), 5.0, in_("Russia"))
             if k.t < x.t <= k.t + timedelta(days=7)]
    Q.add("multi_hop", f"Within the 7 days (168 hours) after the magnitude {mag_s(k.mag)} Kamchatka Peninsula "
          f"earthquake of {long_date(k.d)}, how many other magnitude 5.0+ earthquakes located in Russia were "
          f"recorded?", [str(len(after))], "number", (k.t + timedelta(days=7)).date(), [k] + after,
          sched_other((k.t + timedelta(days=7)).date()), 0.0)
    l25 = unique_max(D.sel(date(2025, 1, 1), date(2025, 12, 31), 7.0))
    l26 = D.sel(date(2026, 1, 1), date(2026, 9, 30), 7.0)
    top26 = max(x.mag for x in l26)
    Q.add("multi_hop", "By how many magnitude units did the largest earthquake of 2025 exceed the largest earthquake "
          "of January-September 2026? Answer to one decimal.", [f"{l25.mag - top26:.1f}"], "number",
          date(2026, 9, 30), [l25] + [x for x in l26 if x.mag == top26], [date(2026, 9, 30), WIN_END], 0.001)
    e = unique_max(D.sel(a, b, 6.0), key=lambda x: x.depth)
    Q.add("multi_hop", "What USGS PAGER alert level was recorded for the deepest magnitude 6.0+ earthquake of 2025?",
          [e.alert or "none"] + (["no alert", "none issued"] if not e.alert else []), "text", b, [e],
          sched_other(b))
    p = unique_max(D.sel(a, b, 6.0, in_("Philippines")))
    wk = [x for x in D.sel(p.d, p.d + timedelta(days=7), 6.0, in_("Philippines"))
          if p.t < x.t <= p.t + timedelta(days=7)]
    Q.add("multi_hop", f"In the 7 days (168 hours) after the strongest 2025 earthquake {loc_desc('the Philippines')}, "
          f"how many further magnitude 6.0+ earthquakes in or off the Philippines were recorded?",
          [str(len(wk))], "number", b, [p] + wk, sched_other(b), 0.0)
    c = unique_max(D.sel(a, b, 5.0, in_("Chile")))
    others = [x for x in D.sel(c.d, c.d) if x.id != c.id]
    Q.add("multi_hop", f"On the UTC day of the strongest 2025 earthquake {loc_desc('Chile')}, how many other "
          f"magnitude 4.5+ earthquakes were recorded worldwide?", [str(len(others))], "number", b, [c] + others,
          sched_other(b), 0.0)
    mm = l25.d.month
    m6 = D.sel(date(2025, mm, 1), month_end(l25.d), 6.0)
    Q.add("multi_hop", "In the calendar month in which the largest earthquake of 2025 occurred, how many earthquakes "
          "of magnitude 6.0 or greater were recorded worldwide (including that one)?", [str(len(m6))], "number", b,
          m6, sched_other(b), 0.0)
    af = next(x for x in D.sel(k.d, None, 6.0, in_("Russia")) if x.t > k.t)
    Q.add("multi_hop", f"What was the magnitude of the first magnitude 6.0+ earthquake in Russia after the magnitude "
          f"{mag_s(k.mag)} Kamchatka Peninsula mainshock of {long_date(k.d)}, and how many minutes after the "
          f"mainshock did it occur (using the reported UTC hours and minutes)?",
          [f"{mag_s(af.mag)}, {int((af.t.replace(second=0) - k.t.replace(second=0)).total_seconds() // 60)} minutes"],
          "text", af.d, [k, af], sched_other(af.d))

    # --- abstain
    e = next(x for x in D.ev if "Ende, Indonesia" in x.place and x.mag >= 7.5)
    Q.add("abstain", f"What was the magnitude of the earthquake near Ende, Indonesia on {long_date(e.d)}?",
          [f"Not known as of the ask date: {long_date(e.d)} is in the future."], "abstain", e.d, [],
          [date(2026, 6, 30), date(2026, 7, 31)])
    Q.add("abstain", "Where did the largest earthquake of September 2026 strike?",
          ["Not known as of the ask date: September 2026 has not happened yet."], "abstain", date(2026, 9, 30), [],
          [date(2026, 7, 31), date(2026, 8, 31)])
    Q.add("abstain", "How many magnitude 6.0+ earthquakes occurred worldwide in May 2025?",
          ["Not known as of the ask date: May 2025 has not happened yet."], "abstain", date(2025, 5, 31), [],
          [date(2025, 3, 31), date(2025, 4, 30)])
    d = date(2025, 3, 15)
    assert not D.sel(d, d, 7.0)
    Q.add("abstain", f"What was the depth of the magnitude 7.0+ earthquake {loc_desc('Japan')} on {long_date(d)}?",
          [f"False premise: no magnitude 7.0+ earthquake was recorded anywhere on {long_date(d)}."], "abstain", d,
          [], [date(2025, 3, 31), date(2025, 9, 30)])
    assert not D.sel(date(2025, 6, 1), date(2025, 6, 30), None, lambda x: x.alert == "red")
    Q.add("abstain", "Where did the earthquake that received a red USGS PAGER alert in June 2025 strike?",
          ["False premise: no earthquake received a red alert in June 2025."], "abstain", date(2025, 6, 30), [],
          [date(2025, 7, 31), date(2026, 1, 31)])
    assert not D.sel(date(2025, 1, 1), date(2025, 12, 31), None, lambda x: "Greece" in x.place and x.tsunami)
    Q.add("abstain", "On what date in 2025 did an earthquake in Greece trigger the USGS tsunami flag?",
          ["False premise: no earthquake located in Greece had the tsunami flag set in 2025."], "abstain",
          date(2025, 12, 31), [], [date(2026, 1, 31), WIN_END])
    assert not D.sel(date(2026, 1, 1), WIN_END, 8.0)
    Q.add("abstain", "What was the focal depth of the magnitude 8.0+ earthquake of 2026?",
          ["False premise: no magnitude 8.0+ earthquake occurred in 2026 (through 31 October)."], "abstain",
          WIN_END, [], [date(2026, 6, 30), WIN_END])
    Q.add("abstain", "What was the strongest earthquake recorded worldwide in November 2026?",
          ["Not known as of the ask date: November 2026 has not happened yet."], "abstain", WIN_END, [], [WIN_END])
    Q.add("abstain", f"How many people were killed by the magnitude {mag_s(my.mag)} Mandalay, Myanmar earthquake of "
          f"{long_date(my.d)}?", ["Not in the record: the catalogue lists magnitude, location, depth, time, alert "
                                 "level and tsunami flag, not casualties."], "abstain", my.d, [],
          [date(2025, 4, 30), date(2026, 3, 31)])
    assert not D.sel(date(2025, 1, 1), date(2025, 12, 31), 6.0, in_("Iceland"))
    Q.add("abstain", "What was the magnitude of the magnitude 6.0+ earthquake in Iceland in 2025?",
          ["False premise: no magnitude 6.0+ earthquake was located in Iceland in 2025."], "abstain",
          date(2025, 12, 31), [], [date(2026, 2, 28), WIN_END])

    return Q.expand()


# ---------------------------------------------------------------- readme

def write_readme(D: Data, items: list[dict], qs: list[dict]) -> None:
    cats = Counter(q["category"] for q in qs)
    base = {q["base_id"]: q for q in qs}
    bcats = Counter(q["category"] if q["category"] not in ("point_recent", "point_old") else "point"
                    for q in base.values())
    (OUT / "README.md").write_text(f"""# quakes

USGS earthquake catalogue (ComCat), magnitude 4.5 and above, worldwide, {WIN_START} to {WIN_END} (UTC event
dates). Built by `uv run python -m factbase.datasets.quakes.build` (resumable: raw monthly responses are cached in
`data/raw/quakes/YYYY-MM.json`; delete a file to re-fetch it).

## Source and terms

- FDSN event web service: `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude=4.5`,
  paged by calendar month.
- USGS data are in the US public domain; credit "U.S. Geological Survey".

## Items

- {len(items)} items, one per event with `type == "earthquake"` (skipped: {dict(D.skipped)}).
- `ts` = event origin time (UTC) + 30 minutes (assumed publication lag). Items are sorted by `ts`; events in the
  last 30 minutes of 31 October 2026 have a `ts` on 1 November 2026.
- `text` is prose: time (HH:MM UTC), date, magnitude and type, location, depth, USGS id, PAGER alert, tsunami flag.
  Coordinates are only in `meta`.
- `meta` = mag, magType, place, region, lat, lon, depth_km, alert, tsunami, usgs_id, time. `region` is the part of
  `place` after the last comma; USGS "named event" places ("2025 Mandalay, Burma (Myanmar) Earthquake",
  "The 2026 Kumamoto Region, Japan Earthquake") have the year prefix and "Earthquake" suffix stripped first, so
  their region is e.g. "Burma (Myanmar)"; places without a comma ("Drake Passage") are their own region.
- Magnitudes are kept to two decimals (a few events have values like 4.55); depths to 0.1 km.

## Questions

- {len(qs)} questions, {len(base)} base questions, all `gold_source = "structured"` (computed in code from the
  cached catalogue, no LLM).
- Instances by category: {dict(sorted(cats.items()))}.
- Base questions by category: {dict(sorted(bcats.items()))}.
- Point facts are re-asked at the first month-end after the fact, +3, +6, +12 months and 31 October 2026 (inside
  the window); other questions at the first month-end after the fact, +6 months and the final day, or at the
  dates stated in the question.
- Area conditions ("in or off Japan") match any event whose USGS location string names the area
  (e.g. both "..., Japan" and "..., Japan region"); the question text says so.
- Counts and maxima use UTC event dates. Every non-abstain question's evidence items have `ts <= ask_at`;
  as-of questions assert that no qualifying event falls in the 30-minute lag at the end of the as-of day.
- Rankings, k-th largest and "most" questions assert that the relevant values are distinct (no ties). Rounded
  averages/percentages assert the raw value is not on a rounding boundary.
- Abstain questions: asked before the fact, false premises checked in code (no M7+ that day, no red alert that
  month, no M8+ in 2026, ...), or attributes not in the catalogue (casualties).

## Known issues

- The catalogue is a snapshot fetched for this build. USGS revises magnitudes, depths, alerts and places for weeks
  to months after an event, so the most recent events are the least final and a rebuild may differ.
- The 30-minute lag is a simplification; real USGS publication times vary (minutes to hours, and revisions later).
- Some magnitude 4.5+ events outside the US are catalogued with mb, which is less comparable to mww.
- Point-lookup "time" questions give HH:MM; seconds are not shown in the text.
""")


# ---------------------------------------------------------------- main

def main() -> None:
    D = Data()
    items = build_items(D)
    qs = build_questions(D)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(OUT / "questions.jsonl", "w") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    write_readme(D, items, qs)
    print(f"items: {len(items)}  questions: {len(qs)}  base: {len({q['base_id'] for q in qs})}")
    print(" by category:", dict(Counter(q["category"] for q in qs)))


if __name__ == "__main__":
    main()
