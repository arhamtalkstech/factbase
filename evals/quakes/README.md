# quakes

USGS earthquake catalogue (ComCat), magnitude 4.5 and above, worldwide, 2024-11-01 to 2026-10-31 (UTC event
dates). Built by `uv run python -m factbase.datasets.quakes.build` (resumable: raw monthly responses are cached in
`data/raw/quakes/YYYY-MM.json`; delete a file to re-fetch it).

## Source and terms

- FDSN event web service: `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude=4.5`,
  paged by calendar month.
- USGS data are in the US public domain; credit "U.S. Geological Survey".

## Items

- 16259 items, one per event with `type == "earthquake"` (skipped: {'landslide': 3}).
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

- 217 questions, 82 base questions, all `gold_source = "structured"` (computed in code from the
  cached catalogue, no LLM).
- Instances by category: {'abstain': 19, 'aggregate': 58, 'as_of_state': 14, 'change': 15, 'multi_hop': 23, 'ordering': 26, 'point_old': 48, 'point_recent': 14}.
- Base questions by category: {'abstain': 10, 'aggregate': 23, 'as_of_state': 10, 'change': 7, 'multi_hop': 8, 'ordering': 9, 'point': 15}.
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
