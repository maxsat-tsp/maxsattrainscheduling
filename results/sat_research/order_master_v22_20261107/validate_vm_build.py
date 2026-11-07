from pathlib import Path
from types import SimpleNamespace
import json,re,subprocess,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
tested=json.loads(Path('/tmp/order-master-v22-tested-source.json').read_text())
for name,digest in tested.items():assert extended.focus.sha(Path(name))==digest,name
rust=Path('/tmp/order-master-v22-rust-tests.log').read_text();python=Path('/tmp/order-master-v22-python-tests.log').read_text()
m=re.search(r'test result: ok\. (\d+) passed; 0 failed;',rust);n=re.search(r'Ran (\d+) tests',python)
assert m and n and '\nOK\n' in python
root=Path('results/aglr/order-master-v22-build');root.mkdir(parents=True,exist_ok=True)
binary=Path('target/release/ddd').resolve()
meta=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 binary_sha256=extended.focus.sha(binary),cargo_lock_sha256=extended.focus.sha(Path('Cargo.lock')),
 rust_library_tests_passed=int(m[1]),python_tests_passed=int(n[1]),tested_source_sha256=tested,
 rust_tests_log_sha256=extended.focus.sha(Path('/tmp/order-master-v22-rust-tests.log')),
 python_tests_log_sha256=extended.focus.sha(Path('/tmp/order-master-v22-python-tests.log')),
 validator_sha256=extended.focus.sha(Path(__file__)),
 salvers=extended.dependency_state(extended.REPO.parent/'salvers'),ipamir=extended.dependency_state(extended.REPO.parent/'ipamir-rs'))
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all']).strip()
extended.save(root/'manifest.json',meta);checks=[]
cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4',order_master='true')
for objective in ['finsteps123','infsteps180','cont']:
 reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216/cases')/objective/'origA1'/f'{objective}.json'
 cost=json.loads(reference.read_text())[0]['solves'][0]['cost']
 args=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
 case=Path('results/aglr')/f'order-master-v22-smoke-{objective}'
 extended.run_case('Smoke',objective,'origA1',args,case)
 r=extended.assess_case(case,'Smoke',objective,'origA1',30,cfg)
 assert not r['errors'] and r['proven'] and r['solve']['cost']==cost,r
 assert r['solve']['maxsat_resource_order_rows']==0
 assert r['solve']['maxsat_order_master_schedules']>0
 checks.append(dict(objective=objective,cost=cost,seconds=r['time'],pairs=r['solve']['maxsat_resource_order_pairs'],
   master_models=r['solve']['maxsat_order_master_models'],master_schedules=r['solve']['maxsat_order_master_schedules'],
   paths_added=r['solve']['maxsat_order_paths_added']))
args.timeout=2;case=Path('results/aglr/order-master-v22-hard-probe')
extended.run_case('Smoke','infsteps180','stationA11',args,case)
r=extended.assess_case(case,'Smoke','infsteps180','stationA11',2,cfg)
assert not r['errors'] and r['status'] in ('timeout','ok') and r['solve']['process_exit_code']==0
assert r['solve']['maxsat_sat_timeout_mode']=='native-watchdog-deadline'
# Alias smoke: only the dispatch alias differs, master flag is explicit too.
cfg=dict(cfg,solver='maxsat_order_graph');args.timeout=30;args.method_definitions={'Alias':cfg}
case=Path('results/aglr/order-master-v22-smoke-alias')
extended.run_case('Alias','cont','origA1',args,case)
r=extended.assess_case(case,'Alias','cont','origA1',30,cfg)
assert not r['errors'] and r['proven'] and r['solve']['cost']==5526
extended.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=r['status'],alias_cost=5526))
print(json.dumps(dict(validation_passed=True,**meta,smokes=checks)),flush=True)
