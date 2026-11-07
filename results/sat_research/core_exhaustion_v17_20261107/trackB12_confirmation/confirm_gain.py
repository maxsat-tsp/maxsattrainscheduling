from pathlib import Path
from types import SimpleNamespace
import json,os,subprocess,sys,time
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
source=json.loads((reference/'manifest.json').read_text())
binary=Path('/home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/target/release/ddd')
assert extended.focus.sha(binary)==source['binary_sha256']
root=Path('results/aglr/v17-trackB12-confirm');root.mkdir(parents=True,exist_ok=True)
manifest=dict(schema='v17-single-gain-confirmation-v1',solver_source_commit=source['solver_source_commit'],
 runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),binary_sha256=source['binary_sha256'],
 definition=source['definition'],dataset_sha256=source['dataset_sha256'],
 reference_manifest_sha256=extended.focus.sha(reference/'manifest.json'),reference_report_sha256=extended.focus.sha(reference/'full_audit.json'),
 reference_raw_sha256=extended.focus.sha(reference/'cases/cont/trackB12/cont.json'),
 selection=[dict(objective='cont',name='trackB12',expected_cost=15182)],repeats=3,timeout_seconds=300,ram_kb=6000000,
 cpu_affinity=sorted(os.sched_getaffinity(0)),parallel_context='V18 unresolved screening on physical CPU group 0,1,4,5; confirmations on disjoint group 2,3,6,7; timings diagnostic only',
 script_sha256=extended.focus.sha(Path(__file__)),submission_passed=False)
assert manifest['dataset_sha256']==extended.focus.dataset_hash()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all']).strip()
if (root/'manifest.json').exists():assert json.loads((root/'manifest.json').read_text())==manifest
else:extended.save(root/'manifest.json',manifest)
args=SimpleNamespace(timeout=300,ram_kb=6000000,binary=binary,method_definitions={'V17-confirm':source['definition']})
records=[]
try:
 for repeat in [1,2,3]:
  case=root/'cases'/f'repeat-{repeat}'/'cont'/'trackB12'
  if not (case/'cont.json').exists():
   print(f'Confirm V17 trackB12 repeat {repeat}',flush=True)
   extended.run_case('V17-confirm','cont','trackB12',args,case)
  r=extended.assess_case(case,'V17-confirm','cont','trackB12',300,source['definition'])
  assert not r['errors'] and r['status'] not in extended.audit.FATAL_STATUSES,r['errors']
  if r['proven']:assert r['solve']['cost']==15182
  records.append(dict(repeat=repeat,status=r['status'],proven=r['proven'],reproduced=r['proven'] and r['solve']['cost']==15182,
   seconds=r['time'],cost=r['solve'].get('cost'),lb=r['solve'].get('lb'),ub=r['solve'].get('ub'),sha256=extended.focus.sha(case/'cont.json')))
  extended.save(root/'confirmation_audit.json',dict(schema=manifest['schema'],expected_runs=3,completed_runs=len(records),complete=len(records)==3,
   confirmed=len(records)==3 and all(r['reproduced'] for r in records),errors=[],cases=records,submission_passed=False,
   scope='three repeats of V17 trackB12/cont only; not a full candidate confirmation; concurrent timing diagnostic'))
except BaseException as error:
 extended.save(root/'failure.json',dict(error=str(error) or type(error).__name__));raise
