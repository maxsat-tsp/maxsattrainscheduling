#!/usr/bin/env bash
# One resumable round, stopped after six hours (including all child processes).
set -euo pipefail
export ROUND_LIMIT_SECONDS="${ROUND_LIMIT_SECONDS:-21600}"
[[ "$ROUND_LIMIT_SECONDS" =~ ^[1-9][0-9]*$ ]] || exit 2
export RUN_ID="${RUN_ID:-${1:-screen}-$(date -u +%Y%m%dT%H%M%SZ)}"
exec timeout --signal=TERM --kill-after=30 "${ROUND_LIMIT_SECONDS}s" \
  bash run_aglr_experiments.sh "${1:-screen}"
