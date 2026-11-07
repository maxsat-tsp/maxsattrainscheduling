#!/usr/bin/env bash
set -euo pipefail
# Preserve the original round deadline across validator-only restarts.
round_deadline_epoch=1794056633
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/master-batch-v26/maxsattrainscheduling
# Keep native builds and timing runs separate from the frozen V25 screen.
while systemctl is-active --quiet maxsat-master-rounded-v25-screen; do
    sleep 20
done
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/master-batch-v26-python-tests.log 2>&1
cargo test --release --locked --lib -j 2 -- --test-threads=1 > /tmp/master-batch-v26-rust-tests.log 2>&1
cargo build --release --locked --bin ddd -j 2 > /tmp/master-batch-v26-build.log 2>&1
python3 /tmp/validate_master_batch_v26.py
reference=/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216
binary=./target/release/ddd
trial_root=results/aglr/master-batch-v26-unresolved300
python3 quick_scripts/analyze/targeted_order_cycles.py run --component order-master-batch \
 --reference "$reference" --binary "$binary" \
 --build-manifest results/aglr/master-batch-v26-build/manifest.json \
 --results "$trial_root" --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit --reference "$reference" --results "$trial_root" \
 > results/aglr/master-batch-v26-independent-audit.json
remaining_seconds=$((round_deadline_epoch - $(date -u +%s) - 60))
if (( remaining_seconds > 390 )); then
    python3 quick_scripts/analyze/confirm_component_gains.py --trial "$trial_root" --reference "$reference" \
      --binary "$binary" --results results/aglr/master-batch-v26-followup --round-seconds "$remaining_seconds"
    python3 quick_scripts/analyze/confirm_component_gains.py --audit --trial "$trial_root" --reference "$reference" \
      --results results/aglr/master-batch-v26-followup > results/aglr/master-batch-v26-followup-independent-audit.json
fi
