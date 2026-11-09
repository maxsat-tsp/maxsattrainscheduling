#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?Set the pinned worktree}"
: "${RUN_ID:?Set a fixed campaign ID}"
: "${REFERENCE:?Set the raw V17 reference}"
: "${PREVIOUS_ROOT:?Set the V36 campaign root}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9 || exit 75
[[ ! -e "$root/COMPLETED" && ! -e "$root/FAILED" && ! -e "$root/SKIPPED" ]] || exit 0
trap 'code=$?; printf "exit=%s line=%s\n" "$code" "$LINENO" > "$root/FAILED"; exit 78' ERR
if [[ ! -f "$root/deadline_epoch" ]]; then
    printf '%s\n' "$(( $(date -u +%s) + 21600 ))" > "$root/deadline_epoch"
fi
remaining() { printf '%s\n' "$(( $(cat "$root/deadline_epoch") - $(date -u +%s) - 60 ))"; }
while systemctl is-active --quiet maxsat-v17-assumptions-v36.service; do
    if (( $(remaining) <= 390 )); then touch "$root/INCOMPLETE"; exit 0; fi
    echo 'Waiting for V36; no build or measurement runs alongside it.'
    sleep 30
done
python3 - "$PREVIOUS_ROOT" "$REFERENCE" "$root" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,'quick_scripts/analyze')
import targeted_order_cycles as trial
import extended_timeout_experiments as ex
previous,reference,root=map(Path,sys.argv[1:])
if not (previous/'COMPLETED').exists() or (previous/'FAILED').exists():
    raise ValueError('V36 did not finish cleanly; do not start another trial')
reports=[]
for component in trial.ASSUMPTION_COMPONENTS:
    report=trial.audit_saved(previous/component,reference)
    reports.append(report)
    if report['newly_solved']:break
if not all(r['complete'] and r['audit_passed'] and not r['errors'] for r in reports):
    raise ValueError('V36 is incomplete or has audit errors')
gain=any(r['newly_solved'] for r in reports)
ex.save(root/'predecessor_gate.json',dict(previous=str(previous),reports=reports,
    skip_for_previous_gain=gain,submission_passed=False))
if gain:(root/'SKIPPED').write_text('Confirm and regress the V36 gain before another method.\n')
PY
[[ ! -f "$root/SKIPPED" ]] || exit 0

source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
# Reuse the dependency build cache only after V36 has stopped. The new
# executable is copied into this campaign, then hashed before any trial.
export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target
if [[ ! -f "$root/preflight.json" ]]; then
    python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python-tests.log" 2>&1
    cargo test --release --locked --lib core_minimize::tests -j 2 -- --test-threads=1 > "$root/rust-core-tests.log" 2>&1
    cargo test --release --locked --lib bounded_core_trimming_matches_exhaustive -j 2 -- --test-threads=1 > "$root/rust-exhaustive-test.log" 2>&1
    cargo build --release --locked --bin ddd -j 2 > "$root/build.log" 2>&1
    mkdir -p "$root/solver"
    install -m 0755 "$CARGO_TARGET_DIR/release/ddd" "$root/solver/ddd"
    python3 quick_scripts/analyze/validate_core_trim_build.py \
        --root "$root" --reference "$REFERENCE" --binary "$root/solver/ddd"
fi
seconds="$(remaining)"
if (( seconds <= 390 )); then touch "$root/INCOMPLETE"; exit 0; fi
trial="$root/trial"
python3 quick_scripts/analyze/targeted_order_cycles.py run --component core-trim \
    --reference "$REFERENCE" --results "$trial" --binary "$root/solver/ddd" \
    --build-manifest "$root/build_manifest.json" --round-seconds "$seconds"
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
    --reference "$REFERENCE" --results "$trial" > "$root/independent-audit.json"
read -r complete gains < <(python3 - "$root/independent-audit.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));print(int(r['complete']),len(r['newly_solved']))
PY
)
if (( complete != 1 )); then touch "$root/INCOMPLETE"; exit 0; fi
if (( gains > 0 )); then
    seconds="$(remaining)"
    if (( seconds > 390 )); then
        python3 quick_scripts/analyze/confirm_component_gains.py --trial "$trial" \
            --reference "$REFERENCE" --binary "$root/solver/ddd" \
            --results "$root/followup" --round-seconds "$seconds"
        python3 quick_scripts/analyze/confirm_component_gains.py --audit --trial "$trial" \
            --reference "$REFERENCE" --results "$root/followup" > "$root/followup-independent-audit.json"
    fi
    touch "$root/GAIN_REQUIRES_REVIEW"
fi
printf 'completed_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$root/COMPLETED"
