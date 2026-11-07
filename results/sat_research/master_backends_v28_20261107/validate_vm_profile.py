from pathlib import Path
from types import SimpleNamespace
import json,re,sys
sys.path.insert(0,'quick_scripts/analyze')
import targeted_order_cycles as t
import extended_timeout_experiments as e
backend=sys.argv[1];assert backend in ('minisat','cadical')
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
source,_,_=t.load_reference(reference);cfg=t.experiment_config(source,'order-master-seeds',backend,0)
primary=Path('/home/tuyenkv/projects/master-seeds-v27/maxsattrainscheduling');binary=primary/'target/release/ddd'
meta=json.loads((primary/'results/aglr/master-seeds-v27-build/manifest.json').read_text());assert e.focus.sha(binary)==meta['binary_sha256']
log=Path(f'/tmp/master-backends-v28-{backend}-python-tests.log');text=log.read_text();count=re.search(r'Ran (\d+) tests',text)
assert count and int(count[1])>=116 and '\nOK\n' in text
root=Path('results/aglr')/f'master-backends-v28-{backend}-validation';root.mkdir(parents=True,exist_ok=True);checks=[]
args=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary,method_definitions={'Smoke':cfg})
for objective,expected in [('finsteps123',11),('infsteps180',34),('cont',5526)]:
 case=Path('results/aglr')/f'master-backends-v28-{backend}-smoke-{objective}'
 if not (case/f'{objective}.json').exists():e.run_case('Smoke',objective,'origA1',args,case)
 r=e.assess_case(case,'Smoke',objective,'origA1',30,cfg);assert not r['errors'] and r['status'] in ('ok','timeout'),r
 if r['proven']:assert r['solve']['cost']==r['solve']['lb']==r['solve']['ub']==expected
 for counter in ['maxsat_partial_sat_calls','maxsat_resource_order_rows']:
  if counter in r['solve']:assert r['solve'][counter]==0
  else:assert r['status']=='timeout' and not r['proven'] and r['solve']['maxsat_assumptions']=='full'
 checks.append(dict(objective=objective,status=r['status'],proven=r['proven'],cost=r['solve'].get('cost'),seconds=r['time'],
  raw_sha256=e.focus.sha(case/f'{objective}.json'),core_minimize_calls=r['solve'].get('maxsat_core_minimize_calls'),
  seed_clauses=r['solve'].get('maxsat_order_master_seed_clauses')))
 e.save(root/'progress.json',dict(smokes=checks,passed=False))
assert any(r['proven'] for r in checks),'no known-optimum smoke was proved'
assert any((r['seed_clauses'] or 0)>0 for r in checks),'seeded cost path not exercised'
args.timeout=2;case=Path('results/aglr')/f'master-backends-v28-{backend}-deadline-probe'
if not (case/'infsteps180.json').exists():e.run_case('Smoke','infsteps180','stationA11',args,case)
r=e.assess_case(case,'Smoke','infsteps180','stationA11',2,cfg);assert not r['errors'] and r['status'] in ('ok','timeout') and r['solve']['process_exit_code']==0
assert r['solve']['maxsat_sat_timeout_mode']=={'minisat':'native-watchdog-deadline','cadical':'native-remaining-budget'}[backend]
e.save(root/'validation.json',dict(passed=True,backend=backend,smokes=checks,deadline_probe_status=r['status'],
 python_tests_passed=int(count[1]),python_tests_log_sha256=e.focus.sha(log),validator_sha256=e.focus.sha(Path(__file__)),
 binary_sha256=meta['binary_sha256'],solver_source_commit=meta['git_commit'],measurement_context='paired-screen',paired_run_id='master-backends-v28',
 missing_timeout_counters='retained as missing, never imputed as zero',submission_passed=False))
print(json.dumps(dict(validation_passed=True,backend=backend,smokes=checks)),flush=True)
