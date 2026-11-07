#!/usr/bin/env bash
set -euo pipefail
source /home/tuyenkv/.cargo/env
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
cd /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling
exec taskset -c 0,1,4,5 python3 /tmp/complete_core_full_dataset.py
