"""Read-only independent audit of the archived 31- and 216-pair completions.

Run from the repository root. Parent paths point to extracted immutable archives.
"""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path.cwd()/'quick_scripts/analyze'))
import extended_timeout_experiments as extended
import compare_sat_backends as dual
import published_baselines as published

p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--parent',type=Path,required=True)
p.add_argument('--reference',type=Path,required=True);args=p.parse_args()
root=args.root;manifest=json.loads((root/'manifest.json').read_text())
full=manifest['schema']=='completed-core-full-v1'
assert manifest['schema'] in ('completed-core-full-v1','completed-core-hardset-v1')
report_name='full_audit.json' if full else 'hardset_audit.json'
saved=json.loads((root/report_name).read_text());index=json.loads((root/'snapshot.json').read_text())
assert index['schema']=='core-completion-snapshot-v1' and index['report']==report_name
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
assert actual==set(index['file_sha256'])|{'snapshot.json'}
for name,digest in index['file_sha256'].items():
 path=root/name;assert path.resolve().is_relative_to(root.resolve()) and not path.is_symlink()
 assert extended.focus.sha(path)==digest,name
assert not (root/'failure.json').exists() and not saved['errors'] and not saved['submission_passed']
assert manifest['dataset_sha256']==extended.focus.dataset_hash()
assert manifest['reference_manifest_sha256']==extended.focus.sha(args.reference/'manifest.json')
parent=json.loads((args.parent/'manifest.json').read_text())
parent_report='hardset_audit.json' if full else 'core_minimization_audit.json'
assert manifest['partial_manifest_sha256']==extended.focus.sha(args.parent/'manifest.json')
assert manifest['partial_report_sha256']==extended.focus.sha(args.parent/parent_report)
for key in ('definition','solver_source_commit','binary_sha256','timeout_seconds','ram_kb','cpu_affinity'):
 assert manifest[key]==parent[key],key
selection=manifest['instances_by_objective']
expected=[(o,n) for o,names in selection.items() for n in names]
assert len(expected)==len(set(expected))==(216 if full else 31)
if full:
 assert set(selection)==set(extended.audit.OBJECTIVES)
 assert all(names==extended.common.EXPECTED_NAMES for names in selection.values())
else:
 assert selection==json.loads((args.reference/'manifest.json').read_text())['plan']['instances_by_objective']
imports={(o,n) for o,names in parent['instances_by_objective'].items() for n in names}
assert imports.issubset(expected)
source=json.loads((args.reference/'manifest.json').read_text());baseline={role:{} for role in dual.ROLES};oracle={}
for task in dual.tasks(source['plan']):
 if task[0]!='minisat':continue
 r=dual.assess(args.reference,task,source);assert not r['errors']
 baseline[task[1]][task[2:]]=r
 if r['proven']:oracle[task[2:]]=r['solve']['cost']
if full:
 rows,meta=published.load_directory(Path('results'))
 assert manifest['published_cost_reference_sha256']==meta['file_sha256']
 for r in rows:
  if r['tag'] not in ('CSOnet','MaxSAT-Journal') or not r['proven']:continue
  key=r['objective'],r['name'];cost=r['solve']['cost']
  if key in oracle:assert extended.common.same_number(oracle[key],cost)
  oracle[key]=cost
tag='Core-E4-full216' if full else 'Core-E4-hard31';records=[];rebuilt=[]
for objective,name in expected:
 case=root/'cases'/objective/name;raw=case/f'{objective}.json'
 receipt=json.loads((case/'measurement.json').read_text())
 assert receipt['raw_sha256']==extended.focus.sha(raw)
 assert receipt['binary_sha256']==manifest['binary_sha256'] and receipt['definition']==manifest['definition']
 reused=(objective,name) in imports
 assert receipt['mode']==('reused-completed-hardset' if full else 'reused-original-bytes') if reused else receipt['mode']=='new-sequential-measurement'
 if reused:
  assert extended.focus.sha(raw)==extended.focus.sha(args.parent/'cases'/objective/name/f'{objective}.json')
  if full:
   assert receipt['source_receipt_sha256']==extended.focus.sha(args.parent/'cases'/objective/name/'measurement.json')
 provenance=dict(l.split('=',1) for l in (case/'logs/manifest.txt').read_text().splitlines() if '=' in l)
 locked=dict(binary_sha256=manifest['binary_sha256'],git_commit=manifest['runner_commit'],git_dirty='0',
  solver=manifest['definition']['solver'],objective=objective,selected_instances=name,selected_instance_count='1',
  instance_timeout_seconds=str(manifest['timeout_seconds']),ram_limit_kb=str(manifest['ram_kb']))
 locked.update({'maxsatddd_'+k:v for k,v in manifest['definition'].items() if k not in ('solver','kind')})
 assert all(provenance.get(k)==v for k,v in locked.items()),(objective,name,'provenance')
 r=extended.assess_case(case,tag,objective,name,manifest['timeout_seconds'],manifest['definition'])
 assert not r['errors'] and r['status'] not in extended.audit.FATAL_STATUSES,(objective,name,r['errors'])
 if r['proven'] and (objective,name) in oracle:assert extended.common.same_number(r['solve']['cost'],oracle[objective,name])
 records.append(r)
 rebuilt.append(dict(objective=objective,name=name,status=r['status'],proven=r['proven'],seconds=r['time'],
  cost=r['solve'].get('cost'),lb=r['solve'].get('lb'),ub=r['solve'].get('ub')))
assert rebuilt==saved['case_bounds']
assert extended.reports_match(extended.audit.summarize(records,manifest['timeout_seconds']),saved['summary'])
assert saved['complete'] and len(records)==saved['completed_runs']==saved['expected_runs']==index['completed_runs']
assert saved['reused_runs']==len(imports) and saved['newly_measured_runs']==len(records)-len(imports)
comparisons=[];indexed={(r['objective'],r['name']):r for r in records}
for role,items in baseline.items():
 paired=set(indexed)&set(items)
 comparisons.append(dict(baseline=role,paired_completed=len(paired),candidate_optimal=sum(indexed[k]['proven'] for k in paired),
  baseline_optimal=sum(items[k]['proven'] for k in paired),
  gained=[list(k) for k in sorted(paired) if indexed[k]['proven'] and not items[k]['proven']],
  lost=[list(k) for k in sorted(paired) if items[k]['proven'] and not indexed[k]['proven']]))
if not full:assert comparisons==saved['comparisons']
print(json.dumps(dict(audit_passed=True,complete=True,completed_runs=len(records),optimal=sum(r['proven'] for r in records),
 reused_runs=len(imports),newly_measured_runs=len(records)-len(imports),summary=saved['summary'],
 comparisons_on_31_hard_pairs=comparisons,unresolved=[dict(objective=r['objective'],name=r['name']) for r in records if not r['proven']],
 submission_passed=False,scope='full candidate coverage; same-cutoff baselines are available only on 31 difficult pairs' if full else saved['scope']),indent=2))
