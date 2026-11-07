from pathlib import Path
from types import SimpleNamespace
import json,re,subprocess,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
original=Path('/home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling')
binary=original/'target/release/ddd';build=original/'results/aglr/master-levels-v23-build/manifest.json'
meta=json.loads(build.read_text());assert meta['binary_sha256']==extended.focus.sha(binary)
python=Path('/tmp/master-full-v24-python-tests.log').read_text();n=re.search(r'Ran (\d+) tests',python);assert n and '\nOK\n' in python
root=Path('results/aglr/master-full-v24-validation');root.mkdir(parents=True,exist_ok=True);checks=[]
cfg=dict(extended.METHODS['Orders-Transitive'],assumptions='full',core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4',order_master='true',order_master_cost_levels='true')
for objective in ['finsteps123','infsteps180','cont']:
 source=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216/cases')/objective/'origA1'/f'{objective}.json'
 cost=json.loads(source.read_text())[0]['solves'][0]['cost']
 args=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
 case=Path('results/aglr')/f'master-full-v24-smoke-{objective}';extended.run_case('Smoke',objective,'origA1',args,case)
 r=extended.assess_case(case,'Smoke',objective,'origA1',30,cfg)
 checks.append(dict(objective=objective,status=r['status'],seconds=r['time'],cost=r['solve'].get('cost'),expected_cost=cost))
 extended.save(root/'progress.json',dict(smokes=checks,passed=False))
 assert not r['errors'] and r['proven'] and r['solve']['cost']==cost,r['status']
 assert r['solve']['maxsat_partial_sat_calls']==0
args.timeout=2;case=Path('results/aglr/master-full-v24-hard-probe')
extended.run_case('Smoke','infsteps180','stationA11',args,case)
r=extended.assess_case(case,'Smoke','infsteps180','stationA11',2,cfg)
assert not r['errors'] and r['status'] in ('timeout','ok') and r['solve']['process_exit_code']==0
extended.save(root/'validation.json',dict(passed=True,smokes=checks,hard_probe_status=r['status'],solver_source_commit=meta['git_commit'],
 runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),binary_sha256=meta['binary_sha256'],
 source_build_manifest_sha256=extended.focus.sha(build),python_tests_passed=int(n[1]),validator_sha256=extended.focus.sha(Path(__file__))))
print(json.dumps(dict(validation_passed=True,smokes=checks)),flush=True)
