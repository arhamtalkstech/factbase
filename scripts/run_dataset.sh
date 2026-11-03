#!/usr/bin/env bash
# Run every architecture on one dataset as three parallel chains, skipping architectures that already
# finished for this run (they have a .stats.json). Chain A runs factbase first so its fact extraction and
# digests land in the LLM cache; the ablations, fact_memory and rollups then reuse them.
# Usage: scripts/run_dataset.sh <dataset> <run_id> [extra args for factbase.eval.run]
set -euo pipefail
cd "$(dirname "$0")/.."
ds="$1"; run="$2"; shift 2
mkdir -p "results/runs/$run/$ds"
A="${CHAIN_A:-factbase,factbase_noagent,factbase_noraw,factbase_nostruct,factbase_nodigest,fact_memory,rollups}"
B="${CHAIN_B:-rolling_summary}"
C="${CHAIN_C:-closed_book,raw_rag,agentic_raw,recent_window}"
for chain in "$A" "$B" "$C"; do
  todo=""
  for a in ${chain//,/ }; do
    [ -f "results/runs/$run/$ds/$a.stats.json" ] || todo="${todo:+$todo,}$a"
  done
  [ -z "$todo" ] && continue
  name=$(echo "$todo" | cut -d, -f1)
  nohup uv run python -m factbase.eval.run --dataset "$ds" --arch "$todo" --run "$run" "$@" \
    >> "results/runs/$run/$ds/chain_$name.out" 2>&1 &
  echo "started $ds: $todo (pid $!)"
done
