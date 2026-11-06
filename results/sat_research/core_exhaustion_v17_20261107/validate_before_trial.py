from pathlib import Path
from types import SimpleNamespace
import json,os,re,subprocess,sys

sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
import compare_sat_backends as dual
from confirm_targeted_core_minimization import choose

root=Path('results/aglr/core-exhaust-v17-build')
root.mkdir(parents=True,exist_ok=True)
rust=Path('/tmp/core-exhaust-v17-rust-tests.log').read_text()
python=Path('/tmp/core-exhaust-v17-python-tests.log').read_text()
match=re.search(r'test result: ok\. (\d+) passed; 0 failed;',rust)
assert match,'Rust library tests must pass before the trial'
python_match=re.search(r'Ran (\d+) tests',python)
assert python_match and '\nOK\n' in python,'Python auditors must pass before the trial'
binary=Path('target/release/ddd').resolve()
metadata=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 binary_sha256=extended.focus.sha(binary),cargo_lock_sha256=extended.focus.sha(Path('Cargo.lock')),
 salvers=extended.dependency_state(extended.REPO.parent/'salvers'),
 ipamir=extended.dependency_state(extended.REPO.parent/'ipamir-rs'),
 rust_library_tests_passed=int(match.group(1)),python_tests_passed=int(python_match.group(1)),
 validator_sha256=extended.focus.sha(Path(__file__)))
extended.save(root/'manifest.json',metadata)
checks=[]
for minimum,conflicts,exhaust in [(0,0,0),(4,100,0),(4,100,4)]:
 cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks=str(minimum),
          core_minimize_conflicts=str(conflicts),core_exhaust_checks=str(exhaust))
 args=SimpleNamespace(timeout=10,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
 case=Path(f'results/aglr/core-exhaust-v17-smoke-{minimum}-{conflicts}-{exhaust}')
 extended.run_case('Smoke','cont','origA1',args,case)
 record=extended.assess_case(case,'Smoke','cont','origA1',10,cfg)
 assert not record['errors'] and record['proven'] and record['solve']['cost']==5526,record
 if exhaust: assert record['solve']['maxsat_native_exhaust_checks']>0
 checks.append(dict(core_checks=minimum,conflicts=conflicts,exhaust_checks=exhaust,cost=5526,
                    native_exhaust_checks=record['solve'].get('maxsat_native_exhaust_checks')))
 print(json.dumps(checks[-1]),flush=True)
cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4')
args=SimpleNamespace(timeout=2,ram_kb=6000000,binary=binary,method_definitions={'HardProbe':cfg})
case=Path('results/aglr/core-exhaust-v17-hard-probe')
extended.run_case('HardProbe','infsteps180','stationA11',args,case)
record=extended.assess_case(case,'HardProbe','infsteps180','stationA11',2,cfg)
assert not record['errors'] and record['status'] in ('timeout','ok'),record
assert record['solve']['process_exit_code']==0
assert record['solve']['maxsat_sat_timeout_mode']=='native-watchdog-deadline'

# With two gains now observed, verify that the selected V16 configuration
# retains the old candidate's solved cases before trying another component.
v16_tree=Path('/home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling')
reference=Path('/home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22')
trials=[v16_tree/'results/aglr'/f'core-v16-conflicts{c}-unresolved300' for c in (1000,100)]
winner,_=choose(trials,reference)
selected=json.loads((winner/'manifest.json').read_text())
v16_binary=v16_tree/'target/release/ddd'
assert extended.focus.sha(v16_binary)==selected['binary_sha256']
source=json.loads((reference/'manifest.json').read_text())
regression=[]
for task in dual.tasks(source['plan']):
 if task[:2]!=('minisat','Orders-Transitive'):continue
 prior=dual.assess(reference,task,source)
 if prior['proven']:regression.append(dict(objective=task[2],name=task[3],cost=prior['solve']['cost']))
regroot=Path('results/aglr/core-v16-regression-selected');regroot.mkdir(parents=True,exist_ok=True)
locked=dict(schema='v16-solved-case-regression-v1',solver_source_commit=selected['solver_source_commit'],
 runner_commit=metadata['git_commit'],binary_sha256=selected['binary_sha256'],
 dataset_sha256=selected['dataset_sha256'],definition=selected['definition'],
 reference_manifest_sha256=extended.focus.sha(reference/'manifest.json'),
 reference_report_sha256=extended.focus.sha(reference/'backend_comparison.json'),
 selected_trial_manifest_sha256=extended.focus.sha(winner/'manifest.json'),
 selection=regression,timeout_seconds=300,ram_kb=6000000,cpu_affinity=selected['cpu_affinity'],
 scope='regression on previously solved difficult cases; not a full-dataset result',submission_passed=False)
if (regroot/'manifest.json').exists():assert json.loads((regroot/'manifest.json').read_text())==locked
else:extended.save(regroot/'manifest.json',locked)
runtime=SimpleNamespace(timeout=300,ram_kb=6000000,binary=v16_binary,
                        method_definitions={'V16-regression':selected['definition']})
rows=[]
saved_affinity=os.sched_getaffinity(0)
try:
 os.sched_setaffinity(0,set(selected['cpu_affinity']))
 for item in regression:
  objective,name=item['objective'],item['name'];case=regroot/'cases'/objective/name
  if not (case/f'{objective}.json').exists():
   print(f'Regress V16: {objective}/{name}',flush=True)
   extended.run_case('V16-regression',objective,name,runtime,case)
  result=extended.assess_case(case,'V16-regression',objective,name,300,selected['definition'])
  same=result['proven'] and extended.common.same_number(result['solve']['cost'],item['cost'])
  rows.append(dict(objective=objective,name=name,expected_cost=item['cost'],cost=result['solve'].get('cost'),
                   status=result['status'],proven=result['proven'],retained=same,seconds=result['time'],
                   errors=result['errors'],sha256=extended.focus.sha(case/f'{objective}.json')))
  passed=len(rows)==len(regression) and all(row['retained'] for row in rows)
  extended.save(regroot/'regression_audit.json',dict(schema=locked['schema'],expected_runs=len(regression),
      completed_runs=len(rows),complete=len(rows)==len(regression),passed=passed,
      lost=[dict(objective=row['objective'],name=row['name']) for row in rows if not row['retained']],
      cases=rows,submission_passed=False))
  assert not result['errors'] and result['status'] not in extended.audit.FATAL_STATUSES,result
  assert not result['proven'] or same,'V16 proved cost changed during regression'
finally:
 os.sched_setaffinity(0,saved_affinity)
assert rows and all(row['retained'] for row in rows),'V16 lost a previously solved case; inspect regression before V17'
extended.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=record['status'],
                hard_probe_deadline_hit=record['solve'].get('maxsat_sat_deadline_hit',False),
                v16_regression_passed=True,v16_regression_cases=len(rows)))
print(json.dumps(dict(validation_passed=True,**metadata)),flush=True)
