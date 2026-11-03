"""Football dataset: top-flight league results from openfootball plus a programmatic quiz.

Run: uv run python -m factbase.datasets.football.build
"""

from __future__ import annotations

import calendar
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

NAME = "football"
ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / NAME
OUT = ROOT / "data" / NAME
URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league}.json"

# code -> (long name, short name, timezone of kickoff times in the source)
LEAGUES = {
    "en.1": ("English Premier League", "Premier League", "Europe/London"),
    "de.1": ("German Bundesliga", "Bundesliga", "Europe/Berlin"),
    "fr.1": ("French Ligue 1", "Ligue 1", "Europe/Paris"),
}
SEASONS = ["2024-25", "2025-26", "2026-27"]
COMPLETED = ["2024-25", "2025-26"]
CAP = date(2026, 10, 31)
SEED = 20241101

MANUAL_ALIASES = {
    "Manchester United FC": ["Manchester United", "Man United", "Man Utd"],
    "Manchester City FC": ["Manchester City", "Man City"],
    "Tottenham Hotspur FC": ["Tottenham Hotspur", "Tottenham", "Spurs"],
    "Wolverhampton Wanderers FC": ["Wolverhampton Wanderers", "Wolverhampton", "Wolves"],
    "Brighton & Hove Albion FC": ["Brighton & Hove Albion", "Brighton"],
    "Nottingham Forest FC": ["Nottingham Forest", "Forest"],
    "Newcastle United FC": ["Newcastle United", "Newcastle"],
    "West Ham United FC": ["West Ham United", "West Ham"],
    "Leicester City FC": ["Leicester City", "Leicester"],
    "Ipswich Town FC": ["Ipswich Town", "Ipswich"],
    "Leeds United FC": ["Leeds United", "Leeds"],
    "Coventry City FC": ["Coventry City", "Coventry"],
    "Hull City AFC": ["Hull City", "Hull"],
    "AFC Bournemouth": ["Bournemouth"],
    "Sunderland AFC": ["Sunderland"],
    "Paris Saint-Germain FC": ["Paris Saint-Germain", "PSG", "Paris SG"],
    "FC Bayern München": ["Bayern Munich", "Bayern München", "Bayern"],
    "Bayer 04 Leverkusen": ["Bayer Leverkusen", "Leverkusen"],
    "Borussia Dortmund": ["Dortmund", "BVB"],
    "Borussia Mönchengladbach": ["Mönchengladbach", "Monchengladbach", "Gladbach"],
    "Eintracht Frankfurt": ["Frankfurt"],
    "VfB Stuttgart": ["Stuttgart"],
    "RB Leipzig": ["Leipzig"],
    "SC Freiburg": ["Freiburg"],
    "VfL Wolfsburg": ["Wolfsburg"],
    "SV Werder Bremen": ["Werder Bremen", "Bremen"],
    "TSG 1899 Hoffenheim": ["Hoffenheim", "TSG Hoffenheim"],
    "1. FSV Mainz 05": ["Mainz 05", "Mainz"],
    "1. FC Union Berlin": ["Union Berlin"],
    "1. FC Heidenheim 1846": ["Heidenheim"],
    "1. FC Köln": ["FC Köln", "Köln", "Cologne"],
    "FC Augsburg": ["Augsburg"],
    "FC St. Pauli 1910": ["St. Pauli", "FC St. Pauli"],
    "VfL Bochum 1848": ["VfL Bochum", "Bochum"],
    "Holstein Kiel": ["Kiel"],
    "Hamburger SV": ["Hamburg", "HSV"],
    "FC Schalke 04": ["Schalke 04", "Schalke"],
    "SC Paderborn 07": ["Paderborn"],
    "SV 07 Elversberg": ["Elversberg", "SV Elversberg"],
    "Olympique de Marseille": ["Marseille", "OM"],
    "Olympique Lyonnais": ["Lyon", "OL"],
    "AS Monaco FC": ["AS Monaco", "Monaco"],
    "Lille OSC": ["Lille", "LOSC"],
    "Racing Club de Lens": ["RC Lens", "Lens"],
    "OGC Nice": ["Nice"],
    "Stade Brestois 29": ["Stade Brestois", "Brest"],
    "Stade Rennais FC 1901": ["Stade Rennais", "Rennes"],
    "RC Strasbourg Alsace": ["Strasbourg"],
    "Stade de Reims": ["Reims"],
    "AS Saint-Étienne": ["Saint-Étienne", "Saint-Etienne"],
    "Montpellier HSC": ["Montpellier"],
    "Toulouse FC": ["Toulouse"],
    "FC Nantes": ["Nantes"],
    "AJ Auxerre": ["Auxerre"],
    "Angers SCO": ["Angers"],
    "Le Havre AC": ["Le Havre"],
    "FC Lorient": ["Lorient"],
    "FC Metz": ["Metz"],
    "ES Troyes AC": ["Troyes"],
    "Le Mans FC": ["Le Mans"],
}


def aliases(team: str) -> list[str]:
    out = [team, *MANUAL_ALIASES.get(team, [])]
    stripped = re.sub(r"^(A?FC) | (A?FC)$", "", team)
    if stripped not in out:
        out.append(stripped)
    return out


def short(team: str) -> str:
    return aliases(team)[1] if len(aliases(team)) > 1 else team


def fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return month_end(date(d.year + y, m + 1, 1))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------------------------------------------------------------- download


