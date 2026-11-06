#!/usr/bin/env bash
# Two backend workers; each worker runs one SAT case at a time.
set -euo pipefail
: "${BIN:?Set BIN to the locked release ddd binary}"
: "${SOLVER_MANIFEST:?Set SOLVER_MANIFEST to the recorded binary build manifest}"
: "${MINISAT_REFERENCE:?Set MINISAT_REFERENCE to an immutable audited campaign}"
: "${CADICAL_REFERENCE:?Set CADICAL_REFERENCE to an immutable audited campaign}"
RUN_ID="${RUN_ID:-backends300-20261106}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
exec python3 quick_scripts/analyze/compare_sat_backends.py run \
    --plan "${BACKEND_PLAN:-results/sat_research/cadical_300_20261106/plan.json}" \
    --binary "$BIN" --solver-manifest "$SOLVER_MANIFEST" \
    --minisat-reference "$MINISAT_REFERENCE" --cadical-reference "$CADICAL_REFERENCE" \
    --minisat-cpus "${MINISAT_CPUS:-0,1,4,5}" --cadical-cpus "${CADICAL_CPUS:-2,3,6,7}" \
    --ram-kb "${BACKEND_RAM_KB:-6000000}" --round-seconds "${ROUND_LIMIT_SECONDS:-21600}" \
    --results "${RESULTS_ROOT:-results/aglr}/$RUN_ID"
