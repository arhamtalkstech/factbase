from __future__ import annotations

from pathlib import Path

from .base import Memory


def _classes() -> dict[str, type[Memory]]:
    from . import baselines

    out: dict[str, type[Memory]] = {
        "closed_book": baselines.ClosedBook,
        "recent_window": baselines.RecentWindow,
        "rolling_summary": baselines.RollingSummary,
        "raw_rag": baselines.RawRAG,
        "agentic_raw": baselines.AgenticRaw,
    }
    from . import layered, structured

    out.update(structured.CLASSES)
    out.update(layered.CLASSES)
    return out


_V6 = {"compute": True, "records_all": True, "max_steps": 10, "enforce_compute": True, "abstain_guard": True, "rules_v6": True}
_V7U = {**_V6, "facts": True, "digests": False, "extract_speaker_only": True, "extract_v2": True, "threads": True, "typed": True,
        "profile": True, "conflicts": True, "offload": True, "budget": 6}
_V7F = {**_V6, "facts": False, "digests": False, "per_feed_card": True, "extract_v2": False, "threads": False, "typed": False,
        "profile": False, "conflicts": False, "offload": True, "budget": 6}

# Named variants: arch name -> (class name, fixed config)
VARIANTS: dict[str, tuple[str, dict]] = {
    "factbase_noagent": ("factbase", {"agent": False}),
    "factbase_noraw": ("factbase", {"raw": False}),
    "factbase_nostruct": ("factbase", {"struct": False}),
    "factbase_nodigest": ("factbase", {"digests": False}),
    # v2 (designed after reading v1 failures): every raw item is a SQL row, python compute tool, schema card, routing prompt
    "factbase_v2": ("factbase", {"compute": True, "records_all": True, "max_steps": 10}),
    # control: the same v2 agent over raw records only, no extracted facts and no digests
    "agentic_sql": ("factbase", {"compute": True, "records_all": True, "facts": False, "digests": False, "max_steps": 10}),
    # v3: v2 + analytic questions must call sql/python before answering
    "factbase_v3": ("factbase", {"compute": True, "records_all": True, "max_steps": 10, "enforce_compute": True}),
    "agentic_sql_v3": ("factbase", {"compute": True, "records_all": True, "facts": False, "digests": False, "max_steps": 10, "enforce_compute": True}),
    # v4: v3 + abstentions need two differently phrased hybrid searches first
    "factbase_v4": ("factbase", {"compute": True, "records_all": True, "max_steps": 10, "enforce_compute": True, "abstain_guard": True}),
    "agentic_sql_v4": ("factbase", {"compute": True, "records_all": True, "facts": False, "digests": False, "max_steps": 10, "enforce_compute": True, "abstain_guard": True}),
    # v5 (exploratory, designed after reading Iran failures): v4 + calibrated answer rules
    "agentic_sql_v5": ("factbase", {"compute": True, "records_all": True, "facts": False, "digests": False, "max_steps": 10, "enforce_compute": True, "abstain_guard": True, "calibrated": True}),
    # v6: v4 (compute enforced + abstain guard) with the unified answer policy ANSWER_RULES_V6
    "agentic_sql_v6": ("factbase", {"compute": True, "records_all": True, "facts": False, "digests": False, "max_steps": 10, "enforce_compute": True, "abstain_guard": True, "rules_v6": True}),
    # v6 + per-feed schema card (matters only when one memory holds several feeds)
    "agentic_sql_v6f": ("factbase", {"compute": True, "records_all": True, "facts": False, "digests": False, "max_steps": 10, "enforce_compute": True, "abstain_guard": True, "rules_v6": True, "per_feed_card": True}),
    # v6 + extracted facts from the speaker's own turns (conversations), no digests
    "factbase_v6u": ("factbase", {"compute": True, "records_all": True, "facts": True, "digests": False, "max_steps": 10, "enforce_compute": True, "abstain_guard": True, "rules_v6": True, "extract_speaker_only": True}),
    # ---- v7: layered additions (see memories/layered.py), each switchable for leave-one-out evaluation
    # conversations: v6u + topic threads, typed/priority facts, standing profile, non-destructive conflicts, offload, budget
    "factbase_v7u": ("factbase_v7", {**_V7U}),
    "factbase_v7u_no_threads": ("factbase_v7", {**_V7U, "threads": False}),
    "factbase_v7u_no_typed": ("factbase_v7", {**_V7U, "typed": False}),
    "factbase_v7u_no_profile": ("factbase_v7", {**_V7U, "profile": False}),
    "factbase_v7u_no_conflicts": ("factbase_v7", {**_V7U, "conflicts": False}),
    "factbase_v7u_no_offload": ("factbase_v7", {**_V7U, "offload": False}),
    "factbase_v7u_no_budget": ("factbase_v7", {**_V7U, "budget": None}),
    # chosen on the dev split: keep profile, conflicts, typed ranking, budget; drop threads and offload
    "factbase_v7u_best": ("factbase_v7", {**_V7U, "threads": False, "offload": False}),
    # recommended for conversations after the test-split attribution: v6u + extraction v2 only
    "factbase_v7c": ("factbase_v7", {**_V7U, "threads": False, "offload": False, "profile": False, "conflicts": False, "typed": False}),
    # test-split attribution of factbase_v7u_best
    "factbase_v7u_best_no_profile": ("factbase_v7", {**_V7U, "threads": False, "offload": False, "profile": False}),
    "factbase_v7u_best_no_conflicts": ("factbase_v7", {**_V7U, "threads": False, "offload": False, "conflicts": False}),
    "factbase_v7u_extract_only": ("factbase_v7", {**_V7U, "threads": False, "offload": False, "profile": False, "conflicts": False, "typed": False}),
    # feeds, lean: v6f + offload + budget + read_records (no extracted facts)
    "agentic_sql_v7f": ("factbase_v7", {**_V7F}),
    "agentic_sql_v7f_no_offload": ("factbase_v7", {**_V7F, "offload": False}),
    "agentic_sql_v7f_no_budget": ("factbase_v7", {**_V7F, "budget": None}),
    # feeds, full: facts v2 with storyline threads, types, conflicts + offload + budget
    "factbase_v7f": ("factbase_v7", {**_V7F, "facts": True, "extract_v2": True, "threads": True, "typed": True, "conflicts": True}),
    # v2 without structured meta: SQL rows carry only date/source/title/text
    "factbase_v2_nostruct": ("factbase", {"compute": True, "records_all": True, "struct": False, "max_steps": 10}),
}


def build(arch: str, dataset: str, workdir: Path, **cfg) -> Memory:
    classes = _classes()
    if arch in VARIANTS:
        base, fixed = VARIANTS[arch]
        m = classes[base](dataset, workdir, **{**fixed, **cfg})
        m.name = arch
        return m
    return classes[arch](dataset, workdir, **cfg)


def names() -> list[str]:
    return list(_classes()) + list(VARIANTS)
