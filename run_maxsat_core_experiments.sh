#!/usr/bin/env bash
# Compare assumption schedules while keeping the CSOnet refinement unchanged.
# screen: three schedules, development set, 30 s, up to two workers.
# promote: the two experimental schedules, development set, 120 s, sequential.
# candidate: one locked schedule, all 72 instances, 120 s, sequential.
set -euo pipefail

mode="${1:-screen}"
[[ "$mode" =~ ^(screen|promote|candidate|confirm)$ ]] || exit 2
RUN_ID="${RUN_ID:-core-$mode-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
RESULTS_ROOT="${RESULTS_ROOT:-results/aglr}"
BIN="${BIN:-./target/release/ddd}"
SCREEN_PARALLELISM="${SCREEN_PARALLELISM:-2}"
EXPERIMENT_SET="${EXPERIMENT_SET:-assumptions}"
[[ "$EXPERIMENT_SET" =~ ^(assumptions|costs|orders|orders-sparse)$ ]] || exit 2
[[ "$SCREEN_PARALLELISM" =~ ^[1-9][0-9]*$ ]] || exit 2
development="origA3 trackA3 stationA3 origA6 trackA6 stationA6 origA9 trackA9 stationA9 origA12 trackA12 stationA12 origB3 trackB3 stationB3 origB6 trackB6 stationB6 origB9 trackB9 stationB9 origB12 trackB12 stationB12"
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
    echo "ERROR: commit changes before starting an experiment." >&2; exit 2;
}
[[ -x "$BIN" ]] || exit 2
root="$RESULTS_ROOT/$RUN_ID"
mkdir -p "$root"

if [[ "$mode" == screen ]]; then
    strategies=(legacy full geometric)
    [[ "$EXPERIMENT_SET" != costs ]] || strategies=(legacy sparse)
    [[ "$EXPERIMENT_SET" != orders ]] || strategies=(legacy orders)
    [[ "$EXPERIMENT_SET" != orders-sparse ]] || strategies=(orders-sparse)
    cutoff=30
    instances="$development"
    parallelism="$SCREEN_PARALLELISM"
elif [[ "$mode" == promote ]]; then
    strategies=(full geometric)
    [[ "$EXPERIMENT_SET" != costs ]] || strategies=(sparse)
    [[ "$EXPERIMENT_SET" != orders ]] || strategies=(orders)
    [[ "$EXPERIMENT_SET" != orders-sparse ]] || strategies=(orders-sparse)
    cutoff=120
    instances="$development"
    parallelism=1
elif [[ "$mode" == candidate ]]; then
    selected_variant="${CORE_VARIANT:-${MAXSATDDD_ASSUMPTIONS:-}}"
    strategies=("${selected_variant:?Set CORE_VARIANT (or MAXSATDDD_ASSUMPTIONS) for candidate mode}")
    cutoff=120
    instances=""
    parallelism=1
else
    : "${FULL_DIR:?Set FULL_DIR to the audited full candidate}"
    selected_variant="$(python3 - "$FULL_DIR" "$BIN" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
audit = json.loads((root / "aglr_audit.json").read_text())
if audit["errors"] or not (audit.get("gate") or {}).get("coverage_passed"):
    raise SystemExit("ERROR: full coverage and a clean audit are required before repeats")
values = dict(line.split("=", 1) for line in (root / "AGLR/config.txt").read_text().splitlines())
current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
binary_hash = hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest()
if values["git_commit"] != current_commit or values["binary_sha256"] != binary_hash:
    raise SystemExit("ERROR: repeats must use the original full-candidate source and binary")
print("orders-sparse" if values.get("resource_orders") == "true" and values.get("sparse_costs") == "true" else
      "orders" if values.get("resource_orders") == "true" else
      "sparse" if values.get("sparse_costs") == "true" else values["assumptions"])
PY
)"
    strategies=("$selected_variant")
    instances="$(tr '\n' ' ' < "$FULL_DIR/confirm_instances.txt")"
    [[ -n "${instances// /}" ]] || { echo "No cases require repeats."; exit 0; }
    cutoff=120
    parallelism=1
fi

