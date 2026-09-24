#!/usr/bin/env bash
# Kiểm thử các cải tiến 1 (suy luận sớm) và 2 (refinement có chọn lọc).
#
# CÁCH DÙNG:
#   Sau khi sửa const trong src/solvers/ddd/maxsat_rc2.rs, chạy:
#     bash test_improvements.sh <tên_cấu_hình> [timeout]
#
# Ví dụ:
#   bash test_improvements.sh C           # phiên bản gốc (tắt hết)
#   bash test_improvements.sh C+B         # Cải tiến 1: suy luận sớm
#   bash test_improvements.sh C+R         # Cải tiến 2: refinement chọn lọc
#   bash test_improvements.sh C+B+R       # Kết hợp cả hai
#   bash test_improvements.sh C+B+R 60    # Timeout 60s
#
# Trước mỗi lần chạy, sửa các const trong maxsat_rc2.rs:
#
#   Dòng 162  REFINEMENT_BUDGET:
#     None          → không giới hạn (add-all = baseline Cải tiến 2)
#     Some(32)      → budget K=32 (Cải tiến 2 có chọn lọc)
#
#   Cải tiến 1 (propagate_bounds, tighten_ub_from_cost):
#     Bật/tắt bằng cách xoá hoặc thêm lại các lời gọi trong code.
#     (Xem hướng dẫn Mục 4 trong student_implementation_guide_vi.tex)
#
# Kết quả lưu vào: results/improvements/<TIMESTAMP>-<tên_cấu_hình>/

set -euo pipefail

CONFIG="${1:-C}"
TIMEOUT_SECS="${2:-120}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
OUT_DIR="results/improvements/${TIMESTAMP}-${CONFIG}"
BIN="./target/release/ddd"
RUN_SCRIPT="quick_scripts/run_all_txt_instances_limited.sh"
CSV_BATCH="quick_scripts/analyze/json_to_csv_batch.py"

# ── Kiểm tra ──────────────────────────────────────────────────────────────────

if [ ! -f "Cargo.toml" ]; then
    echo "ERROR: Chạy từ thư mục gốc maxsattrainscheduling/"
    exit 1
fi

# ── Nhắc nhở sinh viên kiểm tra const ─────────────────────────────────────────

echo "================================================================"
echo "KIỂM THỬ CẢI TIẾN: $CONFIG"
echo "================================================================"
echo ""
echo "Kiểm tra const hiện tại trong maxsat_rc2.rs:"
echo ""

# Hiển thị các dòng const liên quan để sinh viên xác nhận trước khi chạy
grep -n "REFINEMENT_BUDGET\|USE_HEURISTIC" src/solvers/ddd/maxsat_rc2.rs \
    | grep "^[0-9]*:.*const" \
    | sed 's/^/  /'

echo ""
echo "Cấu hình bạn muốn chạy: $CONFIG"
echo "  C       → REFINEMENT_BUDGET = None,    Cải tiến 1 TẮT"
echo "  C+B     → REFINEMENT_BUDGET = None,    Cải tiến 1 BẬT"
echo "  C+R     → REFINEMENT_BUDGET = Some(K), Cải tiến 1 TẮT"
echo "  C+B+R   → REFINEMENT_BUDGET = Some(K), Cải tiến 1 BẬT"
echo ""
read -rp "Đã đặt const đúng chưa? Nhấn Enter để tiếp tục, Ctrl+C để huỷ... "
echo ""

# ── Bước 1: Build ─────────────────────────────────────────────────────────────

echo "[1/3] Building (cargo build --release)..."
if ! cargo build --release 2>&1; then
    echo "ERROR: Build thất bại."
    exit 1
fi
echo "  OK: $BIN"
echo ""

mkdir -p "$OUT_DIR"

# ── Bước 2: Chạy 3 objectives ─────────────────────────────────────────────────

OBJECTIVES=(finsteps123 infsteps180 cont)
CURRENT_RUN=0
START_ALL=$(date +%s)

echo "[2/3] Running 3 objectives (timeout ${TIMEOUT_SECS}s/instance)..."
echo ""

for obj in "${OBJECTIVES[@]}"; do
    CURRENT_RUN=$((CURRENT_RUN + 1))
    json_out="${OUT_DIR}/${CONFIG}_${obj}.json"

    echo "------------------------------------------------------------"
    echo "[$CURRENT_RUN/3] $CONFIG | $obj"
    echo "  Output: $json_out"
    echo "------------------------------------------------------------"

    t0=$(date +%s)

    BIN="$BIN" \
    SOLVER=maxsat_rc2 \
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

echo "[3/3] Xong"
echo "================================================================"
echo "Cấu hình:        $CONFIG"
echo "Tổng thời gian:  ${ELAPSED}s ($((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "Kết quả tại:     $OUT_DIR/"
echo ""
echo "Files:"
ls -lh "$OUT_DIR"/*.csv 2>/dev/null | awk '{print "  " $NF}' || echo "  (không có CSV)"
echo ""
echo "================================================================"
echo ""
echo "Bước tiếp theo:"
echo "  1. So sánh với cấu hình khác:"
echo "       python3 quick_scripts/analyze/mk_table.py $OUT_DIR"
echo ""
echo "  2. Kiểm tra nghiệm giống nhau (chi phí phải bằng C):"
echo "       diff <(grep -h cost $OUT_DIR/*.csv | sort) \\"
echo "            <(grep -h cost results/improvements/*-C/*.csv | sort)"
echo ""
echo "  3. Debug instance đơn lẻ:"
echo "       ./target/release/ddd -s maxsat_rc2 --txt-instances \\"
echo "         --instance-name-filter origA1 --instance-name-exact \\"
echo "         --objective finsteps123"
