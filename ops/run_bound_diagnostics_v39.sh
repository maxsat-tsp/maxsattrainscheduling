#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?Set the pinned diagnostic worktree}"
: "${RUN_ID:?Set a fixed run ID}"
: "${REFERENCE:?Set the audited full V17 reference}"
: "${MIP_ROOT:?Set the existing full-120 BigM-Gurobi directory}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9 || exit 75
[[ ! -e "$root/COMPLETED" && ! -e "$root/FAILED" ]] || exit 0
trap 'code=$?; printf "exit=%s line=%s\n" "$code" "$LINENO" > "$root/FAILED"; exit 78' ERR
[[ -f "$root/deadline_epoch" ]] || date -u -d '+6 hours' +%s > "$root/deadline_epoch"
remaining() { printf '%s\n' "$(( $(cat "$root/deadline_epoch") - $(date -u +%s) - 60 ))"; }
while systemctl is-active --quiet maxsat-intrinsic-am1-v38.service; do
    if (( $(remaining) < 900 )); then touch "$root/INCOMPLETE"; exit 0; fi
    echo 'Waiting for V38; diagnostic measurements run sequentially.'
    sleep 30
done
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target
if [[ ! -f "$root/preflight.json" ]]; then
    python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python-tests.log" 2>&1
    cargo test --release --locked --lib bound_diagnostic_ -j 2 -- --test-threads=1 > "$root/rust-diagnostic-tests.log" 2>&1
    cargo test --release --locked --lib binary_objective_tests -j 2 -- --test-threads=1 > "$root/rust-objective-tests.log" 2>&1
    cargo build --release --locked --bin bound_diagnostic --bin ddd -j 2 > "$root/build.log" 2>&1
    mkdir -p "$root/solver"
    install -m 0755 "$CARGO_TARGET_DIR/release/bound_diagnostic" "$root/solver/bound_diagnostic"
    install -m 0755 "$CARGO_TARGET_DIR/release/ddd" "$root/solver/ddd"
    python3 quick_scripts/analyze/validate_bound_diagnostic_build.py \
        --root "$root" --reference "$REFERENCE"
fi
seconds="$(remaining)"
if (( seconds < 360 )); then touch "$root/INCOMPLETE"; exit 0; fi
python3 quick_scripts/analyze/diagnose_optimal_bounds.py run \
    --reference "$REFERENCE" --results "$root/trial" \
    --mip infsteps180 "$MIP_ROOT/infsteps180.json" --mip cont "$MIP_ROOT/cont.json" \
    --binary "$root/solver/bound_diagnostic" --build-manifest "$root/build_manifest.json" \
    --round-seconds "$seconds"
python3 quick_scripts/analyze/diagnose_optimal_bounds.py audit \
    --results "$root/trial" --reference "$REFERENCE" > "$root/independent-audit.json"
python3 - "$root" <<'PY'
from pathlib import Path
import json,sys
root=Path(sys.argv[1]);report=json.load(open(root/'independent-audit.json'))
(root/('COMPLETED' if report['complete'] else 'INCOMPLETE')).write_text(
    'Oracle-assisted diagnosis only; not a new coverage result.\n')
PY