run_strategy() {
    local strategy="$1" tag="${2:-Core-$1}"
    [[ "$strategy" =~ ^(legacy|full|geometric|sparse|orders|orders-sparse)$ ]] || exit 2
    local assumptions="$strategy" sparse_costs=false resource_orders=false
    if [[ "$strategy" == sparse ]]; then
        assumptions=legacy
        sparse_costs=true
    fi
    if [[ "$strategy" == orders ]]; then
        assumptions=legacy
        resource_orders=true
    fi
    if [[ "$strategy" == orders-sparse ]]; then
        assumptions=legacy
        sparse_costs=true
        resource_orders=true
    fi
    [[ "$mode" != candidate ]] || tag=AGLR
    local dir="$root/$tag"
    mkdir -p "$dir"
    # Exact match on resume; never mix a configuration with earlier outputs.
    python3 - "$dir/config.txt" "$tag" "$assumptions" "$cutoff" "$instances" "$BIN" "$parallelism" "$sparse_costs" "$resource_orders" <<'PY'
import hashlib
import pathlib
import subprocess
import sys
path = pathlib.Path(sys.argv[1])
tag, strategy, cutoff, instances, binary, parallelism, sparse_costs, resource_orders = sys.argv[2:]
values = dict(tag=tag, kind="exact", solver="maxsat_ddd_ladder_sc", policy="legacy",
              assumptions=strategy, sparse_costs=sparse_costs, resource_orders=resource_orders, timeout_seconds=cutoff,
              instances=",".join(instances.split()), process_exit_required="true",
              git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              binary_sha256=hashlib.sha256(pathlib.Path(binary).read_bytes()).hexdigest(),
              parallelism=parallelism)
content = "".join(f"{key}={value}\n" for key, value in values.items())
if path.exists() and path.read_text() != content:
    raise SystemExit("ERROR: resume would change the locked experiment configuration")
if not path.exists():
    path.write_text(content)
PY
    local ram_limit="${RAM_LIMIT_KB:-15000000}"
    ram_limit=$((ram_limit / parallelism))
    for objective in finsteps123 infsteps180 cont; do
        BIN="$BIN" SOLVER=maxsat_ddd_ladder_sc OBJECTIVE="$objective" \
        INSTANCE_NAMES="$instances" INSTANCE_TIMEOUT_SECS="$cutoff" \
        RAM_LIMIT_KB="$ram_limit" INSTANCE_ORDER_SEED=20261105 \
        MAXSATDDD_ASSUMPTIONS="$assumptions" MAXSATDDD_SPARSE_COSTS="$sparse_costs" \
        MAXSATDDD_RESOURCE_ORDERS="$resource_orders" \
        JSON_OUT="$dir/$objective.json" RUN_LOG_DIR="$dir/$objective.logs" \
            bash quick_scripts/run_all_txt_instances_limited.sh
    done
}

if [[ "$mode" == confirm ]]; then
    for repeat in 1 2 3; do
        run_strategy "$selected_variant" "AGLR-confirm-$repeat"
    done
else
workers=()
trap 'for worker in "${workers[@]}"; do kill "$worker" 2>/dev/null || true; done' EXIT
for strategy in "${strategies[@]}"; do
    run_strategy "$strategy" &
    workers+=("$!")
    if (( ${#workers[@]} >= parallelism )); then
        for worker in "${workers[@]}"; do wait "$worker"; done
        workers=()
    fi
done
for worker in "${workers[@]}"; do wait "$worker"; done
workers=()
trap - EXIT
fi

audit_args=()
[[ "$mode" != confirm ]] || audit_args+=(--reference-full "$FULL_DIR")
python3 quick_scripts/analyze/audit_aglr_campaign.py "$root" --timeout "$cutoff" \
    --conference-reference results --conference-profile published-csv-120 \
    --conference-runtime-mode assumed-equivalent "${audit_args[@]}"
python3 - "$root/aglr_audit.json" <<'PY'
import json
import sys
audit = json.load(open(sys.argv[1]))
if audit["errors"]:
    raise SystemExit("ERROR: audit failed; do not promote this experiment")
PY
