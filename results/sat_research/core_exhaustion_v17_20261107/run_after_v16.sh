#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling
services=(maxsat-core-v16-conflicts1000.service maxsat-core-v16-conflicts100.service maxsat-core-v16-confirm-v2.service)
printf 'Waiting for V16 trials and confirmations\n'
while true; do
    waiting=0
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then waiting=1; fi
    done
    if [[ "$waiting" == 0 ]]; then break; fi
    sleep 30
done
for service in "${services[@]}"; do
    result="$(systemctl show "$service" --property=Result --value)"
    status="$(systemctl show "$service" --property=ExecMainStatus --value)"
    if [[ "$result" != success || "$status" != 0 ]]; then
        printf 'Prerequisite failed: %s result=%s exit=%s\n' "$service" "$result" "$status" >&2
        exit 1
    fi
done
python3 - <<'PY'
import json,pathlib,shutil
p=pathlib.Path('/home/tuyenkv/projects/limited-core-confirm-v16/maxsattrainscheduling/results/aglr/core-v16-confirm-selected')
r=json.loads((p/'confirmation_audit.json').read_text())
assert r['complete'] and r['confirmed'],'V16 gains must reproduce in all three repeats before this successor trial'
assert not (p/'failure.json').exists(),'V16 confirmation has a retained failure'
assert shutil.disk_usage('.').free>2500000000,'Need at least 2.5 GB free for a separate release build'
PY
printf 'Validate and build V17 from the pinned source\n'
cargo test --release --locked --lib -j 2 -- --test-threads=1 > /tmp/core-exhaust-v17-rust-tests.log 2>&1
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/core-exhaust-v17-python-tests.log 2>&1
cargo build --release --locked --bin ddd -j 2 > /tmp/core-exhaust-v17-build.log 2>&1
python3 /tmp/validate_core_exhaustion_v17.py
printf 'Run only cases still unresolved by the selected V16 configuration\n'
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_core_minimization.py \
    --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
    --previous-trials \
      /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts1000-unresolved300 \
      /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts100-unresolved300 \
    --binary ./target/release/ddd \
    --build-manifest results/aglr/core-exhaust-v17-build/manifest.json \
    --core-exhaust-checks 4 \
    --results results/aglr/core-exhaust-v17-unresolved300 \
    --ram-kb 6000000 --round-seconds 21600
python3 quick_scripts/analyze/audit_targeted_core_minimization.py audit \
    results/aglr/core-exhaust-v17-unresolved300 \
    --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
    --previous-trials \
      /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts1000-unresolved300 \
      /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts100-unresolved300 \
    > results/aglr/core-exhaust-v17-independent-audit.json
