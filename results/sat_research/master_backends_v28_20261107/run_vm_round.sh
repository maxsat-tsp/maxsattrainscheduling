#!/usr/bin/env bash
set -euo pipefail
backend=${1:?backend required}
case "$backend" in minisat|cadical) ;; *) exit 2;; esac
round_deadline_epoch=${AGLR_V28_DEADLINE_EPOCH:?original round deadline required}
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/master-backends-v28/maxsattrainscheduling
while systemctl is-active --quiet maxsat-master-seeds-v27; do
    sleep 20
done
python3 /tmp/prepare_master_backends_v28.py "$backend"
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > "/tmp/master-backends-v28-$backend-python-tests.log" 2>&1
python3 /tmp/validate_master_backends_v28.py "$backend"
reference=/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216
binary=/home/tuyenkv/projects/master-seeds-v27/maxsattrainscheduling/target/release/ddd
build=/home/tuyenkv/projects/master-seeds-v27/maxsattrainscheduling/results/aglr/master-seeds-v27-build/manifest.json
trial_root="results/aglr/master-backends-v28-$backend-unresolved300"
python3 quick_scripts/analyze/targeted_order_cycles.py run --component order-master-seeds --objectives infsteps180 \
 --backend "$backend" --core-minimize-conflicts 0 --measurement-context paired-screen --paired-run-id master-backends-v28 \
 --reuse-build --reference "$reference" --binary "$binary" --build-manifest "$build" \
 --results "$trial_root" --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit --reference "$reference" --results "$trial_root" \
 > "results/aglr/master-backends-v28-$backend-independent-audit.json"
remaining_seconds=$((round_deadline_epoch - $(date -u +%s) - 60))
if (( remaining_seconds > 390 )); then
 python3 quick_scripts/analyze/confirm_component_gains.py --trial "$trial_root" --reference "$reference" \
  --binary "$binary" --results "results/aglr/master-backends-v28-$backend-followup" --round-seconds "$remaining_seconds"
 python3 quick_scripts/analyze/confirm_component_gains.py --audit --trial "$trial_root" --reference "$reference" \
  --results "results/aglr/master-backends-v28-$backend-followup" > "results/aglr/master-backends-v28-$backend-followup-independent-audit.json"
fi
