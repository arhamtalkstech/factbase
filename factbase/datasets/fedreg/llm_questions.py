"""LLM-from-source quiz for fedreg: one item -> one question, then a separate verification pass.

The writer sees only the one item (plus titles/dates of similar items so it can disambiguate).
The verifier sees the same item, the proposed Q/A and the text of near-duplicate items, and must
confirm the answer is stated in the item and the question picks out exactly one document.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from datetime import date

from factbase import llm
from factbase.datasets.fedreg.questions import Builder, WIN_END, long_date, month_end, point_category, reask_dates

TAG = "dataset:fedreg"
N_CANDIDATES = 30
SEED = 20261102

# Accepted by the verifier but dropped on manual review (reason in evals/fedreg/README.md).
EXCLUDE = {"fedreg:2025-22656"}
BAD_ALIAS = re.compile(r"^(Entity|Individual|Vessel) \d+$", re.I)

SKIP_TITLE = re.compile(r"Agency Information Collection|Technical Advisory Committee|Sunshine Act|Public Briefing|"
                        r"Meeting|Correction", re.I)

GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {"type": "boolean"},
        "question": {"type": "string"},
        "answer": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "answer_type": {"type": "string", "enum": ["text", "number", "date"]},
        "evidence_quote": {"type": "string"},
    },
    "required": ["usable", "question", "answer", "aliases", "answer_type", "evidence_quote"],
    "additionalProperties": False,
}

VER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_stated_in_item": {"type": "boolean"},
        "answer_correct": {"type": "boolean"},
        "question_identifies_one_document": {"type": "boolean"},
        "self_contained_with_explicit_date": {"type": "boolean"},
        "not_dependent_on_truncated_text": {"type": "boolean"},
        "corrected_answer": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["answer_stated_in_item", "answer_correct", "question_identifies_one_document",
                 "self_contained_with_explicit_date", "not_dependent_on_truncated_text", "corrected_answer", "reason"],
    "additionalProperties": False,
}

GEN_SYSTEM = """You write one quiz question from ONE Federal Register document for a memory benchmark.
Rules:
- The answer must be stated explicitly in the document text shown. Never use outside knowledge.
- Ask about substance: what the action does, which country/program it concerns, which entities, persons or
  vessels are named, which executive order or authority it relies on, how many entities were added (only if the
  text states the number), what a general license authorizes, who signed it, etc. Do NOT ask for the publication
  date, effective date, executive order number or proclamation number of this document (covered elsewhere).
- The question must be self-contained and pick out this one document unambiguously: name the issuing agency,
  the document type, its title (or a distinctive description if the title is generic, e.g. "Notice of OFAC
  Sanctions Action") and its exact publication date. Several other documents have similar titles (listed
  below); make sure your question could not be about them.
- The answer must be short (at most ~12 words) and exact: a name, number, country, program tag, or short phrase.
- Do not ask about anything near the "[...excerpt truncated]" marker, and do not ask for counts of list entries
  if the list is cut off. Do not ask questions whose answer is merely the title.
- Give 0-4 aliases (other acceptable phrasings of the same answer).
- evidence_quote: copy the exact sentence(s) from the text that contain the answer.
- If the document has no substantive, checkable fact (e.g. only boilerplate, image placeholders), set usable=false."""

VER_SYSTEM = """You verify a quiz question written from ONE Federal Register document.
You get the document text (the only valid source), the question and proposed answer, and texts of other documents
with similar titles that a reader would also have seen. Check strictly:
- answer_stated_in_item: the answer is explicitly supported by the document text (not inferred, not outside knowledge).
- answer_correct: the proposed answer is a correct and complete answer to the question. If it is wrong or
  incomplete, give the correct short answer in corrected_answer (else repeat the answer).
- question_identifies_one_document: given the agency, type, title/description and publication date in the
  question, exactly one document (this one) fits, and none of the similar documents would give a different answer.
- self_contained_with_explicit_date: no relative time words; the publication date is stated explicitly.
- not_dependent_on_truncated_text: the answer would not change if the text after "[...excerpt truncated]" were known
  (e.g. counting a list that is cut off fails this).
