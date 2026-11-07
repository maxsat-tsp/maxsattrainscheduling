from pathlib import Path
from types import SimpleNamespace
import json,re,subprocess,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as e
import targeted_order_cycles as trial
rust=Path('/tmp/master-batch-v26-rust-tests.log').read_text();python=Path('/tmp/master-batch-v26-python-tests.log').read_text()
m=re.search(r'test result: ok\. (\d+) passed; 0 failed;',rust);n=re.search(r'Ran (\d+) tests',python)
assert m and int(m[1])>=78 and n and int(n[1])>=111 and '\nOK\n' in python
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all']).strip()
tracked=subprocess.check_output(['git','ls-files','src','quick_scripts','Cargo.lock','Cargo.toml'],text=True).splitlines()
root=Path('results/aglr/master-batch-v26-build');root.mkdir(parents=True,exist_ok=True);binary=Path('target/release/ddd').resolve()
meta=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),binary_sha256=e.focus.sha(binary),
 cargo_lock_sha256=e.focus.sha(Path('Cargo.lock')),rust_library_tests_passed=int(m[1]),python_tests_passed=int(n[1]),
 tested_source_sha256={p:e.focus.sha(Path(p)) for p in tracked},rust_tests_log_sha256=e.focus.sha(Path('/tmp/master-batch-v26-rust-tests.log')),
 python_tests_log_sha256=e.focus.sha(Path('/tmp/master-batch-v26-python-tests.log')),validator_sha256=e.focus.sha(Path(__file__)),
 salvers=e.dependency_state(e.REPO.parent/'salvers'),ipamir=e.dependency_state(e.REPO.parent/'ipamir-rs'))
e.save(root/'manifest.json',meta)
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
source,_,_=trial.load_reference(reference);cfg=trial.candidate_config(source,'order-master-batch');checks=[]
for objective in ['finsteps123','infsteps180','cont']:
 cost=json.loads((reference/'cases'/objective/'origA1'/f'{objective}.json').read_text())[0]['solves'][0]['cost']
 args=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
 case=Path('results/aglr')/f'master-batch-v26-smoke-{objective}'
 if not (case/f'{objective}.json').exists():e.run_case('Smoke',objective,'origA1',args,case)
 r=e.assess_case(case,'Smoke',objective,'origA1',30,cfg)
 assert not r['errors'] and r['status'] in ('ok','timeout'),r
 if r['proven']:assert r['solve']['cost']==r['solve']['lb']==r['solve']['ub']==cost
 for counter in ['maxsat_partial_sat_calls','maxsat_resource_order_rows']:
  if counter in r['solve']:
   assert r['solve'][counter]==0
  else:
   assert r['status']=='timeout' and not r['proven'] and r['solve']['maxsat_assumptions']=='full'
 checks.append(dict(objective=objective,status=r['status'],proven=r['proven'],seconds=r['time'],cost=r['solve'].get('cost'),expected_cost=cost,
  raw_sha256=e.focus.sha(case/f'{objective}.json'),partial_calls_telemetry_available='maxsat_partial_sat_calls' in r['solve'],max_batch=r['solve'].get('maxsat_order_master_max_batch')))
 e.save(root/'validation_progress.json',dict(smokes=checks,passed=False))
assert any(r['proven'] for r in checks),'all real-case smokes timed out; stop before expensive screening'
assert max(r['max_batch'] or 0 for r in checks)>1,'batched separation was not exercised'
args.timeout=2;case=Path('results/aglr/master-batch-v26-hard-probe')
if not (case/'infsteps180.json').exists():e.run_case('Smoke','infsteps180','stationA11',args,case)
probe=e.assess_case(case,'Smoke','infsteps180','stationA11',2,cfg)
assert not probe['errors'] and probe['status'] in ('timeout','ok') and probe['solve']['process_exit_code']==0
assert probe['solve']['maxsat_sat_timeout_mode']=='native-watchdog-deadline'
e.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=probe['status'],
 policy='native exactness tests and valid real-case statuses; every proved smoke matches known cost; at least one proved smoke; a valid real-case timeout is a performance outcome',
 binary_sha256=meta['binary_sha256'],solver_source_commit=meta['git_commit'],submission_passed=False))
print(json.dumps(dict(validation_passed=True,smokes=checks)),flush=True)
