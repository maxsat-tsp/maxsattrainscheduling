#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${ORIGINAL:?}" "${RESULTS:?}" "${CPLEX_BIN:?}" "${CPLEX_REFERENCE:?}"
cd "$REPO"
mkdir -p "$RESULTS"
exec 9>"$RESULTS/campaign.lock"
flock -n 9
[[ ! -f "$RESULTS/COMPLETED" && ! -f "$RESULTS/FAILED" ]] || exit 0
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$RESULTS/FAILED"; exit 78' ERR
while systemctl is-active --quiet maxsat-v45-long600-followup.service; do
    sleep 15
done
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic

python3 - "$ORIGINAL" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,'quick_scripts/analyze')
from extended_timeout_experiments import focus
root=Path(sys.argv[1])
for method in ('CSOnet','BigM-Gurobi'):
    manifest=json.loads((root/'controls'/method/'manifest.json').read_text())
    evidence=focus.sha(root/'solver/ddd')
    if manifest['binary_sha256'] != evidence:
        raise ValueError('original ddd binary hash changed')
    if method=='BigM-Gurobi' and not json.loads((root/'controls'/method/'audit.json').read_text())['complete']:
        raise ValueError('expected completed Gurobi stage')
if not json.loads((root/'controls/BigM-CPLEX/audit.json').read_text())['complete']:
    raise ValueError('expected completed CPLEX stage')
PY
candidate="$ORIGINAL/hard/manifest.json"
source_commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$candidate")"
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "$RESULTS/python-tests.log" 2>&1
for method in CSOnet MaxSAT-Journal; do
    stage="$RESULTS/controls/$method"
    extra=()
    if [[ "$method" == CSOnet ]]; then extra=(--prior-results "$ORIGINAL/controls/CSOnet"); fi
    taskset -c 0,1,4,5 python3 quick_scripts/analyze/run_long_baseline_cases.py \
        --method "$method" --candidate-manifest "$candidate" --results "$stage" \
        --binary "$ORIGINAL/solver/ddd" --binary-source-commit "$source_commit" \
        --cplex "$CPLEX_BIN" --cplex-reference "$CPLEX_REFERENCE" --round-seconds 21000 "${extra[@]}"
    if ! python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["complete"])' "$stage/audit.json"; then
        touch "$RESULTS/INCOMPLETE"
        exit 0
    fi
done
python3 quick_scripts/analyze/summarize_long_controls.py "$RESULTS" --original "$ORIGINAL"
touch "$RESULTS/COMPLETED"
