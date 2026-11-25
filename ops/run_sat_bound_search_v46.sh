#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${RUN_ID:?}" "${REFERENCE:?}" "${DIAGNOSTIC_ROOT:?}" "${MIP_ROOT:?}" "${CPLEX_REFERENCE:?}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9
[[ ! -f "$root/COMPLETED" && ! -f "$root/FAILED" ]] || exit 0
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$root/FAILED"; exit 78' ERR
rm -f "$root/INCOMPLETE"
deadline=$(( $(date +%s) + 21600 ))
remaining() { printf '%s\n' "$(( deadline - $(date +%s) - 90 ))"; }
incomplete() {
    touch "$root/INCOMPLETE"
    if [[ "${RESUME_PHASES:-0}" == 1 ]]; then exit 75; fi
    exit 0
}
if [[ -n "${AFTER_UNIT:-}" ]]; then
    while systemctl is-active --quiet "$AFTER_UNIT"; do
        if (( $(remaining) < 700 )); then incomplete; fi
        sleep 15
    done
fi

source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target

session="${THRESHOLD_SESSION:-reuse-offset}"
cutoff="${SEARCH_TIMEOUT_SECS:-600}"
reserve=$((cutoff + 100))
binary="$root/solver/sat_bound_search"
if [[ ! -f "$root/preflight.json" ]]; then
    python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python-tests.log" 2>&1
    cargo test --release --locked --lib bound_search::tests -j 2 -- --test-threads=1 > "$root/rust-search-tests.log" 2>&1
    cargo test --release --locked --lib binary_objective_tests -j 2 -- --test-threads=1 > "$root/rust-objective-tests.log" 2>&1
    cargo test --release --locked --lib maxsat_ladder_sc::progress::tests -j 2 -- --test-threads=1 > "$root/rust-rc2-tests.log" 2>&1
    cargo test --release --locked --lib legacy_and_aglr_match_exhaustive_optimum_on_tiny_problem -j 2 -- --test-threads=1 > "$root/rust-legacy-tests.log" 2>&1
    cargo build --release --locked --bin sat_bound_search -j 2 > "$root/build.log" 2>&1
    mkdir -p "$root/solver"
    install "$CARGO_TARGET_DIR/release/sat_bound_search" "$binary"
    python3 quick_scripts/analyze/validate_sat_bound_search_build.py --root "$root" --reference "$REFERENCE" \
        --threshold-policy upper --rc2-warmup-seconds 60 --threshold-session "$session"
fi

selection=results/sat_research/v45_long600_20261121/complete_snapshot.tar.gz
run_phase() {
    local phase="$1" seconds
    shift
    seconds="$(remaining)"
    if (( seconds < reserve )); then incomplete; fi
    taskset -c 0,1,4,5 python3 quick_scripts/analyze/run_sat_bound_search.py run \
        --reference "$REFERENCE" --diagnostic-root "$DIAGNOSTIC_ROOT" --binary "$binary" \
        --results "$phase" --build-manifest "$root/build_manifest.json" --selection-archive "$selection" \
        --threshold-policy upper --threshold-session "$session" --rc2-warmup-seconds 60 \
        --timeout "$cutoff" --round-seconds "$seconds" "$@"
    if [[ -f "$phase/followup_stopped.json" ]]; then return; fi
    if ! python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["complete"])' "$phase/audit.json"; then
        incomplete
    fi
}
compare() {
    local args=()
    if [[ -n "${CUTOFF_REFERENCE:-}" ]]; then args+=(--cutoff-reference "$CUTOFF_REFERENCE"); fi
    python3 quick_scripts/analyze/compare_search_bounds.py --candidate "$root/hard" \
        --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" --cplex-tail "$CPLEX_REFERENCE" \
        --gurobi-json cont "$MIP_ROOT/cont.json" --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" "${args[@]}" "$@"
}
run_phase "$root/hard"
compare --output "$root/hard-evaluation.json" --reference-pool "$root/hard-reference-pool.json"
if python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["newly_solved"])' "$root/hard/audit.json"; then
    run_phase "$root/followup" --followup "$root/hard"
    if [[ ! -f "$root/followup/followup_stopped.json" ]]; then
        compare --followup "$root/followup" --output "$root/full-evaluation.json" \
            --reference-pool "$root/full-reference-pool.json"
    fi
fi
touch "$root/COMPLETED"
