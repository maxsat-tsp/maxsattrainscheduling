#!/usr/bin/env bash
# One controlled round; the watchdog includes screen, promote, full and repeats.
set -euo pipefail
export CYCLE_ID="${CYCLE_ID:-core-cycle-$(date -u +%Y%m%dT%H%M%SZ)}"
export RESULTS_ROOT="${RESULTS_ROOT:-results/aglr}"
if [[ "${CORE_CYCLE_BOUNDED:-0}" != 1 ]]; then
    export CORE_CYCLE_BOUNDED=1
    exec timeout --signal=TERM --kill-after=30 "${ROUND_LIMIT_SECONDS:-21600}s" bash "$0"
fi
RUN_ID="$CYCLE_ID-screen" bash run_maxsat_core_experiments.sh screen
RUN_ID="$CYCLE_ID-promote" bash run_maxsat_core_experiments.sh promote
selection_exit=0
selected="$(python3 quick_scripts/analyze/select_core_variant.py "$RESULTS_ROOT/$CYCLE_ID-promote")" || selection_exit=$?
if (( selection_exit == 0 )); then
    export CORE_VARIANT="$selected"
    RUN_ID="$CYCLE_ID-candidate" bash run_maxsat_core_experiments.sh candidate
    if python3 - "$RESULTS_ROOT/$CYCLE_ID-candidate/aglr_audit.json" <<'PY'
import json, sys
audit = json.load(open(sys.argv[1]))
sys.exit(0 if not audit["errors"] and (audit.get("gate") or {}).get("coverage_passed") else 1)
PY
    then
        FULL_DIR="$RESULTS_ROOT/$CYCLE_ID-candidate" RUN_ID="$CYCLE_ID-confirm" \
            bash run_maxsat_core_experiments.sh confirm
    fi
elif (( selection_exit == 1 )); then
    echo "No candidate preserves development coverage; inspect core_selection.json before the next round."
else
    echo "Selection failed; stop the round and inspect the error." >&2
    exit "$selection_exit"
fi
