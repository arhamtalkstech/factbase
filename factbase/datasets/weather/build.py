"""Build the `weather` dataset: daily Open-Meteo archive weather for 12 cities plus a programmatic quiz.

Usage: uv run python -m factbase.datasets.weather.build
"""

from __future__ import annotations

import calendar
import json
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "weather"
OUT = ROOT / "data" / "weather"
NAME = "weather"

WIN_START = date(2024, 11, 1)
WIN_END = date(2026, 10, 31)
VARS = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "wind_speed_10m_max")
API = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={a}"
       "&end_date={b}&daily=" + ",".join(VARS) + "&timezone=UTC")

# slug: (name, country, continent, lat, lon)
CITIES = {
    "london": ("London", "United Kingdom", "Europe", 51.5072, -0.1276),
    "moscow": ("Moscow", "Russia", "Europe", 55.7558, 37.6173),
    "cairo": ("Cairo", "Egypt", "Africa", 30.0444, 31.2357),
    "lagos": ("Lagos", "Nigeria", "Africa", 6.5244, 3.3792),
    "johannesburg": ("Johannesburg", "South Africa", "Africa", -26.2041, 28.0473),
    "mumbai": ("Mumbai", "India", "Asia", 19.0760, 72.8777),
    "beijing": ("Beijing", "China", "Asia", 39.9042, 116.4074),
    "tokyo": ("Tokyo", "Japan", "Asia", 35.6762, 139.6503),
    "sydney": ("Sydney", "Australia", "Oceania", -33.8688, 151.2093),
    "new-york": ("New York", "United States", "North America", 40.7128, -74.0060),
    "mexico-city": ("Mexico City", "Mexico", "North America", 19.4326, -99.1332),
    "sao-paulo": ("São Paulo", "Brazil", "South America", -23.5505, -46.6333),
}


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


def date_gold(d: date) -> list[str]:
    return [d.isoformat(), long_date(d)]


def r1(x: float) -> str:
    """Round to one decimal, refusing values that sit on a rounding boundary."""
    f = abs(x * 10) % 1
    assert abs(f - 0.5) > 0.02, x
    return f"{round(x, 1):.1f}"


def ok1(x: float) -> bool:
    return abs(abs(x * 10) % 1 - 0.5) > 0.02


def ts_of(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 6, tzinfo=timezone.utc) + timedelta(days=1)


