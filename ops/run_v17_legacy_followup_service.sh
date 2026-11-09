#!/usr/bin/env bash
# Unattended follow-up on the 13 hard cases using the strongest V17 legacy
# configuration. Each variant changes one RC2/core setting.

set -euo pipefail

REPO="${REPO:-/home/tuyenkv/projects/maxsattrainscheduling}"
DEFAULT_COMMIT="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || printf 'nogit')"
RUN_ID="${RUN_ID:-v17-legacy-hardset-300-$(date -u +%Y%m%d)-$DEFAULT_COMMIT}"
RESULTS_ROOT="${RESULTS_ROOT:-$REPO/results/aglr}"
CAMPAIGN_DIR="$RESULTS_ROOT/$RUN_ID"
REFERENCE="${REFERENCE:-$REPO/results/sat_research/core_exhaustion_v17_20261107/full_216}"
BIN="${BIN:-$REPO/target/release/ddd}"
TIMEOUT="${TIMEOUT:-300}"
RAM_LIMIT_KB="${RAM_LIMIT_KB:-6000000}"
RUNNER="$REPO/quick_scripts/run_all_txt_instances_limited.sh"
AUDITOR="$REPO/quick_scripts/analyze/audit_aglr_hardset.py"
CSV_BATCH="$REPO/quick_scripts/analyze/json_to_csv_batch.py"
LOCK_FILE="${LOCK_FILE:-$HOME/.cache/maxsat-v17-legacy-hardset.lock}"

mkdir -p "$(dirname "$LOCK_FILE")" "$CAMPAIGN_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "another V17 legacy campaign is running" >&2; exit 2; }

cd "$REPO"
source /home/tuyenkv/miniconda3/etc/profile.d/conda.sh
conda activate gurobi
export GUROBI_HOME=/home/tuyenkv/miniconda3/envs/gurobi
export LD_LIBRARY_PATH=/home/tuyenkv/miniconda3/envs/gurobi/lib
export GRB_LICENSE_FILE=/home/tuyenkv/gurobi.lic

# Do not compete with the preceding AGLR service if this unit was started early.
while systemctl is-active --quiet maxsat-aglr-v17-hardset.service; do
  echo "waiting for maxsat-aglr-v17-hardset.service"
  sleep 60
done

[[ -f Cargo.toml && -x "$BIN" && -f "$RUNNER" && -f "$AUDITOR" ]] || {
  echo "missing repository, binary, runner, or auditor" >&2
  exit 2
}
[[ -f "$REFERENCE/full_audit.json" ]] || { echo "missing V17 reference" >&2; exit 2; }
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
  echo "repository must be clean" >&2
  git status --short >&2
  exit 2
}

binary_sha256="$(sha256sum "$BIN" | awk '{print $1}')"
git_commit="$(git rev-parse HEAD)"

python3 - "$REFERENCE/full_audit.json" "$CAMPAIGN_DIR/selection.json" <<'PY'
import json, sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text())
out={"finsteps123":[],"infsteps180":[],"cont":[]}
for row in data["case_bounds"]:
    if not row.get("proven",False): out[row["objective"]].append(row["name"])
if sum(map(len,out.values())) != 13:
    raise SystemExit(f"expected 13 unresolved cases, got {out}")
Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+"\n")
PY

if [[ ! -s "$CAMPAIGN_DIR/campaign.txt" ]]; then
  {
    printf 'schema=v17-legacy-hardset-campaign-v1\n'
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'git_commit=%s\n' "$git_commit"
    printf 'binary_sha256=%s\n' "$binary_sha256"
    printf 'reference=%s\n' "$REFERENCE"
    printf 'timeout_seconds=%s\n' "$TIMEOUT"
    printf 'ram_limit_kb=%s\n' "$RAM_LIMIT_KB"
    printf 'solver=maxsat_ddd_ladder_sc\n'
    printf 'policy=legacy\n'
    printf 'backend=minisat\n'
    printf 'resource_orders=true\n'
    printf 'order_transitivity=true\n'
    printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$CAMPAIGN_DIR/campaign.txt"
else
  grep -Fxq "git_commit=$git_commit" "$CAMPAIGN_DIR/campaign.txt"
  grep -Fxq "binary_sha256=$binary_sha256" "$CAMPAIGN_DIR/campaign.txt"
fi

stable_seed() {
  python3 - "$1" <<'PY'
import hashlib, sys
print(int(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8],16) % 2147483647 or 1)
PY
}

