from pathlib import Path
from types import SimpleNamespace
import json,re,subprocess,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
rust=Path('/tmp/initial-cost-v19-rust-tests.log').read_text();python=Path('/tmp/initial-cost-v19-python-tests.log').read_text()
m=re.search(r'test result: ok\. (\d+) passed; 0 failed;',rust);n=re.search(r'Ran (\d+) tests',python)
assert m and n and '\nOK\n' in python
root=Path('results/aglr/initial-cost-v19-build');root.mkdir(parents=True,exist_ok=True)
binary=Path('target/release/ddd').resolve()
meta=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 binary_sha256=extended.focus.sha(binary),cargo_lock_sha256=extended.focus.sha(Path('Cargo.lock')),
 rust_library_tests_passed=int(m[1]),python_tests_passed=int(n[1]),validator_sha256=extended.focus.sha(Path(__file__)),
 salvers=extended.dependency_state(extended.REPO.parent/'salvers'),ipamir=extended.dependency_state(extended.REPO.parent/'ipamir-rs'))
extended.save(root/'manifest.json',meta);checks=[]
for offset in ['false','true']:
 cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4',extract_initial_cost=offset)
 args=SimpleNamespace(timeout=10,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
 case=Path('results/aglr')/f'initial-cost-v19-smoke-{offset}'
 extended.run_case('Smoke','cont','origA1',args,case)
 r=extended.assess_case(case,'Smoke','cont','origA1',10,cfg)
 assert not r['errors'] and r['proven'] and r['solve']['cost']==5526
 assert r['solve']['maxsat_initial_cost_offset']==(4799 if offset=='true' else 0)
 checks.append(dict(extract_initial_cost=offset,cost=5526,initial_cost_offset=r['solve']['maxsat_initial_cost_offset']))
cfg=dict(cfg,extract_initial_cost='true');case=Path('results/aglr/initial-cost-v19-hard-probe')
args.timeout=2;args.method_definitions={'Probe':cfg};extended.run_case('Probe','infsteps180','stationA11',args,case)
r=extended.assess_case(case,'Probe','infsteps180','stationA11',2,cfg)
assert not r['errors'] and r['status'] in ('timeout','ok') and r['solve']['process_exit_code']==0
assert r['solve']['maxsat_sat_timeout_mode']=='native-watchdog-deadline'
extended.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=r['status']))
print(json.dumps(dict(validation_passed=True,**meta)),flush=True)
