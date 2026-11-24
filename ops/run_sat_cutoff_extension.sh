#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${EXTENSION_ROOT:?}" "${V47_ROOT:?}" "${V47_UNIT:?}" "${V45_ROOT:?}"
: "${REFERENCE:?}" "${DIAGNOSTIC_ROOT:?}" "${CPLEX_REFERENCE:?}" "${CPLEX_BIN:?}"
cd "$REPO"
mkdir -p "$EXTENSION_ROOT"
exec 9>"$EXTENSION_ROOT/campaign.lock"
flock -n 9
if [[ -f "$EXTENSION_ROOT/COMPLETED" ]]; then exit 0; fi
if [[ -f "$EXTENSION_ROOT/FAILED" ]]; then exit 78; fi
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$EXTENSION_ROOT/FAILED"; exit 78' ERR
rm -f "$EXTENSION_ROOT/INCOMPLETE"
deadline=$(( $(date +%s) + 21600 ))
remaining() { printf '%s\n' "$(( deadline - $(date +%s) - 90 ))"; }
incomplete() { touch "$EXTENSION_ROOT/INCOMPLETE"; exit 75; }

while :; do
    if [[ -f "$V47_ROOT/FAILED" ]]; then
        printf 'V47 failed. Read %s/FAILED\n' "$V47_ROOT" > "$EXTENSION_ROOT/FAILED"
        exit 78
    fi
    state="$(systemctl show "$V47_UNIT" --property=ActiveState --value)"
    if [[ "$state" == inactive && -f "$V47_ROOT/COMPLETED" ]]; then break; fi
    if [[ "$state" == failed ]]; then
        printf 'V47 service failed. Check %s.\n' "$V47_UNIT" > "$EXTENSION_ROOT/FAILED"
        exit 78
    fi
    if (( $(remaining) < 1350 )); then incomplete; fi
    sleep 20
done
if (( $(remaining) < 1350 )); then incomplete; fi

source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic

status=0
python3 quick_scripts/analyze/run_sat_cutoff_extension.py run \
    --results "$EXTENSION_ROOT" --v47 "$V47_ROOT" \
    --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" --cplex-reference "$CPLEX_REFERENCE" \
    --v45-binary "$V45_ROOT/solver/sat_bound_search" --ddd "$V45_ROOT/solver/ddd" \
    --cplex "$CPLEX_BIN" --round-seconds "$(remaining)" || status=$?
if (( status == 75 )); then incomplete; fi
if (( status != 0 )); then
    printf 'extension runner exited %d\n' "$status" > "$EXTENSION_ROOT/FAILED"
    exit 78
fi
