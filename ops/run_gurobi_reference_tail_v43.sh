#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?Set the frozen runner checkout}"
: "${BIN:?Set the frozen ordinary binary from V39}"
cd "$REPO"
root="$REPO/results/aglr/gurobi-reference300-v43-20261110"
mkdir -p "$root"
exec 9>"$root/campaign.lock"
flock -n 9 || exit 75
[[ ! -e "$root/COMPLETED" && ! -e "$root/FAILED" && ! -e "$root/INCOMPLETE" ]] || exit 0
trap 'code=$?; printf "exit=%s line=%s\n" "$code" "$LINENO" > "$root/FAILED"; exit 78' ERR
[[ -f "$root/deadline_epoch" ]] || date -u -d '+6 hours' +%s > "$root/deadline_epoch"
remaining() { printf '%s\n' "$(( $(cat "$root/deadline_epoch") - $(date -u +%s) - 60 ))"; }
candidate="$REPO/results/aglr/sat-bound-search-v43-20261110"
while [[ ! -f "$candidate/COMPLETED" && ! -f "$candidate/FAILED" && ! -f "$candidate/INCOMPLETE" ]]; do
    if (( $(remaining) < 360 )); then touch "$root/INCOMPLETE"; exit 0; fi
    sleep 30
done
if (( $(remaining) < 360 )); then touch "$root/INCOMPLETE"; exit 0; fi
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
if [[ ! -f "$root/smoke_audit.json" ]]; then
    python3 - "$root" "$BIN" <<'PY'
from pathlib import Path
from types import SimpleNamespace
import sys,json,tarfile
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as ex
root,binary=map(Path,sys.argv[1:]);runtime=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary)
with tarfile.open('results/sat_research/v39_bound_diagnostics_20261109/raw_snapshot.tar.gz') as t:
    evidence=json.load(t.extractfile('./build_manifest.json'))
if ex.focus.sha(binary)!=evidence['ordinary_binary_sha256']:raise ValueError('ordinary binary changed before smoke')
rows=[]
for o,cost in [('finsteps123',11),('infsteps180',34),('cont',5526)]:
    p=root/'smoke'/o
    if not (p/(o+'.json')).exists():ex.run_case('BigM-Gurobi',o,'origA1',runtime,p)
    r=ex.assess_case(p,'BigM-Gurobi',o,'origA1',30)
    if r['errors'] or not r['proven'] or r['solve']['cost']!=cost:raise ValueError('Gurobi smoke failed')
    rows.append(dict(objective=o,cost=cost,proven=True))
ex.save(root/'smoke_audit.json',dict(audit_passed=True,cases=rows))
PY
fi
checked_reference="$REPO/results/sat_research/v42_sat_bound_search_20261109/full_evaluation.json"
if [[ -f "$candidate/followup-priority-evaluation.json" ]]; then checked_reference="$candidate/followup-priority-evaluation.json"; fi
python3 quick_scripts/analyze/run_gurobi_reference_tail.py run --results "$root" \
    --inventory results/sat_research/baseline_inventory_20261110/gurobi_inventory.json \
    --binary "$BIN" --build-evidence results/sat_research/v39_bound_diagnostics_20261109/raw_snapshot.tar.gz \
    --checked-reference "$checked_reference" \
    --round-seconds "$(remaining)"
python3 quick_scripts/analyze/run_gurobi_reference_tail.py audit --results "$root" > "$root/independent_audit.json"
complete="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["complete"]))' "$root/audit.json")"
if (( complete != 1 )); then touch "$root/INCOMPLETE"; exit 0; fi
if [[ -f "$candidate/COMPLETED" ]]; then
    python3 - "$root" "$candidate" <<'PY'
from pathlib import Path
import json,subprocess,sys
root,candidate=map(Path,sys.argv[1:]);extra=[]
for r in json.loads((root/'audit.json').read_text())['cases']:
    extra+=['--gurobi-json',r['objective'],str(root/'cases/BigM-Gurobi'/r['objective']/r['name']/(r['objective']+'.json'))]
if (candidate/'followup/manifest.json').exists():extra+=['--followup',str(candidate/'followup')]
subprocess.run([sys.executable,'quick_scripts/analyze/compare_search_bounds.py',
    '--candidate',str(candidate/'hard'),
    '--reference','/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216',
    '--diagnostics','/home/tuyenkv/projects/bound-diagnostics-v39/results/aglr/bound-diagnostics-v39-20261109',
    '--gurobi-json','cont','results/sat_research/v39_bound_diagnostics_20261109/gurobi_cont_source.json',
    '--gurobi-json','infsteps180','results/sat_research/v40_sat_bound_search_20261109/gurobi_infsteps180_source.json',
    '--reference-pool',str(candidate/'evaluation/post_gurobi_reference_pool.json'),
    '--output',str(candidate/'evaluation/post_gurobi_evaluation.json'),*extra],check=True)
PY
fi
touch "$root/COMPLETED"
