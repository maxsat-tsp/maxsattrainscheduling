#!/usr/bin/env bash
# Measure the candidate once; reuse the four complete, audited baseline runs.
set -euo pipefail
: "${EXTENDED_REFERENCE:?Set EXTENDED_REFERENCE to the completed 300-second campaign}"
: "${BIN:?Set BIN to the new release ddd binary}"
: "${EXPORT_BIN:?Set EXPORT_BIN to the release export_lp binary}"
: "${CPLEX_BIN:?Set CPLEX_BIN to the licensed CPLEX executable}"
RUN_ID="${RUN_ID:-mincore300-20261106}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
trial_root="${RESULTS_ROOT:-results/aglr}/$RUN_ID"
if [[ ! -f "$trial_root/plan.json" ]]; then
    python3 quick_scripts/analyze/extended_timeout_experiments.py candidate-plan \
        --reference-results "$EXTENDED_REFERENCE" --output "$trial_root/plan.json"
fi
exec timeout --signal=TERM --kill-after=20 "${ROUND_LIMIT_SECONDS:-21600}s" \
    python3 quick_scripts/analyze/extended_timeout_experiments.py run \
    --plan "$trial_root/plan.json" --reference-results "$EXTENDED_REFERENCE" \
    --binary "$BIN" --export-binary "$EXPORT_BIN" --cplex-binary "$CPLEX_BIN" \
    --results "$trial_root" --timeout 300 \
    --round-seconds "${ROUND_LIMIT_SECONDS:-21600}" --ram-kb "${RAM_LIMIT_KB:-15000000}"
