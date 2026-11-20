#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${RUN_ID:?}" "${REFERENCE:?}" "${DIAGNOSTIC_ROOT:?}" "${MIP_ROOT:?}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9
[[ ! -f "$root/COMPLETED" && ! -f "$root/FAILED" ]] || exit 0
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$root/FAILED"; exit 78' ERR
if [[ ! -f "$root/deadline_epoch" ]]; then date -u -d '+6 hours' +%s > "$root/deadline_epoch"; fi
remaining() { printf '%s\n' "$(( $(cat "$root/deadline_epoch") - $(date -u +%s) - 60 ))"; }

source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target
runner=quick_scripts/analyze/run_sat_bound_search.py
comparator=quick_scripts/analyze/compare_search_bounds.py
selection=results/sat_research/v42_sat_bound_search_20261109/complete_snapshot.tar.gz
common=(--reference "$REFERENCE" --diagnostic-root "$DIAGNOSTIC_ROOT")
bin="$root/solver/sat_bound_search"
if [[ ! -f "$root/preflight-complete" ]]; then
    python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python-tests.log" 2>&1
    cargo test --release --locked --lib bound_search::tests -j 2 -- --test-threads=1 > "$root/rust-search-tests.log" 2>&1
    cargo test --release --locked --lib binary_objective_tests -j 2 -- --test-threads=1 > "$root/rust-objective-tests.log" 2>&1
    cargo test --release --locked --lib maxsat_ladder_sc::progress::tests -j 2 -- --test-threads=1 > "$root/rust-rc2-tests.log" 2>&1
    cargo test --release --locked --lib legacy_and_aglr_match_exhaustive_optimum_on_tiny_problem -j 2 -- --test-threads=1 > "$root/rust-legacy-tests.log" 2>&1
    cargo build --release --locked --bin sat_bound_search -j 2 > "$root/build.log" 2>&1
    for mode in reuse restart-assumptions; do
        probe="$root/preflight-$mode"
        mkdir -p "$probe/solver"
        install -m 0755 "$CARGO_TARGET_DIR/release/sat_bound_search" "$probe/solver/sat_bound_search"
        cp "$root/"*-tests.log "$probe/"
        python3 quick_scripts/analyze/validate_sat_bound_search_build.py --root "$probe" --reference "$REFERENCE" \
            --threshold-policy upper --rc2-warmup-seconds 60 --threshold-session "$mode"
    done
    mkdir -p "$(dirname "$bin")"
    install -m 0755 "$root/preflight-reuse/solver/sat_bound_search" "$bin"
    touch "$root/preflight-complete"
fi

compare() {
    python3 "$comparator" --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" \
        --gurobi-json cont "$MIP_ROOT/cont.json" \
        --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" \
        "$@"
}
run_phase() {
    local mode="$1" phase="$2" seconds
    shift 2
    seconds="$(remaining)"
    if (( seconds < 360 )); then touch "$root/INCOMPLETE"; exit 0; fi
    python3 "$runner" run "${common[@]}" --results "$phase" --binary "$bin" \
        --build-manifest "$root/preflight-$mode/build_manifest.json" --threshold-policy upper \
        --rc2-warmup-seconds 60 --threshold-session "$mode" --round-seconds "$seconds" \
        --selection-archive "$selection" "$@"
    if [[ -f "$phase/followup_stopped.json" ]]; then return; fi
    if ! python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["complete"])' "$phase/audit.json"; then
        touch "$root/INCOMPLETE"
        exit 0
    fi
}
for mode in reuse restart-assumptions; do
    run_phase "$mode" "$root/$mode/hard"
    compare --candidate "$root/$mode/hard" --reference-pool "$root/hard-reference-pool.json" \
        --output "$root/$mode/hard-evaluation.json"
done
python3 quick_scripts/analyze/summarize_v45.py "$root"
winner="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["winner_for_regression"] or "")' "$root/matched-comparison.json")"
if [[ -n "$winner" ]]; then
    for mode in "$winner" "$( [[ "$winner" == reuse ]] && echo restart-assumptions || echo reuse )"; do
        if ! python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["newly_solved"])' "$root/$mode/hard/audit.json"; then continue; fi
        run_phase "$mode" "$root/$mode/followup" --followup "$root/$mode/hard"
        if [[ -f "$root/$mode/followup/followup_stopped.json" ]]; then continue; fi
        compare --candidate "$root/$mode/hard" --followup "$root/$mode/followup" \
            --reference-pool "$root/full-reference-pool.json" --output "$root/$mode/full-evaluation.json"
        break
    done
fi
touch "$root/COMPLETED"
