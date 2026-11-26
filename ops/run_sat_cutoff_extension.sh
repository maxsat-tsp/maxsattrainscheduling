#!/usr/bin/env bash
set -Eeuo pipefail
: "${REPO:?}" "${EXTENSION_ROOT:?}" "${V45_ROOT:?}"
: "${REFERENCE:?}" "${DIAGNOSTIC_ROOT:?}" "${CPLEX_REFERENCE:?}" "${CPLEX_BIN:?}"
if [[ -n "${V49_ROOT:-}" ]]; then
    : "${V49_UNIT:?}" "${CUTOFF_REFERENCE_1200:?}"
    search_root="$V49_ROOT"
    search_unit="$V49_UNIT"
    selection=(--after-v49 "$V49_ROOT" --baseline-1200 "$CUTOFF_REFERENCE_1200")
    reserve=2550
else
    : "${V47_ROOT:?}" "${V47_UNIT:?}"
    search_root="$V47_ROOT"
    search_unit="$V47_UNIT"
    selection=(--v47 "$V47_ROOT")
    reserve=1350
fi
cd "$REPO"
mkdir -p "$EXTENSION_ROOT"
exec 9>"$EXTENSION_ROOT/campaign.lock"
flock -n 9
if [[ -f "$EXTENSION_ROOT/COMPLETED" || -f "$EXTENSION_ROOT/SKIPPED" ]]; then exit 0; fi
if [[ -f "$EXTENSION_ROOT/FAILED" || -f "$EXTENSION_ROOT/BLOCKED" ]]; then exit 78; fi
trap 'printf "exit=%s line=%s\n" "$?" "$LINENO" > "$EXTENSION_ROOT/FAILED"; exit 78' ERR
rm -f "$EXTENSION_ROOT/INCOMPLETE"
deadline=$(( $(date +%s) + 21600 ))
remaining() { printf '%s\n' "$(( deadline - $(date +%s) - 90 ))"; }
incomplete() { touch "$EXTENSION_ROOT/INCOMPLETE"; exit 75; }

while :; do
    if [[ -f "$search_root/FAILED" ]]; then
        printf 'Candidate campaign failed. Read %s/FAILED\n' "$search_root" > "$EXTENSION_ROOT/FAILED"
        exit 78
    fi
    state="$(systemctl show "$search_unit" --property=ActiveState --value)"
    if [[ "$state" == inactive && -f "$search_root/COMPLETED" ]]; then break; fi
    if [[ "$state" == failed ]]; then
        printf 'Candidate service failed. Check %s.\n' "$search_unit" > "$EXTENSION_ROOT/FAILED"
        exit 78
    fi
    if (( $(remaining) < reserve )); then incomplete; fi
    sleep 20
done
if (( $(remaining) < reserve )); then incomplete; fi

source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH="$GUROBI_HOME/lib"
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic

args=(run --results "$EXTENSION_ROOT" "${selection[@]}"
    --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" --cplex-reference "$CPLEX_REFERENCE"
    --v45-binary "$V45_ROOT/solver/sat_bound_search" --ddd "$V45_ROOT/solver/ddd"
    --cplex "$CPLEX_BIN")
if [[ -n "${PRIOR_EXTENSION_ROOT:-}" ]]; then args+=(--prior-results "$PRIOR_EXTENSION_ROOT"); fi
runner=quick_scripts/analyze/run_sat_cutoff_extension.py
status=0
python3 "$runner" "${args[@]}" --round-seconds "$(remaining)" || status=$?
if (( status == 76 )); then
    if (( $(remaining) < reserve )); then incomplete; fi
    probe="$EXTENSION_ROOT/diagnostics/solver/ddd"
    if [[ ! -x "$probe" ]]; then
        mkdir -p "$(dirname "$probe")"
        source /home/tuyenkv/.cargo/env
        export CARGO_TARGET_DIR=/home/tuyenkv/projects/maxsattrainscheduling/target
        cargo build --locked --release --bin ddd -j 2 > "$EXTENSION_ROOT/diagnostics/build.log" 2>&1
        install "$CARGO_TARGET_DIR/release/ddd" "$probe.tmp"
        mv "$probe.tmp" "$probe"
    fi
    if (( $(remaining) < reserve )); then incomplete; fi
    status=0
    python3 "$runner" "${args[@]}" --diagnostic-ddd "$probe" --round-seconds "$(remaining)" || status=$?
fi
if (( status == 75 )); then incomplete; fi
if (( status == 77 )) && [[ -f "$EXTENSION_ROOT/BLOCKED" ]]; then exit 78; fi
if (( status != 0 )); then
    printf 'extension runner exited %d\n' "$status" > "$EXTENSION_ROOT/FAILED"
    exit 78
fi
