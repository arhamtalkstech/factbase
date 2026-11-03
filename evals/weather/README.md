# weather

Daily weather for 12 cities on six continents from the Open-Meteo historical weather archive, 2024-11-01 to
2026-10-31 (the archive had complete data for every city through 2026-10-31 when built). Built by
`uv run python -m factbase.datasets.weather.build` (resumable: raw responses are cached per city and year in
`data/raw/weather/`; delete a file to re-fetch it).

## Source and terms

- `https://archive-api.open-meteo.com/v1/archive?...&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max&timezone=UTC`
  (ERA5 / ERA5-Land reanalysis blended with operational models for the most recent days).
- Open-Meteo data are CC BY 4.0 ("Weather data by Open-Meteo.com"); free non-commercial API use.

| City | Country | Continent | Lat, lon | id slug |
|---|---|---|---|---|
| London | United Kingdom | Europe | 51.5072, -0.1276 | `london` |
| Moscow | Russia | Europe | 55.7558, 37.6173 | `moscow` |
| Cairo | Egypt | Africa | 30.0444, 31.2357 | `cairo` |
| Lagos | Nigeria | Africa | 6.5244, 3.3792 | `lagos` |
| Johannesburg | South Africa | Africa | -26.2041, 28.0473 | `johannesburg` |
| Mumbai | India | Asia | 19.076, 72.8777 | `mumbai` |
| Beijing | China | Asia | 39.9042, 116.4074 | `beijing` |
| Tokyo | Japan | Asia | 35.6762, 139.6503 | `tokyo` |
| Sydney | Australia | Oceania | -33.8688, 151.2093 | `sydney` |
| New York | United States | North America | 40.7128, -74.006 | `new-york` |
| Mexico City | Mexico | North America | 19.4326, -99.1332 | `mexico-city` |
| São Paulo | Brazil | South America | -23.5505, -46.6333 | `sao-paulo` |

## Items

- 8760 items, one per city per UTC day; id `weather:<slug>:<YYYY-MM-DD>`.
- `ts` = the next day at 06:00 UTC (daily values are complete only after the UTC day ends). The 31 October 2026
  items therefore have `ts` 2026-11-01T06:00:00Z, after the last ask date.
- Text: prose with max/min temperature (°C), precipitation sum (mm; "no precipitation" when 0.0) and max 10 m wind
  speed (km/h). Values are as returned (one decimal). Grid-cell values for the given coordinates, not station data.
- `meta`: city, country, continent, lat, lon, date and the four values.

## Questions

- 215 questions, 79 base questions, all `gold_source = "structured"` (computed in code from the cached
  archive responses, no LLM).
- Instances by category: {'abstain': 18, 'aggregate': 56, 'as_of_state': 9, 'change': 19, 'multi_hop': 25, 'ordering': 27, 'point_old': 46, 'point_recent': 15}.
- Base questions by category: {'abstain': 10, 'aggregate': 20, 'as_of_state': 8, 'change': 8, 'multi_hop': 8, 'ordering': 10, 'point': 15}.
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
