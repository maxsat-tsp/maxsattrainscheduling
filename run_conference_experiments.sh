#!/usr/bin/env bash
# Chạy lại toàn bộ thực nghiệm cho bài hội nghị sau khi chỉnh sửa mã nguồn.
#
# Script này thực hiện tuần tự:
#   1. Build lại binary (cargo build --release)
#   2. Chạy 4 cấu hình MaxSAT x 3 objective = 12 lần thực nghiệm
#      (MaxsatBaseline, MaxsatDefault, MaxsatSC, MaxsatPrec)
#   3. Convert kết quả JSON -> CSV
#   4. Tóm tắt kết quả cuối cùng
#
# Kết quả lưu vào: results/<TIMESTAMP>-conference/
#
# Usage:
#   bash run_conference_experiments.sh
#
# Tuỳ chỉnh (env vars):
#   TIMEOUT_SECS   thời gian tối đa mỗi instance (mặc định: 120)
#   RAM_LIMIT_KB   giới hạn RAM mỗi instance (mặc định: 15GB = 15000000)
#   OUT_DIR        thư mục output tuỳ chỉnh (mặc định: tự động theo ngày giờ)
#
# Ví dụ chạy nền (khuyến nghị khi đang viết paper):
#   nohup bash run_conference_experiments.sh > experiment.log 2>&1 &
#   tail -f experiment.log

set -euo pipefail

# ── Cấu hình ──────────────────────────────────────────────────────────────────

TIMEOUT_SECS="${TIMEOUT_SECS:-120}"
RAM_LIMIT_KB="${RAM_LIMIT_KB:-15000000}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
OUT_DIR="${OUT_DIR:-results/${TIMESTAMP}-conference}"
BIN="./target/release/ddd"
CSV_BATCH="quick_scripts/analyze/json_to_csv_batch.py"
RUN_SCRIPT="quick_scripts/run_all_txt_instances_limited.sh"

# ── Kiểm tra môi trường ────────────────────────────────────────────────────────

if [ ! -f "Cargo.toml" ]; then
    echo "ERROR: Chạy script này từ thư mục gốc của repo (maxsattrainscheduling/)"
    exit 1
fi

if [ ! -f "$RUN_SCRIPT" ]; then
    echo "ERROR: Không tìm thấy $RUN_SCRIPT"
    exit 1
fi

if [ ! -f "$CSV_BATCH" ]; then
    echo "ERROR: Không tìm thấy $CSV_BATCH"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 không có trong PATH"
    exit 1
fi

# ── Bước 1: Build ─────────────────────────────────────────────────────────────

echo "================================================================"
echo "CONFERENCE EXPERIMENT RUNNER"
echo "================================================================"
echo "Timestamp:   $TIMESTAMP"
echo "Output dir:  $OUT_DIR"
echo "Timeout:     ${TIMEOUT_SECS}s / instance"
echo "RAM limit:   $((RAM_LIMIT_KB / 1000000))GB / instance"
echo "================================================================"
echo ""
echo "[1/3] Building binary..."
echo "  $ cargo build --release"
echo ""

if ! cargo build --release 2>&1; then
    echo ""
    echo "ERROR: Build thất bại. Kiểm tra lỗi Rust ở trên."
    exit 1
fi

if [ ! -x "$BIN" ]; then
    echo "ERROR: Binary $BIN không tồn tại sau khi build."
    exit 1
fi

echo ""
echo "  Build OK: $BIN"
echo ""

# ── Bước 2: Chạy thực nghiệm ─────────────────────────────────────────────────

mkdir -p "$OUT_DIR"

OBJECTIVES=(finsteps123 infsteps180 cont)
TOTAL_RUNS=9   # 3 configs × 3 objectives (MaxsatDefault đã chạy trước, bỏ qua)
CURRENT_RUN=0

START_ALL=$(date +%s)

echo "[2/3] Running experiments ($TOTAL_RUNS runs total)..."
echo ""

# Hàm chạy 1 cấu hình với 1 objective
run_one() {
    local tag="$1"
    local solver="$2"
    local obj="$3"
    shift 3
    local extra_env=("$@")

    CURRENT_RUN=$((CURRENT_RUN + 1))
    local json_out="${OUT_DIR}/${tag}_${obj}.json"

    echo "------------------------------------------------------------"
    echo "[$CURRENT_RUN/$TOTAL_RUNS] $tag | $obj"
    echo "  Solver: $solver"
    echo "  Output: $json_out"
    if [ ${#extra_env[@]} -gt 0 ]; then
        echo "  Flags:  ${extra_env[*]}"
    fi
    echo "------------------------------------------------------------"

    local t0=$(date +%s)

    BIN="$BIN" \
    SOLVER="$solver" \
    OBJECTIVE="$obj" \
    JSON_OUT="$json_out" \
    INSTANCE_TIMEOUT_SECS="$TIMEOUT_SECS" \
    RAM_LIMIT_KB="$RAM_LIMIT_KB" \
    env "${extra_env[@]}" \
    bash "$RUN_SCRIPT"

    # Convert JSON -> CSV
    if python3 "$CSV_BATCH" "$json_out" --format compact --overwrite 2>/dev/null; then
        local csv_out="${json_out%.json}.csv"
        local n_rows=$(( $(wc -l < "$csv_out") - 1 ))
        local t1=$(date +%s)
        echo "  Done in $((t1 - t0))s | $n_rows instances -> $(basename "$csv_out")"
    else
        echo "  WARNING: CSV conversion failed for $json_out"
    fi
    echo ""
}

for obj in "${OBJECTIVES[@]}"; do

    # Baseline: Croella 2024 (không có cải tiến)
    run_one MaxsatBaseline maxsat_ddd_ladder "$obj"

    # Chỉ SC AMO (tắt precedence graph)
    run_one MaxsatSC maxsat_ddd_ladder_sc "$obj" \
        MAXSATDDD_USE_PRECEDENCE_GRAPH=false \
        MAXSATDDD_USE_SC_AMO=true \
        MAXSATDDD_USE_TOUCHED_CLIQUE_AMO=true

    # Chỉ precedence graph (tắt SC AMO)
    run_one MaxsatPrec maxsat_ddd_ladder_sc "$obj" \
        MAXSATDDD_USE_PRECEDENCE_GRAPH=true \
        MAXSATDDD_USE_SC_AMO=false \
        MAXSATDDD_USE_TOUCHED_CLIQUE_AMO=false

done

# ── Bước 3: Tóm tắt ───────────────────────────────────────────────────────────

END_ALL=$(date +%s)
ELAPSED=$((END_ALL - START_ALL))

echo "[3/3] Summary"
echo "================================================================"
echo "Tất cả $TOTAL_RUNS lần chạy HOÀN THÀNH"
echo "Tổng thời gian: ${ELAPSED}s ($((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "Kết quả lưu tại: $OUT_DIR/"
echo ""
echo "Files CSV:"
ls -lh "$OUT_DIR"/*.csv 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}' || echo "  (không có CSV)"
echo ""
echo "Files JSON:"
ls -lh "$OUT_DIR"/*.json 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}' || echo "  (không có JSON)"
echo "================================================================"
echo ""
echo "Bước tiếp theo:"
echo "  1. Kiểm tra kết quả:  python3 manuscript/journal/audit_existing_results.py"
echo "  2. Tạo bảng LaTeX:    python3 generate_summary_table.py"
echo "  3. Commit kết quả:    git add results/ && git commit -m 'Update experiment results'"
