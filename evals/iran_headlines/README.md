# iran_headlines

A noisy, highly redundant, hourly stream of English news headlines about Iran and the
US/Israel/Gulf conflict, 2024-11-01 to 2026-10-31. The quiz is built from Wikipedia Current
Events Portal (WCEP) bullets and checked against the stream.

Build: `uv run python -m factbase.datasets.iran_headlines.build` (stages: `wcep`, `gkg`,
`items`, `quiz`, `stats`; all downloads are cached under `data/raw/iran_headlines/`).

## Source of the stream

**Planned source:** the GDELT DOC 2.0 API (`mode=artlist`, `maxrecords=250`, query
`(iran OR iranian OR tehran OR hormuz OR irgc) sourcelang:english`, two 12-hour windows per day).

**What happened:** the API answered almost every request from this machine with its
"Please limit requests to one every 5 seconds" message (HTTP 429). This happened even with
15-60 s gaps and backoff up to 15 minutes. In ~20 minutes it returned 9 windows, about one
success every 3-8 minutes, so the 1,460 windows would have taken more than 100 hours. The
partial DOC download (9 windows, 2,231 URLs) is cached in `data/raw/iran_headlines/gdelt/`
for comparison only. It is **not** used in the stream.

**Fallback used:** the raw **GDELT GKG 2.0** 15-minute files
(`https://data.gdeltproject.org/gdeltv2/<YYYYMMDDHHMMSS>.gkg.csv.zip`). They come from the same
GDELT crawl and carry the same article URL, page title (`<PAGE_TITLE>` in V2EXTRASXML), source
domain and processing timestamp as the DOC API's `seendate`. The main GKG feed is English-only;
translated sources are in a separate feed that is not used.

- Sampling: one 15-minute file per hour, rotating :00/:15/:30/:45 across hours, which gives
  17,520 hourly snapshots. If the sampled quarter-hour file is missing, the build tries another
  file from the same hour.
- Match: a row is kept if its page title matches `\b(iran|iranians?|tehran|hormuz|irgc)\b`
  (`meta.match = "headline"`, all kept). It is also kept if the same terms appear only in GKG's
  entities extracted from the article body (counts, themes, locations, persons, organisations,
  quotations, names). For these body-only matches (`meta.match = "article_body"`), a deterministic
  sample of at most 5 per snapshot is kept, chosen by lowest sha1 of the URL. They are realistic
  off-topic noise, the same kind of noise the DOC full-text query returns.
- Item: `text = "<headline> (<domain>, English)"`. `ts` is the GKG processing time in UTC (the
  same field as DOC `seendate`). The URL is in `url`. The id is `iran_headlines:<sha1(url)[:12]>`.
- Duplicates: exact-duplicate URLs are dropped, and the earliest sighting is kept. Syndicated
  copies of the same wire headline on different URLs are **kept** on purpose: 339,210 items
  share only 211,154 distinct titles. A few AP alert titles wrapped in `{...}` are unwrapped.
  No other text is changed.

