#!/usr/bin/env bash
set -Eeuo pipefail

repo=/home/tuyenkv/projects/maxsattrainscheduling
run_id=full-final-120-20261108
root="$repo/results/aglr/$run_id"
lock=/home/tuyenkv/.cache/maxsat-journal-full.lock
mkdir -p "$(dirname "$lock")" "$root"
exec 9>"$lock"
flock -n 9 || { echo "another final campaign is already running"; exit 75; }

source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic
export RUN_ID="$run_id"
export RESULTS_ROOT=results/aglr
export FULL_TIMEOUT_SECS=120
export SKIP_BUILD=1
export AGLR_MIN_GROWTH=32
export AGLR_FRACTION=0.5
export AGLR_MAX_WAIT=5
export CPLEX_RESULTS_DIR=/home/tuyenkv/cplex_csv_final
export SCREEN_PARALLELISM=1

cd "$repo"
printf 'service_started=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$root/service.log"
if bash run_aglr_experiments.sh full >> "$root/service.log" 2>&1; then
  printf 'service_completed=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$root/service.log"
else
  code=$?
  printf 'service_failed=%s exit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$code" >> "$root/service.log"
  exit "$code"
fi