Give a one-sentence reason."""


def _toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def similar_items(it: dict, items: list[dict], k: int = 15) -> list[dict]:
    t = _toks(it["meta"]["title"])
    scored = []
    for o in items:
        if o["id"] == it["id"]:
            continue
        ot = _toks(o["meta"]["title"])
        j = len(t & ot) / max(1, len(t | ot))
        if j >= 0.5:
            gap = abs((date.fromisoformat(o["meta"]["publication_date"]) - date.fromisoformat(it["meta"]["publication_date"])).days)
            scored.append((-(j >= 0.99), gap, o))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [o for _, _, o in scored[:k]]


def group_of(m: dict) -> str:
    a = m["agencies"]
    if "foreign-assets-control-office" in a:
        return "ofac_rule" if m["type"] != "Notice" else "ofac_notice"
    if "industry-and-security-bureau" in a:
        return "bis"
    if "state-department" in a:
        return "state"
    return "pres"


def select_candidates(items: list[dict]) -> list[dict]:
    key_count = defaultdict(int)
    for it in items:
        key_count[(it["meta"]["title"], it["meta"]["publication_date"])] += 1
    pool = []
    for it in items:
        m = it["meta"]
        if SKIP_TITLE.search(m["title"]) or m.get("correction_of") or m["document_number"].startswith("C1-"):
            continue
        if key_count[(m["title"], m["publication_date"])] > 1:
            continue
        ex = it["text"].split("Text excerpt:", 1)[-1]
        if len(ex) < 700:
            continue
        pool.append(it)
    rng = random.Random(SEED)
    buckets = defaultdict(list)
    for it in pool:
        d = date.fromisoformat(it["meta"]["publication_date"])
        q = (d.year, (d.month - 1) // 3)
        buckets[(q, group_of(it["meta"]))].append(it)
    for v in buckets.values():
        rng.shuffle(v)
    quarters = sorted({k[0] for k in buckets})
    groups = ["ofac_notice", "bis", "pres", "ofac_rule", "state"]
    chosen: list[dict] = []
    # Round-robin over quarters and groups so candidates spread across time and sources.
    while len(chosen) < N_CANDIDATES:
        progressed = False
        for g in groups:
            for q in quarters:
                if len(chosen) >= N_CANDIDATES:
                    break
                b = buckets.get((q, g))
                if b:
                    chosen.append(b.pop())
                    progressed = True
        if not progressed:
            break
    return sorted(chosen, key=lambda it: it["ts"])


def generate(it: dict, items: list[dict]) -> dict:
    sims = similar_items(it, items)
    sim_list = "\n".join(f"- {o['meta']['publication_date']} | {o['meta']['title']}" for o in sims) or "(none)"
    user = (f"DOCUMENT (item id {it['id']}):\n{it['text']}\n\nOTHER DOCUMENTS WITH SIMILAR TITLES (date | title):\n"
            f"{sim_list}\n\nWrite the question.")
    return llm.ask_json(GEN_SYSTEM, user, GEN_SCHEMA, tag=TAG)


def verify(it: dict, items: list[dict], g: dict) -> dict:
    sims = similar_items(it, items, k=5)
    sim_txt = "\n\n".join(f"[{o['id']}]\n{o['text'][:1500]}" for o in sims) or "(none)"
    user = (f"DOCUMENT:\n{it['text']}\n\nQUESTION: {g['question']}\nPROPOSED ANSWER: {g['answer']}\n"
            f"EVIDENCE QUOTE: {g['evidence_quote']}\n\nSIMILAR DOCUMENTS:\n{sim_txt}")
    return llm.ask_json(VER_SYSTEM, user, VER_SCHEMA, tag=TAG)


def build_llm(items: list[dict], B: Builder, n_abstain: int = 6) -> tuple[list[dict], dict]:
    cands = select_candidates(items)
    gens = llm.pmap(lambda it: generate(it, items), cands, workers=8)
    pairs = [(it, g) for it, g in zip(cands, gens) if isinstance(g, dict) and g.get("usable") and g.get("question")]
    vers = llm.pmap(lambda p: verify(p[0], items, p[1]), pairs, workers=8)
    log = {"candidates": len(cands), "generated": len(pairs), "accepted": 0, "rejected": []}
    accepted = []
    for (it, g), v in zip(pairs, vers):
        if not isinstance(v, dict):
            log["rejected"].append({"id": it["id"], "reason": f"verify error {v}"})
            continue
        ok = all(v.get(k) for k in ("answer_stated_in_item", "answer_correct", "question_identifies_one_document",
                                     "self_contained_with_explicit_date", "not_dependent_on_truncated_text"))
        if not ok:
            log["rejected"].append({"id": it["id"], "q": g["question"], "a": g["answer"], "reason": v.get("reason")})
            continue
        if it["id"] in EXCLUDE:
            log["rejected"].append({"id": it["id"], "q": g["question"], "a": g["answer"], "reason": "manual exclusion"})
            continue
        accepted.append((it, g))
    log["accepted"] = len(accepted)
    for it, g in accepted:
        fact = date.fromisoformat(it["meta"]["publication_date"])
        gold = [g["answer"]] + [a for a in g.get("aliases", []) if a and a != g["answer"] and not BAD_ALIAS.match(a)]
        tol = 0.0 if g["answer_type"] == "number" else None
        b = B.new_base("L")
        for a in reask_dates(fact):
            B.emit(b, a, g["question"], gold, g["answer_type"], point_category(a, fact), fact, [it["id"]],
                   gold_source="llm_from_source", tol=tol)
    # Abstain: the same kind of question asked before the document existed.
    rng = random.Random(SEED + 1)
    # Only designation / sanctions-action notices: their specific content is not stated in any earlier item.
    early = [(it, g) for it, g in accepted if it["meta"]["publication_date"] >= "2025-03-01"
             and "Sanctions Action" in it["meta"]["title"]]
    for it, g in rng.sample(early, min(n_abstain, len(early))):
        pd = date.fromisoformat(it["meta"]["publication_date"])
        ask = month_end(pd.year, pd.month - 2)
        b = B.new_base("L")
        B.emit(b, ask, g["question"],
               [f"Not in the record as of {long_date(ask)}; the document was only published on {pd.isoformat()}."],
               "abstain", "abstain", pd, [], gold_source="llm_from_source")
    return accepted, log