def fetch(season: str, league: str) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / f"{season}_{league}.json"
    if not p.exists():
        r = httpx.get(URL.format(season=season, league=league), timeout=60, follow_redirects=True)
        r.raise_for_status()
        p.write_bytes(r.content)
    return json.loads(p.read_text())


# ---------------------------------------------------------------- matches


@dataclass
class Match:
    id: str
    league: str
    season: str
    round: str
    date: date
    time: str | None
    home: str
    away: str
    hg: int
    ag: int
    ht: tuple[int, int] | None
    status: str | None
    ts: datetime

    def goals_for(self, team: str) -> int:
        return self.hg if team == self.home else self.ag

    def goals_against(self, team: str) -> int:
        return self.ag if team == self.home else self.hg

    def result_for(self, team: str) -> str:
        f, a = self.goals_for(team), self.goals_against(team)
        return "W" if f > a else "D" if f == a else "L"


def parse_score(s) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    if isinstance(s, dict):
        ft = tuple(s["ft"]) if s.get("ft") else None
        ht = tuple(s["ht"]) if s.get("ht") else None
        return ft, ht
    if isinstance(s, list) and len(s) == 2:
        ft = tuple(s)
        # The source abbreviates goalless draws as a bare [0, 0]; half-time is then necessarily 0-0.
        return ft, (0, 0) if ft == (0, 0) else None
    return None, None


STATS = Counter()


def load() -> tuple[list[Match], dict[tuple[str, str], set[str]], dict[tuple[str, str], list[dict]]]:
    matches: list[Match] = []
    teams: dict[tuple[str, str], set[str]] = {}
    fixtures: dict[tuple[str, str], list[dict]] = {}
    for league, (_, _, tzname) in LEAGUES.items():
        tz = ZoneInfo(tzname)
        for season in SEASONS:
            data = fetch(season, league)
            fixtures[(league, season)] = data["matches"]
            teams[(league, season)] = {m["team1"] for m in data["matches"]} | {m["team2"] for m in data["matches"]}
            for m in data["matches"]:
                d = date.fromisoformat(m["date"])
                ft, ht = parse_score(m.get("score"))
                if d > CAP:
                    continue
                if ft is None:
                    STATS[f"dropped_no_score:{league}:{season}"] += 1
                    continue
                if m.get("time"):
                    hh, mm = map(int, m["time"].split(":"))
                    local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
                    ts = local.astimezone(timezone.utc) + timedelta(hours=2)
                else:
                    ts = datetime(d.year, d.month, d.day, 22, 0, tzinfo=timezone.utc)
                assert ts.date() == d, (m, ts)
                mid = f"{NAME}:{league}:{season}:{d.isoformat()}:{slug(m['team1'])}-v-{slug(m['team2'])}"
                matches.append(
                    Match(mid, league, season, m["round"], d, m.get("time"), m["team1"], m["team2"],
                          ft[0], ft[1], ht, m.get("status"), ts)
                )
    matches.sort(key=lambda x: (x.ts, x.id))
    assert len({m.id for m in matches}) == len(matches)
    return matches, teams, fixtures


def item_text(m: Match) -> tuple[str, str]:
    lname = LEAGUES[m.league][0]
    when = f"On {fmt(m.date)}, in the {lname} {m.season} season ({m.round})"
    score = f"{m.home} {m.hg}-{m.ag} {m.away}"
    if m.status == "awarded":
        body = (f"{when}, the match between home side {m.home} and away side {m.away} was recorded as an "
                f"awarded result (decided by the league rather than on the pitch): {score}.")
    else:
        if m.hg > m.ag:
            outcome = f"home side {m.home} beat {m.away} {m.hg}-{m.ag}"
        elif m.ag > m.hg:
            outcome = f"away side {m.away} won {m.ag}-{m.hg} at {m.home}"
        else:
            outcome = f"{m.home} (home) and {m.away} (away) drew {m.hg}-{m.ag}"
        body = f"{when}, {outcome}. Final score: {score} (home team first)."
        if m.ht:
            body += f" Half-time: {m.ht[0]}-{m.ht[1]}."
    if m.time:
        body += f" Kickoff was {m.time} local time."
    title = f"{LEAGUES[m.league][1]} {m.season}: {score}" + (" (awarded)" if m.status == "awarded" else "")
    return title, body


def to_item(m: Match) -> dict:
    title, text = item_text(m)
    return {
        "id": m.id,
        "dataset": NAME,
        "ts": iso(m.ts),
        "title": title,
        "text": text,
        "source": "openfootball/football.json",
        "url": f"https://github.com/openfootball/football.json/blob/master/{m.season}/{m.league}.json",
        "meta": {
            "league": LEAGUES[m.league][0],
            "league_code": m.league,
            "season": m.season,
            "round": m.round,
            "date": m.date.isoformat(),
            "kickoff_local": m.time,
            "home": m.home,
            "away": m.away,
            "ft": [m.hg, m.ag],
            "ht": list(m.ht) if m.ht else None,
            "status": m.status,
        },
    }


# ---------------------------------------------------------------- league tables


