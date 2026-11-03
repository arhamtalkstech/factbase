# fedreg: Federal Register sanctions, export-control and trade documents

Long, dense regulatory documents with amendments over time (knowledge updates): OFAC sanctions
actions and regulations, BIS export controls (Entity List etc.), presidential executive orders /
proclamations / national-emergency notices, and State Department sanctions notices.

Built by `uv run python -m factbase.datasets.fedreg.build` (code in `factbase/datasets/fedreg/`).
Raw downloads are cached in `data/raw/fedreg/` (`lists/*.json` API metadata, `text/<doc>.txt` raw text).

## Source and terms

- Federal Register API v1 (`https://www.federalregister.gov/api/v1/documents.json`, no key), queried
  month by month for 2024-11-01..2026-10-31 with `per_page=1000`, plus each document's `raw_text_url`.
  Federal Register content is a US government work in the public domain.
- Selection (title/abstract regex, see `build.py`):
  - every document with agency `foreign-assets-control-office` (OFAC) or `industry-and-security-bureau` (BIS);
  - presidential documents (`type=PRESDOCU`) whose **title** matches Iran, sanction, tariff, duties/duty,
    export, national emergenc(y/ies), import(s)/importation, Section 232/301, foreign terrorist organization,
    "threats to the United States by the Government of", situation in Syria, Venezuelan oil.
    Presidential documents have no abstract in the API, so only the title is used. Import/Section 232
    proclamations were added beyond the brief's keyword list because they are the tariff actions BIS
    documents refer to;
  - State Department documents whose title or abstract mentions Iran or sanctions.

## Items

783 items, 2024-11-01 .. 2026-10-30, one per document. `ts` = publication date
10:00:00Z. `id` = `fedreg:<document_number>`.

| Source | Items |
|---|---|
| BIS | 198 |
| OFAC | 358 |
| Presidential documents | 173 |
| State Department | 54 |

Item `text`: "<type> published in the Federal Register on <date> by <agency>: <title>." then the abstract,
then API metadata lines (executive order / proclamation number, signing date, effective date, the
document's DATES text, CFR parts affected, action, FR doc number and citation), then "Text excerpt:" with
the first ~2500 characters of substantive raw text. The excerpt skips the GPO header, the
agency/title header, the SUMMARY (already present as the abstract) and contact info, starting at
SUPPLEMENTARY INFORMATION where present; `[GRAPHIC]` placeholders, page markers and billing codes are
removed. Long documents end with "[...excerpt truncated]". `meta` holds the structured fields.

## Quiz

259 question instances, 92 base questions, ask dates in 24 months.

| Category | Instances |
|---|---|
| abstain | 21 |
| aggregate | 19 |
| as_of_state | 20 |
| change | 10 |
| multi_hop | 6 |
| ordering | 14 |
| point_old | 126 |
| point_recent | 43 |

| gold_source | Instances | Base |
|---|---|---|
| llm_from_source | 114 | 34 |
| structured | 145 | 58 |

Re-asks: point facts are asked at the first month-end after publication, then about +3, +6 and +12
months, and on 2026-10-31 where those fall in the window (`point_recent` if within 30 days, else
`point_old`). Aggregates, ordering, change and multi-hop questions are re-asked at 2-3 later dates.

### Structured gold (computed in `questions.py` from API metadata)

- Executive order number for a titled order, signing date of an EO, proclamation number.
- Publication date and effective date of named, uniquely titled rules/notices.
- Aggregates: OFAC documents per month (5 months); BIS rules with "Entity List" in the title in 2025;
  OFAC rules titled exactly "Iranian Transactions and Sanctions Regulations" in Aug-Oct 2026;
  presidential "Continuation of the National Emergency ..." notices in 2025.
- Ordering of two named documents.
- As-of state (knowledge updates): latest OFAC document whose title names the Iranian Transactions and
  Sanctions Regulations (5 as-of dates); latest BIS Entity List rule (5); latest version of OFAC Russian
  Harmful Foreign Activities Web General License 13 (13N -> 13O -> 13P); latest "Continuation of the National
  Emergency With Respect to Iran" notice (2). Gold is the publication date (or GL version).
- Change: effective date of the BIS Pakistan rule after its 2024-11-29 correction (gold parsed from the
  correction text); next Entity List rule after 28 March 2025; GL 13O -> 13P; OFAC September 2026 vs 2025 count.
- Multi-hop: days between Proclamation 11052 and the BIS polysilicon rule; days between EO 14203 and OFAC's
  ICC regulations; title/date of the proclamation named in BIS's 2026-10-14 "U.S. content" guidance.
- Abstain: questions about documents asked before they were published, and false premises (no Entity List
  rule in June 2025, no ITSR-titled rule in March 2025, no "Cuban Assets Control Regulations" rule in 2025,
  no Iran national-emergency notice in July 2025). Gold is a short note.

### LLM gold (`llm_questions.py`, grok-4.3 via `factbase.llm`, tag `dataset:fedreg`)

30 candidate items were picked round-robin across quarters and source groups (OFAC notices,
OFAC rules, BIS, presidential, State), skipping information-collection / advisory-committee / meeting /
correction notices, items whose (title, date) is not unique, and items with excerpts under 700 characters.
A writer call sees only the one item plus the titles/dates of similar-titled items and must anchor the
question by agency, type, title and exact publication date; it may not ask for dates/EO numbers (covered
by structured gold) or about truncated text. A separate verifier call sees the item, the Q/A and the
texts of up to 5 near-duplicate items and must confirm: answer stated in the item, answer correct and
complete, question picks out exactly one document, explicit date, not dependent on truncated text.
Generated 30, accepted 28. Rejected: 2 (incomplete answers).
`fedreg:2025-22656` is on a manual exclusion list (multi-part answer) in case it is ever selected.
Six accepted questions about OFAC/State sanctions-action notices are also asked ~2 months before the
notice was published as `abstain` instances.

## Known issues / fairness notes

- Many OFAC notices share the title "Notice of OFAC Sanctions Action(s)"; questions disambiguate by date.
  Several OFAC/State notices list names only in images (`[GRAPHIC]`), so their excerpt is thin.
- Excerpts are truncated at ~2500 characters; long SDN lists and rules are cut. Questions were
  written only from the visible text.
- `effective_on`, `signing_date` and numbers come from the API's current metadata. Where a later
  correction document (`C1-...`) exists in the stream, the original item omits the API effective date
  (it reflects the corrected value that was not yet public); the item still shows its original DATES text.
- Presidential documents are selected by title only, so the presidential subset is not the full set of
  presidential documents; aggregate questions avoid counting presidential documents except the
  "Continuation of the National Emergency" notices, which are all captured by the title filter.
- Some LLM questions are answerable from regulatory boilerplate or general knowledge (e.g. national
  emergencies are continued "for 1 year"; TDO renewals cite EAR section 766.24; EO numbers of well-known
  2025 tariff orders). Compare against the closed-book baseline.
- EO 14388 appears twice in the API (2026-02-25 and a 2026-04-09 republication); it is not used in questions.
- Questions that ask for "the most recent ... and its date" have only the date as gold.
