#!/usr/bin/env bash
# Staged, resumable AGLR campaign.
#
#   bash run_aglr_experiments.sh screen   # 18 settings, 30 s, development set
#   bash run_aglr_experiments.sh promote  # best three settings, 120 s
#   bash run_aglr_experiments.sh full     # locked setting + required baselines
#   bash run_aglr_experiments.sh confirm  # three repeats of hard/gained/lost cases

set -euo pipefail

MODE="${1:-screen}"
RESULTS_ROOT="${RESULTS_ROOT:-results/aglr}"
RUN_ID="${RUN_ID:-${MODE}-$(date +%Y-%m-%d_%H-%M-%S)}"
CAMPAIGN_DIR="$RESULTS_ROOT/$RUN_ID"
BIN="${BIN:-./target/release/ddd}"
RUNNER="quick_scripts/run_all_txt_instances_limited.sh"
AUDITOR="quick_scripts/analyze/audit_aglr_campaign.py"
CSV_BATCH="quick_scripts/analyze/json_to_csv_batch.py"
RAM_LIMIT_KB="${RAM_LIMIT_KB:-15000000}"
EXTERNAL_TIMEOUT_GRACE_SECS="${EXTERNAL_TIMEOUT_GRACE_SECS:-20}"
SCREEN_PARALLELISM="${SCREEN_PARALLELISM:-2}"
ABLATE_PARALLELISM="${ABLATE_PARALLELISM:-$SCREEN_PARALLELISM}"
FULL_TIMEOUT_SECS="${FULL_TIMEOUT_SECS:-120}"
ORDER_SEED_BASE="${ORDER_SEED_BASE:-20261025}"
DEVELOPMENT_INSTANCES="${DEVELOPMENT_INSTANCES:-origA3 trackA3 stationA3 origA6 trackA6 stationA6 origA9 trackA9 stationA9 origA12 trackA12 stationA12 origB3 trackB3 stationB3 origB6 trackB6 stationB6 origB9 trackB9 stationB9 origB12 trackB12 stationB12}"
CONFERENCE_RESULTS_DIR="${CONFERENCE_RESULTS_DIR:-results}"
CONFERENCE_PROFILE="${CONFERENCE_PROFILE:-published-csv-120}"
CONFERENCE_RUNTIME_MODE="${CONFERENCE_RUNTIME_MODE:-assumed-equivalent}"
CONFERENCE_SOURCE_DATA_COMMIT="db0b16f20d97045501e63e4b432a879218a0c180"
if [[ "$CONFERENCE_PROFILE" == "imported-json-150" ]]; then
  CONFERENCE_SOURCE_DATA_COMMIT="c427a104c3c6f844e515efb7f898b684553b0f3f"
elif [[ "$CONFERENCE_PROFILE" != "published-csv-120" ]]; then
  echo "ERROR: CONFERENCE_PROFILE không hợp lệ." >&2
  exit 2
fi
if [[ "$CONFERENCE_PROFILE" == "published-csv-120" && "$FULL_TIMEOUT_SECS" != 120 ]]; then
  echo "ERROR: mốc camera-ready dùng 120 giây; không dùng nó làm mốc chính cho cutoff khác." >&2
  exit 2
fi
AGLR_RESCUE_PROGRESS="${AGLR_RESCUE_PROGRESS:-bound-or-heuristic}"
AGLR_HEURISTIC_PERIOD="${AGLR_HEURISTIC_PERIOD:-1}"
AGLR_HEURISTIC_MIN_GAP="${AGLR_HEURISTIC_MIN_GAP:-0}"
AGLR_USE_OBJECTIVE_BOUND="${AGLR_USE_OBJECTIVE_BOUND:-false}"
AGLR_FILTER_DUPLICATES="${AGLR_FILTER_DUPLICATES:-false}"

case "$MODE" in
  baseline|candidate|ablate|screen|promote|full|confirm) ;;
  *) echo "ERROR: mode phải là baseline, candidate, ablate, screen, promote, full hoặc confirm." >&2; exit 2 ;;
