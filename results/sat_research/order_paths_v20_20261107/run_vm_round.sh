#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/order-paths-v20/maxsattrainscheduling
cargo build --release --locked --bin ddd -j 2 > /tmp/order-paths-v20-build.log 2>&1
python3 /tmp/validate_order_paths_v20.py
python3 quick_scripts/analyze/targeted_order_cycles.py run --component order-paths \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --binary ./target/release/ddd --build-manifest results/aglr/order-paths-v20-build/manifest.json \
 --results results/aglr/order-paths-v20-unresolved300 --round-seconds 21000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --results results/aglr/order-paths-v20-unresolved300 \
 > results/aglr/order-paths-v20-independent-audit.json
