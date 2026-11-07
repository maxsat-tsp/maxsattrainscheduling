"""Audit the extracted confirmation, from the repository root, without mutation."""
from pathlib import Path
import argparse,json,statistics,sys
sys.path.insert(0,str(Path.cwd()/'quick_scripts/analyze'))
import extended_timeout_experiments as extended
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--reference',type=Path,required=True);args=p.parse_args()
root=args.root;m=json.loads((root/'manifest.json').read_text());saved=json.loads((root/'confirmation_audit.json').read_text())
reference=json.loads((args.reference/'manifest.json').read_text())
assert m['schema']==saved['schema']=='v17-single-gain-confirmation-v1'
assert m['reference_manifest_sha256']==extended.focus.sha(args.reference/'manifest.json')
assert m['reference_report_sha256']==extended.focus.sha(args.reference/'full_audit.json')
assert m['reference_raw_sha256']==extended.focus.sha(args.reference/'cases/cont/trackB12/cont.json')
for k in ['solver_source_commit','definition','binary_sha256','dataset_sha256']:assert m[k]==reference[k]
assert m['dataset_sha256']==extended.focus.dataset_hash() and m['repeats']==3
assert m['script_sha256']==extended.focus.sha(Path(__file__).with_name('confirm_gain.py'))
assert m['selection']==[dict(objective='cont',name='trackB12',expected_cost=15182)]
assert not (root/'failure.json').exists() and not saved['errors']
assert saved['complete'] and saved['confirmed'] and not saved['submission_passed']
assert len(saved['cases'])==saved['expected_runs']==saved['completed_runs']==3
assert {r['repeat'] for r in saved['cases']}=={1,2,3}
assert len(list((root/'cases').rglob('cont.json')))==3
cases=[]
for item in saved['cases']:
 case=root/'cases'/f'repeat-{item["repeat"]}'/'cont'/'trackB12'
 provenance=dict(l.split('=',1) for l in (case/'logs/manifest.txt').read_text().splitlines() if '=' in l)
 expected=dict(binary_sha256=m['binary_sha256'],git_commit=m['runner_commit'],git_dirty='0',solver=m['definition']['solver'],
  objective='cont',selected_instances='trackB12',selected_instance_count='1',instance_timeout_seconds='300',ram_limit_kb='6000000')
 expected.update({'maxsatddd_'+k:v for k,v in m['definition'].items() if k not in ('solver','kind')})
 assert all(provenance.get(k)==v for k,v in expected.items())
 r=extended.assess_case(case,'V17-confirm','cont','trackB12',300,m['definition'])
 assert not r['errors'] and r['proven'] and r['solve']['cost']==15182
 assert r['solve']['lb']==r['solve']['ub']==15182
 assert item['proven'] and item['reproduced'] and item['cost']==item['lb']==item['ub']==15182
 assert item['seconds']==r['time'] and item['sha256']==extended.focus.sha(case/'cont.json')
 cases.append(item)
print(json.dumps(dict(audit_passed=True,confirmed=True,complete=True,completed_runs=3,cases=cases,
 median_seconds=statistics.median(r['seconds'] for r in cases),submission_passed=False,
 scope='one V17 gain reproduced three times; concurrent timings diagnostic only'),indent=2))
