#!/usr/bin/env bash
# Run only the objective/instance pairs frozen in the focus manifest.
set -euo pipefail
: "${FOCUS_MANIFEST:?Set FOCUS_MANIFEST to the frozen selection JSON}"
: "${BIN:?Set BIN to the release binary}"
RUN_ID="${RUN_ID:-focus-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
exec timeout --signal=TERM --kill-after=30 "${ROUND_LIMIT_SECONDS:-21600}s" \
    python3 quick_scripts/analyze/focused_experiments.py run \
    --manifest "$FOCUS_MANIFEST" --binary "$BIN" \
    --results "${RESULTS_ROOT:-results/aglr}/$RUN_ID" \
    --variant "${CORE_VARIANT:-orders-transitive}" \
    --timeout "${FOCUS_TIMEOUT_SECS:-120}" --ram-kb "${RAM_LIMIT_KB:-15000000}"
