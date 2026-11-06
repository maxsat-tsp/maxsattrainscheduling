#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/limited-core-confirm-v16/maxsattrainscheduling
while systemctl is-active --quiet maxsat-core-v16-conflicts1000.service || \
      systemctl is-active --quiet maxsat-core-v16-conflicts100.service; do
    sleep 30
done
for service in maxsat-core-v16-conflicts1000.service maxsat-core-v16-conflicts100.service; do
    result="$(systemctl show "$service" --property=Result --value)"
    status="$(systemctl show "$service" --property=ExecMainStatus --value)"
    if [[ "$result" != success || "$status" != 0 ]]; then
        printf 'Parameter service failed: %s, result=%s, exit=%s\n' "$service" "$result" "$status" >&2
        exit 1
    fi
done
taskset -c 0,1,4,5 python3 quick_scripts/analyze/confirm_targeted_core_minimization.py \
    --trials \
      /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts1000-unresolved300 \
      /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts100-unresolved300 \
    --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
    --binary /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/target/release/ddd \
    --results results/aglr/core-v16-confirm-selected \
    --ram-kb 6000000 --round-seconds 21600
