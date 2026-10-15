#!/usr/bin/env bash
set -euo pipefail

BIN="${BIN:-./target/release/ddd}"
SOLVER="${SOLVER:-sat_ddd_sc_totalizer}"
OBJECTIVE="${OBJECTIVE:-cont}"
JSON_OUT="${JSON_OUT:-results_sat_sc_cont_totalizer.json}"
INSTANCE_TIMEOUT_SECS="${INSTANCE_TIMEOUT_SECS:-120}"
EXTERNAL_TIMEOUT_GRACE_SECS="${EXTERNAL_TIMEOUT_GRACE_SECS:-20}"
RAM_LIMIT_KB="${RAM_LIMIT_KB:-12000000}"
KEEP_TMPDIR="${KEEP_TMPDIR:-0}"
SATDDD_OBJECTIVE_ENCODING="${SATDDD_OBJECTIVE_ENCODING:-}"
RUN_LOG_DIR="${RUN_LOG_DIR:-${JSON_OUT%.json}.logs}"
MAXSAT_RC2_BOUND_MODE="${MAXSAT_RC2_BOUND_MODE:-}"
MAXSAT_RC2_REFINEMENT_BUDGET="${MAXSAT_RC2_REFINEMENT_BUDGET:-}"
MAXSAT_RC2_MAX_WAIT_ITERATIONS="${MAXSAT_RC2_MAX_WAIT_ITERATIONS:-}"
MAXSAT_RC2_FULL_SCAN="${MAXSAT_RC2_FULL_SCAN:-}"
MAXSAT_RC2_VALIDATE_BEFORE_RETURN="${MAXSAT_RC2_VALIDATE_BEFORE_RETURN:-}"
RERUN_NON_OK="${RERUN_NON_OK:-0}"
TIMEOUT_BIN="${TIMEOUT_BIN:-}"
export RUST_BACKTRACE="${RUST_BACKTRACE:-1}"