Terms: GDELT data is free for research and commercial use with attribution ("The GDELT
Project"). Headlines belong to their publishers and are kept only as short titles. WCEP text
is CC BY-SA 4.0.

## Counts

- Items: **339,210** (258,255 headline matches, 80,955 body-only matches), 6,166 domains,
  2024-11-01T00:00Z to 2026-10-31T23:45Z.
- Hourly snapshots: 17,520 in total. 417 are missing because of a GDELT outage (see Known issues).

Coverage per month (honest; volume follows the news and the sampling, not a fixed quota):

| Month | Items | Items/day | Headline matches | Body-only matches | Missing hourly files |
|---|---|---|---|---|---|
| 2024-11 | 6697 | 223 | 3167 | 3530 | 0 |
| 2024-12 | 5609 | 181 | 1980 | 3629 | 0 |
| 2025-01 | 5168 | 167 | 1665 | 3503 | 0 |
| 2025-02 | 4614 | 165 | 1558 | 3056 | 0 |
| 2025-03 | 5808 | 187 | 2411 | 3397 | 0 |
| 2025-04 | 7367 | 246 | 4139 | 3228 | 0 |
| 2025-05 | 6370 | 205 | 2937 | 3433 | 0 |
| 2025-06 | 6302 | 210 | 4784 | 1518 | 391 |
| 2025-07 | 6988 | 225 | 3584 | 3404 | 26 |
| 2025-08 | 5939 | 192 | 2510 | 3429 | 0 |
| 2025-09 | 5397 | 180 | 2071 | 3326 | 0 |
| 2025-10 | 4376 | 141 | 1173 | 3203 | 0 |
| 2025-11 | 4418 | 147 | 1472 | 2946 | 0 |
| 2025-12 | 4979 | 161 | 1795 | 3184 | 0 |
| 2026-01 | 14425 | 465 | 10844 | 3581 | 0 |
| 2026-02 | 14407 | 515 | 11188 | 3219 | 0 |
| 2026-03 | 64831 | 2091 | 61111 | 3720 | 0 |
| 2026-04 | 45803 | 1527 | 42203 | 3600 | 0 |
| 2026-05 | 25983 | 838 | 22263 | 3720 | 0 |
| 2026-06 | 28902 | 963 | 25304 | 3598 | 0 |
| 2026-07 | 23830 | 769 | 20117 | 3713 | 0 |
| 2026-08 | 15961 | 515 | 12261 | 3700 | 0 |
| 2026-09 | 14686 | 490 | 11088 | 3598 | 0 |
| 2026-10 | 10350 | 334 | 6630 | 3720 | 0 |

Quiz: **87 base questions, 257 instances**.

| Category | Instances | Base questions |
|---|---|---|
| point_recent | 45 | 47 point bases, shared with point_old |
| point_old | 140 | |
| ordering | 16 | 8 |
| change | 2 | 1 |
| multi_hop | 6 | 3 |
| aggregate | 22 | 11 |
| abstain | 26 (10.1%) | 17 (9 false premise, 8 asked before the event) |

gold_source: `curated_wcep` 235 instances / 76 bases; `structured` 22 / 11. Answer types: text 178,
number 31, date 22, abstain 26. `ask_at` falls in all 24 months. 79 instances are at the final
day, 2026-10-31.

## How gold was made

1. **Candidates:** WCEP day pages (raw wikitext, 730 pages) are parsed into event bullets with their
   topic path. A bullet is kept if the bullet or its topics mention Iran, Iranian, Tehran, IRGC,
   Hormuz, Khamenei, Pezeshkian, Araghchi, Houthi(s) or Hezbollah. This gives 1,819 bullets, 1,468
   with the keyword in the bullet text. A stratified sample of at most 14 per month (310) is used.
2. **Question writing:** grok-4.3 reads only one bullet and writes one question with an explicit
   date and a short gold answer with aliases (309 written).
3. **Verification against the stream:** for each question, headlines from bullet date -1 to +2
   days are prefiltered by keyword overlap (at most 120 distinct titles). An LLM must find
   headlines that clearly state the gold answer, and it rejects ambiguous cases. Then a separate
   *blind* pass answers the question from only those supporting headlines, without seeing the
   gold, and an LLM matcher must agree with the gold. 137 of 309 passed. `evidence_item_ids` are
   the supporting headlines plus their identical-title syndicated copies in the same window.
4. **Point questions:** 47 are spread across months. Questions that an LLM could guess from the
   wording alone (for example "which Yemeni group..." → Houthis) are deprioritised: 46 of 137
   were flagged. They are re-asked at the first month-end on or after the latest evidence, then
   at +3, +6 and +12 months, and on 2026-10-31.
5. **Ordering / change / multi_hop:** an LLM proposes questions from groups of verified bullets
   on the same WCEP storyline, plus one global pass for state changes and multi-hop joins. Each
   question is verified by blind-answering from the union of the bullets' evidence headlines.
   Ordering questions must also have the same order in the stream (first sighting). Questions
   are asked at the first month-end after the later event and on 2026-10-31.
6. **Aggregates** (`structured`) are computed in code over item titles, matched as a whole word
   and case-insensitive. One kind asks for the first date (UTC) a term appears in a headline in
   the record. The other asks for the date in a given month with the most headlines mentioning a
   term, used only when the top day has at least twice the count of the runner-up.
7. **Abstain:** there are two kinds. False-premise questions are written from a bullet and kept
   only if an LLM finds headlines that contradict the premise and none that support it; the
   contradicting headlines are the evidence. Future-event questions repeat a verified point
   question at a month-end 45-150 days before the event.
8. **Manual review:** after reading every base question, I dropped 12 generated questions in
   `EXCLUDE` in `build.py`. They were recurring events that make "which happened first"
   ambiguous, a "change" that was only a promise, vague golds, and one premise that was absent
   rather than contradicted. I also fixed 2 golds whose aliases were really parts of one answer
   (`GOLD_OVERRIDE`).

LLM spend for this dataset: about **$3.02** (ledger rows tagged `dataset:iran_headlines`,
including prompt trials).

## Known issues

- **GDELT outage, 2025-06-14 17:45 to 2025-07-02 02:15 UTC.** GDELT's own master file list has
  no files for this period. A DOC API probe for 2025-06-20 also returned 0 articles. The stream
  therefore has **no items for most of the Twelve-Day War** (13-24 June 2025), including the US
  strikes of 22 June 2025. WCEP bullets from that period fail verification, so no question
  depends on them. Because of the gap, the record's first headline with "Midnight Hammer" is
  2025-07-08. The aggregate question about it is correct *for the record*, but it disagrees with
  real-world knowledge (22 June 2025). That makes it a deliberate leakage trap, so read it that way.
- Hourly sampling: only 1 of 4 quarter-hour files per hour is used, so about a quarter of
  GDELT's matching articles are in the stream. Small events can appear in only 1-2 headlines,
  and many point questions rest on 1-3 distinct headlines.
- Volume is very uneven: about 140-250 items/day in 2024-2025 and up to about 2,100/day in March
  2026, when the 2026 Iran war began. Body-only matches are capped, so they form a flat
  noise floor of about 3,600/month.
- WCEP dates and headline timestamps can differ by a day or two (for example, a Yemen event
  dated 8 Nov 2024 first appears in headlines on 10 Nov). Questions use the WCEP date. Evidence
  is searched from -1 to +2 days around it.
- Some GKG page titles are site boilerplate ("KVOO Story", outlet names) or partly non-English.
  They are kept as realistic noise.
- Only 1 change question and no as_of_state questions survived verification. The headline
  record rarely states both sides of a state change clearly.
- Leakage: many 2024-2025 facts are probably in grok-4.3's pretraining. 2026 facts are probably
  not. Compare with A0 `closed_book`. Point questions repeat the same text at every re-ask, and
  the future-event abstain questions reuse the text of a point question under a different
  `base_id`.
- Aggregates count headline copies, including syndicated ones. Answers are dates, not counts,
  to keep them robust.