esac
[[ "$SCREEN_PARALLELISM" =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: SCREEN_PARALLELISM phải là số nguyên dương." >&2
  exit 2
}
[[ "$ABLATE_PARALLELISM" =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: ABLATE_PARALLELISM phải là số nguyên dương." >&2
  exit 2
}
[[ "$FULL_TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: FULL_TIMEOUT_SECS phải là số nguyên dương." >&2
  exit 2
}
[[ -f Cargo.toml && -f "$RUNNER" && -f "$AUDITOR" ]] || {
  echo "ERROR: Hãy chạy script từ thư mục gốc repository." >&2
  exit 2
}
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ERROR: RUN_ID chỉ được chứa chữ, số, dấu chấm, gạch dưới và gạch ngang." >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "ERROR: Cây Git phải sạch để manifest xác định đúng mã nguồn." >&2
  git status --short >&2
  exit 2
fi
command -v python3 >/dev/null || { echo "ERROR: thiếu python3" >&2; exit 2; }
command -v gurobi_cl >/dev/null || {
  echo "ERROR: thiếu gurobi_cl hoặc Gurobi chưa được kích hoạt." >&2
  exit 2
}

conference_reference_sha256=""
if [[ -d "$CONFERENCE_RESULTS_DIR" ]]; then
  for objective in finsteps123 infsteps180 cont; do
    if [[ "$CONFERENCE_PROFILE" == "published-csv-120" ]]; then
      reference_file="$CONFERENCE_RESULTS_DIR/MaxSAT_Default_RC2_${objective}_120s.csv"
    else
      reference_file="$CONFERENCE_RESULTS_DIR/MaxsatScDefault_${objective}.json"
    fi
    [[ -f "$reference_file" ]] || {
      echo "ERROR: thiếu dữ liệu hội nghị cho $objective trong $CONFERENCE_RESULTS_DIR" >&2
      exit 2
    }
  done
  conference_reference_sha256="$(python3 - "$CONFERENCE_RESULTS_DIR" "$CONFERENCE_PROFILE" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for objective in ("finsteps123", "infsteps180", "cont"):
    path = root / (f"MaxSAT_Default_RC2_{objective}_120s.csv" if sys.argv[2] == "published-csv-120" else f"MaxsatScDefault_{objective}.json")
    digest.update(path.name.encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
print(digest.hexdigest())
PY
)"
fi

mkdir -p "$CAMPAIGN_DIR"

if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
  [[ -x "$BIN" ]] || { echo "ERROR: không tìm thấy binary $BIN" >&2; exit 2; }
else
  cargo build --release --locked --bin ddd
fi

binary_sha256="$(python3 - "$BIN" <<'PY'
import hashlib, pathlib, sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"

campaign_file="$CAMPAIGN_DIR/campaign.txt"
git_commit="$(git rev-parse HEAD)"
if [[ ! -s "$campaign_file" ]]; then
  {
    printf 'mode=%s\n' "$MODE"
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'git_commit=%s\n' "$git_commit"
    printf 'binary_sha256=%s\n' "$binary_sha256"
    printf 'repetitions=1\n'
    printf 'screen_parallelism=%s\n' "$SCREEN_PARALLELISM"
    printf 'ablate_parallelism=%s\n' "$ABLATE_PARALLELISM"
    printf 'full_timeout_seconds=%s\n' "$FULL_TIMEOUT_SECS"
    printf 'rescue_progress=%s\n' "$AGLR_RESCUE_PROGRESS"
    printf 'heuristic_period=%s\n' "$AGLR_HEURISTIC_PERIOD"
    printf 'heuristic_min_gap=%s\n' "$AGLR_HEURISTIC_MIN_GAP"
    printf 'use_objective_bound=%s\n' "$AGLR_USE_OBJECTIVE_BOUND"
    printf 'filter_duplicates=%s\n' "$AGLR_FILTER_DUPLICATES"
    printf 'conference_profile=%s\n' "$CONFERENCE_PROFILE"
    if [[ -n "$conference_reference_sha256" ]]; then
      printf 'conference_reference_dir=%s\n' "$CONFERENCE_RESULTS_DIR"
      printf 'conference_reference_sha256=%s\n' "$conference_reference_sha256"
      printf 'conference_reference_source_data_commit=%s\n' "$CONFERENCE_SOURCE_DATA_COMMIT"
      printf 'conference_runtime_mode=%s\n' "$CONFERENCE_RUNTIME_MODE"
      if [[ "$CONFERENCE_RUNTIME_MODE" == "assumed-equivalent" ]]; then
        printf 'conference_runtime_comparable=true\n'
      else
        printf 'conference_runtime_comparable=false\n'
      fi
    fi
    printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$campaign_file"
else
  python3 - "$campaign_file" "$MODE" "$RUN_ID" "$git_commit" "$binary_sha256" "$conference_reference_sha256" "$CONFERENCE_SOURCE_DATA_COMMIT" "$CONFERENCE_RUNTIME_MODE" "$SCREEN_PARALLELISM" "$ABLATE_PARALLELISM" "$FULL_TIMEOUT_SECS" "$AGLR_RESCUE_PROGRESS" "$AGLR_HEURISTIC_PERIOD" "$AGLR_HEURISTIC_MIN_GAP" "$AGLR_USE_OBJECTIVE_BOUND" "$AGLR_FILTER_DUPLICATES" "$CONFERENCE_PROFILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
expected = dict(zip(("mode", "run_id", "git_commit", "binary_sha256"), sys.argv[2:]))
if sys.argv[6]:
    expected["conference_reference_sha256"] = sys.argv[6]
    expected["conference_reference_source_data_commit"] = sys.argv[7]
    expected["conference_runtime_mode"] = sys.argv[8]
expected.update(zip(("screen_parallelism", "ablate_parallelism", "full_timeout_seconds", "rescue_progress", "heuristic_period", "heuristic_min_gap", "use_objective_bound", "filter_duplicates"), sys.argv[9:]))
expected["conference_profile"] = sys.argv[17]
actual = {}
for line in path.read_text().splitlines():
    key, separator, value = line.partition("=")
    if separator and key not in actual:
        actual[key] = value
wrong = {key: (actual.get(key), value) for key, value in expected.items() if actual.get(key) != value}
if wrong:
    raise SystemExit(f"ERROR: campaign không thể tiếp tục với mã/binary khác: {wrong}")
PY
fi

stable_seed() {
  local tag="$1"
  python3 - "$ORDER_SEED_BASE" "$tag" <<'PY'
import hashlib, sys
base = int(sys.argv[1])
offset = int(hashlib.sha256(sys.argv[2].encode()).hexdigest()[:8], 16)
print((base + offset) % 2147483647 or 1)
PY
}

write_config() {
  local path="$1"; shift
  local expected
  expected="$(printf '%s\n' "$@")"
  if [[ -s "$path" && "$(cat "$path")" != "$expected" ]]; then
    echo "ERROR: $path không khớp cấu hình cần tiếp tục." >&2
    exit 2
  fi
  printf '%s\n' "$@" > "$path"
}

run_method() {
  local tag="$1" solver="$2" kind="$3" policy="$4"
  local min_growth="$5" fraction="$6" max_wait="$7" timeout="$8" instances="$9"
  local method_dir="$CAMPAIGN_DIR/$tag"
  mkdir -p "$method_dir"
  write_config "$method_dir/config.txt" \
    "tag=$tag" \
    "solver=$solver" \
    "kind=$kind" \
    "policy=$policy" \
    "min_growth=$min_growth" \
    "fraction=$fraction" \
    "max_wait=$max_wait" \
    "rescue_progress=$AGLR_RESCUE_PROGRESS" \
    "heuristic_period=$AGLR_HEURISTIC_PERIOD" \
    "heuristic_min_gap=$AGLR_HEURISTIC_MIN_GAP" \
    "use_objective_bound=$AGLR_USE_OBJECTIVE_BOUND" \
    "filter_duplicates=$AGLR_FILTER_DUPLICATES" \
    "process_exit_required=true" \
    "timeout_seconds=$timeout" \
    "instances=$(tr ' ' ',' <<<"$instances")"

  for objective in finsteps123 infsteps180 cont; do
    local json_out="$method_dir/$objective.json"
    local worker_ram="$RAM_LIMIT_KB"
    if [[ "$MODE" == "screen" ]]; then
      worker_ram=$((RAM_LIMIT_KB / SCREEN_PARALLELISM))
    fi
    echo "[$tag] $objective | timeout=${timeout}s | instances=$([[ -n "$instances" ]] && wc -w <<<"$instances" || echo 72)"
    BIN="$BIN" \
    SOLVER="$solver" \
    OBJECTIVE="$objective" \
    JSON_OUT="$json_out" \
    RUN_LOG_DIR="$method_dir/$objective.logs" \
    INSTANCE_TIMEOUT_SECS="$timeout" \
    EXTERNAL_TIMEOUT_GRACE_SECS="$EXTERNAL_TIMEOUT_GRACE_SECS" \
    RAM_LIMIT_KB="$worker_ram" \
    AGLR_POLICY="$policy" \
    AGLR_MIN_GROWTH="$min_growth" \
    AGLR_FRACTION="$fraction" \
    AGLR_MAX_WAIT="$max_wait" \
    AGLR_RESCUE_PROGRESS="$AGLR_RESCUE_PROGRESS" \
    AGLR_HEURISTIC_PERIOD="$AGLR_HEURISTIC_PERIOD" \
    AGLR_HEURISTIC_MIN_GAP="$AGLR_HEURISTIC_MIN_GAP" \
    AGLR_USE_OBJECTIVE_BOUND="$AGLR_USE_OBJECTIVE_BOUND" \
    AGLR_FILTER_DUPLICATES="$AGLR_FILTER_DUPLICATES" \
    INSTANCE_NAMES="$instances" \
    INSTANCE_ORDER_SEED="$(stable_seed "$tag-$objective")" \
    RERUN_NON_OK="${RERUN_NON_OK:-0}" \
      bash "$RUNNER"
    python3 "$CSV_BATCH" "$json_out" --format compact --overwrite >/dev/null
  done
}

latest_path() {
  local name="$1"
  local pointer="$RESULTS_ROOT/latest_${name}.txt"
  [[ -s "$pointer" ]] || { echo "ERROR: chưa có $pointer" >&2; exit 2; }
  cat "$pointer"
}

read_winner() {
  local source_dir="$1"
  python3 - "$source_dir/aglr_ranking.csv" <<'PY'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    row = next(csv.DictReader(handle))
print(row["min_growth"], row["fraction"], row["max_wait"])
PY
}

load_variant() {
  read -r AGLR_RESCUE_PROGRESS AGLR_HEURISTIC_PERIOD AGLR_HEURISTIC_MIN_GAP AGLR_USE_OBJECTIVE_BOUND AGLR_FILTER_DUPLICATES < <(python3 - "$1" <<'PY'
import sys
from pathlib import Path
values = dict(line.split("=", 1) for line in Path(sys.argv[1]).read_text().splitlines() if "=" in line)
print(*(values.get(k, default) for k, default in (
    ("rescue_progress", "bound-or-heuristic"), ("heuristic_period", "1"),
    ("heuristic_min_gap", "0"), ("use_objective_bound", "false"), ("filter_duplicates", "false"))))
PY
  )
}

audit_campaign() {
  python3 "$AUDITOR" "$CAMPAIGN_DIR" --timeout "$1" \
    --conference-reference "$CONFERENCE_RESULTS_DIR" \
    --conference-profile "$CONFERENCE_PROFILE" \
    --conference-runtime-mode "$CONFERENCE_RUNTIME_MODE"
}

if [[ "$MODE" == "baseline" ]]; then
  run_method CSOnet maxsat_ddd_ladder_sc exact legacy 32 0.5 5 "$FULL_TIMEOUT_SECS" ""
  audit_campaign "$FULL_TIMEOUT_SECS"
elif [[ "$MODE" == "candidate" ]]; then
  run_method AGLR maxsat_ddd_ladder_aglr exact adaptive \
    "${AGLR_MIN_GROWTH:-16}" "${AGLR_FRACTION:-0.25}" "${AGLR_MAX_WAIT:-5}" "$FULL_TIMEOUT_SECS" ""
  audit_campaign "$FULL_TIMEOUT_SECS"
elif [[ "$MODE" == "ablate" ]]; then
  # Every variant changes exactly one component relative to Control.
  variants=(
    "Control bound-or-heuristic 1 0 false false"
    "Rescue-model model 1 0 false false"
    "Heuristic-period bound-or-heuristic 2 0 false false"
    "Heuristic-gap bound-or-heuristic 1 1 false false"
    "Filter-duplicates bound-or-heuristic 1 0 false true"
    "Objective-bound bound-or-heuristic 1 0 true false"
  )
  ablate_parallelism="${ABLATE_PARALLELISM:-$SCREEN_PARALLELISM}"
  [[ "$ablate_parallelism" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: ABLATE_PARALLELISM phải là số nguyên dương." >&2
    exit 2
  }
  worker_pids=()
  trap 'for worker in "${worker_pids[@]}"; do kill "$worker" 2>/dev/null || true; done' EXIT
  for variant in "${variants[@]}"; do
    (
      read -r tag AGLR_RESCUE_PROGRESS AGLR_HEURISTIC_PERIOD AGLR_HEURISTIC_MIN_GAP AGLR_USE_OBJECTIVE_BOUND AGLR_FILTER_DUPLICATES <<< "$variant"
      run_method "$tag" maxsat_ddd_ladder_aglr exact adaptive \
        "${AGLR_MIN_GROWTH:-16}" "${AGLR_FRACTION:-0.25}" "${AGLR_MAX_WAIT:-5}" 30 "$DEVELOPMENT_INSTANCES"
    ) &
    worker_pids+=("$!")
    if (( ${#worker_pids[@]} >= ablate_parallelism )); then
      for worker in "${worker_pids[@]}"; do wait "$worker"; done
      worker_pids=()
    fi
  done
  for worker in "${worker_pids[@]}"; do wait "$worker"; done
  worker_pids=()
  trap - EXIT
  audit_campaign 30
elif [[ "$MODE" == "screen" ]]; then
  configs=()
  while IFS= read -r config; do
    configs+=("$config")
  done < <(python3 - "$ORDER_SEED_BASE" <<'PY'
import random, sys
rows = []
for k in (16, 32, 64):
    for rho in (0.25, 0.5, 0.75):
        for wait in (5, 10):
            tag = f"AGLR-k{k}-r{str(rho).replace('.', 'p')}-w{wait}"
            rows.append((tag, k, rho, wait))
random.Random(int(sys.argv[1])).shuffle(rows)
for row in rows:
    print(*row)
PY
  )
  worker_pids=()
  trap 'for worker in "${worker_pids[@]}"; do kill "$worker" 2>/dev/null || true; done' EXIT
  for config in "${configs[@]}"; do
    read -r tag min_growth fraction max_wait <<< "$config"
    (
      run_method "$tag" maxsat_ddd_ladder_aglr exact adaptive \
        "$min_growth" "$fraction" "$max_wait" 30 "$DEVELOPMENT_INSTANCES"
    ) &
    worker_pids+=("$!")
    if (( ${#worker_pids[@]} >= SCREEN_PARALLELISM )); then
      for worker in "${worker_pids[@]}"; do wait "$worker"; done
      worker_pids=()
    fi
  done
  for worker in "${worker_pids[@]}"; do wait "$worker"; done
  worker_pids=()
  trap - EXIT
  audit_campaign 30
  printf '%s\n' "$CAMPAIGN_DIR" > "$RESULTS_ROOT/latest_screen.txt"

elif [[ "$MODE" == "promote" ]]; then
  source_dir="${SCREEN_DIR:-$(latest_path screen)}"
  finalists=()
  while IFS= read -r finalist; do
    finalists+=("$finalist")
  done < <(python3 - "$source_dir/aglr_ranking.csv" "$ORDER_SEED_BASE" <<'PY'
import csv, random, sys
with open(sys.argv[1], newline="") as handle:
    rows = list(csv.DictReader(handle))[:3]
random.Random(int(sys.argv[2])).shuffle(rows)
for row in rows:
    print(row["tag"], row["min_growth"], row["fraction"], row["max_wait"])
PY
  )
  [[ "${#finalists[@]}" -eq 3 ]] || { echo "ERROR: cần đúng ba cấu hình từ screen." >&2; exit 2; }
  for finalist in "${finalists[@]}"; do
    read -r old_tag min_growth fraction max_wait <<< "$finalist"
    load_variant "$source_dir/$old_tag/config.txt"
    tag="Promote-${old_tag}"
    run_method "$tag" maxsat_ddd_ladder_aglr exact adaptive \
      "$min_growth" "$fraction" "$max_wait" 120 "$DEVELOPMENT_INSTANCES"
  done
  audit_campaign 120
  printf '%s\n' "$CAMPAIGN_DIR" > "$RESULTS_ROOT/latest_promote.txt"

elif [[ "$MODE" == "full" ]]; then
  if [[ -n "${AGLR_MIN_GROWTH:-}" && -n "${AGLR_FRACTION:-}" && -n "${AGLR_MAX_WAIT:-}" ]]; then
    min_growth="$AGLR_MIN_GROWTH"; fraction="$AGLR_FRACTION"; max_wait="$AGLR_MAX_WAIT"
  else
    promote_dir="${PROMOTE_DIR:-$(latest_path promote)}"
    read -r min_growth fraction max_wait <<< "$(read_winner "$promote_dir")"
    winner_tag="$(python3 -c 'import csv,sys; print(next(csv.DictReader(open(sys.argv[1])))["tag"])' "$promote_dir/aglr_ranking.csv")"
    load_variant "$promote_dir/$winner_tag/config.txt"
  fi

  methods=()
  while IFS= read -r method; do
    methods+=("$method")
  done < <(python3 - "$min_growth" "$fraction" "$max_wait" "$ORDER_SEED_BASE" <<'PY'
import random, sys
k, rho, wait, seed = sys.argv[1:]
rows = [
    ("MaxSAT-Journal", "maxsat_ddd_ladder", "exact", "legacy", "32", "0.5", "5"),
    ("CSOnet", "maxsat_ddd_ladder_sc", "exact", "legacy", "32", "0.5", "5"),
    ("AGLR-All", "maxsat_ddd_ladder_aglr", "exact", "all-scanned", k, rho, wait),
    ("AGLR", "maxsat_ddd_ladder_aglr", "exact", "adaptive", k, rho, wait),
    ("BigM-Gurobi", "bigm_lazy", "milp", "legacy", "32", "0.5", "5"),
]
random.Random(int(seed)).shuffle(rows)
for row in rows:
    print(*row)
PY
  )
  for method in "${methods[@]}"; do
    read -r tag solver kind policy k rho wait <<< "$method"
    run_method "$tag" "$solver" "$kind" "$policy" "$k" "$rho" "$wait" "$FULL_TIMEOUT_SECS" ""
  done

  if [[ -n "${CPLEX_RESULTS_DIR:-}" ]]; then
    mkdir -p "$CAMPAIGN_DIR/CPLEX"
    python3 - "$CPLEX_RESULTS_DIR" "$CAMPAIGN_DIR/CPLEX" "$FULL_TIMEOUT_SECS" <<'PY'
from pathlib import Path
import shutil, sys

source, target = map(Path, sys.argv[1:3])
for objective in ("finsteps123", "infsteps180", "cont"):
    timeout = sys.argv[3]
    matches = sorted(source.glob(f"results_bigm_{objective}_{timeout}s.csv"))
    matches += sorted(source.glob(f"MILP_BigM_CPLEX_{objective}_{timeout}s.csv"))
    if not matches:
        raise SystemExit(f"ERROR: thiếu CSV CPLEX {timeout}s cho {objective} trong {source}")
    shutil.copy2(matches[-1], target / f"results_bigm_{objective}_{timeout}s.csv")
PY
  else
    echo "LƯU Ý: chưa có CPLEX_RESULTS_DIR; auditor sẽ giữ cổng submission ở trạng thái NOT YET."
  fi
  python3 "$AUDITOR" "$CAMPAIGN_DIR" --timeout "$FULL_TIMEOUT_SECS" \
    --conference-reference "$CONFERENCE_RESULTS_DIR" \
    --conference-profile "$CONFERENCE_PROFILE" \
    --conference-runtime-mode "$CONFERENCE_RUNTIME_MODE"
  printf '%s\n' "$CAMPAIGN_DIR" > "$RESULTS_ROOT/latest_full.txt"

else
  full_dir="${FULL_DIR:-$(latest_path full)}"
  python3 - "$full_dir/aglr_audit.json" <<'PY'
import json, sys
audit = json.load(open(sys.argv[1]))
if not (audit.get("gate") or {}).get("coverage_passed"):
    raise SystemExit("ERROR: chưa đạt cổng coverage; chưa chạy confirm.")
PY
  instances="$(tr '\n' ' ' < "$full_dir/confirm_instances.txt")"
  [[ -n "$instances" ]] || { echo "Không có instance cần chạy xác nhận."; exit 0; }
  read -r min_growth fraction max_wait <<< "$(python3 - "$full_dir/AGLR/config.txt" <<'PY'
import sys
values = dict(line.strip().split("=", 1) for line in open(sys.argv[1]) if "=" in line)
print(values["min_growth"], values["fraction"], values["max_wait"])
PY
  )"
  load_variant "$full_dir/AGLR/config.txt"
  for repetition in 1 2 3; do
    run_method "AGLR-confirm-$repetition" maxsat_ddd_ladder_aglr exact adaptive \
      "$min_growth" "$fraction" "$max_wait" "$FULL_TIMEOUT_SECS" "$instances"
  done
  python3 "$AUDITOR" "$CAMPAIGN_DIR" --timeout "$FULL_TIMEOUT_SECS" --reference-full "$full_dir"
fi

printf 'completed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$campaign_file"
echo "Hoàn tất: $CAMPAIGN_DIR"