class Tables:
    def __init__(self, matches: list[Match], teams: dict[tuple[str, str], set[str]]):
        self.teams = teams
        self.by_ls: dict[tuple[str, str], list[Match]] = defaultdict(list)
        for m in matches:
            self.by_ls[(m.league, m.season)].append(m)
        for v in self.by_ls.values():
            v.sort(key=lambda x: (x.date, x.ts, x.id))

    def played(self, league: str, season: str, upto: date, team: str | None = None,
               start: date | None = None) -> list[Match]:
        return [m for m in self.by_ls[(league, season)]
                if m.date <= upto and (start is None or m.date >= start)
                and (team is None or team in (m.home, m.away))]

    def table(self, league: str, season: str, upto: date) -> list[dict]:
        rows = {t: {"team": t, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0}
                for t in self.teams[(league, season)]}
        for m in self.played(league, season, upto):
            for t in (m.home, m.away):
                r = rows[t]
                res = m.result_for(t)
                r["p"] += 1
                r["gf"] += m.goals_for(t)
                r["ga"] += m.goals_against(t)
                r["w" if res == "W" else "d" if res == "D" else "l"] += 1
                r["pts"] += 3 if res == "W" else 1 if res == "D" else 0
        out = sorted(rows.values(), key=lambda r: (-r["pts"], -(r["gf"] - r["ga"]), -r["gf"], r["team"]))
        for i, r in enumerate(out, 1):
            r["gd"] = r["gf"] - r["ga"]
            r["pos"] = i
        return out

    @staticmethod
    def row(tab: list[dict], team: str) -> dict:
        return next(r for r in tab if r["team"] == team)

    @staticmethod
    def unique_pos(tab: list[dict], team: str) -> bool:
        r = Tables.row(tab, team)
        key = (r["pts"], r["gd"], r["gf"])
        return sum(1 for x in tab if (x["pts"], x["gd"], x["gf"]) == key) == 1

    def season_span(self, league: str, season: str) -> tuple[date, date]:
        ms = self.by_ls[(league, season)]
        return ms[0].date, ms[-1].date

    def current_streak(self, league: str, season: str, team: str, upto: date, kind: str = "W") -> int:
        n = 0
        for m in reversed(self.played(league, season, upto, team)):
            if m.result_for(team) != kind:
                break
            n += 1
        return n

    def longest_streak(self, league: str, season: str, team: str, kind: str = "W") -> int:
        best = cur = 0
        for m in self.played(league, season, date.max, team):
            cur = cur + 1 if m.result_for(team) == kind else 0
            best = max(best, cur)
        return best

    def first_result(self, league: str, season: str, team: str, kind: str) -> Match | None:
        return next((m for m in self.played(league, season, date.max, team) if m.result_for(team) == kind), None)

    def meetings(self, league: str, season: str, a: str, b: str) -> list[Match]:
        return [m for m in self.by_ls[(league, season)] if {m.home, m.away} == {a, b}]


# ---------------------------------------------------------------- quiz


RULE = "3 points for a win, 1 for a draw; ties broken by goal difference, then goals scored"


class Quiz:
    def __init__(self, first_item: date, ts_by_id: dict[str, datetime]):
        self.first = first_item
        self.ts_by_id = ts_by_id
        self.rows: list[dict] = []
        self.n = 0

    def add(self, question: str, gold: list[str], answer_type: str, category: str, fact_time: date,
            evidence: list[str], asks: list[date], tol: float | None = None) -> None:
        self.n += 1
        base = f"{NAME}:q{self.n:04d}"
        asks = sorted({a for a in asks if self.first <= a <= CAP})
        assert asks, question
        for a in asks:
            ask_dt = datetime(a.year, a.month, a.day, 23, 59, 59, tzinfo=timezone.utc)
            if answer_type != "abstain":
                assert all(self.ts_by_id[e] <= ask_dt for e in evidence), (question, a)
                assert a >= fact_time, (question, a)
            cat = category
            if category == "point":
                cat = "point_recent" if (a - fact_time).days <= 30 else "point_old"
            self.rows.append({
                "qid": f"{base}@{a.isoformat()}",
                "base_id": base,
                "dataset": NAME,
                "ask_at": f"{a.isoformat()}T23:59:59Z",
                "question": question,
                "gold": gold,
                "answer_type": answer_type,
                "numeric_tolerance": tol if answer_type == "number" else None,
                "category": cat,
                "fact_time": fact_time.isoformat(),
                "evidence_item_ids": evidence,
                "gold_source": "structured",
            })


def reask(fact: date) -> list[date]:
    first = month_end(fact)
    return [first, add_months(first, 3), add_months(first, 6), add_months(first, 12), CAP]


def two_asks(fact: date, later: int = 6) -> list[date]:
    first = month_end(fact)
    second = add_months(first, later)
    return [first, second if second <= CAP else CAP]


def score_gold(home: str, away: str, h: int, a: int) -> list[str]:
    return [f"{h}-{a}", f"{h}–{a}", f"{short(home)} {h}-{a} {short(away)}", f"{home} {h}-{a} {away}"]


def num(n: int) -> list[str]:
    return [str(n)]


