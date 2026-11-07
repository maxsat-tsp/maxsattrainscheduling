"""Complete a 31-pair evaluation while preserving a validated partial trial."""
from pathlib import Path
from types import SimpleNamespace
import json,os,shutil,subprocess,sys,time

sys.path.insert(0,'quick_scripts/analyze')
import audit_targeted_core_minimization as checker
import compare_sat_backends as dual
import extended_timeout_experiments as extended

repo=extended.REPO
partial=repo/'results/aglr/core-exhaust-v17-followup300'
reference=Path('/home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22')
v16=Path('/home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr')
regression=Path('/home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/results/aglr/core-v16-regression-selected')
trials=[v16/'core-v16-conflicts1000-unresolved300',v16/'core-v16-conflicts100-unresolved300']
report=checker.audit_saved(partial,reference,trials,regression)
assert report['complete'] and report['audit_passed']
candidate=json.loads((partial/'manifest.json').read_text())
anchor=json.loads((reference/'manifest.json').read_text())
binary=Path('/home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/target/release/ddd')
assert extended.focus.sha(binary)==candidate['binary_sha256']
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=repo).strip()
root=repo/'results/aglr/core-exhaust-v17-hard31';root.mkdir(parents=True,exist_ok=True)
config=candidate['definition'];tag='Core-E4-hard31'
locked=dict(schema='completed-core-hardset-v1',runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 solver_source_commit=candidate['solver_source_commit'],binary_sha256=candidate['binary_sha256'],definition=config,
 script_sha256=extended.focus.sha(Path(__file__)),dataset_sha256=extended.focus.dataset_hash(),
 instances_by_objective=anchor['plan']['instances_by_objective'],timeout_seconds=300,ram_kb=6000000,
 cpu_affinity=sorted(os.sched_getaffinity(0)),sequential=True,
 partial_manifest_sha256=extended.focus.sha(partial/'manifest.json'),partial_report_sha256=extended.focus.sha(partial/'core_minimization_audit.json'),
 reference_manifest_sha256=extended.focus.sha(reference/'manifest.json'),reference_report_sha256=extended.focus.sha(reference/'backend_comparison.json'),
 submission_passed=False,scope='complete 31-pair difficult set only; not the full dataset')
if (root/'manifest.json').exists():assert json.loads((root/'manifest.json').read_text())==locked
else:extended.save(root/'manifest.json',locked)
expected=[(o,n) for o,names in locked['instances_by_objective'].items() for n in names]
imports={(o,n) for o,names in candidate['instances_by_objective'].items() for n in names}
assert imports.issubset(expected) and len(expected)==31 and len(imports)==14
oracles={};baseline={role:{} for role in dual.ROLES}
for task in dual.tasks(anchor['plan']):
 if task[0]!='minisat':continue
 r=dual.assess(reference,task,anchor);baseline[task[1]][task[2:]]=r
 if r['proven']:oracles[task[2:]]=r['solve']['cost']
runtime=SimpleNamespace(timeout=300,ram_kb=6000000,binary=binary,method_definitions={tag:config})
deadline=time.monotonic()+21600;records=[]
try:
 for objective,name in expected:
  case=root/'cases'/objective/name
  if (objective,name) in imports:
   source=partial/'cases'/objective/name
   if not case.exists():shutil.copytree(source,case)
   assert extended.focus.sha(case/f'{objective}.json')==extended.focus.sha(source/f'{objective}.json')
   mode='reused-original-bytes'
  else:
   if not (case/f'{objective}.json').exists():
    if deadline-time.monotonic()<390:break
    print(f'Complete E4: {objective}/{name}',flush=True)
    extended.run_case(tag,objective,name,runtime,case)
   mode='new-sequential-measurement'
  result=extended.assess_case(case,tag,objective,name,300,config)
  if result['errors'] or result['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(result['errors']))
  if result['proven'] and (objective,name) in oracles:
   assert extended.common.same_number(result['solve']['cost'],oracles[objective,name]),'proved optimum differs from verified reference'
  receipt=dict(mode=mode,raw_sha256=extended.focus.sha(case/f'{objective}.json'),binary_sha256=locked['binary_sha256'],definition=config)
  if (objective,name) in imports:receipt.update(source=str((partial/'cases'/objective/name).resolve()))
  if (case/'measurement.json').exists():assert json.loads((case/'measurement.json').read_text())==receipt
  else:extended.save(case/'measurement.json',receipt)
  records.append(result)
  indexed={(r['objective'],r['name']):r for r in records}
  comparisons=[]
  for role,items in baseline.items():
   paired=set(indexed)&set(items)
   comparisons.append(dict(baseline=role,paired_completed=len(paired),
     candidate_optimal=sum(indexed[k]['proven'] for k in paired),baseline_optimal=sum(items[k]['proven'] for k in paired),
     gained=[list(k) for k in sorted(paired) if indexed[k]['proven'] and not items[k]['proven']],
     lost=[list(k) for k in sorted(paired) if items[k]['proven'] and not indexed[k]['proven']]))
  audit=dict(schema=locked['schema'],expected_runs=31,completed_runs=len(records),complete=len(records)==31,errors=[],
    summary=extended.audit.summarize(records,300),comparisons=comparisons,
    reused_runs=sum((r['objective'],r['name']) in imports for r in records),
    newly_measured_runs=sum((r['objective'],r['name']) not in imports for r in records),
    case_bounds=[dict(objective=r['objective'],name=r['name'],status=r['status'],proven=r['proven'],
      seconds=r['time'],cost=r['solve'].get('cost'),lb=r['solve'].get('lb'),ub=r['solve'].get('ub')) for r in records],
    submission_passed=False,scope=locked['scope'])
  extended.save(root/'hardset_audit.json',audit)
  extended.audit.write_csv(root/'summary.csv',audit['summary'])
except BaseException as error:
 extended.save(root/'failure.json',dict(error=str(error) or type(error).__name__))
 raise
