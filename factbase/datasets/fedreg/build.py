"""Build the fedreg dataset: Federal Register sanctions / export-control / trade documents.

Run: uv run python -m factbase.datasets.fedreg.build
Sources: OFAC and BIS documents (all), presidential documents whose title is about sanctions,
tariffs/imports, exports or national emergencies, and State Department documents mentioning Iran
or sanctions. Gold is either computed in code from API metadata (structured) or written by an LLM
that reads one item and is then verified against the same item (llm_from_source).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from factbase.datasets.fedreg.fetch import RAW, fetch_lists, fetch_texts, load_text

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "fedreg"
DS = "fedreg"
WIN_START, WIN_END = "2024-11-01", "2026-10-31"
EXCERPT_CHARS = 2500

PRES_RE = re.compile(
    r"iran|sanction|tariff|duties|\bduty\b|export|national emergenc|\bimports?\b|importation|"
    r"section 232|section 301|foreign terrorist organization|threats? to the united states by the government of|"
    r"situation in syria|venezuelan oil",
    re.I,
)
STATE_RE = re.compile(r"iran|sanction", re.I)

AGENCY_LABEL = {
    "foreign-assets-control-office": "the Treasury Department's Office of Foreign Assets Control (OFAC)",
    "industry-and-security-bureau": "the Commerce Department's Bureau of Industry and Security (BIS)",
    "state-department": "the State Department",
    "executive-office-of-the-president": "the President (Executive Office of the President)",
}
PARENTS = {"treasury-department", "commerce-department"}


def select_docs() -> list[dict]:
    lists = fetch_lists()
    docs: dict[str, dict] = {}
    for k in ("ofac", "bis"):
        for d in lists[k]:
            docs[d["document_number"]] = d
    for d in lists["presdocu"]:
        if PRES_RE.search(d["title"] or ""):
            docs[d["document_number"]] = d
    for d in lists["state"]:
        if STATE_RE.search((d["title"] or "") + " " + (d["abstract"] or "")):
            docs[d["document_number"]] = d
    out = [d for d in docs.values() if WIN_START <= d["publication_date"] <= WIN_END]
    out.sort(key=lambda d: (d["publication_date"], d["document_number"]))
    return out


def agency_slugs(d: dict) -> list[str]:
    return [a.get("slug") or "" for a in d.get("agencies") or []]


def agency_text(d: dict) -> str:
    labels = []
    for a in d.get("agencies") or []:
        slug = a.get("slug") or ""
        if slug in PARENTS:
            continue
        labels.append(AGENCY_LABEL.get(slug, "the " + (a.get("name") or a.get("raw_name") or "unknown agency")))
    if not labels:
        labels = ["the " + (a.get("name") or "") for a in d.get("agencies") or []]
    return " and ".join(dict.fromkeys(labels))


def doc_kind(d: dict) -> str:
    if d["type"] == "Presidential Document":
        st = d.get("subtype") or "Document"
        return f"Presidential {st}" if st in ("Notice", "Memorandum", "Determination", "Document", "Other") else st
    return {"Rule": "Final rule", "Notice": "Notice", "Proposed Rule": "Proposed rule"}.get(d["type"], d["type"])


_WS = re.compile(r"\s+")


def _clean(s: str) -> str:
    s = re.sub(r"\[\[Page \d+\]\]", " ", s)
    s = s.replace("``", '"').replace("''", '"')
    return _WS.sub(" ", s).strip()


def excerpt(d: dict) -> str:
    """First ~2,500 characters of substantive text (headers, contacts and repeated summary removed)."""
    t = load_text(d["document_number"])
    m = re.search(r"\[FR Doc No: [^\]]+\]", t)
    if m:
        t = t[m.end():]
    # Drop trailing filing/billing boilerplate.
    t = re.split(r"\[FR Doc\.\s*\S+\s+Filed", t)[0]
    t = re.sub(r"\[GRAPHIC\]\s*\[TIFF OMITTED\]\s*\S+", " ", t)
    t = re.sub(r"BILLING CODE \S+", " ", t, flags=re.I)
    t = re.sub(r"-{5,}|_{5,}|={5,}", " ", t)
    if d["type"] == "Presidential Document":
        if "Title 3--" in t:
            t = t.split("Title 3--", 1)[1]
            t = re.sub(r"^\s*The President", " ", t)
        t = re.sub(r"Presidential Documents", " ", t)
        t = re.sub(r"Federal Register / Vol\. \d+ ?, No\. \d+ / \w+, \w+ \d+, \d{4} /", " ", t)
        return _truncate(_clean(t))
    split = "SUPPLEMENTARY INFORMATION:" in t
    if split:
        head, body = t.split("SUPPLEMENTARY INFORMATION:", 1)
        if not d.get("abstract"):
            sm = re.search(r"SUMMARY:(.*?)(?:DATES:|ADDRESSES:|FOR FURTHER INFORMATION CONTACT:|$)", head, re.S)
            if sm:
                body = "Summary: " + sm.group(1) + " " + body
        t = body
    t = _clean(t)
    # Drop the department / agency / title header that precedes the body.
    title = _clean(d["title"] or "")
    pos = t.find(title) if title else -1
    if not split and 0 <= pos < 800:
        t = t[pos + len(title):].strip()
    # OFAC boilerplate paragraph.
    t = re.sub(
        r"Electronic Availability The (SDN List|Specially Designated Nationals and Blocked Persons List) and "
        r"additional information concerning OFAC sanctions programs are available on OFAC's website: ?\S+",
        "",
        t,
    ).strip()
    t = re.sub(r"^Electronic Availability .*?(?:\(https?://\S+\)|https?://\S+)\.? ?", "", t).strip()
    return _truncate(t)


def _truncate(t: str) -> str:
    if len(t) <= EXCERPT_CHARS:
        return t
    cut = t[:EXCERPT_CHARS]
    sp = cut.rfind(" ")
    return cut[: sp if sp > EXCERPT_CHARS - 200 else EXCERPT_CHARS].rstrip() + " [...excerpt truncated]"


def cfr_text(d: dict) -> str:
    parts = sorted({(c.get("title"), c.get("part")) for c in d.get("cfr_references") or [] if c.get("part")},
                   key=lambda x: (x[0] or 0, int(re.sub(r"\D", "", str(x[1])) or 0)))
    if not parts:
        return ""
    by_title: dict = {}
    for t, p in parts:
        by_title.setdefault(t, []).append(str(p))
    return "; ".join(f"{t} CFR part{'s' if len(ps) > 1 else ''} {', '.join(ps)}" for t, ps in by_title.items())


def make_item(d: dict, corrected: bool = False) -> dict:
    """corrected=True: a later correction document exists. The API's effective_on then reflects the
    corrected value, which was not public on the original publication date, so it is left out."""
    kind = doc_kind(d)
    eff = None if corrected else d.get("effective_on")
    title = (d["title"] or "").strip().rstrip(".")
    bits = [f"{kind} published in the Federal Register on {d['publication_date']} by {agency_text(d)}: {title}."]
    if d.get("abstract"):
        bits.append(_clean(d["abstract"]))
    meta_bits = []
    if d.get("executive_order_number"):
        meta_bits.append(f"Executive Order number: {d['executive_order_number']}.")
    if d.get("proclamation_number"):
        meta_bits.append(f"Proclamation number: {d['proclamation_number']}.")
    if d.get("signing_date"):
        meta_bits.append(f"Signed: {d['signing_date']}.")
    if eff:
        meta_bits.append(f"Effective date: {eff}.")
    if d.get("dates"):
        meta_bits.append(f"Dates: {_clean(d['dates'])}")
    c = cfr_text(d)
    if c:
        meta_bits.append(f"CFR parts affected: {c}.")
    if d.get("action"):
        meta_bits.append(f"Action: {_clean(d['action']).rstrip('.')}.")
    meta_bits.append(f"FR Doc number: {d['document_number']}" + (f"; citation {d['citation']}." if d.get("citation") else "."))
    bits.append(" ".join(meta_bits))
    ex = excerpt(d)
    if ex:
        bits.append("Text excerpt: " + ex)
    text = "\n".join(b for b in bits if b)
    return {
        "id": f"{DS}:{d['document_number']}",
        "dataset": DS,
        "ts": f"{d['publication_date']}T10:00:00Z",
        "title": f"{title} ({kind}, {d['publication_date']})",
        "text": text,
        "source": "Federal Register",
        "url": d.get("html_url"),
        "meta": {
            "document_number": d["document_number"],
            "type": d["type"],
            "subtype": d.get("subtype"),
            "title": title,
            "publication_date": d["publication_date"],
            "effective_on": eff,
            "signing_date": d.get("signing_date"),
            "executive_order_number": d.get("executive_order_number"),
            "proclamation_number": d.get("proclamation_number"),
            "agencies": [s for s in agency_slugs(d) if s],
            "cfr_references": [{"title": c.get("title"), "part": c.get("part")} for c in d.get("cfr_references") or []],
            "citation": d.get("citation"),
            "correction_of": d.get("correction_of"),
        },
    }


def build_items() -> tuple[list[dict], list[dict]]:
    docs = select_docs()
    fetch_texts(docs)
    corrected = {d["document_number"][3:] for d in docs if d["document_number"].startswith("C1-")}
    items = [make_item(d, d["document_number"] in corrected) for d in docs]
    items.sort(key=lambda it: (it["ts"], it["id"]))
    return docs, items


def write_readme(items: list[dict], qs: list[dict], log: dict) -> None:
    from collections import Counter

    def table(c: Counter) -> str:
        return "\n".join(f"| {k} | {v} |" for k, v in sorted(c.items()))

    src = Counter()
    for it in items:
        a = it["meta"]["agencies"]
        src["OFAC" if "foreign-assets-control-office" in a else "BIS" if "industry-and-security-bureau" in a
            else "State Department" if "state-department" in a else "Presidential documents"] += 1
    bases = {q["base_id"]: q for q in qs}
    text = f"""# fedreg: Federal Register sanctions, export-control and trade documents

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

