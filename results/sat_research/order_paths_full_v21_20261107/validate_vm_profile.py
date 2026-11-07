from pathlib import Path
from types import SimpleNamespace
import hashlib,json,re,subprocess,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
original=Path('/home/tuyenkv/projects/order-paths-v20/maxsattrainscheduling')
binary=original/'target/release/ddd';build=original/'results/aglr/order-paths-v20-build/manifest.json'
metadata=json.loads(build.read_text());assert extended.focus.sha(binary)==metadata['binary_sha256']
python=Path('/tmp/order-paths-full-v21-python-tests.log').read_text();n=re.search(r'Ran (\d+) tests',python)
assert n and '\nOK\n' in python
checks=[]
for strategy in ['legacy','full']:
 cfg=dict(extended.METHODS['Orders-Transitive'],assumptions=strategy,core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4',order_path_cuts='true')
 args=SimpleNamespace(timeout=10,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
 case=Path('results/aglr')/f'order-paths-full-v21-smoke-{strategy}'
 extended.run_case('Smoke','cont','origA1',args,case)
 r=extended.assess_case(case,'Smoke','cont','origA1',10,cfg)
 assert not r['errors'] and r['proven'] and r['solve']['cost']==5526
 if strategy=='full':assert r['solve']['maxsat_partial_sat_calls']==0
 checks.append(dict(assumptions=strategy,cost=5526,seconds=r['time'],partial_calls=r['solve']['maxsat_partial_sat_calls'],
  native_calls=r['solve']['maxsat_native_sat_calls'],paths_added=r['solve']['maxsat_order_paths_added']))
cfg=dict(cfg,assumptions='full');case=Path('results/aglr/order-paths-full-v21-hard-probe')
args.timeout=2;args.method_definitions={'Probe':cfg};extended.run_case('Probe','infsteps180','stationA11',args,case)
r=extended.assess_case(case,'Probe','infsteps180','stationA11',2,cfg)
assert not r['errors'] and r['status'] in ('timeout','ok') and r['solve']['process_exit_code']==0
root=Path('results/aglr/order-paths-full-v21-validation');root.mkdir(exist_ok=True)
extended.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=r['status'],
 solver_source_commit=metadata['git_commit'],runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 binary_sha256=metadata['binary_sha256'],source_build_manifest_sha256=extended.focus.sha(build),python_tests_passed=int(n[1]),
 python_tests_log_sha256=extended.focus.sha(Path('/tmp/order-paths-full-v21-python-tests.log')),
 validator_sha256=extended.focus.sha(Path(__file__))))
print(json.dumps(dict(validation_passed=True,python_tests_passed=int(n[1]),smokes=checks)),flush=True)
