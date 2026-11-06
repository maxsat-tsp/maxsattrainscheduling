#!/usr/bin/env bash
# One resumable round; every method gets the same selected pairs and cutoff.
set -euo pipefail
: "${BIN:?Set BIN to the locked release ddd binary}"
: "${EXPORT_BIN:?Set EXPORT_BIN to the release export_lp binary}"
: "${CPLEX_BIN:?Set CPLEX_BIN to the licensed CPLEX executable}"
RUN_ID="${RUN_ID:-extended-300-20261106}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
exec timeout --signal=TERM --kill-after=20 "${ROUND_LIMIT_SECONDS:-21600}s" \
    python3 quick_scripts/analyze/extended_timeout_experiments.py run \
    --plan "${EXTENDED_PLAN:-results/sat_research/extended_300_20261106/plan.json}" \
    --binary "$BIN" --export-binary "$EXPORT_BIN" --cplex-binary "$CPLEX_BIN" \
    --results "${RESULTS_ROOT:-results/aglr}/$RUN_ID" \
    --timeout "${EXTENDED_TIMEOUT_SECS:-300}" \
    --round-seconds "${ROUND_LIMIT_SECONDS:-21600}" --ram-kb "${RAM_LIMIT_KB:-15000000}"