{len(items)} items, {items[0]['ts'][:10]} .. {items[-1]['ts'][:10]}, one per document. `ts` = publication date
10:00:00Z. `id` = `fedreg:<document_number>`.

| Source | Items |
|---|---|
{table(src)}

Item `text`: "<type> published in the Federal Register on <date> by <agency>: <title>." then the abstract,
then API metadata lines (executive order / proclamation number, signing date, effective date, the
document's DATES text, CFR parts affected, action, FR doc number and citation), then "Text excerpt:" with
the first ~{EXCERPT_CHARS} characters of substantive raw text. The excerpt skips the GPO header, the
agency/title header, the SUMMARY (already present as the abstract) and contact info, starting at
SUPPLEMENTARY INFORMATION where present; `[GRAPHIC]` placeholders, page markers and billing codes are
removed. Long documents end with "[...excerpt truncated]". `meta` holds the structured fields.

## Quiz

{len(qs)} question instances, {len(bases)} base questions, ask dates in {len({q['ask_at'][:7] for q in qs})} months.

| Category | Instances |
|---|---|
{table(Counter(q['category'] for q in qs))}

| gold_source | Instances | Base |
|---|---|---|
""" + "\n".join(f"| {k} | {v} | {sum(1 for b in bases.values() if b['gold_source'] == k)} |"
                for k, v in sorted(Counter(q['gold_source'] for q in qs).items())) + f"""

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

{log['candidates']} candidate items were picked round-robin across quarters and source groups (OFAC notices,
OFAC rules, BIS, presidential, State), skipping information-collection / advisory-committee / meeting /
correction notices, items whose (title, date) is not unique, and items with excerpts under 700 characters.
A writer call sees only the one item plus the titles/dates of similar-titled items and must anchor the
question by agency, type, title and exact publication date; it may not ask for dates/EO numbers (covered
by structured gold) or about truncated text. A separate verifier call sees the item, the Q/A and the
texts of up to 5 near-duplicate items and must confirm: answer stated in the item, answer correct and
complete, question picks out exactly one document, explicit date, not dependent on truncated text.
Generated {log['generated']}, accepted {log['accepted']}. Rejected: {len(log['rejected'])} (incomplete answers).
`fedreg:2025-22656` is on a manual exclusion list (multi-part answer) in case it is ever selected.
Six accepted questions about OFAC/State sanctions-action notices are also asked ~2 months before the
notice was published as `abstain` instances.

## Known issues / fairness notes

- Many OFAC notices share the title "Notice of OFAC Sanctions Action(s)"; questions disambiguate by date.
  Several OFAC/State notices list names only in images (`[GRAPHIC]`), so their excerpt is thin.
- Excerpts are truncated at ~{EXCERPT_CHARS} characters; long SDN lists and rules are cut. Questions were
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
"""
    (OUT / "README.md").write_text(text)


def main() -> None:
    from factbase import llm
    from factbase.datasets.fedreg.llm_questions import build_llm
    from factbase.datasets.fedreg.questions import Builder, build_structured

    OUT.mkdir(parents=True, exist_ok=True)
    docs, items = build_items()
    with open(OUT / "items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"items: {len(items)}")

    spent0 = llm.spent_usd(force=True)
    structured = build_structured(items)
    B = Builder(items)
    accepted, log = build_llm(items, B)
    qs = structured + B.qs
    qs.sort(key=lambda q: (q["ask_at"], q["qid"]))
    with open(OUT / "questions.jsonl", "w") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    (RAW / "llm_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    write_readme(items, qs, log)
    print(f"questions: {len(qs)} instances, {len({q['base_id'] for q in qs})} base; "
          f"llm candidates {log['candidates']}, generated {log['generated']}, accepted {log['accepted']}; "
          f"llm spend this run ${llm.spent_usd(force=True) - spent0:.3f}")


if __name__ == "__main__":
    main()
