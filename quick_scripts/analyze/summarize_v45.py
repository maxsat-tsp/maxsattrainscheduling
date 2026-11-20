"""Rank the two matched assumption modes after both hard runs are audited."""
import json
from pathlib import Path
import sys

from extended_timeout_experiments import save

MODES = ('reuse', 'restart-assumptions')


def compare(root):
    reports = {mode: json.loads((root/mode/'hard-evaluation.json').read_text()) for mode in MODES}
    pairs = {mode: {(r['objective'],r['name']): r for r in report['cases']}
             for mode, report in reports.items()}
    if (not all(report['candidate_audit_passed'] and report['complete'] for report in reports.values())
            or len(pairs['reuse']) != 11 or pairs['reuse'].keys() != pairs['restart-assumptions'].keys()
            or len({report['reference_pool_sha256'] for report in reports.values()}) != 1
            or any(r['threshold_session'] != mode for mode in MODES for r in pairs[mode].values())):
        raise ValueError('V45 requires two complete matched configurations and one reference pool')
    counts = {}
    rows = []
    for mode, report in reports.items():
        summary = report['summary']
        records = pairs[mode].values()
        counts[mode] = dict(summary, model_builds=sum(r['sat_model_builds'] for r in records),
            first_query_sat=sum(r['first_query_outcome']=='sat' for r in records),
            first_query_unknown=sum(r['first_query_outcome']=='unknown' for r in records),
            paired_penalty_sum=sum(r['seconds'] if r['proven'] else 600 for r in records))
    for objective, name in pairs['reuse']:
        rows.append(dict(objective=objective,name=name, modes={mode: pairs[mode][objective,name]
            for mode in MODES}))
    def rank(mode):
        row = counts[mode]
        return (-row['proven_optimal'],-row['new_best_bound_cases'],
                row['mean_unsolved_relative_gap'],row['paired_penalty_sum'])
    ranking = sorted(MODES,key=rank)
    winner = ranking[0] if counts[ranking[0]]['proven_optimal'] else None
    return dict(scope='11 hard cases per mode', ranking=ranking, winner_for_regression=winner,
                counts=counts,cases=rows,reference_pool_sha256=reports['reuse']['reference_pool_sha256'])


if __name__ == '__main__':
    root=Path(sys.argv[1])
    save(root/'matched-comparison.json',compare(root))
