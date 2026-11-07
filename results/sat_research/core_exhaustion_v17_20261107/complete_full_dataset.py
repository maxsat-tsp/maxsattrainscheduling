"""Revalidate the completed hard set, then measure only the other 185 pairs."""
from pathlib import Path
from types import SimpleNamespace
import json,os,runpy,shutil,subprocess,sys,time

repo=Path.cwd();hard=repo/'results/aglr/core-exhaust-v17-hard31'
before=(hard/'hardset_audit.json').read_bytes()
context=runpy.run_path('/tmp/complete_core_hardset.py')
assert (hard/'hardset_audit.json').read_bytes()==before,'read-back audit changed the hard-set report'
assert context['audit']['complete'] and context['audit']['completed_runs']==31
import extended_timeout_experiments as extended
import published_baselines as published
binary=context['binary'];config=context['config'];reference=context['reference'];anchor=context['anchor']
source=json.loads((hard/'manifest.json').read_text())
root=repo/'results/aglr/core-exhaust-v17-full216';root.mkdir(parents=True,exist_ok=True)
tag='Core-E4-full216'
published_rows,published_meta=published.load_directory(repo/'results')
structural=[e for e in published_meta['errors'] if not e.startswith('published optimal costs disagree')]
assert not structural,structural
oracles=dict(context['oracles'])
for item in published_rows:
 if item['tag'] not in ('CSOnet','MaxSAT-Journal') or not item['proven']:continue
 key=item['objective'],item['name'];cost=item['solve']['cost']
 if key in oracles:assert extended.common.same_number(oracles[key],cost),'MaxSAT reference costs disagree'
 else:oracles[key]=cost
locked=dict(schema='completed-core-full-v1',runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 solver_source_commit=source['solver_source_commit'],binary_sha256=source['binary_sha256'],definition=config,
 script_sha256=extended.focus.sha(Path(__file__)),source_audit_script_sha256=extended.focus.sha(Path('/tmp/complete_core_hardset.py')),
 dataset_sha256=extended.focus.dataset_hash(),instances_by_objective={o:extended.common.EXPECTED_NAMES for o in extended.audit.OBJECTIVES},
 timeout_seconds=300,ram_kb=6000000,cpu_affinity=sorted(os.sched_getaffinity(0)),sequential=True,
 partial_manifest_sha256=extended.focus.sha(hard/'manifest.json'),partial_report_sha256=extended.focus.sha(hard/'hardset_audit.json'),
 reference_manifest_sha256=extended.focus.sha(reference/'manifest.json'),
 published_cost_reference_sha256=published_meta['file_sha256'],published_cost_oracle_tags=['CSOnet','MaxSAT-Journal'],
 submission_passed=False,scope='full 72-instance dataset, three objectives; baselines are separate references')
if (root/'manifest.json').exists():assert json.loads((root/'manifest.json').read_text())==locked
else:extended.save(root/'manifest.json',locked)
assert extended.focus.sha(binary)==locked['binary_sha256']
expected=[(o,n) for o,names in locked['instances_by_objective'].items() for n in names]
imports=set(context['expected']);assert len(expected)==216 and len(imports)==31
runtime=SimpleNamespace(timeout=300,ram_kb=6000000,binary=binary,method_definitions={tag:config})
deadline=time.monotonic()+21600;records=[]
try:
 for objective,name in expected:
  case=root/'cases'/objective/name
  if (objective,name) in imports:
   original=hard/'cases'/objective/name
   if not case.exists():
    shutil.copytree(original,case,ignore=shutil.ignore_patterns('measurement.json'))
    shutil.copy2(original/'measurement.json',case/'imported_measurement.json')
   assert extended.focus.sha(case/f'{objective}.json')==extended.focus.sha(original/f'{objective}.json')
   mode='reused-completed-hardset'
  else:
   if not (case/f'{objective}.json').exists():
    if deadline-time.monotonic()<390:break
    print(f'Full E4: {objective}/{name}',flush=True)
    extended.run_case(tag,objective,name,runtime,case)
   mode='new-sequential-measurement'
  result=extended.assess_case(case,tag,objective,name,300,config)
  if result['errors'] or result['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(result['errors']))
  if result['proven'] and (objective,name) in oracles:
   assert extended.common.same_number(result['solve']['cost'],oracles[objective,name]),'proved cost differs from MaxSAT references'
  receipt=dict(mode=mode,raw_sha256=extended.focus.sha(case/f'{objective}.json'),binary_sha256=locked['binary_sha256'],definition=config)
  if (objective,name) in imports:
   receipt.update(source=str((hard/'cases'/objective/name).resolve()),
                  source_receipt_sha256=extended.focus.sha(hard/'cases'/objective/name/'measurement.json'))
  if (case/'measurement.json').exists():assert json.loads((case/'measurement.json').read_text())==receipt
  else:extended.save(case/'measurement.json',receipt)
  records.append(result)
  report=dict(schema=locked['schema'],expected_runs=216,completed_runs=len(records),complete=len(records)==216,errors=[],
   summary=extended.audit.summarize(records,300),reused_runs=sum((r['objective'],r['name']) in imports for r in records),
   newly_measured_runs=sum((r['objective'],r['name']) not in imports for r in records),
   case_bounds=[dict(objective=r['objective'],name=r['name'],status=r['status'],proven=r['proven'],seconds=r['time'],
     cost=r['solve'].get('cost'),lb=r['solve'].get('lb'),ub=r['solve'].get('ub')) for r in records],
   submission_passed=False,scope=locked['scope'])
  extended.save(root/'full_audit.json',report);extended.audit.write_csv(root/'summary.csv',report['summary'])
except BaseException as error:
 extended.save(root/'failure.json',dict(error=str(error) or type(error).__name__));raise
