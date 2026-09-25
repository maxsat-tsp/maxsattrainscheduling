#!/usr/bin/env bash
# Kiểm thử cải tiến 1 (suy luận sớm) và cải tiến 2 (refinement có chọn lọc)
# cho bài journal, dựa trên solver maxsat_rc2 (chưa có CLI riêng).
#
# ĐỌC TRƯỚC:
#   maxsat_rc2 là solver mới cho bài journal, KHÁC hoàn toàn với:
#     - maxsat_ddd_ladder     → Croella 2024 (baseline gốc)
#     - maxsat_ddd_ladder_sc  → MaxSAT-Default của bài hội nghị
#
#   Để chạy được, sinh viên cần wire maxsat_rc2 vào main.rs trước.
#   Xem hướng dẫn trong student_implementation_guide_vi.tex, Mục "Tích hợp".
#
# 4 cấu hình so sánh (tên đặt theo tài liệu hướng dẫn):
#
#   RC2-Base   — maxsat_rc2 không có cải tiến nào
#                  const REFINEMENT_BUDGET = None (add-all)
#                  KHÔNG gọi propagate_bounds()
#
#   RC2+B      — + Cải tiến 1: suy luận sớm (propagate_bounds + tighten_ub)
#                  const REFINEMENT_BUDGET = None
#                  GỌI propagate_bounds()
#
#   RC2+R      — + Cải tiến 2: refinement có chọn lọc
#                  const REFINEMENT_BUDGET = Some(32)
#                  KHÔNG gọi propagate_bounds()
#
#   RC2+B+R    — kết hợp cả hai (mục tiêu cuối)
#                  const REFINEMENT_BUDGET = Some(32)
#                  GỌI propagate_bounds()
#
# Usage:
#   bash test_improvements.sh RC2-Base
#   bash test_improvements.sh RC2+B
#   bash test_improvements.sh RC2+R
#   bash test_improvements.sh RC2+B+R
#   bash test_improvements.sh RC2+B+R 60     # timeout 60s
#
# Kết quả lưu vào: results/improvements/<TIMESTAMP>-<cấu_hình>/

set -euo pipefail

CONFIG="${1:-RC2-Base}"
TIMEOUT_SECS="${2:-120}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
OUT_DIR="results/improvements/${TIMESTAMP}-${CONFIG}"
BIN="./target/release/ddd"
RUN_SCRIPT="quick_scripts/run_all_txt_instances_limited.sh"
CSV_BATCH="quick_scripts/analyze/json_to_csv_batch.py"

# Solver CLI name cho maxsat_rc2 (sinh viên cần đặt tên này khi wire vào main.rs)
# Đổi nếu sinh viên đặt tên khác trong main.rs
SOLVER_NAME="${SOLVER_NAME:-maxsat_rc2}"

# ── Kiểm tra ──────────────────────────────────────────────────────────────────

if [ ! -f "Cargo.toml" ]; then
    echo "ERROR: Chạy từ thư mục gốc maxsattrainscheduling/"
    exit 1
fi

# ── Hướng dẫn đặt const ────────────────────────────────────────────────────────

echo "================================================================"
echo "KIỂM THỬ CẢI TIẾN JOURNAL: $CONFIG"
echo "================================================================"
echo ""
echo "Const hiện tại trong src/solvers/ddd/maxsat_rc2.rs:"
grep -n "REFINEMENT_BUDGET" src/solvers/ddd/maxsat_rc2.rs \
    | grep "const" | sed 's/^/  /'
echo ""

case "$CONFIG" in
  "RC2-Base")
    echo "Yêu cầu cho RC2-Base:"
    echo "  - Dòng 162: const REFINEMENT_BUDGET: Option<usize> = None;"
    echo "  - Dòng 129: TẮT propagate_bounds() (comment out hoặc xoá)"
    ;;
  "RC2+B")
    echo "Yêu cầu cho RC2+B (Cải tiến 1 BẬT):"
    echo "  - Dòng 162: const REFINEMENT_BUDGET: Option<usize> = None;"
    echo "  - Dòng 129: BẬT propagate_bounds() (đang bật sẵn)"
    ;;
  "RC2+R")
    echo "Yêu cầu cho RC2+R (Cải tiến 2 BẬT):"
    echo "  - Dòng 162: const REFINEMENT_BUDGET: Option<usize> = Some(32);"
    echo "  - Dòng 129: TẮT propagate_bounds()"
    ;;
  "RC2+B+R")
    echo "Yêu cầu cho RC2+B+R (cả hai BẬT):"
    echo "  - Dòng 162: const REFINEMENT_BUDGET: Option<usize> = Some(32);"
    echo "  - Dòng 129: BẬT propagate_bounds() (đang bật sẵn)"
    ;;
  *)
    echo "Cấu hình không hợp lệ. Dùng: RC2-Base | RC2+B | RC2+R | RC2+B+R"
    exit 1
    ;;
esac

echo ""
read -rp "Đã đặt const đúng chưa? Nhấn Enter để tiếp tục, Ctrl+C để huỷ... "
echo ""

# ── Bước 1: Build ─────────────────────────────────────────────────────────────

echo "[1/3] Building..."
if ! cargo build --release 2>&1; then
    echo "ERROR: Build thất bại."
    exit 1
fi
echo "  OK: $BIN"
echo ""

mkdir -p "$OUT_DIR"

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
    INSTANCE_TIMEOUT_SECS="$TIMEOUT_SECS" \
    RAM_LIMIT_KB="${RAM_LIMIT_KB:-15000000}" \
    bash "$RUN_SCRIPT"

    t1=$(date +%s)

    if python3 "$CSV_BATCH" "$json_out" --format compact --overwrite 2>/dev/null; then
        csv="${json_out%.json}.csv"
        n=$(( $(wc -l < "$csv") - 1 ))
        echo "  Done: $((t1 - t0))s | $n instances | $(basename "$csv")"
    else
        echo "  WARNING: CSV conversion failed"
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
