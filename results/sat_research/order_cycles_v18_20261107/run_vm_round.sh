#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/order-cycles-v18/maxsattrainscheduling
python3 - <<'PY'
import shutil
assert shutil.disk_usage('.').free>1800000000,'Need room for an isolated release build'
PY
cargo test --release --locked --lib -j 2 -- --test-threads=1 > /tmp/order-cycles-v18-rust-tests.log 2>&1
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/order-cycles-v18-python-tests.log 2>&1
cargo build --release --locked --bin ddd -j 2 > /tmp/order-cycles-v18-build.log 2>&1
python3 /tmp/validate_order_cycles_v18.py
python3 quick_scripts/analyze/targeted_order_cycles.py run \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --binary ./target/release/ddd --build-manifest results/aglr/order-cycles-v18-build/manifest.json \
 --results results/aglr/order-cycles-v18-unresolved300 --round-seconds 21000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --results results/aglr/order-cycles-v18-unresolved300 \
 > results/aglr/order-cycles-v18-independent-audit.json
