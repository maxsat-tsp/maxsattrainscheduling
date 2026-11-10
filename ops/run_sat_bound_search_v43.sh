#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?Set the pinned search worktree}"
: "${RUN_ID:?Set a fixed run ID}"
: "${REFERENCE:?Set the audited V17 full reference}"
: "${DIAGNOSTIC_ROOT:?Set the completed V39 root}"
: "${MIP_ROOT:?Set the previously saved Gurobi reference directory}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
selection="$REPO/results/sat_research/v42_sat_bound_search_20261109/complete_snapshot.tar.gz"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9 || exit 75
[[ ! -e "$root/COMPLETED" && ! -e "$root/FAILED" && ! -e "$root/INCOMPLETE" ]] || exit 0
trap 'code=$?; printf "exit=%s line=%s\n" "$code" "$LINENO" > "$root/FAILED"; exit 78' ERR
[[ -f "$root/deadline_epoch" ]] || date -u -d '+6 hours' +%s > "$root/deadline_epoch"
remaining() { printf '%s\n' "$(( $(cat "$root/deadline_epoch") - $(date -u +%s) - 60 ))"; }
while systemctl is-active --quiet maxsat-sat-bound-search-v42.service; do
    if (( $(remaining) < 900 )); then touch "$root/INCOMPLETE"; exit 0; fi
    echo 'Waiting for previous measurements; no search measurements run in parallel.'
    sleep 30
done
if (( $(remaining) < 360 )); then touch "$root/INCOMPLETE"; exit 0; fi
[[ -f /home/tuyenkv/projects/sat-bound-search-v42/results/aglr/sat-bound-search-v42-20261109/COMPLETED ]]
python3 - "$DIAGNOSTIC_ROOT" "$REFERENCE" "$root" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,'quick_scripts/analyze')
import diagnose_optimal_bounds as d
p,reference,root=map(Path,sys.argv[1:])
if not (p/'COMPLETED').exists() or (p/'FAILED').exists():raise ValueError('V39 did not finish cleanly')
r=d.audit(p/'trial',reference)
if not r['complete'] or not r['audit_passed']:raise ValueError('V39 audit failed')
d.ex.save(root/'predecessor_gate.json',r)
PY
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target
if [[ ! -f "$root/preflight.json" ]]; then
    python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python-tests.log" 2>&1
    cargo test --release --locked --lib bound_search::tests -j 2 -- --test-threads=1 > "$root/rust-search-tests.log" 2>&1
    cargo test --release --locked --lib maxsat_ladder_sc::progress::tests -j 2 -- --test-threads=1 > "$root/rust-rc2-tests.log" 2>&1
    cargo test --release --locked --lib legacy_and_aglr_match_exhaustive_optimum_on_tiny_problem -j 2 -- --test-threads=1 > "$root/rust-legacy-tests.log" 2>&1
    cargo test --release --locked --lib binary_objective_tests -j 2 -- --test-threads=1 > "$root/rust-objective-tests.log" 2>&1
    cargo build --release --locked --bin sat_bound_search -j 2 > "$root/build.log" 2>&1
    mkdir -p "$root/solver"
    install -m 0755 "$CARGO_TARGET_DIR/release/sat_bound_search" "$root/solver/sat_bound_search"
    python3 quick_scripts/analyze/validate_sat_bound_search_build.py --root "$root" --reference "$REFERENCE" --threshold-policy upper --rc2-warmup-seconds 60
fi
for phase in hard followup; do
    seconds="$(remaining)"
    if (( seconds < 360 )); then touch "$root/INCOMPLETE"; exit 0; fi
    extra=(--selection-archive "$selection")
    if [[ "$phase" == followup ]]; then
        gains="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["newly_solved"]))' "$root/hard/audit.json")"
        if (( gains == 0 )); then break; fi
        extra=(--selection-archive "$selection" --followup "$root/hard")
    fi
    python3 quick_scripts/analyze/run_sat_bound_search.py run --reference "$REFERENCE" \
        --diagnostic-root "$DIAGNOSTIC_ROOT" --results "$root/$phase" \
        --binary "$root/solver/sat_bound_search" --build-manifest "$root/build_manifest.json" \
        --threshold-policy upper --rc2-warmup-seconds 60 --round-seconds "$seconds" "${extra[@]}"
    python3 quick_scripts/analyze/run_sat_bound_search.py audit --reference "$REFERENCE" \
        --diagnostic-root "$DIAGNOSTIC_ROOT" --results "$root/$phase" > "$root/$phase-independent-audit.json"
    complete="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["complete"]))' "$root/$phase/audit.json")"
    if (( complete != 1 )); then touch "$root/INCOMPLETE"; exit 0; fi
    evaluation=()
    if [[ "$phase" == followup ]]; then evaluation=(--followup "$root/followup"); fi
    python3 quick_scripts/analyze/compare_search_bounds.py \
        --candidate "$root/hard" "${evaluation[@]}" --reference "$REFERENCE" \
        --diagnostics "$DIAGNOSTIC_ROOT" \
        --gurobi-json cont "$MIP_ROOT/cont.json" \
        --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" \
        --reference-pool "$root/$phase-reference-pool.json" --output "$root/$phase-priority-evaluation.json"
done
printf 'completed_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$root/COMPLETED"
