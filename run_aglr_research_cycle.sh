#!/usr/bin/env bash
# A fixed sequence: single-factor trials, top-three promotion, one locked full
# candidate, then independent repeats. The outer watchdog includes all stages.
set -euo pipefail
export CYCLE_ID="${CYCLE_ID:-cycle-$(date -u +%Y%m%dT%H%M%SZ)}"
export RESULTS_ROOT="${RESULTS_ROOT:-results/aglr}"
export FULL_TIMEOUT_SECS="${FULL_TIMEOUT_SECS:-150}"
export CONFERENCE_RUNTIME_MODE="${CONFERENCE_RUNTIME_MODE:-assumed-equivalent}"
if [[ "${AGLR_CYCLE_BOUNDED:-0}" != 1 ]]; then
  export AGLR_CYCLE_BOUNDED=1
  exec timeout --signal=TERM --kill-after=30 "${ROUND_LIMIT_SECONDS:-21600}s" bash "$0"
fi
export SKIP_BUILD=1
[[ -x "${BIN:-./target/release/ddd}" ]] || exit 2

RUN_ID="$CYCLE_ID-ablate" bash run_aglr_experiments.sh ablate
SCREEN_DIR="$RESULTS_ROOT/$CYCLE_ID-ablate" \
  RUN_ID="$CYCLE_ID-promote" bash run_aglr_experiments.sh promote

read -r AGLR_MIN_GROWTH AGLR_FRACTION AGLR_MAX_WAIT \
  AGLR_RESCUE_PROGRESS AGLR_HEURISTIC_PERIOD AGLR_HEURISTIC_MIN_GAP \
  AGLR_USE_OBJECTIVE_BOUND AGLR_FILTER_DUPLICATES < <(python3 - "$RESULTS_ROOT/$CYCLE_ID-promote/aglr_ranking.csv" <<'PY'
import csv, sys
row = next(csv.DictReader(open(sys.argv[1])))
print(*(row[k] for k in ("min_growth", "fraction", "max_wait", "rescue_progress",
                        "heuristic_period", "heuristic_min_gap", "use_objective_bound", "filter_duplicates")))
PY
)
export AGLR_MIN_GROWTH AGLR_FRACTION AGLR_MAX_WAIT AGLR_RESCUE_PROGRESS
export AGLR_HEURISTIC_PERIOD AGLR_HEURISTIC_MIN_GAP AGLR_USE_OBJECTIVE_BOUND AGLR_FILTER_DUPLICATES
RUN_ID="$CYCLE_ID-candidate" bash run_aglr_experiments.sh candidate
if python3 - "$RESULTS_ROOT/$CYCLE_ID-candidate/aglr_audit.json" <<'PY'
import json, sys
audit = json.load(open(sys.argv[1]))
sys.exit(0 if (audit.get("gate") or {}).get("coverage_passed") and not audit["errors"] else 1)
PY
then
  FULL_DIR="$RESULTS_ROOT/$CYCLE_ID-candidate" \
    RUN_ID="$CYCLE_ID-confirm" bash run_aglr_experiments.sh confirm
else
  echo "Coverage chưa vượt hội nghị. Đọc telemetry trước khi chọn ý tưởng tiếp theo."
fi