def eod(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


# ---------------------------------------------------------------- data

def fetch_city(slug: str) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    _, _, _, lat, lon = CITIES[slug]
    out = {}
    for a, b in [(WIN_START, date(2025, 10, 31)), (date(2025, 11, 1), WIN_END)]:
        p = RAW / f"{slug}_{a:%Y%m%d}_{b:%Y%m%d}.json"
        if not p.exists():
            url = API.format(lat=lat, lon=lon, a=a.isoformat(), b=b.isoformat())
            for attempt in range(5):
                try:
                    r = httpx.get(url, timeout=120)
                    r.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 4:
                        raise
                    time.sleep(10 * (attempt + 1))
            p.write_text(r.text)
            time.sleep(1)
        js = json.loads(p.read_text())
        dl = js["daily"]
        for i, ds in enumerate(dl["time"]):
            out[date.fromisoformat(ds)] = tuple(dl[v][i] for v in VARS)
    return out


class Data:
    def __init__(self) -> None:
        raw = {c: fetch_city(c) for c in CITIES}
        # last day on which every city has every variable
        last = WIN_START
        d = WIN_START
        while d <= WIN_END:
            if all(raw[c].get(d) and None not in raw[c][d] for c in CITIES):
                last = d
            else:
                break
            d += timedelta(days=1)
        self.last = last
        # city -> date -> (tmax, tmin, precip, wind)
        self.w: dict[str, dict[date, tuple[float, float, float, float]]] = {
            c: {d: tuple(round(float(x), 1) for x in v) for d, v in sorted(raw[c].items()) if d <= last}
            for c in CITIES
        }
        self.days = sorted(self.w["london"])

    def v(self, c: str, d: date, k: int) -> float:
        return self.w[c][d][k]

    def rng(self, c: str, a: date, b: date) -> list[tuple[date, tuple]]:
        return [(d, x) for d, x in self.w[c].items() if a <= d <= b]


TX, TN, PR, WS = range(4)
VNAME = {TX: "maximum temperature", TN: "minimum temperature", PR: "total precipitation",
         WS: "maximum wind speed at 10 m"}
VUNIT = {TX: "°C", TN: "°C", PR: "mm", WS: "km/h"}


def cname(c: str) -> str:
    return CITIES[c][0]


def iid(c: str, d: date) -> str:
    return f"{NAME}:{c}:{d.isoformat()}"


# ---------------------------------------------------------------- items

def item_text(c: str, d: date, x: tuple) -> str:
    name, country = CITIES[c][:2]
    tx, tn, pr, ws = x
    rain = "no precipitation was recorded" if pr == 0 else f"total precipitation was {pr:.1f} mm"
    return (f"Weather in {name}, {country} on {long_date(d)} ({calendar.day_name[d.weekday()]}, UTC day): "
            f"maximum temperature {tx:.1f} °C, minimum temperature {tn:.1f} °C; {rain}; maximum wind speed at "
            f"10 m was {ws:.1f} km/h. Source: Open-Meteo historical weather archive.")


def build_items(D: Data) -> list[dict]:
    items = []
    order = {c: i for i, c in enumerate(CITIES)}
    for c in CITIES:
        name, country, continent, lat, lon = CITIES[c]
        for d, x in D.w[c].items():
            if not (WIN_START <= d <= WIN_END):
                continue
            tx, tn, pr, ws = x
            items.append({
                "id": iid(c, d), "dataset": NAME, "ts": ts_of(d).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "title": f"{name} weather, {long_date(d)}: high {tx:.1f} °C, low {tn:.1f} °C, {pr:.1f} mm",
                "text": item_text(c, d, x), "source": "Open-Meteo",
                "url": API.format(lat=lat, lon=lon, a=d.isoformat(), b=d.isoformat()),
                "meta": {"city": name, "country": country, "continent": continent, "lat": lat, "lon": lon,
                         "date": d.isoformat(), "temperature_2m_max_c": tx, "temperature_2m_min_c": tn,
                         "precipitation_sum_mm": pr, "wind_speed_10m_max_kmh": ws},
            })
    items.sort(key=lambda it: (it["ts"], order[it["id"].split(":")[1]]))
    return items


# ---------------------------------------------------------------- questions

class Quiz:
    def __init__(self) -> None:
        self.base: list[dict] = []

    def add(self, category: str, question: str, gold: list[str], answer_type: str, fact_time: date,
            evidence: list[tuple[str, date]], asks: list[date], tol: float | None = None) -> None:
        assert asks, question
        self.base.append(dict(category=category, question=question, gold=list(dict.fromkeys(gold)),
                              answer_type=answer_type, fact_time=fact_time, evidence=evidence, asks=asks, tol=tol))

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
                    for _, d in b["evidence"]:
                        assert ts_of(d) <= eod(a), (b["question"], a, d)
                out.append({
                    "qid": f"{base_id}@{a.isoformat()}", "base_id": base_id, "dataset": NAME,
                    "ask_at": f"{a.isoformat()}T23:59:59Z", "question": b["question"], "gold": b["gold"],
                    "answer_type": b["answer_type"], "numeric_tolerance": b["tol"], "category": cat,
                    "fact_time": b["fact_time"].isoformat(),
                    "evidence_item_ids": [iid(c, d) for c, d in b["evidence"]], "gold_source": "structured",
                })
        return out


def t(x: float) -> str:
    return f"{x:.1f}"


def num_gold(x: float, unit: str = "") -> list[str]:
    g = [t(x), f"{x:g}"]
    if unit:
        g.append(f"{t(x)} {unit}")
    return g


def signed1(x: float) -> list[str]:
    s = r1(x)
    return [f"{float(s):+.1f}", s]


def mean(vals: list[float]) -> float:
    return sum(round(v * 10) for v in vals) / len(vals) / 10


def mean1(vals: list[float]) -> tuple[str, float]:
    m = mean(vals)
    return r1(m), m


def total1(vals: list[float]) -> float:
    return sum(round(v * 10) for v in vals) / 10


def strict_kth(pairs: list[tuple[date, float]], k: int, reverse: bool = True) -> tuple[date, float]:
    s = sorted(pairs, key=lambda p: p[1], reverse=reverse)
    vs = [p[1] for p in s[:k + 1]]
    assert len(set(vs)) == len(vs), vs
    return s[k - 1]


def longest_run(days: list[tuple[date, tuple]], pred) -> tuple[int, date, date]:
    best, runs, cur, start = None, [], 0, None
    for d, x in days:
        if pred(x):
            cur, start = (cur + 1, start or d)
            runs.append((cur, start, d))
        else:
            cur, start = 0, None
    lens = sorted(runs, key=lambda r: -r[0])
    top = lens[0]
    # the best run must be strictly longer than any other run
    others = [r for r in runs if r[1] != top[1]]
    assert not others or max(r[0] for r in others) < top[0], top
    return top


def mon(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), month_end(date(y, m, 1))


def mlabel(y: int, m: int) -> str:
    return f"{calendar.month_name[m]} {y}"


def build_questions(D: Data) -> list[dict]:
    Q = Quiz()
    cities = list(CITIES)

    def vals(c, a, b, k):
        return [x[k] for _, x in D.rng(c, a, b)]

    def ev(c, a, b):
        return [(c, d) for d, _ in D.rng(c, a, b)]

    def visible(c, a, k, start, ask):
        """(date, value) pairs from `start` that are published by the end of `ask`."""
        return [(d, x[k]) for d, x in D.rng(c, start, ask) if ts_of(d) <= eod(ask)]

    # --- point lookups
    var_cycle = [TX, PR, TN, WS]
    anchor, n = date(2024, 11, 12), 0
    while anchor <= date(2026, 10, 10):
        c, k = cities[n % 12], var_cycle[n % 4]
        d = anchor
        if k == PR:
            d = max(D.rng(c, anchor, anchor + timedelta(days=14)), key=lambda p: p[1][PR])[0]
            assert D.v(c, d, PR) > 0
        v = D.v(c, d, k)
        Q.add("point", f"What was the daily {VNAME[k]} in {cname(c)} on {long_date(d)} ({VUNIT[k]}, UTC day, "
              f"Open-Meteo archive)?", num_gold(v, VUNIT[k]), "number", d, [(c, d)], sched_point(d), 0.001)
        n += 1
        anchor += timedelta(days=47)

    # --- as_of_state
    a = date(2026, 4, 30)
    pairs = visible("sydney", a, TX, date(2026, 1, 1), a)
    dmax, vmax = strict_kth(pairs, 1)
    Q.add("as_of_state", f"As of {long_date(a)}, what was the highest daily maximum temperature recorded in Sydney so "
          f"far in 2026 (°C), and on what date?", [f"{t(vmax)} °C on {long_date(dmax)}", t(vmax)], "text", a,
          [("sydney", dmax)], [a, WIN_END])
    for a in [date(2025, 9, 15), date(2026, 7, 10)]:
        pairs = visible("cairo", a, PR, WIN_START, a)
        dl = [d for d, v in pairs if v > 0.5][-1]
        assert D.v("cairo", a, PR) <= 0.5
        Q.add("as_of_state", f"As of {long_date(a)}, on what date had Cairo most recently recorded more than 0.5 mm "
              f"of daily precipitation?", date_gold(dl), "date", dl, [("cairo", dl)], [a])
    a = date(2026, 2, 20)
    pairs = visible("moscow", a, TN, date(2025, 12, 1), a)
    dmin, vmin = strict_kth(pairs, 1, reverse=False)
    assert D.v("moscow", a, TN) > vmin
    Q.add("as_of_state", f"As of {long_date(a)}, what was the lowest daily minimum temperature recorded in Moscow "
          f"since 1 December 2025 (°C)?", num_gold(vmin, "°C"), "number", dmin, [("moscow", dmin)], [a], 0.001)
    a = date(2025, 11, 18)
    pairs = visible("mumbai", a, TX, WIN_START, a)
    dl = [d for d, v in pairs if v >= 35.0][-1]
    assert D.v("mumbai", a, TX) < 35.0
    Q.add("as_of_state", f"As of {long_date(a)}, what was the most recent date on which Mumbai's daily maximum "
          f"temperature reached 35.0 °C or more?", date_gold(dl), "date", dl, [("mumbai", dl)], [a])
    a = date(2026, 7, 20)
    best = {c: max(visible(c, a, WS, date(2026, 1, 1), a), key=lambda p: p[1]) for c in cities}
    top = sorted(best, key=lambda c: -best[c][1])
    assert best[top[0]][1] > best[top[1]][1]
    assert D.v(top[0], a, WS) < best[top[0]][1]
    assert sum(1 for _, v in visible(top[0], a, WS, date(2026, 1, 1), a) if v == best[top[0]][1]) == 1
    Q.add("as_of_state", f"As of {long_date(a)}, which of the 12 tracked cities had recorded the highest daily "
          f"maximum wind speed so far in 2026, and what was it (km/h)?",
          [f"{cname(top[0])} ({t(best[top[0]][1])} km/h on {long_date(best[top[0]][0])})", cname(top[0])], "text",
          a, [(c, best[c][0]) for c in best], [a])
    a = date(2025, 3, 20)
    pairs = visible("new-york", a, TN, date(2025, 1, 1), a)
    n0 = sum(1 for _, v in pairs if v < 0)
    last = pairs[-1][0]
    Q.add("as_of_state", f"As of {long_date(a)} (latest reported day {long_date(last)}), on how many days of 2025 so "
          f"far had New York's daily minimum temperature been below 0 °C?", [str(n0)], "number", last,
          [("new-york", d) for d, v in pairs if v < 0], [a], 0.0)
    a = date(2026, 9, 25)
    pairs = visible("london", a, PR, date(2026, 8, 1), a)
    run = 0
    for _, v in reversed(pairs):
        if v == 0:
            run += 1
        else:
            break
    last = pairs[-1][0]
    if run == 0:
        a = None
    Q.add("as_of_state", f"As of {long_date(date(2026, 9, 25))}, the latest reported day being {long_date(last)}: "
          f"for how many consecutive days, ending on {long_date(last)}, had London recorded exactly 0.0 mm of "
          f"precipitation? (0 if it rained on {long_date(last)})", [str(run)], "number", last,
          [("london", d) for d, _ in pairs[-max(run, 1) - 1:]], [date(2026, 9, 25)], 0.0)

    # --- aggregate
    a, b = mon(2025, 8)
    s, _ = mean1(vals("london", a, b, TX))
    Q.add("aggregate", "What was London's average daily maximum temperature in August 2025, in °C rounded to one "
          "decimal place?", [s], "number", b, ev("london", a, b), sched_other(b), 0.003)
    a, b = mon(2025, 7)
    tot = total1(vals("mumbai", a, b, PR))
    Q.add("aggregate", "What was Mumbai's total precipitation in July 2025 (sum of the daily totals, mm, one "
          "decimal)?", [t(tot)], "number", b, ev("mumbai", a, b), sched_other(b), 0.002)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    ln, s0, e0 = longest_run(D.rng("london", a, b), lambda x: x[PR] > 1.0)
    Q.add("aggregate", "In 2025, what was the longest streak of consecutive days on which London recorded more "
          "than 1.0 mm of precipitation each day, and when did it start?",
          [f"{ln} days (from {long_date(s0)} to {long_date(e0)})", str(ln)], "text", b,
          [("london", s0 + timedelta(days=i)) for i in range(ln)], sched_other(b))
    a, b = date(2024, 11, 1), date(2025, 3, 31)
    ln, s0, e0 = longest_run(D.rng("lagos", a, b), lambda x: x[PR] == 0)
    Q.add("aggregate", "Between 1 November 2024 and 31 March 2025, what was the longest run of consecutive days on "
          "which Lagos recorded exactly 0.0 mm of precipitation?", [str(ln), f"{ln} days"], "number", b,
          [("lagos", s0 + timedelta(days=i)) for i in range(ln)], sched_other(b), 0.0)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    hot = [(c_, d) for c_ in ["cairo"] for d, x in D.rng("cairo", a, b) if x[TX] >= 35.0]
    Q.add("aggregate", "On how many days in 2025 did Cairo's daily maximum temperature reach 35.0 °C or higher?",
          [str(len(hot))], "number", b, hot, sched_other(b), 0.0)
    dmax, vmax = strict_kth([(d, x[TX]) for d, x in D.rng("tokyo", a, b)], 1)
    Q.add("aggregate", "On what date in 2025 did Tokyo record its highest daily maximum temperature of the year?",
          date_gold(dmax), "date", b, [("tokyo", dmax)], sched_other(b))
    d2, v2 = strict_kth([(d, x[TX]) for d, x in D.rng("new-york", a, b)], 2)
    Q.add("aggregate", "What was the second-highest daily maximum temperature recorded in New York in 2025 (°C)?",
          num_gold(v2, "°C"), "number", b, [("new-york", d2)], sched_other(b), 0.001)
    a, b = mon(2026, 4)
    grp = ["lagos", "mumbai", "sao-paulo", "mexico-city"]
    means = {c: mean(vals(c, a, b, TX)) for c in grp}
    rk = sorted(grp, key=lambda c: -means[c])
    assert all(means[rk[i]] - means[rk[i + 1]] > 0.05 for i in range(3)), means
    Q.add("aggregate", "Rank Lagos, Mumbai, São Paulo and Mexico City by their average daily maximum temperature in "
          "April 2026, warmest first.", [" > ".join(cname(c) for c in rk), ", ".join(cname(c) for c in rk)], "text",
          b, [x for c in grp for x in ev(c, a, b)], sched_other(b))
    a, b = mon(2025, 8)
    tots = {c: total1(vals(c, a, b, PR)) for c in cities}
    rk = sorted(cities, key=lambda c: -tots[c])
    assert tots[rk[0]] > tots[rk[1]]
    Q.add("aggregate", "Which of the 12 tracked cities (London, Moscow, Cairo, Lagos, Johannesburg, Mumbai, Beijing, "
          "Tokyo, Sydney, New York, Mexico City, São Paulo) had the highest total precipitation in August 2025, and "
          "how much (mm)?", [f"{cname(rk[0])} ({t(tots[rk[0]])} mm)", cname(rk[0])], "text", b,
          [x for c in cities for x in ev(c, a, b)], sched_other(b))
    a, b = date(2025, 12, 1), date(2026, 2, 28)
    fr = [("beijing", d) for d, x in D.rng("beijing", a, b) if x[TN] < 0]
    Q.add("aggregate", "How many days between 1 December 2025 and 28 February 2026 had a daily minimum temperature "
          "below 0 °C in Beijing?", [str(len(fr))], "number", b, fr, sched_other(b), 0.0)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    dm, vm = strict_kth([(d, x[WS]) for d, x in D.rng("sydney", a, b)], 1)
    Q.add("aggregate", "What was the highest daily maximum wind speed recorded in Sydney in 2025 (km/h), and on what "
          "date?", [f"{t(vm)} km/h on {long_date(dm)}", t(vm)], "text", b, [("sydney", dm)], sched_other(b))
    a, b = date(2024, 12, 1), date(2025, 2, 28)
    dm, vm = strict_kth([(d, x[TN]) for d, x in D.rng("moscow", a, b)], 1, reverse=False)
    Q.add("aggregate", "What was the lowest daily minimum temperature in Moscow in winter 2024-25 (1 December 2024 "
          "to 28 February 2025), and on what date?", [f"{t(vm)} °C on {long_date(dm)}", t(vm)], "text", b,
          [("moscow", dm)], sched_other(b))
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    best = {c: strict_kth([(d, x[PR]) for d, x in D.rng(c, a, b)], 1) if c == "mumbai" else
            max(((d, x[PR]) for d, x in D.rng(c, a, b)), key=lambda p: p[1]) for c in cities}
    rk = sorted(cities, key=lambda c: -best[c][1])
    assert best[rk[0]][1] > best[rk[1]][1]
    assert [d for d, x in D.rng(rk[0], a, b) if x[PR] == best[rk[0]][1]] == [best[rk[0]][0]]
    Q.add("aggregate", "Across the 12 tracked cities, which city recorded the single wettest day of 2025 (highest "
          "daily precipitation total), and on what date?",
          [f"{cname(rk[0])}, {long_date(best[rk[0]][0])} ({t(best[rk[0]][1])} mm)", cname(rk[0])], "text", b,
          [(c, best[c][0]) for c in cities], sched_other(b))
    cold = [("johannesburg", d) for d, x in D.rng("johannesburg", a, b) if x[TN] < 2.0]
    Q.add("aggregate", "On how many days in 2025 did Johannesburg's daily minimum temperature fall below 2.0 °C?",
          [str(len(cold))], "number", b, cold, sched_other(b), 0.0)
    wet = [m for m in range(1, 13) if total1(vals("london", *mon(2025, m), PR)) > 60.0]
    assert all(abs(total1(vals("london", *mon(2025, m), PR)) - 60.0) > 0.5 for m in range(1, 13))
    Q.add("aggregate", "In how many calendar months of 2025 did London's total precipitation exceed 60 mm?",
          [str(len(wet))], "number", b, ev("london", a, b), sched_other(b), 0.0)
    m = next(m for m in (3, 4, 2, 5) if ok1(sum(round((x[TX] - x[TN]) * 10) for _, x in
                                              D.rng("mexico-city", *mon(2026, m))) / len(D.rng("mexico-city", *mon(2026, m))) / 10))
    a, b = mon(2026, m)
    s, _ = mean1([x[TX] - x[TN] for _, x in D.rng("mexico-city", a, b)])
    Q.add("aggregate", f"What was Mexico City's average daily temperature range (daily maximum minus daily minimum) in "
          f"{mlabel(2026, m)}, in °C rounded to one decimal?", [s], "number", b, ev("mexico-city", a, b), sched_other(b),
          0.003)
    a, b = mon(2026, 7)
    tn = [("tokyo", d) for d, x in D.rng("tokyo", a, b) if x[TN] >= 25.0]
    Q.add("aggregate", "How many nights in July 2026 did Tokyo's daily minimum temperature stay at or above 25.0 °C?",
          [str(len(tn))], "number", b, tn, sched_other(b), 0.0)
    a, b = date(2026, 1, 1), date(2026, 3, 31)
    d3, v3 = strict_kth([(d, x[PR]) for d, x in D.rng("sao-paulo", a, b)], 3)
    Q.add("aggregate", "What was the third-highest daily precipitation total in São Paulo between 1 January and 31 "
          "March 2026 (mm)?", num_gold(v3, "mm"), "number", b, [("sao-paulo", d3)], sched_other(b), 0.001)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    h40 = [c for c in cities if max(vals(c, a, b, TX)) >= 40.0]
    Q.add("aggregate", "How many of the 12 tracked cities recorded a daily maximum temperature of 40.0 °C or more at "
          "least once in 2025, and which?", [f"{len(h40)}: {', '.join(cname(c) for c in h40)}", str(len(h40))],
          "text", b, [(c, max(D.rng(c, a, b), key=lambda p: p[1][TX])[0]) for c in h40], sched_other(b))
    tot = total1(vals("cairo", a, b, PR))
    Q.add("aggregate", "What was Cairo's total precipitation for the whole of 2025 (mm, one decimal)?", [t(tot)],
          "number", b, [("cairo", d) for d, x in D.rng("cairo", a, b) if x[PR] > 0], sched_other(b), 0.01)

    # --- change
    def mean_change(c, k, y1, y2, m, label):
        m1, m2 = mean(vals(c, *mon(y1, m), k)), mean(vals(c, *mon(y2, m), k))
        b = mon(y2, m)[1]
        Q.add("change", f"How did {cname(c)}'s average daily {VNAME[k]} in {mlabel(y2, m)} compare with "
              f"{mlabel(y1, m)}? Give {y2} minus {y1} in °C, one decimal (negative if {label}).",
              signed1(m2 - m1), "number", b, ev(c, *mon(y1, m)) + ev(c, *mon(y2, m)), sched_other(b), 0.003)

    mean_change("london", TX, 2025, 2026, 7, "cooler")
    mean_change("sydney", TN, 2025, 2026, 7, "colder")
    mean_change("moscow", TN, 2024, 2025, 12, "colder")
    p1, p2 = total1(vals("mumbai", *mon(2025, 6), PR)), total1(vals("mumbai", *mon(2026, 6), PR))
    Q.add("change", "By how many millimetres did Mumbai's total June precipitation change from June 2025 to June "
          "2026 (2026 minus 2025, one decimal)?", [f"{p2 - p1:+.1f}", f"{p2 - p1:.1f}"], "number",
          date(2026, 6, 30), ev("mumbai", *mon(2025, 6)) + ev("mumbai", *mon(2026, 6)), sched_other(date(2026, 6, 30)),
          0.002)
    f1 = sum(1 for v in vals("moscow", *mon(2025, 1), TX) if v < 0)
    f2 = sum(1 for v in vals("moscow", *mon(2026, 1), TX) if v < 0)
    assert f1 != f2
    Q.add("change", "How did the number of 'ice days' (daily maximum temperature below 0 °C) in Moscow change from "
          "January 2025 to January 2026? Give the January 2026 count minus the January 2025 count.",
          [f"{f2 - f1:+d}", str(f2 - f1)], "number", date(2026, 1, 31),
          ev("moscow", *mon(2025, 1)) + ev("moscow", *mon(2026, 1)), sched_other(date(2026, 1, 31)), 0.0)
    d1, d2 = date(2025, 8, 1), date(2026, 2, 1)
    v1, v2 = D.v("tokyo", d1, TX), D.v("tokyo", d2, TX)
    Q.add("change", f"By how much did Tokyo's daily maximum temperature on {long_date(d2)} differ from that on "
          f"{long_date(d1)}? Give the later minus the earlier, °C, one decimal.", [f"{v2 - v1:+.1f}", f"{v2 - v1:.1f}"],
          "number", d2, [("tokyo", d1), ("tokyo", d2)], sched_other(d2), 0.002)
    h1 = max(vals("cairo", date(2025, 1, 1), date(2025, 12, 31), TX))
    h2 = max(vals("cairo", date(2026, 1, 1), date(2026, 9, 30), TX))
    Q.add("change", "How did Cairo's hottest daily maximum temperature of January-September 2026 compare with its "
          "hottest of calendar year 2025? Give 2026 minus 2025, °C, one decimal.", [f"{h2 - h1:+.1f}", f"{h2 - h1:.1f}"],
          "number", date(2026, 9, 30),
          [("cairo", d) for d, x in D.rng("cairo", date(2025, 1, 1), date(2026, 9, 30)) if x[TX] in (h1, h2)],
          [date(2026, 9, 30), WIN_END], 0.002)
    w1 = sum(1 for v in vals("new-york", date(2025, 1, 1), date(2025, 3, 31), PR) if v > 1.0)
    w2 = sum(1 for v in vals("new-york", date(2026, 1, 1), date(2026, 3, 31), PR) if v > 1.0)
    Q.add("change", "How did the number of days with more than 1.0 mm of precipitation in New York change from Q1 2025 "
          "to Q1 2026 (January to March)? Give the 2026 count minus the 2025 count.",
          list(dict.fromkeys([f"{w2 - w1:+d}", str(w2 - w1)])), "number", date(2026, 3, 31),
          ev("new-york", date(2025, 1, 1), date(2025, 3, 31)) + ev("new-york", date(2026, 1, 1), date(2026, 3, 31)),
          sched_other(date(2026, 3, 31)), 0.0)

    # --- ordering
    def first_day(c, start, pred, end=WIN_END):
        return next(d for d, x in D.rng(c, start, end) if pred(x))

    def last_day(c, start, end, pred):
        return [d for d, x in D.rng(c, start, end) if pred(x)][-1]

    d = first_day("london", date(2025, 3, 1), lambda x: x[TX] >= 25.0)
    Q.add("ordering", "On or after 1 March 2025, on what date did London's daily maximum temperature first reach "
          "25.0 °C?", date_gold(d), "date", d, [("london", d)], sched_other(d))
    ny = first_day("new-york", date(2025, 10, 1), lambda x: x[TN] < -5.0)
    bj = first_day("beijing", date(2025, 10, 1), lambda x: x[TX] < 0)
    assert abs((ny - bj).days) >= 3
    fst = ("New York's first minimum below -5.0 °C", ny) if ny < bj else ("Beijing's first sub-zero maximum", bj)
    Q.add("ordering", "Counting from 1 October 2025, which happened first: New York recording a daily minimum below "
          "-5.0 °C, or Beijing recording a daily maximum below 0 °C (a day that stayed below freezing)?",
          [f"{fst[0]} came first ({long_date(fst[1])})", "New York" if ny < bj else "Beijing"], "text", max(ny, bj),
          [("new-york", ny), ("beijing", bj)], sched_other(max(ny, bj)))
    for c in ("moscow", "new-york"):
        lf = last_day(c, date(2025, 1, 1), date(2025, 6, 30), lambda x: x[TN] < 0)
        ff = first_day(c, date(2025, 7, 1), lambda x: x[TN] < 0)
        Q.add("ordering", f"In 2025, how many days passed between {cname(c)}'s last spring day with a minimum below "
              f"0 °C (before 1 July) and its first autumn day with a minimum below 0 °C (after 1 July)?",
              [str((ff - lf).days)], "number", ff, [(c, lf), (c, ff)], sched_other(ff), 0.0)
    trio = ["london", "new-york", "beijing"]
    fd = {c: first_day(c, date(2025, 1, 1), lambda x: x[TX] >= 30.0) for c in trio}
    assert len(set(fd.values())) == 3
    srt = sorted(trio, key=lambda c: fd[c])
    Q.add("ordering", "Order London, New York and Beijing by the date on which each first reached a daily maximum of "
          "30.0 °C or more in 2025, earliest first.", [" < ".join(cname(c) for c in srt),
                                                       ", ".join(cname(c) for c in srt)], "text", fd[srt[-1]],
          [(c, fd[c]) for c in trio], sched_other(fd[srt[-1]]))
    d = first_day("mumbai", date(2026, 1, 1), lambda x: x[PR] > 20.0)
    Q.add("ordering", "What was the first date in 2026 on which Mumbai recorded more than 20.0 mm of precipitation in "
          "a day?", date_gold(d), "date", d, [("mumbai", d)], sched_other(d))
    d = last_day("tokyo", date(2025, 1, 1), date(2025, 12, 31), lambda x: x[TX] >= 30.0)
    Q.add("ordering", "What was the last date in 2025 on which Tokyo's daily maximum temperature reached 30.0 °C or "
          "more?", date_gold(d), "date", date(2025, 12, 31), [("tokyo", d)], sched_other(date(2025, 12, 31)))
    sy = first_day("sydney", date(2026, 3, 1), lambda x: x[TN] < 8.0)
    jb = first_day("johannesburg", date(2026, 3, 1), lambda x: x[TN] < 3.0)
    assert abs((sy - jb).days) >= 3
    Q.add("ordering", "Counting from 1 March 2026, which came first: Sydney's first daily minimum below 8.0 °C or "
          "Johannesburg's first daily minimum below 3.0 °C? How many days apart were they?",
          [f"{'Sydney' if sy < jb else 'Johannesburg'}, {abs((jb - sy).days)} days earlier",
           "Sydney" if sy < jb else "Johannesburg"], "text", max(sy, jb), [("sydney", sy), ("johannesburg", jb)],
          sched_other(max(sy, jb)))
    d = first_day("moscow", date(2025, 8, 1), lambda x: x[TX] < 10.0)
    Q.add("ordering", "After 1 August 2025, on what date did Moscow first have a daily maximum temperature below "
          "10.0 °C?", date_gold(d), "date", d, [("moscow", d)], sched_other(d))
    grp = ["beijing", "tokyo", "new-york", "cairo"]
    fd = {c: first_day(c, date(2026, 1, 1), lambda x: x[TX] >= 35.0) for c in grp}
    assert len(set(fd.values())) == 4
    srt = sorted(grp, key=lambda c: fd[c])
    Q.add("ordering", "In 2026, which of Beijing, Tokyo, New York and Cairo was the first to record a daily maximum "
          "temperature of 35.0 °C or more, and which was the last of the four?",
          [f"first {cname(srt[0])} ({long_date(fd[srt[0]])}), last {cname(srt[-1])} ({long_date(fd[srt[-1]])})"],
          "text", fd[srt[-1]], [(c, fd[c]) for c in grp], sched_other(fd[srt[-1]]))

    # --- multi_hop
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    dc, _ = strict_kth([(d, x[TX]) for d, x in D.rng("cairo", a, b)], 1)
    Q.add("multi_hop", "What was London's daily maximum temperature on the day in 2025 when Cairo recorded its highest "
          "daily maximum of the year (°C)?", num_gold(D.v("london", dc, TX), "°C"), "number", b,
          [("cairo", dc), ("london", dc)], sched_other(b), 0.001)
    a, b = mon(2026, 1)
    m1, m2 = mean(vals("sydney", a, b, TX)), mean(vals("johannesburg", a, b, TX))
    assert abs(m1 - m2) > 0.1
    w = "Sydney" if m1 > m2 else "Johannesburg"
    Q.add("multi_hop", "Which city was warmer on average in January 2026, Sydney or Johannesburg, judged by the mean "
          "daily maximum temperature, and by how much (°C, one decimal)?", [f"{w}, by {r1(abs(m1 - m2))} °C", w],
          "text", b, ev("sydney", a, b) + ev("johannesburg", a, b), sched_other(b))
    d = date(2025, 12, 21)
    v = D.v("sydney", d, TX) - D.v("tokyo", d, TX)
    Q.add("multi_hop", f"On {long_date(d)}, how much higher was Sydney's daily maximum temperature than Tokyo's (°C, "
          f"one decimal)?", [t(v)], "number", d, [("sydney", d), ("tokyo", d)], sched_point(d), 0.002)
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    dw, _ = strict_kth([(d, x[PR]) for d, x in D.rng("mumbai", a, b)], 1)
    Q.add("multi_hop", "What was Mumbai's maximum wind speed (km/h) on its wettest day of 2025?",
          num_gold(D.v("mumbai", dw, WS), "km/h"), "number", b, [("mumbai", dw)], sched_other(b), 0.001)
    a, b = date(2025, 12, 1), date(2026, 2, 28)
    dm, _ = strict_kth([(d, x[TN]) for d, x in D.rng("moscow", a, b)], 1, reverse=False)
    Q.add("multi_hop", "On the date of Moscow's lowest daily minimum temperature in winter 2025-26 (1 December 2025 to "
          "28 February 2026), what was New York's daily minimum temperature (°C)?",
          num_gold(D.v("new-york", dm, TN), "°C"), "number", b, [("moscow", dm), ("new-york", dm)], sched_other(b),
          0.001)
    a, b = mon(2025, 7)
    nw = [d for d, x in D.rng("london", a, b) if x[TX] > D.v("moscow", d, TX)]
    assert all(D.v("london", d, TX) != D.v("moscow", d, TX) for d, _ in D.rng("london", a, b))
    Q.add("multi_hop", "On how many days in July 2025 was London's daily maximum temperature higher than Moscow's?",
          [str(len(nw))], "number", b, ev("london", a, b) + ev("moscow", a, b), sched_other(b), 0.0)
    d = date(2026, 3, 15)
    rngs = {c: D.v(c, d, TX) - D.v(c, d, TN) for c in cities}
    rk = sorted(cities, key=lambda c: -rngs[c])
    assert rngs[rk[0]] - rngs[rk[1]] > 0.05
    Q.add("multi_hop", f"On {long_date(d)}, which of the 12 tracked cities had the largest daily temperature range "
          f"(maximum minus minimum), and how large was it (°C)?", [f"{cname(rk[0])} ({t(rngs[rk[0]])} °C)",
                                                                   cname(rk[0])], "text", d,
          [(c, d) for c in cities], sched_point(d)[:3])
    a, b = date(2025, 1, 1), date(2025, 12, 31)
    nd = [d for d, x in D.rng("lagos", a, b) if x[TN] > D.v("cairo", d, TX)]
    Q.add("multi_hop", "On how many days in 2025 was Lagos's daily minimum temperature higher than Cairo's daily "
          "maximum temperature on the same day?", [str(len(nd))], "number", b,
          [(c, d) for d in nd for c in ("lagos", "cairo")], sched_other(b), 0.0)

    # --- abstain
    d = date(2025, 6, 14)
    Q.add("abstain", f"What was the daily maximum temperature in London on {long_date(d)}?",
          [f"Not known: {long_date(d)} is after the ask date."], "abstain", d, [], [date(2025, 4, 30), date(2025, 5, 31)])
    Q.add("abstain", "What was Mumbai's total precipitation in August 2026?",
          ["Not known: August 2026 is not over (or has not started) at the ask date."], "abstain", date(2026, 8, 31),
          [], [date(2026, 6, 30), date(2026, 7, 31)])
    d = date(2025, 9, 9)
    Q.add("abstain", f"What was the daily maximum temperature in Paris on {long_date(d)}?",
          ["Not in the record: Paris is not one of the 12 tracked cities."], "abstain", d, [],
          [date(2025, 9, 30), date(2026, 3, 31)])
    d = date(2026, 1, 12)
    Q.add("abstain", f"What was the relative humidity in Tokyo on {long_date(d)}?",
          ["Not in the record: only daily maximum/minimum temperature, precipitation and maximum wind speed are "
           "tracked."], "abstain", d, [], [date(2026, 1, 31), date(2026, 7, 31)])
    assert max(vals("london", WIN_START, WIN_END, TX)) < 40.0
    Q.add("abstain", "What was London's minimum temperature on the day in 2025 when its maximum reached 40 °C?",
          ["False premise: London never reached 40 °C in 2025 (or anywhere in the record)."], "abstain",
          date(2025, 12, 31), [], [date(2025, 8, 31), date(2026, 1, 31)])
    assert max(vals("cairo", date(2025, 1, 1), date(2025, 12, 31), PR)) <= 20.0
    Q.add("abstain", "On what date in 2025 did Cairo record more than 20 mm of rain in a single day?",
          ["False premise: Cairo never recorded more than 20 mm in a day in 2025."], "abstain", date(2025, 12, 31),
          [], [date(2026, 1, 31), WIN_END])
    assert min(vals("lagos", *mon(2026, 1), TN)) >= 15.0
    Q.add("abstain", "On which day in January 2026 did Lagos's daily minimum temperature fall below 15 °C?",
          ["False premise: Lagos's daily minimum never fell below 15 °C in January 2026."], "abstain",
          date(2026, 1, 31), [], [date(2026, 2, 28), WIN_END])
    d = date(2025, 12, 3)
    Q.add("abstain", f"What was the maximum wind speed in Johannesburg on {long_date(d)}?",
          [f"Not known: {long_date(d)} is after the ask date."], "abstain", d, [],
          [date(2025, 10, 31), date(2025, 11, 30)])
    d = date(2026, 10, 31)
    Q.add("abstain", f"What was the daily maximum temperature in New York on {long_date(d)}?",
          [f"Not yet known: the {long_date(d)} reading is published the following morning (06:00 UTC)."], "abstain",
          d, [], [d])
    d = date(2026, 5, 20)
    Q.add("abstain", f"How much rain fell in Sydney on {long_date(d)}?",
          [f"Not yet known: the {long_date(d)} reading is published the following morning (06:00 UTC)."], "abstain",
          d, [], [d])

    return Q.expand()


# ---------------------------------------------------------------- readme

def write_readme(D: Data, items: list[dict], qs: list[dict]) -> None:
    cats = Counter(q["category"] for q in qs)
    base = {q["base_id"]: q for q in qs}
    bcats = Counter(q["category"] if q["category"] not in ("point_recent", "point_old") else "point"
                    for q in base.values())
    rows = "\n".join(f"| {v[0]} | {v[1]} | {v[2]} | {v[3]}, {v[4]} | `{k}` |" for k, v in CITIES.items())
    (OUT / "README.md").write_text(f"""# weather

Daily weather for 12 cities on six continents from the Open-Meteo historical weather archive, {WIN_START} to
{D.last} (the archive had complete data for every city through {D.last} when built). Built by
`uv run python -m factbase.datasets.weather.build` (resumable: raw responses are cached per city and year in
`data/raw/weather/`; delete a file to re-fetch it).

## Source and terms

- `https://archive-api.open-meteo.com/v1/archive?...&daily={','.join(VARS)}&timezone=UTC`
  (ERA5 / ERA5-Land reanalysis blended with operational models for the most recent days).
- Open-Meteo data are CC BY 4.0 ("Weather data by Open-Meteo.com"); free non-commercial API use.

| City | Country | Continent | Lat, lon | id slug |
|---|---|---|---|---|
{rows}

## Items

- {len(items)} items, one per city per UTC day; id `weather:<slug>:<YYYY-MM-DD>`.
- `ts` = the next day at 06:00 UTC (daily values are complete only after the UTC day ends). The 31 October 2026
  items therefore have `ts` 2026-11-01T06:00:00Z, after the last ask date.
- Text: prose with max/min temperature (°C), precipitation sum (mm; "no precipitation" when 0.0) and max 10 m wind
  speed (km/h). Values are as returned (one decimal). Grid-cell values for the given coordinates, not station data.
- `meta`: city, country, continent, lat, lon, date and the four values.

## Questions

- {len(qs)} questions, {len(base)} base questions, all `gold_source = "structured"` (computed in code from the cached
  archive responses, no LLM).
- Instances by category: {dict(sorted(cats.items()))}.
- Base questions by category: {dict(sorted(bcats.items()))}.
- Point facts are re-asked at the first month-end after the fact, +3, +6, +12 months and 31 October 2026 (inside
  the window); others at the first month-end after the fact, +6 months and the final day, or the dates stated.
- As-of questions only use days already published at the ask time (day D is visible from D+1 06:00 UTC) and assert
  the answer would not change if the ask-day's own value were included.
- Averages are of the daily values, rounded to one decimal; the builder asserts no average sits on a rounding
  boundary. Sums are exact in tenths of a mm. Thresholds are stated with their comparison ("more than 1.0 mm",
  "35.0 °C or more").
- Maxima, minima, k-th values, rankings and "longest streak" assert uniqueness (no ties).
- Abstain: asked before the fact, the ask-day's own value (not yet published), untracked cities or variables, and
  false premises checked in code.

## Known issues

- Archive values for the last few days before a build come from operational model analyses and may be revised
  when ERA5 catches up; a rebuild can shift recent values slightly.
- Reanalysis grid cells (about 9-25 km) smooth extremes; values differ from airport station records.
- Precipitation "0.0" can hide trace amounts below 0.05 mm.
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
    print(f"items: {len(items)}  last day: {D.last}  questions: {len(qs)}  base: {len({q['base_id'] for q in qs})}")
    print(" by category:", dict(Counter(q["category"] for q in qs)))


if __name__ == "__main__":
    main()
