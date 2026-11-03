# football

Match results from three European top flights (English Premier League, German Bundesliga,
French Ligue 1), one item per played league match, from the first match of 2024-25 to the last
result available in the source. Tests evolving state and exact aggregation over many small events
(league tables, streaks, totals, head-to-heads).

Built by `uv run python -m factbase.datasets.football.build` (no LLM calls; cost $0).

## Source and terms

- [openfootball/football.json](https://github.com/openfootball/football.json), files
  `{season}/{en.1,de.1,fr.1}.json` for seasons 2024-25, 2025-26 and 2026-27. Raw files are cached in
  `data/raw/football/`. openfootball data is public domain (CC0 / "no rights reserved").
- es.1 and it.1 were also checked but not used: their 2024-25 files are missing all 10 Matchday 38
  results, so final 2024-25 tables would be wrong.

## Window (differs from the common window)

- Items: **2024-08-16 to 2026-09-20** (first 2024-25 match to the last
  result in the source). The window starts in August 2024, not 2024-11-01, so league tables are complete
  from matchday 1.
- The 2026-27 files only contain results up to **2026-09-20** (the source had not been updated further when
  downloaded on 2026-11-02); later fixtures exist with no score. Nothing after 2026-09-20 is in the
  stream, and no question asks about state after that date.
- Questions are asked from 2024-09-30 to 2026-10-31 (cap 2026-10-31).

## Items

| League | Season | Items | Last result |
|---|---|---|---|
| English Premier League | 2024-25 | 380 | 2025-05-25 |
| English Premier League | 2025-26 | 380 | 2026-05-24 |
| English Premier League | 2026-27 | 50 | 2026-09-20 |
| German Bundesliga | 2024-25 | 306 | 2025-05-17 |
| German Bundesliga | 2025-26 | 306 | 2026-05-16 |
| German Bundesliga | 2026-27 | 36 | 2026-09-20 |
| French Ligue 1 | 2024-25 | 306 | 2025-05-17 |
| French Ligue 1 | 2025-26 | 305 | 2026-05-17 |
| French Ligue 1 | 2026-27 | 45 | 2026-09-20 |

Total: 2114 items.

- `ts` = local kickoff date+time converted to UTC using the league's home timezone (Europe/London,
  Europe/Berlin, Europe/Paris, DST-aware) **plus 2 hours** (approximate final whistle). Every item has a
  kickoff time, and every `ts` falls on the match's calendar date. (Fallback if a time were missing:
  22:00Z on the match date.)
- `text` gives date, league, season, round, home/away sides, outcome, final score (home first),
  half-time score when present, and local kickoff time. No venue (not in the source).
- `meta` = {league, league_code, season, round, date, kickoff_local, home, away, ft, ht, status}.
- The source writes goalless draws in 2025-26 and 2026-27 as a bare `[0, 0]` instead of `{ft, ht}`; these
  are read as FT 0-0 with HT 0-0 (implied).
- Matches without a score (dated on or before 2026-10-31) are dropped; for 2026-27 these are the fixtures
  from 2026-09-21 onward that the source has not filled in yet:
- `dropped_no_score:de.1:2026-27`: 34
- `dropped_no_score:en.1:2026-27`: 38
- `dropped_no_score:fr.1:2025-26`: 1
- `dropped_no_score:fr.1:2026-27`: 33
  (The fr.1 2025-26 drop is FC Nantes vs Toulouse FC on 2026-05-17, marked `canceled` in the source.)
- Two results are marked `awarded` in the source and are stated as such in the text: 1. FC Union Berlin 0-2
  VfL Bochum 1848 (2024-12-14) and Montpellier HSC 0-2 AS Saint-Étienne (2025-03-16). Their `ts` is the
  match time even though the league's decision was published later.

Final tables computed from the items (sanity check against real-world outcomes):

| League | Season | Champion | Pts | Runner-up | Pts |
|---|---|---|---|---|---|
| English Premier League | 2024-25 | Liverpool FC | 84 | Arsenal FC | 74 |
| English Premier League | 2025-26 | Arsenal FC | 85 | Manchester City FC | 78 |
| German Bundesliga | 2024-25 | FC Bayern München | 82 | Bayer 04 Leverkusen | 69 |
| German Bundesliga | 2025-26 | FC Bayern München | 89 | Borussia Dortmund | 73 |
| French Ligue 1 | 2024-25 | Paris Saint-Germain FC | 84 | Olympique de Marseille | 65 |
| French Ligue 1 | 2025-26 | Paris Saint-Germain FC | 76 | Racing Club de Lens | 70 |

## Questions

256 instances from 95 base questions. Ask dates span 26 distinct months.

Instances by category: {'point_recent': 22, 'as_of_state': 40, 'abstain': 23, 'aggregate': 53, 'change': 18, 'point_old': 72, 'ordering': 12, 'multi_hop': 16}.
Base questions by kind: {'point': 22, 'as_of_state': 20, 'abstain': 9, 'aggregate': 21, 'change': 9, 'ordering': 6, 'multi_hop': 8}.

All gold answers are `structured`: computed in code from the parsed results with a league-table
implementation (3 points per win, 1 per draw; order by points, goal difference, goals scored, then name).
Every question that depends on a table position names this rule, and positions are only asked when the
team is not level with any other team on points, goal difference and goals scored (leader questions require
the leader to be strictly ahead on points), so real-world tie-breakers (head-to-head etc.) never matter.

Question families (selection is seeded random, `SEED=20241101`):

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