if ! [[ "$INSTANCE_TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: INSTANCE_TIMEOUT_SECS phải là số nguyên dương." >&2
  exit 2
fi
if ! [[ "$EXTERNAL_TIMEOUT_GRACE_SECS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: EXTERNAL_TIMEOUT_GRACE_SECS phải là số nguyên không âm." >&2
  exit 2
fi
EXTERNAL_TIMEOUT_SECS=$((INSTANCE_TIMEOUT_SECS + EXTERNAL_TIMEOUT_GRACE_SECS))

if [[ -z "$TIMEOUT_BIN" ]]; then
  TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
fi

# `SatDddSettings` knobs forwarded to `--satddd-*` flags when set.
# Empty value means "leave the binary's default in place".
# `SATDDD_USE_PRECEDENCE_GRAPH` is kept as an alias for the renamed
# `--satddd-use-precedence-graph` so older invocations still work.
SATDDD_USE_PRECEDENCE_GRAPH="${SATDDD_USE_PRECEDENCE_GRAPH:-${SATDDD_USE_PRECEDENCE_GRAPH:-}}"
SATDDD_PREALLOC_COST_THRESHOLDS="${SATDDD_PREALLOC_COST_THRESHOLDS:-}"
SATDDD_SEED_PRECEDENCE_FROM_EARLIEST="${SATDDD_SEED_PRECEDENCE_FROM_EARLIEST:-}"
SATDDD_SEED_RESOURCE_CONFLICTS="${SATDDD_SEED_RESOURCE_CONFLICTS:-}"
SATDDD_USE_SC_AMO="${SATDDD_USE_SC_AMO:-}"

# `MaxSatDddLadderScSettings` knobs forwarded to `--maxsat-ladder-sc-*`
# flags when set. Effective only when SOLVER=maxsat_ddd_ladder_sc. Empty
# value means "leave the binary's default in place".
MAXSATDDD_USE_PRECEDENCE_GRAPH="${MAXSATDDD_USE_PRECEDENCE_GRAPH:-}"
MAXSATDDD_USE_SC_AMO="${MAXSATDDD_USE_SC_AMO:-}"
MAXSATDDD_USE_TOUCHED_CLIQUE_AMO="${MAXSATDDD_USE_TOUCHED_CLIQUE_AMO:-}"

tmpdir="$(mktemp -d /tmp/ddd-run-all.XXXXXX)"
order_file="$tmpdir/order.txt"
touch "$order_file"
mkdir -p "$RUN_LOG_DIR"
instance_json_dir="$RUN_LOG_DIR/instances"
mkdir -p "$instance_json_dir"

binary_sha256="unavailable"
if command -v sha256sum >/dev/null 2>&1; then
  binary_sha256="$(sha256sum "$BIN" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  binary_sha256="$(shasum -a 256 "$BIN" | awk '{print $1}')"
fi

timeout_sha256="unavailable"
if [[ -n "$TIMEOUT_BIN" && -f "$TIMEOUT_BIN" ]]; then
  timeout_sha256="$(python3 - "$TIMEOUT_BIN" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
fi

script_sha256="$(python3 - "$0" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"

cpu_model="$(
  (sysctl -n machdep.cpu.brand_string 2>/dev/null || \
   lscpu 2>/dev/null | awk -F: '$1 ~ /^Model name/ {sub(/^[[:space:]]+/, "", $2); print $2; exit}' || \
   awk -F: '$1 ~ /^model name/ {sub(/^[[:space:]]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null || \
   true) \
    | head -n 1
)"
cpu_model="${cpu_model:-unavailable}"
logical_cpus="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf unavailable)"
memory_bytes="$(
  sysctl -n hw.memsize 2>/dev/null || \
  awk '/^MemTotal:/ {printf "%.0f\n", $2 * 1024; exit}' /proc/meminfo 2>/dev/null || \
  printf unavailable
)"
system_description="$(uname -a)"
gurobi_version="$(gurobi_cl --version 2>/dev/null | head -n 1 || true)"
gurobi_version="${gurobi_version:-unavailable}"

git_dependency_commit() {
  git -C "$1" rev-parse HEAD 2>/dev/null || printf unavailable
}

git_dependency_diff_sha256() {
  if ! git -C "$1" rev-parse --git-dir >/dev/null 2>&1; then
    printf unavailable
    return
  fi
  git -C "$1" diff --binary | python3 -c \
    'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

git_dependency_state_sha256() {
  if ! git -C "$1" rev-parse --git-dir >/dev/null 2>&1; then
    printf unavailable
    return
  fi
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
digest.update(subprocess.check_output(["git", "-C", str(root), "diff", "--binary"]))
untracked = subprocess.check_output(
    ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"]
).split(b"\0")
for raw_name in sorted(name for name in untracked if name):
    digest.update(raw_name)
    digest.update(b"\0")
    digest.update((root / raw_name.decode()).read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
}

git_dependency_dirty_count() {
  if ! git -C "$1" rev-parse --git-dir >/dev/null 2>&1; then
    printf unavailable
    return
  fi
  git -C "$1" status --porcelain --untracked-files=all 2>/dev/null | wc -l | tr -d ' '
}

salvers_commit="$(git_dependency_commit ../salvers)"
salvers_diff_sha256="$(git_dependency_diff_sha256 ../salvers)"
salvers_state_sha256="$(git_dependency_state_sha256 ../salvers)"
salvers_dirty_count="$(git_dependency_dirty_count ../salvers)"
ipamir_commit="$(git_dependency_commit ../ipamir-rs)"
ipamir_diff_sha256="$(git_dependency_diff_sha256 ../ipamir-rs)"
ipamir_state_sha256="$(git_dependency_state_sha256 ../ipamir-rs)"
ipamir_dirty_count="$(git_dependency_dirty_count ../ipamir-rs)"
cargo_lock_sha256="$(python3 - <<'PY'
import hashlib
from pathlib import Path

path = Path("Cargo.lock")
print(hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "unavailable")
PY
)"

read -r dataset_file_count dataset_sha256 < <(python3 - <<'PY'
import hashlib
from pathlib import Path

paths = [
    directory / f"Instance{line}{number}.txt"
    for directory in (
        Path("instances/original"),
        Path("instances/addtracktime"),
        Path("instances/addstationtime"),
    )
    for line in ("A", "B")
    for number in range(1, 13)
]
missing = [str(path) for path in paths if not path.is_file()]
if missing:
    raise SystemExit(f"ERROR: Thiếu file dữ liệu: {missing}")
digest = hashlib.sha256()
for path in paths:
    digest.update(path.as_posix().encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(len(paths), digest.hexdigest())
PY
)

run_fingerprint="$(python3 - \
  "$binary_sha256" "$script_sha256" "$SOLVER" "$OBJECTIVE" \
  "$INSTANCE_TIMEOUT_SECS" "$EXTERNAL_TIMEOUT_GRACE_SECS" \
  "$RAM_LIMIT_KB" "${TIMEOUT_BIN:-unavailable}" "$timeout_sha256" \
  "${MAXSAT_RC2_BOUND_MODE:-default}" \
  "${MAXSAT_RC2_REFINEMENT_BUDGET:-default}" \
  "${MAXSAT_RC2_MAX_WAIT_ITERATIONS:-default}" \
  "${MAXSAT_RC2_FULL_SCAN:-default}" \
  "${MAXSAT_RC2_VALIDATE_BEFORE_RETURN:-default}" \
  "${SATDDD_OBJECTIVE_ENCODING:-default}" \
  "${SATDDD_USE_PRECEDENCE_GRAPH:-default}" \
  "${SATDDD_PREALLOC_COST_THRESHOLDS:-default}" \
  "${SATDDD_SEED_PRECEDENCE_FROM_EARLIEST:-default}" \
  "${SATDDD_SEED_RESOURCE_CONFLICTS:-default}" \
  "${SATDDD_USE_SC_AMO:-default}" \
  "${MAXSATDDD_USE_PRECEDENCE_GRAPH:-default}" \
  "${MAXSATDDD_USE_SC_AMO:-default}" \
  "${MAXSATDDD_USE_TOUCHED_CLIQUE_AMO:-default}" \
  "${cpu_model:-unavailable}" "$logical_cpus" "$memory_bytes" "$system_description" \
  "$cargo_lock_sha256" "$dataset_file_count" "$dataset_sha256" \
  "$salvers_commit" "$salvers_diff_sha256" "$salvers_state_sha256" "$salvers_dirty_count" \
  "$ipamir_commit" "$ipamir_diff_sha256" "$ipamir_state_sha256" "$ipamir_dirty_count" <<'PY'
import hashlib
import json
import sys

print(hashlib.sha256(json.dumps(sys.argv[1:], separators=(",", ":")).encode()).hexdigest())
PY
)"

manifest="$RUN_LOG_DIR/manifest.txt"
if [[ -s "$manifest" ]]; then
  old_fingerprint="$(awk -F= '$1 == "run_fingerprint" {print $2; exit}' "$manifest")"
  if [[ -z "$old_fingerprint" || "$old_fingerprint" != "$run_fingerprint" ]]; then
    echo "ERROR: Không thể dùng lại $RUN_LOG_DIR vì cấu hình hoặc binary đã thay đổi." >&2
    echo "Hãy dùng RUN_LOG_DIR mới, hoặc quay lại đúng binary và cấu hình cũ." >&2
    exit 2
  fi
  printf 'resumed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$manifest"
else
  {
    printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'run_fingerprint=%s\n' "$run_fingerprint"
    printf 'git_commit=%s\n' "$(git rev-parse HEAD 2>/dev/null || printf unavailable)"
    printf 'git_dirty=%s\n' "$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    printf 'binary=%s\n' "$BIN"
    printf 'binary_sha256=%s\n' "$binary_sha256"
    printf 'cargo_lock_sha256=%s\n' "$cargo_lock_sha256"
    printf 'dataset_file_count=%s\n' "$dataset_file_count"
    printf 'dataset_sha256=%s\n' "$dataset_sha256"
    printf 'run_script_sha256=%s\n' "$script_sha256"
    printf 'salvers_git_commit=%s\n' "$salvers_commit"
    printf 'salvers_diff_sha256=%s\n' "$salvers_diff_sha256"
    printf 'salvers_state_sha256=%s\n' "$salvers_state_sha256"
    printf 'salvers_git_dirty_count=%s\n' "$salvers_dirty_count"
    printf 'ipamir_git_commit=%s\n' "$ipamir_commit"
    printf 'ipamir_diff_sha256=%s\n' "$ipamir_diff_sha256"
    printf 'ipamir_state_sha256=%s\n' "$ipamir_state_sha256"
    printf 'ipamir_git_dirty_count=%s\n' "$ipamir_dirty_count"
    printf 'solver=%s\n' "$SOLVER"
    printf 'objective=%s\n' "$OBJECTIVE"
    printf 'instance_timeout_seconds=%s\n' "$INSTANCE_TIMEOUT_SECS"
    printf 'external_timeout_grace_seconds=%s\n' "$EXTERNAL_TIMEOUT_GRACE_SECS"
    printf 'external_timeout_seconds=%s\n' "$EXTERNAL_TIMEOUT_SECS"
    printf 'timeout_binary=%s\n' "${TIMEOUT_BIN:-unavailable}"
    printf 'timeout_binary_sha256=%s\n' "$timeout_sha256"
    printf 'ram_limit_kb=%s\n' "$RAM_LIMIT_KB"
    printf 'maxsat_rc2_bound_mode=%s\n' "${MAXSAT_RC2_BOUND_MODE:-default}"
    printf 'maxsat_rc2_refinement_budget=%s\n' "${MAXSAT_RC2_REFINEMENT_BUDGET:-default}"
    printf 'maxsat_rc2_max_wait_iterations=%s\n' "${MAXSAT_RC2_MAX_WAIT_ITERATIONS:-default}"
    printf 'maxsat_rc2_full_scan=%s\n' "${MAXSAT_RC2_FULL_SCAN:-default}"
    printf 'maxsat_rc2_validate_before_return=%s\n' "${MAXSAT_RC2_VALIDATE_BEFORE_RETURN:-default}"
    printf 'satddd_objective_encoding=%s\n' "${SATDDD_OBJECTIVE_ENCODING:-default}"
    printf 'satddd_use_precedence_graph=%s\n' "${SATDDD_USE_PRECEDENCE_GRAPH:-default}"
    printf 'satddd_prealloc_cost_thresholds=%s\n' "${SATDDD_PREALLOC_COST_THRESHOLDS:-default}"
    printf 'satddd_seed_precedence_from_earliest=%s\n' "${SATDDD_SEED_PRECEDENCE_FROM_EARLIEST:-default}"
    printf 'satddd_seed_resource_conflicts=%s\n' "${SATDDD_SEED_RESOURCE_CONFLICTS:-default}"
    printf 'satddd_use_sc_amo=%s\n' "${SATDDD_USE_SC_AMO:-default}"
    printf 'maxsatddd_use_precedence_graph=%s\n' "${MAXSATDDD_USE_PRECEDENCE_GRAPH:-default}"
    printf 'maxsatddd_use_sc_amo=%s\n' "${MAXSATDDD_USE_SC_AMO:-default}"
    printf 'maxsatddd_use_touched_clique_amo=%s\n' "${MAXSATDDD_USE_TOUCHED_CLIQUE_AMO:-default}"
    printf 'rustc=%s\n' "$(rustc --version 2>/dev/null || printf unavailable)"
    printf 'gurobi=%s\n' "${gurobi_version:-unavailable}"
    printf 'cpu_model=%s\n' "${cpu_model:-unavailable}"
    printf 'logical_cpus=%s\n' "$logical_cpus"
    printf 'memory_bytes=%s\n' "$memory_bytes"
    printf 'system=%s\n' "$system_description"
  } >"$manifest"
  git diff --binary >"$RUN_LOG_DIR/source.diff" 2>/dev/null || true
fi
cleanup() {
  if [[ "$KEEP_TMPDIR" = "1" ]]; then
    echo "Preserved run artifacts in $tmpdir"
  else
    rm -rf "$tmpdir"
  fi
}
trap cleanup EXIT

run_one() {
  local instance_name="$1"
  local out_json="$instance_json_dir/$instance_name.json"
  local stdout_log="$RUN_LOG_DIR/$instance_name.stdout.log"
  local stderr_log="$RUN_LOG_DIR/$instance_name.stderr.log"
  local -a extra_args=()
  local effective_solver="$SOLVER"
  local status=0
  local start_ms=0
  local end_ms=0
  local elapsed_ms=0
  local elapsed_seconds="0.0"

  if [[ -n "$SATDDD_OBJECTIVE_ENCODING" ]]; then
    if [[ "$effective_solver" == "sat_ddd_sc_totalizer" ]]; then
      effective_solver="sat_ddd_sc"
    fi
    extra_args+=(--satddd-objective-encoding "$SATDDD_OBJECTIVE_ENCODING")
  fi

  if [[ -n "$SATDDD_USE_PRECEDENCE_GRAPH" ]]; then
    extra_args+=(--satddd-use-precedence-graph "$SATDDD_USE_PRECEDENCE_GRAPH")
  fi
  if [[ -n "$SATDDD_PREALLOC_COST_THRESHOLDS" ]]; then
    extra_args+=(--satddd-prealloc-cost-thresholds "$SATDDD_PREALLOC_COST_THRESHOLDS")
  fi
  if [[ -n "$SATDDD_SEED_PRECEDENCE_FROM_EARLIEST" ]]; then
    extra_args+=(--satddd-seed-precedence-from-earliest "$SATDDD_SEED_PRECEDENCE_FROM_EARLIEST")
  fi
  if [[ -n "$SATDDD_SEED_RESOURCE_CONFLICTS" ]]; then
    extra_args+=(--satddd-seed-resource-conflicts "$SATDDD_SEED_RESOURCE_CONFLICTS")
  fi
  if [[ -n "$SATDDD_USE_SC_AMO" ]]; then
    extra_args+=(--satddd-use-sc-amo "$SATDDD_USE_SC_AMO")
  fi

  if [[ -n "$MAXSATDDD_USE_PRECEDENCE_GRAPH" ]]; then
    extra_args+=(--maxsat-ladder-sc-use-precedence-graph "$MAXSATDDD_USE_PRECEDENCE_GRAPH")
  fi
  if [[ -n "$MAXSATDDD_USE_SC_AMO" ]]; then
    extra_args+=(--maxsat-ladder-sc-use-sc-amo "$MAXSATDDD_USE_SC_AMO")
  fi
  if [[ -n "$MAXSATDDD_USE_TOUCHED_CLIQUE_AMO" ]]; then
    extra_args+=(--maxsat-ladder-sc-use-touched-clique-amo "$MAXSATDDD_USE_TOUCHED_CLIQUE_AMO")
  fi
  if [[ -n "$MAXSAT_RC2_BOUND_MODE" ]]; then
    extra_args+=(--maxsat-rc2-bound-mode "$MAXSAT_RC2_BOUND_MODE")
  fi
  if [[ -n "$MAXSAT_RC2_REFINEMENT_BUDGET" ]]; then
    extra_args+=(--maxsat-rc2-refinement-budget "$MAXSAT_RC2_REFINEMENT_BUDGET")
  fi
  if [[ -n "$MAXSAT_RC2_MAX_WAIT_ITERATIONS" ]]; then
    extra_args+=(--maxsat-rc2-max-wait-iterations "$MAXSAT_RC2_MAX_WAIT_ITERATIONS")
  fi
  if [[ -n "$MAXSAT_RC2_FULL_SCAN" ]]; then
    extra_args+=(--maxsat-rc2-full-scan "$MAXSAT_RC2_FULL_SCAN")
  fi
  if [[ -n "$MAXSAT_RC2_VALIDATE_BEFORE_RETURN" ]]; then
    extra_args+=(--maxsat-rc2-validate-before-return "$MAXSAT_RC2_VALIDATE_BEFORE_RETURN")
  fi

  printf '%s\n' "$instance_name" >> "$order_file"

  if [[ -s "$out_json" ]] && python3 - "$out_json" "$instance_name" "$RERUN_NON_OK" <<'PY'
import json
import sys

path, expected_name, rerun_non_ok = sys.argv[1:]
try:
    data = json.load(open(path))
    item = data[0] if isinstance(data, list) and len(data) == 1 else data
    solve = item["solves"][0]
    valid = item.get("name") == expected_name and isinstance(solve.get("status"), str)
    if rerun_non_ok == "1" and solve.get("status") != "ok":
        valid = False
except (OSError, ValueError, KeyError, IndexError, TypeError):
    valid = False
raise SystemExit(0 if valid else 1)
PY
  then
    echo "Reusing $instance_name"
    return 0
  fi

  echo "Running $instance_name"
  if [[ -z "$TIMEOUT_BIN" ]]; then
    echo "ERROR: Không tìm thấy timeout hoặc gtimeout trong PATH." >&2
    echo "Cài GNU coreutils hoặc đặt TIMEOUT_BIN tới chương trình tương thích." >&2
    exit 2
  fi
  start_ms="$(python3 -c 'import time; print(time.time_ns() // 1_000_000)')"

  (
    if [[ "$RAM_LIMIT_KB" -gt 0 ]]; then
      ulimit -Sv "$RAM_LIMIT_KB"
    fi

    exec "$TIMEOUT_BIN" -k 20 "${EXTERNAL_TIMEOUT_SECS}s" \
      "$BIN" \
      -s "$effective_solver" \
      --txt-instances \
      --instance-name-filter "$instance_name" \
      --instance-name-exact \
      --objective "$OBJECTIVE" \
      --timeout-seconds "$INSTANCE_TIMEOUT_SECS" \
      "${extra_args[@]}" \
      --json-output "$out_json" \
      >"$stdout_log" \
      2>"$stderr_log"
  ) || status=$?
  end_ms="$(python3 -c 'import time; print(time.time_ns() // 1_000_000)')"
  elapsed_ms=$((end_ms - start_ms))
  elapsed_seconds="$(awk "BEGIN { printf \"%.3f\", $elapsed_ms / 1000 }")"

  if [[ -s "$out_json" ]]; then
    return 0
  fi

  local external_status="failed"
  if [[ "$status" -eq 124 ]]; then
    external_status="external_timeout"
  elif [[ "$status" -eq 137 ]]; then
    external_status="killed"
  elif [[ "$status" -eq 134 ]]; then
    external_status="aborted"
  elif [[ "$status" -eq 139 ]]; then
    external_status="segfault"
  elif [[ "$status" -eq 101 ]]; then
    external_status="panic"
  fi

  cat >"$out_json" <<EOF
[
  {
    "index": null,
    "name": "$instance_name",
    "trains": null,
    "conflicts": null,
    "avg_tracks": null,
    "conflicting_visit_pairs": null,
    "delay_cost_type": "$OBJECTIVE",
    "solves": [
      {
        "solver_name": "$effective_solver",
        "status": "$external_status",
        "external_status": "$external_status",
        "exit_code": $status,
        "sol_time": $elapsed_ms,
        "total_time": $elapsed_seconds
      }
    ]
  }
]
EOF
}

for prefix in orig track station; do
  for infra in A B; do
    for number in $(seq 1 12); do
      run_one "${prefix}${infra}${number}"
    done
  done
done

python3 - "$instance_json_dir" "$order_file" "$JSON_OUT" <<'PY'
import json
import sys
from pathlib import Path

tmpdir = Path(sys.argv[1])
order_file = Path(sys.argv[2])
json_out = Path(sys.argv[3])

items = []
for line in order_file.read_text().splitlines():
    if not line:
        continue
    data = json.loads((tmpdir / f"{line}.json").read_text())
    if isinstance(data, list):
        items.extend(data)
    else:
        items.append(data)

expected = [
    f"{prefix}{infra}{number}"
    for prefix in ("orig", "track", "station")
    for infra in ("A", "B")
    for number in range(1, 13)
]
names = [item.get("name") for item in items]
if names != expected:
    missing = sorted(set(expected) - set(names))
    unexpected = sorted(set(names) - set(expected), key=str)
    duplicates = sorted({name for name in names if names.count(name) > 1}, key=str)
    raise SystemExit(
        "ERROR: Kết quả không có đúng 72 instance theo thứ tự chuẩn. "
        f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}"
    )

for item in items:
    solves = item.get("solves")
    if not isinstance(solves, list) or len(solves) != 1:
        raise SystemExit(
            f"ERROR: {item.get('name')} không có đúng một kết quả solver."
        )
    if not isinstance(solves[0], dict) or not isinstance(solves[0].get("status"), str):
        raise SystemExit(
            f"ERROR: {item.get('name')} không có trường status hợp lệ."
        )

for idx, item in enumerate(items):
    item["index"] = idx

json_out.write_text(json.dumps(items, indent=2))
print(f"Wrote {json_out}")
PY
