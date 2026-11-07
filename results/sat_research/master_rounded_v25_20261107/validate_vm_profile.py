from pathlib import Path
from types import SimpleNamespace
import json,re,subprocess,sys
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as extended
import targeted_order_cycles as trial
original=Path('/home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling')
binary=original/'target/release/ddd';build=original/'results/aglr/master-levels-v23-build/manifest.json'
meta=json.loads(build.read_text());assert meta['binary_sha256']==extended.focus.sha(binary)
python=Path('/tmp/master-rounded-v25-python-tests.log').read_text();n=re.search(r'Ran (\d+) tests',python);assert n and '\nOK\n' in python
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
source,selection,_=trial.load_reference(reference)
cfg=trial.candidate_config(source,'order-master-levels-full')
prior=Path('/home/tuyenkv/projects/master-full-v24/maxsattrainscheduling/results/aglr')
prior_case=prior/'master-full-v24-smoke-infsteps180'
r=extended.assess_case(prior_case,'Smoke','infsteps180','origA1',30,cfg)
assert not r['errors'] and r['proven'] and r['solve']['cost']==34
provenance=dict(l.split('=',1) for l in (prior_case/'logs/manifest.txt').read_text().splitlines() if '=' in l)
assert provenance['binary_sha256']==meta['binary_sha256']
assert r['solve']['maxsat_partial_sat_calls']==0
root=Path('results/aglr/master-rounded-v25-validation');root.mkdir(parents=True,exist_ok=True)
args=SimpleNamespace(timeout=2,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
case=Path('results/aglr/master-rounded-v25-hard-probe')
if not (case/'infsteps180.json').exists():extended.run_case('Smoke','infsteps180','stationA11',args,case)
probe=extended.assess_case(case,'Smoke','infsteps180','stationA11',2,cfg)
assert not probe['errors'] and probe['status'] in ('timeout','ok') and probe['solve']['process_exit_code']==0
extended.save(root/'validation.json',dict(passed=True,scope='infsteps180 only; continuous-objective 30-second smoke remains a timeout',
 inherited_smoke=dict(objective='infsteps180',name='origA1',cost=34,seconds=r['time'],
 raw_sha256=extended.focus.sha(prior_case/'infsteps180.json'),provenance_sha256=extended.focus.sha(prior_case/'logs/manifest.txt')),
 hard_probe_status=probe['status'],solver_source_commit=meta['git_commit'],
 runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),binary_sha256=meta['binary_sha256'],
 source_build_manifest_sha256=extended.focus.sha(build),python_tests_passed=int(n[1]),validator_sha256=extended.focus.sha(Path(__file__))))
print(json.dumps(dict(validation_passed=True,scope='infsteps180 only')),flush=True)
