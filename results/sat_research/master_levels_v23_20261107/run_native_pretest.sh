#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling
cargo test --release --locked --lib -j 2 -- --test-threads=1 > /tmp/master-levels-v23-rust-tests.log 2>&1
python3 -m unittest discover -s quick_scripts/analyze -p 'test_*.py' > /tmp/master-levels-v23-python-tests.log 2>&1
