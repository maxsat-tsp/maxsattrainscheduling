#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/initial-cost-v19/maxsattrainscheduling
printf 'Wait for the isolated V18 screening trial before validation and measurement\n'
while systemctl is-active --quiet maxsat-order-cycles-v18-v3.service; do sleep 30; done
[[ "$(systemctl show maxsat-order-cycles-v18-v3.service -p ExecMainStatus --value)" == 0 ]]
python3 - <<'PY'
import json,sys,shutil
from pathlib import Path
sys.path.insert(0,'quick_scripts/analyze');import targeted_order_cycles as trial
source=Path('/home/tuyenkv/projects/order-cycles-v18/maxsattrainscheduling/results/aglr/order-cycles-v18-unresolved300')
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
report=trial.audit_saved(source,reference)
assert report['complete'] and report['audit_passed']
decision=Path('results/aglr/initial-cost-v19-decision.json');decision.parent.mkdir(parents=True,exist_ok=True)
decision.write_text(json.dumps(dict(v18_complete=True,v18_gains=report['newly_solved'],
 action='hold-for-confirmation-of-v18-gains' if report['newly_solved'] else 'test-one-initial-cost-component'),indent=2)+'\n')
assert shutil.disk_usage('.').free>1500000000
PY
if python3 -c 'import json;from pathlib import Path;r=json.loads(Path("results/aglr/initial-cost-v19-decision.json").read_text());raise SystemExit(0 if r["v18_gains"] else 1)'; then
    printf 'V18 has gains; retain them for confirmation before changing another component\n'
    exit 0
fi
cargo test --release --locked --lib -j 2 -- --test-threads=1 > /tmp/initial-cost-v19-rust-tests.log 2>&1
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/initial-cost-v19-python-tests.log 2>&1
cargo build --release --locked --bin ddd -j 2 > /tmp/initial-cost-v19-build.log 2>&1
python3 /tmp/validate_initial_cost_v19.py
python3 quick_scripts/analyze/targeted_order_cycles.py run --component initial-cost \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --binary ./target/release/ddd --build-manifest results/aglr/initial-cost-v19-build/manifest.json \
 --results results/aglr/initial-cost-v19-unresolved300 --round-seconds 14000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --results results/aglr/initial-cost-v19-unresolved300 \
 > results/aglr/initial-cost-v19-independent-audit.json
