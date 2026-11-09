#!/usr/bin/env bash
# Run from a detached, pinned worktree. Reuse the tested V17 binary unchanged.
set -Eeuo pipefail

: "${REPO:?Set the pinned worktree path}"
: "${RUN_ID:?Set one fixed ID for the entire campaign, including restarts}"
: "${REFERENCE:?Set the raw audited V17 full216 directory}"
: "${BIN:?Set the frozen V17 binary path}"
: "${BUILD_MANIFEST:?Set the original binary build manifest}"
cd "$REPO"
root="$REPO/results/aglr/$RUN_ID"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9 || exit 75
[[ ! -e "$root/COMPLETED" && ! -e "$root/FAILED" ]] || exit 0
trap 'code=$?; printf "exit=%s line=%s\n" "$code" "$LINENO" > "$root/FAILED"; exit 78' ERR

source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic

# A persistent wall deadline prevents restarts from creating unlimited rounds.
if [[ ! -f "$root/deadline_epoch" ]]; then
  printf '%s\n' "$(( $(date -u +%s) + 21600 ))" > "$root/deadline_epoch"
fi
remaining() {
  printf '%s\n' "$(( $(cat "$root/deadline_epoch") - $(date -u +%s) - 60 ))"
}

python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$root/python_tests.log" 2>&1
python3 - "$root" "$REFERENCE" "$BIN" "$BUILD_MANIFEST" <<'PY'
import json, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,'quick_scripts/analyze')
import targeted_order_cycles as trial
import extended_timeout_experiments as extended
root,reference,binary,build=map(Path,sys.argv[1:])
source,selection,_=trial.load_reference(reference)
locked=json.loads(build.read_text())
trial.validate_build(locked,'separate-runner',binary,reuse=True)
if locked['binary_sha256']!=source['binary_sha256']:
    raise ValueError('use the original audited V17 binary for this contrast')
report=[]
for component in trial.ASSUMPTION_COMPONENTS:
    config=trial.candidate_config(source,component)
    runtime=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary,
        method_definitions={'smoke':config})
    for objective in extended.audit.OBJECTIVES:
        case=root/'smoke'/component/objective
        if not (case/f'{objective}.json').exists():
            extended.run_case('smoke',objective,'origA1',runtime,case)
        record=extended.assess_case(case,'smoke',objective,'origA1',30,config)
        expected=next(row['cost'] for row in json.loads((reference/'full_audit.json').read_text())['case_bounds']
                      if row['objective']==objective and row['name']=='origA1' and row['proven'])
        if record['errors'] or not record['proven'] or record['solve']['cost']!=expected:
            raise ValueError(f'smoke failed: {component}/{objective}: {record["errors"]}')
        report.append(dict(component=component,objective=objective,cost=expected,proven=True))
extended.save(root/'preflight.json',dict(audit_passed=True,smoke=report,
    binary_sha256=locked['binary_sha256'],solver_source_commit=locked['git_commit'],selection=selection))
PY

for component in assumptions-full assumptions-geometric; do
  seconds="$(remaining)"
  (( seconds > 390 )) || { printf 'round wall limit reached\n' > "$root/INCOMPLETE"; exit 0; }
  trial="$root/$component"
  python3 quick_scripts/analyze/targeted_order_cycles.py run \
    --component "$component" --reuse-build --reference "$REFERENCE" \
    --binary "$BIN" --build-manifest "$BUILD_MANIFEST" \
    --results "$trial" --round-seconds "$seconds"
  python3 quick_scripts/analyze/targeted_order_cycles.py audit \
    --reference "$REFERENCE" --results "$trial" > "$root/$component-independent-audit.json"
  read -r complete gains < <(python3 - "$root/$component-independent-audit.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));print(int(d['complete']),len(d['newly_solved']))
PY
  )
  (( complete == 1 )) || { printf 'partial %s\n' "$component" > "$root/INCOMPLETE"; exit 0; }
  if (( gains > 0 )); then
    # Reproduce all new optima three times, then regress previously solved pairs.
    seconds="$(remaining)"
    if (( seconds > 390 )); then
      python3 quick_scripts/analyze/confirm_component_gains.py \
        --trial "$trial" --reference "$REFERENCE" --binary "$BIN" \
        --results "$root/followup-$component" --round-seconds "$seconds"
      python3 quick_scripts/analyze/confirm_component_gains.py --audit \
        --trial "$trial" --reference "$REFERENCE" --results "$root/followup-$component" \
        > "$root/followup-$component-independent-audit.json"
    fi
    printf '%s\n' "$component" > "$root/GAIN_REQUIRES_REVIEW"
    break
  fi
done
printf 'completed_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$root/COMPLETED"
echo 'Round finished; no SOTA or full-coverage claim is implied.'
