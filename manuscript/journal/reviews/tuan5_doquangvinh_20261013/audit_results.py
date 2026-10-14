#!/usr/bin/env python3
"""Read-only audit of the pinned week-5 submission. Uses only the standard library.

Usage: python3 audit_results.py /path/to/student/repository
Writes audit_summary.csv, matched_comparisons.csv and audit_evidence.json here.
No student files are modified. Counts are reported labels, not new optimality proofs.
"""
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics as st
import subprocess
import sys

OUT = Path(__file__).resolve().parent
OBJECTIVES = ('finsteps123', 'infsteps180', 'cont')
RUNS = {
    'Base': ('2026-09-27_19-19-19-RC2-Base', 'RC2-Base'),
    'B': ('2026-09-26_22-33-15-RC2+B', 'RC2+B'),
    'R32': ('2026-09-27_18-25-54-RC2+R', 'RC2+R'),
    'BR8': ('2026-10-06_08-47-32-RC2+B+R', 'RC2+B+R'),
    'BR32': ('2026-09-27_23-45-00-RC2+B+R', 'RC2+B+R'),
    'BR128': ('2026-10-06_16-34-56-RC2+B+R', 'RC2+B+R'),
}


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return [{k.strip(): v.strip() for k, v in row.items()} for row in csv.DictReader(stream)]


