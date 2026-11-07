from pathlib import Path
import json,os,sys
sys.path.insert(0,'quick_scripts/analyze')
import targeted_order_cycles as t
import extended_timeout_experiments as e
backend=sys.argv[1];assert backend in ('minisat','cadical')
reference=Path('/home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216')
primary=Path('/home/tuyenkv/projects/master-seeds-v27/maxsattrainscheduling')
trial=primary/'results/aglr/master-seeds-v27-unresolved300'
r=t.audit_saved(trial,reference);assert r['complete'] and r['completed_runs']==4 and not r['errors']
manifest=json.loads((trial/'manifest.json').read_text());assert manifest['objective_filter']==['infsteps180']
build=primary/'results/aglr/master-seeds-v27-build/manifest.json';meta=json.loads(build.read_text());binary=primary/'target/release/ddd'
assert meta['rust_library_tests_passed']>=79 and meta['binary_sha256']==manifest['binary_sha256']==e.focus.sha(binary)
source,_,_=t.load_reference(reference)
cfg=t.experiment_config(source,'order-master-seeds',backend,0)
root=Path('results/aglr')/f'master-backends-v28-{backend}-preflight';root.mkdir(parents=True,exist_ok=True)
e.save(root/'decision.json',dict(preceding_completed_runs=r['completed_runs'],preceding_gains=r['newly_solved'],
 preceding_manifest_sha256=e.focus.sha(trial/'manifest.json'),preceding_report_sha256=e.focus.sha(trial/'order_master_seeds_audit.json'),
 source_build_manifest_sha256=e.focus.sha(build),binary_sha256=e.focus.sha(binary),definition=cfg,
 cpu_affinity=sorted(os.sched_getaffinity(0)),measurement_context='paired-screen',paired_run_id='master-backends-v28',
 reason='Same frozen binary and four rounded-objective cases; only backend differs within the pair. Conflict cap zero is common because the CaDiCaL adapter does not enforce the MiniSAT-specific cap.',
 submission_passed=False))
print(json.dumps(dict(preflight_passed=True,backend=backend)),flush=True)
