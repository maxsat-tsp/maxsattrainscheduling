#!/usr/bin/env bash
# Chạy đúng một lượt trên toàn bộ 72 instance. Mặc định dùng bốn cấu hình;
# JOURNAL_CONFIGS có thể giới hạn cấu hình cho một phân tích sensitivity.

set -euo pipefail

TIMEOUT_SECS="${1:-120}"
REFINEMENT_BUDGET="${2:-128}"
JOURNAL_CONFIGS="${JOURNAL_CONFIGS:-RC2-Base RC2+B RC2+R RC2+B+R}"
EXTERNAL_TIMEOUT_GRACE_SECS="${EXTERNAL_TIMEOUT_GRACE_SECS:-20}"
RESULTS_ROOT="${RESULTS_ROOT:-results/improvements}"
RUN_ID="${RUN_ID:-journal-once-$(date +%Y-%m-%d_%H-%M-%S)}"
BIN="${BIN:-./target/release/ddd}"
SALVERS_REQUIRED_COMMIT="ac2b30c2570361e1a6a5d63a7ed715505f0bb201"
SALVERS_PATCH="external_patches/salvers-rustsat-compat.patch"

if [[ ! "$TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: timeout phải là số nguyên dương." >&2
    exit 2
fi
if [[ ! "$REFINEMENT_BUDGET" =~ ^[0-9]+$ ]]; then
    echo "ERROR: refinement budget phải là số nguyên không âm." >&2
    exit 2
fi
if [[ ! "$EXTERNAL_TIMEOUT_GRACE_SECS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: EXTERNAL_TIMEOUT_GRACE_SECS phải là số nguyên không âm." >&2
    exit 2
fi
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: RUN_ID chỉ được chứa chữ, số, dấu chấm, gạch dưới và gạch ngang." >&2
    exit 2
fi
read -r -a configs <<<"$JOURNAL_CONFIGS"
if [[ "${#configs[@]}" -eq 0 ]]; then
    echo "ERROR: JOURNAL_CONFIGS không được rỗng." >&2
    exit 2
fi
seen_configs=" "
for config in "${configs[@]}"; do
    case "$config" in
        RC2-Base|RC2+B|RC2+R|RC2+B+R) ;;
        *) echo "ERROR: Cấu hình không hợp lệ trong JOURNAL_CONFIGS: $config" >&2; exit 2 ;;
    esac
    if [[ "$seen_configs" == *" $config "* ]]; then
        echo "ERROR: Cấu hình bị lặp trong JOURNAL_CONFIGS: $config" >&2
        exit 2
    fi
    seen_configs+="$config "
done
configs_csv="$(IFS=,; echo "${configs[*]}")"
if [[ ! -f Cargo.toml ]]; then
    echo "ERROR: Hãy chạy script từ thư mục gốc maxsattrainscheduling/." >&2
    exit 2
fi
if ! git -C ../ipamir-rs rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: Không tìm thấy dependency ../ipamir-rs" >&2
    exit 2
fi
if ! command -v timeout >/dev/null 2>&1 && ! command -v gtimeout >/dev/null 2>&1; then
    echo "ERROR: Không tìm thấy timeout hoặc gtimeout trong PATH." >&2
    exit 2
fi
if ! command -v gurobi_cl >/dev/null 2>&1; then
    echo "ERROR: Không tìm thấy gurobi_cl trong PATH; cần Gurobi và license hợp lệ." >&2
    exit 2
fi
if [[ "$(git -C ../salvers rev-parse HEAD 2>/dev/null || true)" != "$SALVERS_REQUIRED_COMMIT" ]]; then
    echo "ERROR: ../salvers chưa ở commit $SALVERS_REQUIRED_COMMIT" >&2
    exit 2
fi
if ! git -C ../salvers apply --check --reverse "$PWD/$SALVERS_PATCH" >/dev/null 2>&1; then
    echo "ERROR: Chưa áp dụng $SALVERS_PATCH vào ../salvers" >&2
    exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    echo "ERROR: Cây Git chưa sạch. Hãy commit hoặc cất các thay đổi trước khi chạy." >&2
    git status --short >&2
    exit 2
fi

mkdir -p "$RESULTS_ROOT"
campaign_dir="$RESULTS_ROOT/$RUN_ID"
mkdir -p "$campaign_dir"
campaign_file="$campaign_dir/campaign.txt"
commit="$(git rev-parse HEAD)"

expected_campaign_lines=(
    "run_id=$RUN_ID"
    "git_commit=$commit"
    "timeout_seconds=$TIMEOUT_SECS"
    "external_timeout_grace_seconds=$EXTERNAL_TIMEOUT_GRACE_SECS"
    "refinement_budget=$REFINEMENT_BUDGET"
    "repetitions=1"
    "instances_per_objective=72"
    "objectives=finsteps123,infsteps180,cont"
    "configs=$configs_csv"
)

if [[ -s "$campaign_file" ]]; then
    for line in "${expected_campaign_lines[@]}"; do
        if ! grep -Fqx "$line" "$campaign_file"; then
            echo "ERROR: $campaign_file không khớp: $line" >&2
            exit 2
        fi
    done
    echo "Tiếp tục chiến dịch $RUN_ID"
else
    {
        printf '%s\n' "${expected_campaign_lines[@]}"
        printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$campaign_file"
fi

printf '%s\n' "$RUN_ID" >"$RESULTS_ROOT/journal_once_run_id.txt"

echo "Build đúng binary ddd từ Cargo.lock..."
if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    echo "Dùng binary đã build: $BIN"
else
    cargo build --release --locked --bin ddd
fi
[[ -x "$BIN" ]] || { echo "ERROR: Không tạo được $BIN" >&2; exit 1; }

for config in "${configs[@]}"; do
    echo "================================================================"
    echo "$config: 72 instance x 3 objectives, một lần"
    echo "================================================================"
    OUT_DIR="$campaign_dir/$config" \
    BIN="$BIN" \
    SKIP_BUILD=1 \
    RERUN_NON_OK=0 \
    EXTERNAL_TIMEOUT_GRACE_SECS="$EXTERNAL_TIMEOUT_GRACE_SECS" \
        bash test_improvements.sh "$config" "$TIMEOUT_SECS" "$REFINEMENT_BUDGET" \
        2>&1 | tee -a "$campaign_dir/$config.log"
done

echo "Kiểm tra cấu hình, telemetry, chi phí và tạo bảng tổng hợp..."
python3 quick_scripts/analyze/audit_journal_campaign.py "$campaign_dir"

printf 'completed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$campaign_file"
echo "Hoàn tất một lượt: $campaign_dir"
