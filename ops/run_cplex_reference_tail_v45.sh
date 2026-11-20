#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${RUN_ID:?}" "${REFERENCE:?}" "${DIAGNOSTIC_ROOT:?}" "${MIP_ROOT:?}" "${CPLEX_BIN:?}"
cd "$REPO"
sat="$REPO/results/aglr/$RUN_ID"
root="$REPO/results/aglr/cplex-reference300-v45-20261120"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9
[[ ! -f "$root/COMPLETED" && ! -f "$root/FAILED" ]] || exit 0
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$root/FAILED"; exit 78' ERR
while systemctl is-active --quiet maxsat-sat-bound-search-v45.service; do
    sleep 15
done
runner=quick_scripts/analyze/run_cplex_reference_tail.py
python3 "$runner" run --cplex "$CPLEX_BIN" --results "$root" --round-seconds 21000
python3 "$runner" audit --results "$root" > "$root/independent-audit.json"
if ! python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["complete"])' "$root/audit.json"; then
    touch "$root/INCOMPLETE"
    exit 0
fi
for mode in reuse restart-assumptions; do
    candidate="$sat/$mode"
    if [[ ! -f "$candidate/hard-evaluation.json" ]]; then continue; fi
    args=()
    if [[ -f "$candidate/full-evaluation.json" ]]; then args+=(--followup "$candidate/followup"); fi
    level=hard
    if (( ${#args[@]} )); then level=full; fi
    python3 quick_scripts/analyze/compare_search_bounds.py --candidate "$candidate/hard" "${args[@]}" \
        --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" \
        --gurobi-json cont "$MIP_ROOT/cont.json" --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" \
        --cplex-tail "$root" --reference-pool "$root/$level-reference-pool.json" \
        --output "$root/$mode-$level-evaluation.json"
done
touch "$root/COMPLETED"
