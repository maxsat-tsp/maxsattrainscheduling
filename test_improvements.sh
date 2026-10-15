#!/usr/bin/env bash
# Kiểm thử cải tiến 1 (suy luận sớm) và cải tiến 2 (refinement có chọn lọc)
# cho bài journal, dựa trên solver maxsat_rc2.
#
# ĐỌC TRƯỚC:
#   maxsat_rc2 là solver mới cho bài journal, KHÁC hoàn toàn với:
#     - maxsat_ddd_ladder     → Croella 2024 (baseline gốc)
#     - maxsat_ddd_ladder_sc  → MaxSAT-Default của bài hội nghị
#
# 4 cấu hình so sánh (tên đặt theo tài liệu hướng dẫn):
#
#   RC2-Base   — maxsat_rc2 không có cải tiến nào
#                  --maxsat-rc2-bound-mode off
#                  --maxsat-rc2-refinement-budget all
#
#   RC2+B      — + Cải tiến 1: suy luận cận và thứ tự bắt buộc
#                  --maxsat-rc2-bound-mode chain-cost-forced
#                  --maxsat-rc2-refinement-budget all
#
#   RC2+R      — + Cải tiến 2: refinement có chọn lọc
#                  --maxsat-rc2-bound-mode off
#                  --maxsat-rc2-refinement-budget K
#
#   RC2+B+R    — kết hợp cả hai (mục tiêu cuối)
#                  --maxsat-rc2-bound-mode chain-cost-forced
#                  --maxsat-rc2-refinement-budget K
#
# Usage:
#   bash test_improvements.sh RC2-Base
#   bash test_improvements.sh RC2+B
#   bash test_improvements.sh RC2+R
#   bash test_improvements.sh RC2+B+R
#   bash test_improvements.sh RC2+B+R 60 128 # timeout 60s, K=128
#   OUT_DIR=results/improvements/<thu_muc_cu> bash test_improvements.sh RC2+B+R 60 128
#     → tiếp tục đúng chiến dịch cũ và dùng lại các instance đã có kết quả.
#   RERUN_NON_OK=1 ...
#     → vẫn dùng lại kết quả ok nhưng chạy lại timeout/panic của chiến dịch cũ.
#
# Kết quả lưu vào: results/improvements/<TIMESTAMP>-<cấu_hình>/

set -euo pipefail

CONFIG="${1:-RC2-Base}"
TIMEOUT_SECS="${2:-120}"
REFINEMENT_BUDGET="${3:-128}"
EXTERNAL_TIMEOUT_GRACE_SECS="${EXTERNAL_TIMEOUT_GRACE_SECS:-20}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
OUT_DIR="${OUT_DIR:-results/improvements/${TIMESTAMP}-${CONFIG}}"
BIN="${BIN:-./target/release/ddd}"
RUN_SCRIPT="quick_scripts/run_all_txt_instances_limited.sh"
CSV_BATCH="quick_scripts/analyze/json_to_csv_batch.py"
AUDIT_SCRIPT="quick_scripts/analyze/audit_journal_campaign.py"

SOLVER_NAME="${SOLVER_NAME:-maxsat_rc2}"

# ── Kiểm tra ──────────────────────────────────────────────────────────────────

if [ ! -f "Cargo.toml" ]; then
    echo "ERROR: Chạy từ thư mục gốc maxsattrainscheduling/"
    exit 1
fi

echo "================================================================"
echo "KIỂM THỬ CẢI TIẾN JOURNAL: $CONFIG"
echo "================================================================"

case "$CONFIG" in
  "RC2-Base")
    BOUND_MODE="off"
    EFFECTIVE_BUDGET="all"
    ;;
  "RC2+B")
    BOUND_MODE="chain-cost-forced"
    EFFECTIVE_BUDGET="all"
    ;;
  "RC2+R")
    BOUND_MODE="off"
    EFFECTIVE_BUDGET="$REFINEMENT_BUDGET"
    ;;
  "RC2+B+R")
    BOUND_MODE="chain-cost-forced"
    EFFECTIVE_BUDGET="$REFINEMENT_BUDGET"
    ;;
  *)
    echo "Cấu hình không hợp lệ. Dùng: RC2-Base | RC2+B | RC2+R | RC2+B+R"
    exit 1
    ;;
esac

echo "  bound mode: $BOUND_MODE"
echo "  refinement budget: $EFFECTIVE_BUDGET"
echo "  full scan: true"
echo "  validate before return: true"
echo ""

# ── Bước 1: Build ─────────────────────────────────────────────────────────────

echo "[1/3] Building..."
if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    if [[ ! -x "$BIN" ]]; then
        echo "ERROR: SKIP_BUILD=1 nhưng không tìm thấy $BIN" >&2
        exit 1
    fi
    echo "  Dùng binary đã build: $BIN"
else
    if ! cargo build --release --locked --bin ddd 2>&1; then
        echo "ERROR: Build thất bại."
        exit 1
    fi