def write_csv(name, rows):
    with (OUT / name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def same(a, b):
    if a is None:
        return b == ''
    if isinstance(a, (int, float)):
        try:
            return math.isclose(a, float(b), rel_tol=1e-9, abs_tol=1e-9)
        except (ValueError, TypeError):
            return False
    return str(a) == str(b)


def main():
    root = Path(sys.argv[1]).resolve()
    evidence = {'commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                'files_sha256': {}, 'csv_json_mismatches': [], 'summary_mismatches': [],
                'cost_bound_mismatches': [], 'pairwise_cost_mismatches': [],
                'conference_cost_mismatches': [], 'failure_instances': {}, 'matched_details': []}
    data, summaries = {}, []
    expected = {f'{p}{line}{i}' for p in ('orig', 'track', 'station') for line in 'AB' for i in range(1, 13)}
    for label, (directory, prefix) in RUNS.items():
        for obj in OBJECTIVES:
            file = root / 'results/improvements' / directory / f'{prefix}_{obj}.json'
            evidence['files_sha256'][str(file.relative_to(root))] = hashlib.sha256(file.read_bytes()).hexdigest()
            raw = json.loads(file.read_text())
            assert len(raw) == 72 and {r['name'] for r in raw} == expected, file
            assert all(len(r['solves']) == 1 for r in raw), file
            rows = {r['name']: r['solves'][0] for r in raw}
            data[label, obj] = rows
            csvrows = read_csv(file.with_suffix('.csv'))
            assert len(csvrows) == 72 and {r['name'] for r in csvrows} == expected
            for row in csvrows:
                for key, value in rows[row['name']].items():
                    if key in row and not same(value, row[key]):
                        evidence['csv_json_mismatches'].append([label, obj, row['name'], key, value, row[key]])
            ok = [r for r in rows.values() if r['status'] == 'ok']
            bound_equal = 0
            for name, row in rows.items():
                if row['status'] == 'ok':
                    if abs(row['lb'] - row['ub']) <= 1e-6 * max(1, abs(row['ub'])):
                        bound_equal += 1
                    if row['cost'] != row['lb'] or row['cost'] != row['ub']:
                        evidence['cost_bound_mismatches'].append([label, obj, name, row])
            failures = {name: r['status'] for name, r in rows.items() if r['status'] != 'ok'}
            evidence['failure_instances'][f'{label}/{obj}'] = failures
            summaries.append(dict(config=label, objective=obj, n=72, ok=len(ok),
                panic=sum(r['status'] == 'panic' for r in rows.values()),
                timeout=sum('timeout' in r['status'] for r in rows.values()),
                other=sum(r['status'] != 'ok' and r['status'] != 'panic' and 'timeout' not in r['status'] for r in rows.values()),
                success_pct=100*len(ok)/72, equal_bounds=bound_equal,
                mean_ok_ms=st.mean(r['sol_time'] for r in ok),
                median_ok_ms=st.median(r['sol_time'] for r in ok),
                total_recorded_s=sum(r['total_time'] for r in rows.values()),
                mean_cost=st.mean(r['cost'] for r in ok)))
    submitted = root / 'submissions/tuan5_doquangvinh'
    mapping = {'OK': 'ok', 'N': 'n', 'Success': 'success_pct', 'Optimal': 'equal_bounds',
               'Mean solve (ms)': 'mean_ok_ms', 'Median solve (ms)': 'median_ok_ms', 'Mean cost': 'mean_cost'}
    for filename in ('summary.csv', 'summary_budget.csv'):
        for row in read_csv(submitted / filename):
            label = ('BR' + row['Budget']) if 'Budget' in row else {
                'RC2-Base': 'Base', 'RC2+B': 'B', 'RC2+R': 'R32', 'RC2+B+R': 'BR32'}[row['Configuration']]
            actual = next(s for s in summaries if s['config'] == label and s['objective'] == row['Objective'])
            check = dict(mapping)
            if 'Budget' in row:
                check.update({'Panic': 'panic', 'Timeout': 'timeout', 'Other': 'other', 'Total (s)': 'total_recorded_s'})
            for key, source in check.items():
                if not same(actual[source], row[key]):
                    evidence['summary_mismatches'].append([filename, label, row['Objective'], key, actual[source], row[key]])
            if not same(actual['total_recorded_s']/72, row['Mean total (s)']):
                evidence['summary_mismatches'].append([filename, label, row['Objective'], 'Mean total (s)'])
            if not same(72-actual['ok'], row['Failed']):
                evidence['summary_mismatches'].append([filename, label, row['Objective'], 'Failed'])
    comparisons = []
    for obj in OBJECTIVES:
        for left, right in itertools.combinations(RUNS, 2):
            a, b = data[left, obj], data[right, obj]
            names = sorted(n for n in expected if a[n]['status'] == b[n]['status'] == 'ok')
            for n in names:
                if a[n]['cost'] != b[n]['cost']:
                    evidence['pairwise_cost_mismatches'].append([obj, left, right, n, a[n]['cost'], b[n]['cost']])
            if (left, right) not in [('Base', 'BR128'), ('BR32', 'BR128'), ('BR8', 'BR128')]:
                continue
            ta = [a[n]['sol_time'] for n in names]
            tb = [b[n]['sol_time'] for n in names]
            ratios = [x/y for x, y in zip(ta, tb)]
            comparisons.append(dict(objective=obj, left=left, right=right, common_n=len(names),
                left_mean_ms=st.mean(ta), right_mean_ms=st.mean(tb), left_median_ms=st.median(ta),
                right_median_ms=st.median(tb), right_faster=sum(x>y for x,y in zip(ta,tb)),
                median_paired_speedup=st.median(ratios), geometric_paired_speedup=math.exp(st.mean(map(math.log, ratios)))))
            evidence['matched_details'].append(dict(objective=obj, left=left, right=right,
                common=names, left_only_ok=sorted(n for n in expected if a[n]['status']=='ok' and b[n]['status']!='ok'),
                right_only_ok=sorted(n for n in expected if b[n]['status']=='ok' and a[n]['status']!='ok')))
        for method in ('Baseline', 'Default'):
            ref = read_csv(root / 'results' / f'MaxSAT_{method}_RC2_{obj}_120s.csv')
            for r in ref:
                if r.get('status') != 'ok':
                    continue
                for label in RUNS:
                    new = data[label, obj].get(r['name'])
                    if new and new['status'] == 'ok' and not same(new['cost'], r['cost']):
                        evidence['conference_cost_mismatches'].append([method, obj, label, r['name'], r['cost'], new['cost']])
    write_csv('audit_summary.csv', summaries)
    write_csv('matched_comparisons.csv', comparisons)
    (OUT / 'audit_evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: len(v) for k,v in evidence.items() if k.endswith('mismatches')}, indent=2))
    print(f'Checked {len(data)} files, {len(data)*72} runs. Outputs: {OUT}')
    print(json.dumps(comparisons, indent=2))


if __name__ == '__main__':
    main()
