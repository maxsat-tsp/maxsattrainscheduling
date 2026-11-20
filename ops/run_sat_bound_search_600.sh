#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${RUN_ID:?}" "${REFERENCE:?}" "${DIAGNOSTIC_ROOT:?}" "${MIP_ROOT:?}" "${CPLEX_BIN:?}" "${CPLEX_REFERENCE:?}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9
[[ ! -f "$root/COMPLETED" && ! -f "$root/FAILED" ]] || exit 0
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$root/FAILED"; exit 78' ERR
while systemctl is-active --quiet maxsat-cplex-reference300-v45-retry.service; do
    sleep 15
done

source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target
sat="$root/solver/sat_bound_search"
ddd="$root/solver/ddd"
if [[ ! -f "$root/preflight.json" ]]; then
    python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python-tests.log" 2>&1
    cargo test --release --locked --lib bound_search::tests -j 2 -- --test-threads=1 > "$root/rust-search-tests.log" 2>&1
    cargo test --release --locked --lib binary_objective_tests -j 2 -- --test-threads=1 > "$root/rust-objective-tests.log" 2>&1
    cargo test --release --locked --lib maxsat_ladder_sc::progress::tests -j 2 -- --test-threads=1 > "$root/rust-rc2-tests.log" 2>&1
    cargo test --release --locked --lib legacy_and_aglr_match_exhaustive_optimum_on_tiny_problem -j 2 -- --test-threads=1 > "$root/rust-legacy-tests.log" 2>&1
    cargo build --release --locked --bin sat_bound_search --bin ddd -j 2 > "$root/build.log" 2>&1
    mkdir -p "$root/solver"
    install "$CARGO_TARGET_DIR/release/sat_bound_search" "$sat"
    install "$CARGO_TARGET_DIR/release/ddd" "$ddd"
    python3 quick_scripts/analyze/validate_sat_bound_search_build.py --root "$root" --reference "$REFERENCE" \
        --threshold-policy upper --rc2-warmup-seconds 60 --threshold-session reuse
fi

common=(--reference "$REFERENCE" --diagnostic-root "$DIAGNOSTIC_ROOT")
runner=quick_scripts/analyze/run_sat_bound_search.py
selection=results/sat_research/v42_sat_bound_search_20261109/complete_snapshot.tar.gz
run_sat() {
    taskset -c 0,1,4,5 python3 "$runner" run "${common[@]}" --binary "$sat" \
        --build-manifest "$root/build_manifest.json" --threshold-policy upper \
        --rc2-warmup-seconds 60 --threshold-session reuse --timeout 600 --round-seconds 21000 \
        --selection-archive "$selection" "$@"
}
complete() {
    python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["complete"])' "$1"
}
run_sat --results "$root/hard"
if ! complete "$root/hard/audit.json"; then touch "$root/INCOMPLETE"; exit 0; fi
cplex=()
if [[ -f "$CPLEX_REFERENCE/COMPLETED" ]]; then cplex=(--cplex-tail "$CPLEX_REFERENCE"); fi
comparison() {
    python3 quick_scripts/analyze/compare_search_bounds.py --candidate "$root/hard" \
        --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" \
        --gurobi-json cont "$MIP_ROOT/cont.json" --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" \
        "${cplex[@]}" "$@"
}
comparison --output "$root/hard-evaluation.json" --reference-pool "$root/hard-reference-pool.json"

for method in BigM-Gurobi BigM-CPLEX CSOnet MaxSAT-Journal; do
    stage="$root/controls/$method"
    affinity=()
    if [[ "$method" == CSOnet || "$method" == MaxSAT-Journal ]]; then affinity=(taskset -c 0,1,4,5); fi
    "${affinity[@]}" python3 quick_scripts/analyze/run_long_baseline_cases.py --method "$method" \
        --candidate-manifest "$root/hard/manifest.json" --results "$stage" \
        --binary "$ddd" --cplex "$CPLEX_BIN" --cplex-reference "$CPLEX_REFERENCE" --round-seconds 21000
    if ! complete "$stage/audit.json"; then touch "$root/INCOMPLETE"; exit 0; fi
done
python3 quick_scripts/analyze/summarize_long_controls.py "$root"

if python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["newly_solved"])' "$root/hard/audit.json"; then
    run_sat --results "$root/followup" --followup "$root/hard"
    if [[ ! -f "$root/followup/followup_stopped.json" ]]; then
        if ! complete "$root/followup/audit.json"; then touch "$root/INCOMPLETE"; exit 0; fi
        comparison --followup "$root/followup" --output "$root/full-evaluation.json" \
            --reference-pool "$root/full-reference-pool.json"
    fi
fi
rm -f "$root/INCOMPLETE"
touch "$root/COMPLETED"
