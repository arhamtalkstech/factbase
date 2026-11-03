"""Compile the v7 evaluation (docs/preregistration_v7.md) into docs/v7_results.md from graded runs.

uv run python -m factbase.eval.v7_report
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from ..paths import RUNS_DIR, ledger_rows, read_jsonl
from .analyze import mcnemar

ROOT = Path(__file__).resolve().parents[2]
FEEDS = ["markets", "football", "sec_filings", "fedreg", "world_quiz", "iran_headlines"]
LME_TYPES = ["knowledge-update", "multi-session", "temporal-reasoning", "single-session-preference", "single-session-user",
             "single-session-assistant"]


def load(path: Path) -> dict:
    return {r["qid"]: r for r in read_jsonl(path)}


def lme(run: str, arch: str) -> dict:
    return load(RUNS_DIR / run / "longmemeval" / f"{arch}.graded.jsonl")


def feed(run: str, ds: str, arch: str) -> dict:
    return load(RUNS_DIR / run / ds / f"{arch}.graded.jsonl")


def acc(R: dict, keys) -> str:
    keys = list(keys)
    return f"{100 * sum(R[k]['correct'] for k in keys) / len(keys):.1f}%" if keys else "–"


def paired(A: dict, B: dict, keys) -> str:
    w = sum(1 for k in keys if A[k]["correct"] and not B[k]["correct"])
    l = sum(1 for k in keys if B[k]["correct"] and not A[k]["correct"])
    return f"+{w} / -{l} (p = {mcnemar(w, l):.2g})"


def lme_table(title: str, variants: list[tuple[str, dict]], base: dict, note: str = "") -> list[str]:
    keys = set(base)
    for _, R in variants:
        keys &= set(R)
    keys = sorted(keys)
    if not keys:
        return [f"### {title}", "", "not run", ""]
    L = [f"### {title}", "", note, ""] if note else [f"### {title}", ""]
    L.append("| variant | all | " + " | ".join(t.replace("single-session-", "ss-") for t in LME_TYPES) + " | abstain | vs baseline | in tok/q | USD/q |")
    L.append("|---" * (len(LME_TYPES) + 6) + "|")
    for name, R in variants:
        per = []
        for t in LME_TYPES:
            ks = [k for k in keys if R[k]["question_type"] == t and not R[k]["abst"]]
            per.append(f"{sum(R[k]['correct'] for k in ks)}/{len(ks)}")
        ab = [k for k in keys if R[k]["abst"]]
        vs = "–" if R is base else paired(R, base, keys)
        tin = sum(R[k].get("tokens_in", 0) for k in keys) / len(keys)
        usd = sum(R[k].get("usd", 0) for k in keys) / len(keys)
        L.append(f"| {name} | **{acc(R, keys)}** | " + " | ".join(per) + f" | {sum(R[k]['correct'] for k in ab)}/{len(ab)} | {vs} | {tin:.0f} | {usd:.4f} |")
    L += ["", f"n = {len(keys)} questions.", ""]
    return L


def feed_summary(rows: list[dict]) -> tuple:
    n = len(rows)
    return (100 * sum(r["correct"] for r in rows) / n, sum(r["tokens_in"] for r in rows) / n, sum(r["usd"] for r in rows) / n)


def cache_share(prefix: str) -> float:
    i = c = 0
    for r in ledger_rows():
        if r["tag"].startswith(prefix):
            i += r["in"]
            c += r["cached"]
    return c / i if i else 0.0


def main() -> None:
    L = ["# v7 results", "", "Evaluation of the layered additions, as pre-registered in [`preregistration_v7.md`](preregistration_v7.md).",
         "Layers and switches are described in [`layers.md`](layers.md). All answers by grok-4.3 at reasoning effort low.", ""]

    L += [
        "## Summary", "",
        "| Pre-registered hypothesis | Result |", "|---|---|",
        "| H7.1 v7u beats v6u on the interleaved channel, and removing threads hurts | v7u 89.2% against 84.2% (+8/-2, p = 0.11, not significant). Removing threads costs one question (88.3%). **Threads are not the reason.** Interleaving barely hurts any design: v6u 85.7% to 84.0%, v7u_best 89.1% to 89.1% on the same questions. |",
        "| H7.2 the profile helps preference questions | Dev: 8/10 against 5/10 without it. Test: 15/20 with or without it. **Not confirmed**; the dev effect was small-sample noise. |",
        "| H7.3 conflict resolution helps knowledge updates | Test: 55/61 with, 55/61 without. **Not confirmed.** |",
        "| H7.4 offload cuts input tokens by 15%+ at most 1 point lost | Tokens +3%, cost +24%, prompt-cache share 38% to 30%. **Refuted**: agent loops are about 3 calls, too short to benefit, and rewriting history breaks caching. |",
        "| H7.5 a search budget of 6 cuts cost and latency | The budget almost never bound. **No effect.** |",
        "| H7.6 typed priority ranking is within 2 points | **Confirmed** (no measurable effect). |",
        "| H7.7 v7u is at least as accurate as v6u on the test split | **Confirmed**: 86.4% against 82.3% (+32/-15, p = 0.019), and cheaper. |",
        "",
        "What actually improved the system: asking the extractor for a topic, a memory type and a priority for every fact "
        "(extraction v2). With nothing else changed, LongMemEval-S test accuracy rose from 82.3% to 87.2% (p = 0.008) at lower "
        "cost per question. The other layers stay available as switches for auditability and human review, where accuracy was "
        "not the goal: the conflict log records every supersession decision, and the profile and thread views are readable "
        "Markdown with fact ids. On fact and market feeds no v7 layer helped; the v6 design stays the recommendation there.",
        "",
    ]

    # ---- conversations
    L += ["## Conversations (LongMemEval-S)", ""]
    base_dev = lme("lme_v6udev", "factbase_v6u")
    dev = [("factbase_v6u (baseline)", base_dev), ("factbase_v7u (all layers)", lme("lme_v7dev", "factbase_v7u"))]
    for a in ["no_threads", "no_offload", "no_profile", "no_conflicts", "no_typed", "no_budget"]:
        dev.append((f"v7u without {a[3:]}", lme("lme_v7dev", f"factbase_v7u_{a}")))
    L += lme_table("Dev split, leave-one-out (attribution only, small n)", dev, base_dev)

    base_test = lme("lme_v6utest", "factbase_v6u")
    test = [("factbase_v6u (baseline)", base_test), ("factbase_v7u_best (chosen on dev)", lme("lme_v7test", "factbase_v7u_best"))]
    L += lme_table("Test split (run once, configuration fixed on dev)", test, base_test)
    attr = [("factbase_v6u (baseline)", base_test), ("factbase_v7u_best", lme("lme_v7test", "factbase_v7u_best")),
            ("v7u_best without profile", lme("lme_v7test", "factbase_v7u_best_no_profile")),
            ("v7u_best without conflicts", lme("lme_v7test", "factbase_v7u_best_no_conflicts")),
            ("extraction v2 only (no profile, conflicts, typed ranking)", lme("lme_v7test", "factbase_v7u_extract_only"))]
    L += lme_table(
        "Test split attribution (run after the pre-registered test result; selection among these is post hoc)", attr, base_test,
        "The gain comes from the richer extraction itself (topic, memory type and priority requested for every fact). The "
        "profile, conflict resolution and priority ranking add no measurable accuracy on 413 questions; the extraction-only "
        "variant is the cheapest and is not significantly different from v7u_best.",
    )

    inter_base = lme("lme_inter", "factbase_v6u")
    inter = [("factbase_v6u (baseline)", inter_base), ("agentic_sql_v6 (no facts)", lme("lme_inter", "agentic_sql_v6")),
             ("factbase_v7u (all layers)", lme("lme_inter", "factbase_v7u")), ("v7u without threads", lme("lme_inter", "factbase_v7u_no_threads")),
             ("factbase_v7u_best", lme("lme_inter", "factbase_v7u_best"))]
    L += lme_table("Interleaved channel (120 test questions, same-day sessions mixed message by message, no session labels)",
                   inter, inter_base)

    # ---- feeds
    L += ["## Feeds", "", "### 360-question stratified sample of the six fact datasets", "",
          "| variant | accuracy | vs baseline | input tokens/q | USD/q |", "|---|---|---|---|---|"]
    base = {d: feed("v6facts", d, "agentic_sql_v6") for d in FEEDS}
    for name, run, arch in [("agentic_sql_v6 (baseline)", "v6facts", "agentic_sql_v6"), ("agentic_sql_v7f (offload + budget)", "v7feeds", "agentic_sql_v7f"),
                            ("v7f without offload", "v7feeds", "agentic_sql_v7f_no_offload"), ("v7f without budget", "v7feeds", "agentic_sql_v7f_no_budget")]:
        R = {d: feed(run, d, arch) for d in FEEDS}
        rows = [r for d in FEEDS for r in R[d].values()]
        if not rows:
            continue
        a, tin, usd = feed_summary(rows)
        if run == "v6facts":
            vs = "–"
        else:
            w = sum(1 for d in FEEDS for q in R[d] if q in base[d] and R[d][q]["correct"] and not base[d][q]["correct"])
            l = sum(1 for d in FEEDS for q in R[d] if q in base[d] and base[d][q]["correct"] and not R[d][q]["correct"])
            vs = f"+{w} / -{l} (p = {mcnemar(w, l):.2g})"
        L.append(f"| {name} | {a:.1f}% | {vs} | {tin:.0f} | {usd:.4f} |")
    L += ["", f"Share of input tokens served from the prompt cache: agentic_sql_v6 {100 * cache_share('mem:agentic_sql_v6:'):.0f}%, "
          f"agentic_sql_v7f {100 * cache_share('mem:agentic_sql_v7f:'):.0f}%. Offload rewrites earlier messages, which breaks the cached prefix.", ""]
    L += ["### Held-out feeds", "", "| dataset | agentic_sql_v6 | agentic_sql_v7f |", "|---|---|---|"]
    for d in ["quakes", "weather"]:
        b, v = feed("heldout_v6", d, "agentic_sql_v6"), feed("v7heldout", d, "agentic_sql_v7f")
        keys = [k for k in v if k in b]
        if keys:
            L.append(f"| {d} | {acc(b, keys)} | {acc(v, keys)} |")
    L.append("")
    b, v = feed("v7news", "world_quiz", "agentic_sql_v6"), feed("v7news", "world_quiz", "factbase_v7f")
    keys = [k for k in v if k in b]
    if keys:
        L += ["### News storylines (world_quiz, 265 questions)", "", "| variant | accuracy | vs agentic_sql_v6 |", "|---|---|---|",
              f"| agentic_sql_v6 | {acc(b, keys)} | – |", f"| factbase_v7f (facts with threads, types, conflicts) | {acc(v, keys)} | {paired(v, b, keys)} |", ""]
    (ROOT / "docs" / "v7_results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
