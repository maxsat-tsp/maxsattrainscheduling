#!/usr/bin/env bash
set -Eeuo pipefail
: "${EVAL_REPO:?Set the frozen evaluation checkout}"
: "${CANDIDATE_ROOT:?Set the V40 campaign root}"
: "${REFERENCE:?Set the V17 full reference}"
: "${DIAGNOSTIC_ROOT:?Set the completed V39 root}"
: "${MIP_ROOT:?Set the saved BigM-Gurobi reference directory}"
cd "$EVAL_REPO"
out="$CANDIDATE_ROOT/evaluation"
mkdir -p "$out"
exec 9>"$out/evaluator.lock"
flock -n 9 || exit 75
trap 'code=$?; printf "exit=%s line=%s\n" "$code" "$LINENO" > "$out/EVALUATION_FAILED"' ERR
for (( cycle=0; cycle<360; cycle++ )); do
    if [[ -f "$CANDIDATE_ROOT/hard/manifest.json" ]]; then
        python3 quick_scripts/analyze/compare_search_bounds.py \
            --candidate "$CANDIDATE_ROOT/hard" --reference "$REFERENCE" \
            --diagnostics "$DIAGNOSTIC_ROOT" --completed-only \
            --gurobi-json cont "$MIP_ROOT/cont.json" \
            --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" \
            --reference-pool "$out/hard_reference_pool.json" \
            --output "$out/priority_evaluation.json"
        complete="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["complete"]))' "$out/priority_evaluation.json")"
        if (( complete == 1 )) && [[ -f "$CANDIDATE_ROOT/COMPLETED" ]]; then
            if [[ -f "$CANDIDATE_ROOT/followup/manifest.json" ]]; then
                python3 quick_scripts/analyze/compare_search_bounds.py \
                    --candidate "$CANDIDATE_ROOT/hard" --followup "$CANDIDATE_ROOT/followup" \
                    --reference "$REFERENCE" --diagnostics "$DIAGNOSTIC_ROOT" \
                    --gurobi-json cont "$MIP_ROOT/cont.json" \
                    --gurobi-json infsteps180 "$MIP_ROOT/infsteps180.json" \
                    --reference-pool "$out/full_reference_pool.json" --output "$out/full_evaluation.json"
            fi
            touch "$out/EVALUATION_COMPLETE"; exit 0
        fi
    fi
    if [[ -f "$CANDIDATE_ROOT/FAILED" || -f "$CANDIDATE_ROOT/INCOMPLETE" ]]; then
        touch "$out/EVALUATION_STOPPED"; exit 0
    fi
    sleep 60
done
touch "$out/EVALUATION_INCOMPLETE"
