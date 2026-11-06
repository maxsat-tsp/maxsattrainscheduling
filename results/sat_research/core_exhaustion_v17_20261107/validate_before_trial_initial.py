from pathlib import Path
from types import SimpleNamespace
import json,re,subprocess,sys

sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended

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
extended.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=record['status'],
                hard_probe_deadline_hit=record['solve'].get('maxsat_sat_deadline_hit',False)))
print(json.dumps(dict(validation_passed=True,**metadata)),flush=True)
