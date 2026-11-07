#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/master-levels-v23-python-tests.log 2>&1
cargo build --release --locked --bin ddd -j 2 > /tmp/master-levels-v23-build.log 2>&1
python3 /tmp/validate_master_levels_v23.py
reference=/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216
trial_root=results/aglr/master-levels-v23-unresolved300
python3 quick_scripts/analyze/targeted_order_cycles.py run --component order-master-levels \
 --reference "$reference" --binary ./target/release/ddd \
 --build-manifest results/aglr/master-levels-v23-build/manifest.json \
 --results "$trial_root" --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit --reference "$reference" --results "$trial_root" \
 > results/aglr/master-levels-v23-independent-audit.json
remaining_seconds=$((21600 - SECONDS - 60))
if (( remaining_seconds > 390 )); then
    python3 quick_scripts/analyze/confirm_component_gains.py --trial "$trial_root" --reference "$reference" \
      --binary ./target/release/ddd --results results/aglr/master-levels-v23-followup \
      --round-seconds "$remaining_seconds"
    python3 quick_scripts/analyze/confirm_component_gains.py --audit --trial "$trial_root" --reference "$reference" \
      --results results/aglr/master-levels-v23-followup > results/aglr/master-levels-v23-followup-independent-audit.json
fi
