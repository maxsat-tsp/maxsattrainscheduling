#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling
while systemctl is-active --quiet maxsat-core-exhaust-v17.service; do sleep 30; done
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/core-exhaust-v17-followup-python-tests.log 2>&1
python3 - <<'PY'
from pathlib import Path
from types import SimpleNamespace
import json,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
import targeted_core_minimization as targeted
old=Path('/home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling')
reference=Path('/home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22')
prior=Path('/home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr')
build=json.loads((old/'results/aglr/core-exhaust-v17-build/manifest.json').read_text())
assert build['rust_library_tests_passed']==56 and build['python_tests_passed']==85
assert build['git_commit']=='43cae7674338e0468db1c7be04c446cddb983eef'
assert extended.focus.sha(old/'target/release/ddd')==build['binary_sha256']
assert not (old/'results/aglr/core-exhaust-v17-unresolved300/manifest.json').exists(),'Do not duplicate an already started trial'
for minimum,conflicts,exhaust in [(0,0,0),(4,100,0),(4,100,4)]:
 cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks=str(minimum),core_minimize_conflicts=str(conflicts),core_exhaust_checks=str(exhaust))
 case=old/f'results/aglr/core-exhaust-v17-smoke-{minimum}-{conflicts}-{exhaust}'
 record=extended.assess_case(case,'Smoke','cont','origA1',10,cfg)
 assert record['proven'] and not record['errors'] and record['solve']['cost']==5526
cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4')
probe=extended.assess_case(old/'results/aglr/core-exhaust-v17-hard-probe','HardProbe','infsteps180','stationA11',2,cfg)
assert not probe['errors'] and probe['status'] in ('ok','timeout')
confirmation=Path('/home/tuyenkv/projects/limited-core-confirm-v16/maxsattrainscheduling/results/aglr/core-v16-confirm-selected')
confirmed=json.loads((confirmation/'confirmation_audit.json').read_text())
assert confirmed['complete'] and confirmed['confirmed'] and not (confirmation/'failure.json').exists()
selection,config,evidence=targeted.unresolved_after_trials(reference,
 [prior/'core-v16-conflicts1000-unresolved300',prior/'core-v16-conflicts100-unresolved300'],
 old/'results/aglr/core-v16-regression-selected')
print(json.dumps(dict(phase='validated successor including all regression losses',
                     selection=selection,source_binary_sha256=build['binary_sha256'])),flush=True)
PY
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_core_minimization.py \
  --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
  --previous-trials \
    /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts1000-unresolved300 \
    /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts100-unresolved300 \
  --regression-reference /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/results/aglr/core-v16-regression-selected \
  --binary /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/target/release/ddd \
  --build-manifest /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/results/aglr/core-exhaust-v17-build/manifest.json \
  --core-exhaust-checks 4 \
  --results results/aglr/core-exhaust-v17-followup300 --ram-kb 6000000 --round-seconds 21600
python3 quick_scripts/analyze/audit_targeted_core_minimization.py audit \
  results/aglr/core-exhaust-v17-followup300 \
  --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
  --previous-trials \
    /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts1000-unresolved300 \
    /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts100-unresolved300 \
  --regression-reference /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/results/aglr/core-v16-regression-selected \
  > results/aglr/core-exhaust-v17-followup-independent-audit.json
