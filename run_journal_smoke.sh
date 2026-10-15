#!/usr/bin/env bash
# Run one exact instance under all four journal ablation configurations.

set -euo pipefail

TIMEOUT_SECS="${1:-120}"
REFINEMENT_BUDGET="${2:-128}"
INSTANCE_NAME="${3:-origA1}"
OBJECTIVE="${4:-finsteps123}"
MAX_WAIT_ITERATIONS="${MAX_WAIT_ITERATIONS:-5}"
EXTERNAL_TIMEOUT_GRACE_SECS="${EXTERNAL_TIMEOUT_GRACE_SECS:-20}"
BIN="${BIN:-./target/release/ddd}"
RESULTS_ROOT="${RESULTS_ROOT:-results/improvements}"
RUN_ID="${RUN_ID:-smoke-$(date +%Y-%m-%d_%H-%M-%S)}"
OUT_DIR="$RESULTS_ROOT/$RUN_ID"
AUDIT_SCRIPT="quick_scripts/analyze/audit_journal_campaign.py"

if [[ ! "$TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: timeout phải là số nguyên dương." >&2
    exit 2
fi
if [[ ! "$REFINEMENT_BUDGET" =~ ^[0-9]+$ ]]; then
    echo "ERROR: refinement budget phải là số nguyên không âm." >&2
    exit 2
fi
if [[ ! "$MAX_WAIT_ITERATIONS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: MAX_WAIT_ITERATIONS phải là số nguyên không âm." >&2
    exit 2
fi
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: RUN_ID chỉ được chứa chữ, số, dấu chấm, gạch dưới và gạch ngang." >&2
    exit 2
fi
case "$OBJECTIVE" in
    finsteps123|infsteps180|cont) ;;
    *) echo "ERROR: objective phải là finsteps123, infsteps180 hoặc cont." >&2; exit 2 ;;
esac
if [[ ! -f Cargo.toml ]]; then
    echo "ERROR: Hãy chạy script từ thư mục gốc maxsattrainscheduling/." >&2
    exit 2
fi

TIMEOUT_BIN="${TIMEOUT_BIN:-$(command -v timeout || command -v gtimeout || true)}"
if [[ -z "$TIMEOUT_BIN" ]]; then
    echo "ERROR: Không tìm thấy timeout hoặc gtimeout trong PATH." >&2
    exit 2
fi

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
    cargo build --release --locked --bin ddd
fi
[[ -x "$BIN" ]] || { echo "ERROR: Không tìm thấy binary $BIN" >&2; exit 2; }

mkdir -p "$OUT_DIR"
printf '%s\n' \
    "git_commit=$(git rev-parse HEAD)" \
    "instance=$INSTANCE_NAME" \
    "objective=$OBJECTIVE" \
    "timeout_seconds=$TIMEOUT_SECS" \
    "refinement_budget=$REFINEMENT_BUDGET" \
    "max_wait_iterations=$MAX_WAIT_ITERATIONS" \
    >"$OUT_DIR/smoke.txt"

configs=(RC2-Base RC2+B RC2+R RC2+B+R)
for config in "${configs[@]}"; do
    case "$config" in
        RC2-Base)
            bound_mode=off
            effective_budget=all
            ;;
        RC2+B)
            bound_mode=chain-cost-forced
            effective_budget=all
            ;;
        RC2+R)
            bound_mode=off
            effective_budget="$REFINEMENT_BUDGET"
            ;;
        RC2+B+R)
            bound_mode=chain-cost-forced
            effective_budget="$REFINEMENT_BUDGET"
            ;;
    esac

    json_out="$OUT_DIR/$config.json"
    stdout_log="$OUT_DIR/$config.stdout.log"
    stderr_log="$OUT_DIR/$config.stderr.log"
    external_timeout=$((TIMEOUT_SECS + EXTERNAL_TIMEOUT_GRACE_SECS))

    echo "Smoke: $config | $INSTANCE_NAME | $OBJECTIVE"
    "$TIMEOUT_BIN" -k 20 "${external_timeout}s" \
        "$BIN" \
        -s maxsat_rc2 \
        --txt-instances \
        --instance-name-filter "$INSTANCE_NAME" \
        --instance-name-exact \
        --objective "$OBJECTIVE" \
        --timeout-seconds "$TIMEOUT_SECS" \
        --maxsat-rc2-bound-mode "$bound_mode" \
        --maxsat-rc2-refinement-budget "$effective_budget" \
        --maxsat-rc2-max-wait-iterations "$MAX_WAIT_ITERATIONS" \
        --maxsat-rc2-full-scan true \
        --maxsat-rc2-validate-before-return true \
        --json-output "$json_out" \
        >"$stdout_log" \
        2>"$stderr_log"

    python3 "$AUDIT_SCRIPT" \
        --file "$json_out" \
        --config "$config" \
        --objective "$OBJECTIVE" \
        --timeout "$TIMEOUT_SECS" \
        --budget "$REFINEMENT_BUDGET" \
        --max-wait "$MAX_WAIT_ITERATIONS" \
        --instance-name "$INSTANCE_NAME"

    python3 - "$json_out" <<'PY'
import json
import sys

solve = json.load(open(sys.argv[1]))[0]["solves"][0]
if solve.get("status") != "ok":
    raise SystemExit(
        f"ERROR: Smoke test phải hoàn thành tối ưu, nhận status={solve.get('status')!r}"
    )
PY

    if grep -Ein "panicked|Gurobi.*error|license.*error" "$stderr_log" >/dev/null 2>&1; then
        echo "ERROR: stderr của $config có panic hoặc lỗi Gurobi." >&2
        grep -Ein "panicked|Gurobi.*error|license.*error" "$stderr_log" >&2
        exit 1
    fi
done

python3 - "$OUT_DIR" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
costs = {
    path.stem: json.loads(path.read_text())[0]["solves"][0].get("cost")
    for path in root.glob("RC2*.json")
}
if len(costs) != 4 or len(set(costs.values())) != 1:
    raise SystemExit(f"ERROR: Bốn cấu hình smoke không cùng chi phí: {costs}")
print(f"Chi phí tối ưu khớp giữa bốn cấu hình: {next(iter(costs.values()))}")
PY

echo "Smoke test đạt cho bốn cấu hình: $OUT_DIR"