run_variant() {
  local tag="$1" checks="$2" conflicts="$3" exhaust="$4"
  local dir="$CAMPAIGN_DIR/$tag" selection_json
  selection_json="$(python3 - "$CAMPAIGN_DIR/selection.json" <<'PY'
import json, sys
print(json.dumps(json.load(open(sys.argv[1])), separators=(",", ":")))
PY
)"
  mkdir -p "$dir"
  cat > "$dir/config.txt" <<EOF2
tag=$tag
solver=maxsat_ddd_ladder_sc
kind=exact
policy=legacy
timeout_seconds=$TIMEOUT
instances_by_objective=$selection_json
assumptions=legacy
backend=minisat
sparse_costs=false
resource_orders=true
order_transitivity=true
core_minimize_checks=$checks
core_minimize_conflicts=$conflicts
core_exhaust_checks=$exhaust
process_exit_required=true
EOF2

  for objective in infsteps180 cont; do
    names="$(python3 - "$CAMPAIGN_DIR/selection.json" "$objective" <<'PY'
import json, sys
print(" ".join(json.load(open(sys.argv[1]))[sys.argv[2]]))
PY
)"
    out="$dir/$objective.json"
    [[ -s "$out" ]] && echo "[$tag] resuming $objective"
    echo "[$tag] running $objective | timeout=${TIMEOUT}s | instances=$names"
    BIN="$BIN" SOLVER=maxsat_ddd_ladder_sc OBJECTIVE="$objective" JSON_OUT="$out" \
    RUN_LOG_DIR="$dir/$objective.logs" INSTANCE_TIMEOUT_SECS="$TIMEOUT" \
    EXTERNAL_TIMEOUT_GRACE_SECS=30 RAM_LIMIT_KB="$RAM_LIMIT_KB" \
    INSTANCE_NAMES="$names" INSTANCE_ORDER_SEED="$(stable_seed "$RUN_ID-$tag-$objective")" \
    MAXSATDDD_ASSUMPTIONS=legacy MAXSATDDD_BACKEND=minisat MAXSATDDD_SPARSE_COSTS=false \
    MAXSATDDD_RESOURCE_ORDERS=true MAXSATDDD_ORDER_TRANSITIVITY=true \
    MAXSATDDD_CORE_MINIMIZE_CHECKS="$checks" MAXSATDDD_CORE_MINIMIZE_CONFLICTS="$conflicts" \
    MAXSATDDD_CORE_EXHAUST_CHECKS="$exhaust" RERUN_NON_OK=1 bash "$RUNNER"
    python3 "$CSV_BATCH" "$out" --format compact --overwrite >/dev/null
  done
  python3 "$AUDITOR" --variant "$dir" --reference "$REFERENCE" --timeout "$TIMEOUT" \
    > "$dir/audit_stdout.json"
  cat "$dir/audit_stdout.json"
}

run_variant mincore8 8 100 4
run_variant mincore16 16 100 4
run_variant exhaust8 4 100 8
# A zero conflict budget is rejected by the solver; do not run it.

python3 - "$CAMPAIGN_DIR" <<'PY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1]); rows=[]
for path in sorted(root.glob("*/hardset_audit.json")):
    data=json.loads(path.read_text())
    rows.append({"variant":data["variant"],"audit_passed":data["audit_passed"],
                 "projected_total":data["projected_total"],
                 "projected_coverage":data["projected_coverage"],
                 "newly_solved":data["newly_solved"]})
(root/"round_summary.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
best=max(rows,key=lambda row:(row["audit_passed"],row["projected_total"],row["variant"]))
(root/"best_variant.txt").write_text(best["variant"]+"\n")
print(json.dumps({"best":best,"all":rows},sort_keys=True))
PY
printf 'completed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$CAMPAIGN_DIR/campaign.txt"
echo "completed: $CAMPAIGN_DIR"