fi
echo "  OK: $BIN"
echo ""

mkdir -p "$OUT_DIR"

config_file="$OUT_DIR/config.txt"
expected_config_lines=(
    "config=$CONFIG"
    "bound_mode=$BOUND_MODE"
    "refinement_budget=$EFFECTIVE_BUDGET"
    "max_wait_iterations=${MAX_WAIT_ITERATIONS:-5}"
    "timeout_seconds=$TIMEOUT_SECS"
    "external_timeout_grace_seconds=$EXTERNAL_TIMEOUT_GRACE_SECS"
)
if [[ -s "$config_file" ]]; then
    for line in "${expected_config_lines[@]}"; do
        if ! grep -Fqx "$line" "$config_file"; then
            echo "ERROR: $config_file không khớp cấu hình cần chạy: $line" >&2
            echo "Hãy dùng OUT_DIR mới hoặc chạy lại đúng cấu hình cũ." >&2
            exit 2
        fi
    done
    echo "Tiếp tục chiến dịch đã có tại $OUT_DIR"
else
    printf '%s\n' "${expected_config_lines[@]}" >"$config_file"
fi

# ── Bước 2: Chạy 3 objectives ─────────────────────────────────────────────────

OBJECTIVES=(finsteps123 infsteps180 cont)
START_ALL=$(date +%s)

echo "[2/3] Running 3 objectives (timeout ${TIMEOUT_SECS}s/instance)..."
echo ""

run_idx=0
for obj in "${OBJECTIVES[@]}"; do
    run_idx=$((run_idx + 1))
    json_out="${OUT_DIR}/${CONFIG}_${obj}.json"

    echo "------------------------------------------------------------"
    echo "[$run_idx/3] $CONFIG | $obj"
    echo "  Solver: $SOLVER_NAME"
    echo "  Output: $json_out"
    echo "------------------------------------------------------------"

    t0=$(date +%s)

    BIN="$BIN" \
    SOLVER="$SOLVER_NAME" \
    OBJECTIVE="$obj" \
    JSON_OUT="$json_out" \
    RUN_LOG_DIR="${OUT_DIR}/${obj}.logs" \
    INSTANCE_TIMEOUT_SECS="$TIMEOUT_SECS" \
    EXTERNAL_TIMEOUT_GRACE_SECS="$EXTERNAL_TIMEOUT_GRACE_SECS" \
    RAM_LIMIT_KB="${RAM_LIMIT_KB:-15000000}" \
    MAXSAT_RC2_BOUND_MODE="$BOUND_MODE" \
    MAXSAT_RC2_REFINEMENT_BUDGET="$EFFECTIVE_BUDGET" \
    MAXSAT_RC2_MAX_WAIT_ITERATIONS="${MAX_WAIT_ITERATIONS:-5}" \
    MAXSAT_RC2_FULL_SCAN="true" \
    MAXSAT_RC2_VALIDATE_BEFORE_RETURN="true" \
    RERUN_NON_OK="${RERUN_NON_OK:-0}" \
    bash "$RUN_SCRIPT"

    t1=$(date +%s)

    python3 "$AUDIT_SCRIPT" \
        --file "$json_out" \
        --config "$CONFIG" \
        --objective "$obj" \
        --timeout "$TIMEOUT_SECS" \
        --budget "$REFINEMENT_BUDGET" \
        --max-wait "${MAX_WAIT_ITERATIONS:-5}"

    if python3 "$CSV_BATCH" "$json_out" --format compact --overwrite 2>/dev/null; then
        csv="${json_out%.json}.csv"
        n=$(( $(wc -l < "$csv") - 1 ))
        if [[ "$n" -ne 72 ]]; then
            echo "ERROR: $csv có $n dòng dữ liệu, cần đúng 72." >&2
            exit 3
        fi
        echo "  Done: $((t1 - t0))s | $n instances | $(basename "$csv")"
    else
        echo "ERROR: Không thể chuyển $json_out sang CSV." >&2
        exit 3
    fi
    echo ""
done

# ── Bước 3: Tóm tắt ───────────────────────────────────────────────────────────

END_ALL=$(date +%s)
ELAPSED=$((END_ALL - START_ALL))

echo "[3/3] Kết quả"
echo "================================================================"
echo "Cấu hình:       $CONFIG"
echo "Thời gian:      ${ELAPSED}s ($((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "Kết quả tại:    $OUT_DIR/"
echo ""
echo "Files CSV:"
ls -lh "$OUT_DIR"/*.csv 2>/dev/null | awk '{print "  " $NF}' || echo "  (không có)"
echo ""
echo "================================================================"
echo ""
echo "So sánh chi phí giữa các cấu hình (phải bằng nhau):"
echo "  ls results/improvements/"
echo "  # rồi so sánh cột 'cost' giữa RC2-Base và RC2+B+R"
