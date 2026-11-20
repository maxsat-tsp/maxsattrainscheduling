"""Compare the five methods on the same eleven objective/instance pairs."""
import argparse
import json
from pathlib import Path

from bound_quality import compare, envelope
from extended_timeout_experiments import save
from run_long_baseline_cases import CUTOFF, METHODS


def summarize(root, original=None):
    original = root if original is None else original
    hard = json.loads((original/'hard/audit.json').read_text())
    reference = json.loads((original/'hard-evaluation.json').read_text())
    rows = {
        method:json.loads(((original if method.startswith('BigM-') else root)
                           /'controls'/method/'audit.json').read_text())
        for method in METHODS
    }
    if not hard['complete'] or not hard['audit_passed'] or not reference['complete']:
        raise ValueError('incomplete candidate')
    candidate = {(r['objective'],r['name']):r for r in hard['records']}
    historical = {(r['objective'],r['name']):r['all_reference'] for r in reference['cases']}
    controls = {}
    for method, report in rows.items():
        by_case = {(r['objective'],r['name']):r for r in report['cases']}
        if (not report['audit_passed'] or not report['complete'] or report['timeout_seconds'] != CUTOFF
                or len(by_case) != 11 or by_case.keys() != candidate.keys()):
            raise ValueError(f'{method} does not have a matched audited hard set')
        controls[method] = by_case
    cases = []
    for pair, row in candidate.items():
        baselines = {method:by_case[pair] for method,by_case in controls.items()}
        bounds = [r if r['upper_witness_verified'] else dict(r,ub=None) for r in baselines.values()]
        known = envelope([*bounds,dict(historical[pair],source='audited historical envelope')])
        change = compare(row['lb'],row['ub'],known['lb'],known['ub'])
        cases.append(dict(candidate=row,baselines=baselines,comparison=change))
    return dict(scope='matched hard set of 11 pairs; no full-dataset coverage or runtime comparison',
        timeout_seconds=CUTOFF,candidate_proven=sum(r['proven'] for r in candidate.values()),
        baseline_proven={method:r['proven'] for method,r in rows.items()},
        baseline_reused={method:r['reused'] for method,r in rows.items()},
        baseline_external_timeouts={method:r.get('external_timeouts',0) for method,r in rows.items()},
        candidate_new_best_bound_cases=sum(row['comparison']['new_bound']
                                          for row in cases if not row['candidate']['proven']),
        cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--original',type=Path)
    args = parser.parse_args()
    save(args.directory/'matched600.json',summarize(args.directory,args.original))