def build_quiz(matches: list[Match], T: Tables, quiz: Quiz, rng: random.Random) -> None:
    lname = {k: v[0] for k, v in LEAGUES.items()}
    real = [m for m in matches if m.status != "awarded"]

    # ---- point lookups: one match per equal time bin, rotating leagues and phrasings
    t0, t1 = matches[0].date, matches[-1].date
    nbins = 26
    span = (t1 - t0).days + 1
    league_cycle = list(LEAGUES)
    for i in range(nbins):
        lo = t0 + timedelta(days=span * i // nbins)
        hi = t0 + timedelta(days=span * (i + 1) // nbins - 1)
        lg = league_cycle[i % 3]
        pool = [m for m in real if lo <= m.date <= hi and m.league == lg] or \
               [m for m in real if lo <= m.date <= hi]
        if not pool:
            continue
        m = rng.choice(pool)
        variant = i % 3
        if variant == 2 and m.ht:
            q = (f"What was the half-time score of the {lname[m.league]} match between {m.home} (home) and "
                 f"{m.away} (away) played on {fmt(m.date)}? Give the home team's goals first.")
            gold = score_gold(m.home, m.away, *m.ht)
        elif variant == 1:
            q = (f"In the {lname[m.league]} {m.season} season, what was the final score when {m.home} hosted "
                 f"{m.away}? Give the home team's goals first.")
            gold = score_gold(m.home, m.away, m.hg, m.ag)
        else:
            q = (f"What was the final score of the {lname[m.league]} match between {m.home} (home) and "
                 f"{m.away} (away) played on {fmt(m.date)}? Give the home team's goals first.")
            gold = score_gold(m.home, m.away, m.hg, m.ag)
        quiz.add(q, gold, "text", "point", m.date, [m.id], reask(m.date))

    def season_month_ends(league: str, season: str) -> list[date]:
        a, b = T.season_span(league, season)
        out, d = [], month_end(a + timedelta(days=20))
        while d < b:
            out.append(d)
            d = add_months(d, 1)
        return out

    def asof_dates(league: str, season: str) -> list[date]:
        if season == "2026-27":
            return [T.season_span(league, season)[1]]
        return season_month_ends(league, season)

    def asof_asks(d: date) -> list[date]:
        first = d if d == month_end(d) else month_end(d)
        later = add_months(first, 6)
        return [first, later if later <= CAP else CAP]

    def ev_all(league: str, season: str, upto: date) -> list[str]:
        return [m.id for m in T.played(league, season, upto)]

    def ev_team(league: str, season: str, upto: date, team: str, start: date | None = None) -> list[str]:
        return [m.id for m in T.played(league, season, upto, team, start)]

    # ---- as_of_state: league leader (strictly ahead on points), one per league-season
    for lg in LEAGUES:
        for season in SEASONS:
            cands = []
            for d in asof_dates(lg, season):
                tab = T.table(lg, season, d)
                if tab[0]["pts"] > tab[1]["pts"]:
                    cands.append((d, tab))
            if not cands:
                continue
            d, tab = rng.choice(cands)
            leader = tab[0]["team"]
            q = (f"Based on {lname[lg]} {season} results up to and including {fmt(d)}, which team was top of "
                 f"the table ({RULE})?")
            quiz.add(q, aliases(leader), "text", "as_of_state", d, ev_all(lg, season, d), asof_asks(d))

    # ---- as_of_state: a team's points and position
    combos = [(lg, s) for lg in LEAGUES for s in COMPLETED]
    rng.shuffle(combos)
    for lg, season in combos[:5]:
        d = rng.choice(season_month_ends(lg, season))
        tab = T.table(lg, season, d)
        team = rng.choice(tab[:8])["team"]
        pts = T.row(tab, team)["pts"]
        q = (f"How many league points did {team} have in the {lname[lg]} {season} table after all matches "
             f"played up to and including {fmt(d)} (3 for a win, 1 for a draw)?")
        quiz.add(q, num(pts), "number", "as_of_state", d, ev_team(lg, season, d, team), asof_asks(d), 0.0)
    rng.shuffle(combos)
    for lg, season in combos[:4]:
        for _ in range(50):
            d = rng.choice(season_month_ends(lg, season))
            tab = T.table(lg, season, d)
            team = rng.choice(tab)["team"]
            if T.unique_pos(tab, team):
                break
        pos = T.row(tab, team)["pos"]
        q = (f"What position was {team} in the {lname[lg]} {season} table after all matches played up to and "
             f"including {fmt(d)} ({RULE})?")
        quiz.add(q, [str(pos), f"{pos}{'st' if pos == 1 else 'nd' if pos == 2 else 'rd' if pos == 3 else 'th'}"],
                 "number", "as_of_state", d, ev_all(lg, season, d), asof_asks(d), 0.0)

    # ---- as_of_state: current winning run
    streak_cands = []
    for lg in LEAGUES:
        for season in COMPLETED:
            for d in season_month_ends(lg, season):
                for team in T.teams[(lg, season)]:
                    n = T.current_streak(lg, season, team, d)
                    if n >= 3:
                        streak_cands.append((lg, season, d, team, n))
    rng.shuffle(streak_cands)
    used_leagues = set()
    for lg, season, d, team, n in streak_cands:
        if lg in used_leagues:
            continue
        used_leagues.add(lg)
        ev = [m.id for m in T.played(lg, season, d, team)[-(n + 1):]]
        q = (f"As of {fmt(d)}, how many consecutive {lname[lg]} {season} matches had {team} won (its winning run "
             f"counting back from its most recent league match on or before that date)?")
        quiz.add(q, num(n), "number", "as_of_state", d, ev, asof_asks(d), 0.0)
        if len(used_leagues) == 2:
            break

    # ---- aggregate: goals scored in a calendar month
    # May is excluded: relegation play-offs then are not league matches but could be confused with them.
    months = sorted({(m.league, m.season, m.date.year, m.date.month) for m in real
                     if m.season in COMPLETED and m.date.month != 5})
    rng.shuffle(months)
    months.sort(key=lambda x: list(LEAGUES).index(x[0]))
    months = [x for trio in zip(*[[m for m in months if m[0] == lg] for lg in LEAGUES]) for x in trio]
    for lg, season, y, mo in months[:5]:
        start, end = date(y, mo, 1), month_end(date(y, mo, 1))
        teams = sorted(t for t in T.teams[(lg, season)] if len(T.played(lg, season, end, t, start)) >= 2)
        team = rng.choice(teams)
        ms = T.played(lg, season, end, team, start)
        g = sum(m.goals_for(team) for m in ms)
        q = (f"How many goals did {team} score in total across its {lname[lg]} matches played in "
             f"{start.strftime('%B %Y')}?")
        quiz.add(q, num(g), "number", "aggregate", ms[-1].date, [m.id for m in ms],
                 [end, add_months(end, 6), CAP], 0.0)

    # ---- aggregate: wins in a date range
    for lg in LEAGUES:
        season = rng.choice(COMPLETED)
        a, b = T.season_span(lg, season)
        start = a + timedelta(days=rng.randint(10, 120))
        end = start + timedelta(days=rng.randint(55, 100))
        team = rng.choice(sorted(T.teams[(lg, season)]))
        ms = T.played(lg, season, end, team, start)
        w = sum(1 for m in ms if m.result_for(team) == "W")
        q = (f"How many {lname[lg]} matches did {team} win between {fmt(start)} and {fmt(end)} inclusive?")
        quiz.add(q, num(w), "number", "aggregate", end, [m.id for m in ms],
                 [month_end(end), add_months(month_end(end), 6), CAP], 0.0)

    # ---- aggregate: champions and champion points of completed seasons
    for lg in LEAGUES:
        for season in COMPLETED:
            end = T.season_span(lg, season)[1]
            tab = T.table(lg, season, end)
            assert tab[0]["pts"] > tab[1]["pts"]
            champ = tab[0]["team"]
            q = (f"Which team won the {lname[lg]} {season} season, i.e. finished top of the final table "
                 f"({RULE})?")
            quiz.add(q, aliases(champ), "text", "aggregate", end, ev_all(lg, season, end),
                     [month_end(end), add_months(month_end(end), 6), CAP])
    for lg, season in [(lg, rng.choice(COMPLETED)) for lg in LEAGUES]:
        end = T.season_span(lg, season)[1]
        tab = T.table(lg, season, end)
        q = (f"How many points did the champion of the {lname[lg]} {season} season finish with, counting 3 per "
             f"win and 1 per draw over all its league matches?")
        quiz.add(q, num(tab[0]["pts"]), "number", "aggregate", end, ev_team(lg, season, end, tab[0]["team"]),
                 [month_end(end), CAP], 0.0)

    # ---- aggregate: draws in a league in a month
    for lg, season, y, mo in months[5:7]:
        start, end = date(y, mo, 1), month_end(date(y, mo, 1))
        ms = T.played(lg, season, end, None, start)
        dr = sum(1 for m in ms if m.hg == m.ag)
        q = f"How many {lname[lg]} matches played in {start.strftime('%B %Y')} ended in a draw?"
        quiz.add(q, num(dr), "number", "aggregate", end, [m.id for m in ms], [end, CAP], 0.0)

    # ---- aggregate: longest winning run in a completed season (top-4 sides)
    rng.shuffle(combos)
    for lg, season in combos[:2]:
        end = T.season_span(lg, season)[1]
        team = rng.choice(T.table(lg, season, end)[:4])["team"]
        n = T.longest_streak(lg, season, team)
        q = (f"What was {team}'s longest run of consecutive wins in the {lname[lg]} {season} season "
             f"(league matches only)?")
        quiz.add(q, num(n), "number", "aggregate", end, ev_team(lg, season, end, team), [month_end(end), CAP], 0.0)

    # ---- change: points gained between two dates
    rng.shuffle(combos)
    for lg, season in combos[:4]:
        mes = season_month_ends(lg, season)
        i = rng.randrange(0, len(mes) - 2)
        d1, d2 = mes[i], mes[i + 2]
        team = rng.choice(T.table(lg, season, d2)[:10])["team"]
        p1 = T.row(T.table(lg, season, d1), team)["pts"]
        p2 = T.row(T.table(lg, season, d2), team)["pts"]
        q = (f"How many points did {team} gain in the {lname[lg]} {season} table between the end of {fmt(d1)} "
             f"and the end of {fmt(d2)}?")
        quiz.add(q, num(p2 - p1), "number", "change", d2, ev_team(lg, season, d2, team, d1 + timedelta(days=1)),
                 [d2, add_months(d2, 6) if add_months(d2, 6) <= CAP else CAP], 0.0)

    # ---- change: position change
    rng.shuffle(combos)
    made = 0
    for lg, season in combos:
        mes = season_month_ends(lg, season)
        for _ in range(200):
            i = rng.randrange(0, len(mes) - 2)
            d1, d2 = mes[i], mes[i + 2]
            t1, t2 = T.table(lg, season, d1), T.table(lg, season, d2)
            team = rng.choice(t2)["team"]
            if T.unique_pos(t1, team) and T.unique_pos(t2, team):
                p1, p2 = T.row(t1, team)["pos"], T.row(t2, team)["pos"]
                if abs(p1 - p2) >= 2:
                    break
        else:
            continue
        delta = p1 - p2
        word = "up" if delta > 0 else "down"
        q = (f"In the {lname[lg]} {season} table ({RULE}), how many places did {team} move between the end of "
             f"{fmt(d1)} and the end of {fmt(d2)}? Answer as a signed number (positive = moved up the table).")
        gold = [f"{delta:+d}", f"{word} {abs(delta)}", f"moved {word} {abs(delta)} places",
                f"from {p1} to {p2}"] + ([str(delta)] if delta > 0 else [])
        quiz.add(q, gold, "text", "change", d2, ev_all(lg, season, d2),
                 [d2, add_months(d2, 6) if add_months(d2, 6) <= CAP else CAP])
        made += 1
        if made == 3:
            break

    # ---- change: who replaced the leader
    lead_changes = []
    for lg in LEAGUES:
        for season in COMPLETED:
            mes = season_month_ends(lg, season)
            for d1, d2 in zip(mes, mes[1:]):
                a, b = T.table(lg, season, d1), T.table(lg, season, d2)
                if a[0]["pts"] > a[1]["pts"] and b[0]["pts"] > b[1]["pts"] and a[0]["team"] != b[0]["team"]:
                    lead_changes.append((lg, season, d1, d2, a[0]["team"], b[0]["team"]))
    for lg, season, d1, d2, old, new in rng.sample(lead_changes, min(2, len(lead_changes))):
        q = (f"{old} was top of the {lname[lg]} {season} table at the end of {fmt(d1)}. Which team was top at "
             f"the end of {fmt(d2)} ({RULE})?")
        quiz.add(q, aliases(new), "text", "change", d2, ev_all(lg, season, d2),
                 [d2, add_months(d2, 6) if add_months(d2, 6) <= CAP else CAP])

    # ---- ordering: whose first league defeat came first (top-4 sides, same season, different leagues)
    for season in COMPLETED:
        tops = []
        for lg in LEAGUES:
            end = T.season_span(lg, season)[1]
            tops += [(lg, r["team"]) for r in T.table(lg, season, end)[:3]]
        for _ in range(2 if season == "2024-25" else 1):
            for _ in range(100):
                (la, a), (lb, b) = rng.sample(tops, 2)
                fa, fb = T.first_result(la, season, a, "L"), T.first_result(lb, season, b, "L")
                if fa and fb and fa.date != fb.date and la != lb:
                    break
            first = a if fa.date < fb.date else b
            q = (f"In the {season} season, which team suffered its first league defeat earlier: {a} "
                 f"({lname[la]}) or {b} ({lname[lb]})?")
            ft = max(fa.date, fb.date)
            quiz.add(q, aliases(first), "text", "ordering", ft,
                     ev_team(la, season, fa.date, a) + ev_team(lb, season, fb.date, b),
                     [month_end(ft), add_months(month_end(ft), 6) if add_months(month_end(ft), 6) <= CAP else CAP])

    # ---- ordering: days between the two league meetings of a pair
    for lg in rng.sample(list(LEAGUES), 2):
        season = rng.choice(COMPLETED)
        end = T.season_span(lg, season)[1]
        top = [r["team"] for r in T.table(lg, season, end)[:6]]
        a, b = rng.sample(top, 2)
        m1, m2 = T.meetings(lg, season, a, b)  # top-6 sides always meet twice
        days = (m2.date - m1.date).days
        q = (f"How many days passed between the first and second {lname[lg]} {season} meetings of {a} and {b}?")
        quiz.add(q, num(days), "number", "ordering", m2.date, [m1.id, m2.id],
                 [month_end(m2.date), CAP], 0.0)

    # ---- ordering: which side reached a points mark first
    lg_a, lg_b = rng.sample(list(LEAGUES), 2)
    season = "2024-25"
    ca = T.table(lg_a, season, date.max)[0]["team"]
    cb = T.table(lg_b, season, date.max)[0]["team"]

    def reach(lg: str, team: str, mark: int) -> Match:
        pts = 0
        for m in T.played(lg, season, date.max, team):
            pts += {"W": 3, "D": 1, "L": 0}[m.result_for(team)]
            if pts >= mark:
                return m
        raise AssertionError

    for mark in (50, 40, 60, 30):
        ra, rb = reach(lg_a, ca, mark), reach(lg_b, cb, mark)
        if ra.date != rb.date:
            break
    else:
        raise AssertionError("no points mark separates the two champions")
    first = ca if ra.date < rb.date else cb
    ft = max(ra.date, rb.date)
    q = (f"In the {season} season, which team reached {mark} league points first: {ca} ({lname[lg_a]}) or "
         f"{cb} ({lname[lg_b]})?")
    quiz.add(q, aliases(first), "text", "ordering", ft,
             ev_team(lg_a, season, ra.date, ca) + ev_team(lg_b, season, rb.date, cb),
             [month_end(ft), CAP])

    # ---- multi_hop: head-to-head aggregates across both meetings
    for _ in range(4):
        lg, season = rng.choice(combos)
        end = T.season_span(lg, season)[1]
        a, b = rng.sample([r["team"] for r in T.table(lg, season, end)[:8]], 2)
        ms = T.meetings(lg, season, a, b)
        assert len(ms) == 2
        ga = sum(m.goals_for(a) for m in ms)
        gb = sum(m.goals_for(b) for m in ms)
        q = (f"Across both {lname[lg]} {season} meetings between {a} and {b}, what was the aggregate score? "
             f"Give {a}'s total goals first.")
        quiz.add(q, [f"{ga}-{gb}", f"{ga}–{gb}", f"{short(a)} {ga}-{gb} {short(b)}"], "text", "multi_hop",
                 ms[-1].date, [m.id for m in ms], [month_end(ms[-1].date), CAP])
    for _ in range(2):
        lg, season = rng.choice(combos)
        end = T.season_span(lg, season)[1]
        a, b = rng.sample([r["team"] for r in T.table(lg, season, end)[:10]], 2)
        ms = T.meetings(lg, season, a, b)
        assert len(ms) == 2
        p = sum({"W": 3, "D": 1, "L": 0}[m.result_for(a)] for m in ms)
        q = (f"How many league points did {a} take from its two {lname[lg]} {season} matches against {b} "
             f"(3 for a win, 1 for a draw)?")
        quiz.add(q, num(p), "number", "multi_hop", ms[-1].date, [m.id for m in ms],
                 [month_end(ms[-1].date), CAP], 0.0)
    for _ in range(2):
        lg, season = rng.choice(combos)
        m = rng.choice([x for x in T.by_ls[(lg, season)] if x.hg != x.ag and x.status != "awarded"
                        and len(T.meetings(lg, season, x.home, x.away)) == 2])
        rev = next(x for x in T.by_ls[(lg, season)] if x.home == m.away and x.away == m.home)
        late, early = (m, rev) if m.date > rev.date else (rev, m)
        winner = late.home if late.hg > late.ag else late.away
        loser = late.away if winner == late.home else late.home
        hi, lo = max(late.hg, late.ag), min(late.hg, late.ag)
        q = (f"On {fmt(late.date)}, {winner} beat {loser} {hi}-{lo} in the {lname[lg]} {season} season. What was "
             f"the final score of the other league meeting between the two clubs that season, when {early.home} "
             f"hosted {early.away}? Give the home team's goals first.")
        quiz.add(q, score_gold(early.home, early.away, early.hg, early.ag), "text", "multi_hop", late.date,
                 [early.id, late.id], [month_end(late.date), CAP])

    # ---- abstain: match not yet played at ask time
    for i, lg in enumerate(list(LEAGUES) + list(LEAGUES)[:2]):
        season = COMPLETED[i % 2]
        a, b = T.season_span(lg, season)
        pool = [m for m in T.by_ls[(lg, season)] if m.date >= a + timedelta(days=120) and m.status != "awarded"]
        m = rng.choice(pool)
        asks = [add_months(month_end(m.date), k) for k in (-1, -2, -4)]
        asks = [x for x in asks if x < m.date]
        note = (f"Not yet played as of the ask date: the match was scheduled for {fmt(m.date)}, so no result was "
                f"available.")
        if i % 2 == 0:
            q = (f"What was the final score of the {lname[lg]} match between {m.home} (home) and {m.away} (away) "
                 f"on {fmt(m.date)}?")
        else:
            q = f"In the {lname[lg]} {season} season, what was the final score when {m.home} hosted {m.away}?"
        quiz.add(q, [note], "abstain", "abstain", m.date, [m.id], asks)

    # ---- abstain: fixture that never happened (promoted side vs a club in the season before promotion)
    pairs = [("en.1", "2024-25", "2025-26"), ("de.1", "2024-25", "2025-26"), ("fr.1", "2025-26", "2026-27"),
             ("en.1", "2025-26", "2026-27")]
    for lg, s_prev, s_next in pairs:
        newcomers = sorted(T.teams[(lg, s_next)] - T.teams[(lg, s_prev)])
        team = rng.choice(newcomers)
        end = T.season_span(lg, s_prev)[1]
        opp = T.table(lg, s_prev, end)[0]["team"]
        assert not any(team in (m.home, m.away) for m in T.by_ls[(lg, s_prev)])
        q = f"What was the final score when {team} hosted {opp} in the {lname[lg]} {s_prev} season?"
        note = f"False premise: {team} was not in the {lname[lg]} in {s_prev}, so this league match never took place."
        quiz.add(q, [note], "abstain", "abstain", end, [], [month_end(end), CAP])


# ---------------------------------------------------------------- main


def main() -> None:
    matches, teams, fixtures = load()
    items = [to_item(m) for m in matches]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    T = Tables(matches, teams)
    quiz = Quiz(matches[0].date, {m.id: m.ts for m in matches})
    build_quiz(matches, T, quiz, random.Random(SEED))
    quiz.rows.sort(key=lambda q: (q["ask_at"], q["qid"]))
    with open(OUT / "questions.jsonl", "w") as f:
        for q in quiz.rows:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    write_readme(matches, T, quiz.rows)
    print(f"items={len(items)} questions={len(quiz.rows)} base={quiz.n}")
    print(dict(Counter(q["category"] for q in quiz.rows)))
    print(dict(STATS))


def write_readme(matches: list[Match], T: Tables, qs: list[dict]) -> None:
    per = Counter((m.league, m.season) for m in matches)
    last = {(lg, s): T.season_span(lg, s)[1] for lg in LEAGUES for s in SEASONS}
    champs = []
    for lg in LEAGUES:
        for s in COMPLETED:
            tab = T.table(lg, s, date.max)
            champs.append(f"| {LEAGUES[lg][0]} | {s} | {tab[0]['team']} | {tab[0]['pts']} | "
                          f"{tab[1]['team']} | {tab[1]['pts']} |")
    count_rows = "\n".join(
        f"| {LEAGUES[lg][0]} | {s} | {per[(lg, s)]} | {last[(lg, s)].isoformat()} |"
        for lg in LEAGUES for s in SEASONS)
    cats = Counter(q["category"] for q in qs)
    bases = Counter()
    seen = set()
    for q in qs:
        if q["base_id"] not in seen:
            seen.add(q["base_id"])
            bases[q["category"] if not q["category"].startswith("point") else "point"] += 1
    asks = sorted({q["ask_at"][:10] for q in qs})
    dropped = "\n".join(f"- `{k}`: {v}" for k, v in sorted(STATS.items())) or "- none"
    text = f"""# football

Match results from three European top flights (English Premier League, German Bundesliga,
French Ligue 1), one item per played league match, from the first match of 2024-25 to the last
result available in the source. Tests evolving state and exact aggregation over many small events
(league tables, streaks, totals, head-to-heads).

Built by `uv run python -m factbase.datasets.football.build` (no LLM calls; cost $0).

## Source and terms

- [openfootball/football.json](https://github.com/openfootball/football.json), files
  `{{season}}/{{en.1,de.1,fr.1}}.json` for seasons 2024-25, 2025-26 and 2026-27. Raw files are cached in
  `data/raw/football/`. openfootball data is public domain (CC0 / "no rights reserved").
- es.1 and it.1 were also checked but not used: their 2024-25 files are missing all 10 Matchday 38
  results, so final 2024-25 tables would be wrong.

## Window (differs from the common window)

- Items: **{matches[0].date.isoformat()} to {matches[-1].date.isoformat()}** (first 2024-25 match to the last
  result in the source). The window starts in August 2024, not 2024-11-01, so league tables are complete
  from matchday 1.
- The 2026-27 files only contain results up to **2026-09-20** (the source had not been updated further when
  downloaded on 2026-11-02); later fixtures exist with no score. Nothing after 2026-09-20 is in the
  stream, and no question asks about state after that date.
- Questions are asked from {asks[0]} to {asks[-1]} (cap 2026-10-31).

## Items

| League | Season | Items | Last result |
|---|---|---|---|
{count_rows}

Total: {len(matches)} items.

- `ts` = local kickoff date+time converted to UTC using the league's home timezone (Europe/London,
  Europe/Berlin, Europe/Paris, DST-aware) **plus 2 hours** (approximate final whistle). Every item has a
  kickoff time, and every `ts` falls on the match's calendar date. (Fallback if a time were missing:
  22:00Z on the match date.)
- `text` gives date, league, season, round, home/away sides, outcome, final score (home first),
  half-time score when present, and local kickoff time. No venue (not in the source).
- `meta` = {{league, league_code, season, round, date, kickoff_local, home, away, ft, ht, status}}.
- The source writes goalless draws in 2025-26 and 2026-27 as a bare `[0, 0]` instead of `{{ft, ht}}`; these
  are read as FT 0-0 with HT 0-0 (implied).
- Matches without a score (dated on or before 2026-10-31) are dropped; for 2026-27 these are the fixtures
  from 2026-09-21 onward that the source has not filled in yet:
{dropped}
  (The fr.1 2025-26 drop is FC Nantes vs Toulouse FC on 2026-05-17, marked `canceled` in the source.)
- Two results are marked `awarded` in the source and are stated as such in the text: 1. FC Union Berlin 0-2
  VfL Bochum 1848 (2024-12-14) and Montpellier HSC 0-2 AS Saint-Étienne (2025-03-16). Their `ts` is the
  match time even though the league's decision was published later.

Final tables computed from the items (sanity check against real-world outcomes):

| League | Season | Champion | Pts | Runner-up | Pts |
|---|---|---|---|---|---|
{chr(10).join(champs)}

## Questions

{len(qs)} instances from {len(seen)} base questions. Ask dates span {len({a[:7] for a in asks})} distinct months.

Instances by category: {dict(cats)}.
Base questions by kind: {dict(bases)}.

All gold answers are `structured`: computed in code from the parsed results with a league-table
implementation (3 points per win, 1 per draw; order by points, goal difference, goals scored, then name).
Every question that depends on a table position names this rule, and positions are only asked when the
team is not level with any other team on points, goal difference and goals scored (leader questions require
the leader to be strictly ahead on points), so real-world tie-breakers (head-to-head etc.) never matter.

Question families (selection is seeded random, `SEED={SEED}`):

- point (score / half-time score of one match; re-asked at month-end after, +3, +6, +12 months, 2026-10-31).
- as_of_state: leader as of a date (one per league-season), a team's points or position as of a month-end,
  current winning run as of a date. Asked at that date and ~6 months later.
- aggregate: a team's goals in a calendar month, wins in a date range, champion and champion's points of a
  completed season, draws in a league-month, longest winning run in a season.
- change: points gained between two month-ends, signed position change, who replaced the leader.
- ordering: whose first league defeat came first (cross-league), days between two meetings, who reached
  50 points first.
- multi_hop: aggregate score over both meetings, points taken from both meetings, reverse-fixture score
  given one result.
- abstain: a fixture asked about 1-4 months before it was played; a fixture that never happened (a newly
  promoted club "hosting" the previous season's champion in the season before promotion).

## Known issues

- Tables are computed purely from results. They ignore any points deductions; none applied in these
  league-seasons to the best of our knowledge, and every table question is phrased as "based on results".
- Real league tie-break rules differ (e.g. head-to-head); the quiz avoids any position that depends on them.
- Team names use openfootball's full official forms (e.g. "FC Bayern München", "Paris Saint-Germain FC");
  gold lists include common short names.
- The model may know famous results (e.g. 2024-25 champions) from pretraining; compare against A0
  closed-book. Questions about 2025-26 and 2026-27 are less exposed.
- Abstain "not yet played" questions name a real future fixture; a model that guesses a score is wrong
  even if the guess later turns out to match the real result.
"""
    (OUT / "README.md").write_text(text)


if __name__ == "__main__":
    main()
