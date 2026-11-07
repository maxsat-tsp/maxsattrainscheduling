from pathlib import Path
import argparse,hashlib,json,statistics,sys

parser=argparse.ArgumentParser()
parser.add_argument('snapshot',type=Path)
parser.add_argument('--reference',type=Path,required=True)
parser.add_argument('--profiles',type=Path,nargs='+',required=True)
args=parser.parse_args()
sys.path.insert(0,str(Path.cwd()/'quick_scripts/analyze'))
import extended_timeout_experiments as extended
from confirm_targeted_core_minimization import choose

root=args.snapshot
index=json.loads((root/'snapshot.json').read_text())
assert index['schema']=='core-confirmation-snapshot-v1'
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
assert actual==set(index['file_sha256'])|{'snapshot.json'}
for name,digest in index['file_sha256'].items():
 path=(root/name).resolve()
 assert path.is_relative_to(root.resolve()) and not (root/name).is_symlink()
 assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
manifest=json.loads((root/'manifest.json').read_text())
saved=json.loads((root/'confirmation_audit.json').read_text())
assert manifest['schema']==saved['schema']=='targeted-core-confirmation-v1'
assert manifest['repeats']==3 and not manifest['submission_passed'] and not saved['submission_passed']
assert manifest['dataset_sha256']==extended.focus.dataset_hash()
winner,prior=choose(args.profiles,args.reference)
selected=json.loads((winner/'manifest.json').read_text())
assert manifest['definition']==selected['definition']
assert manifest['binary_sha256']==selected['binary_sha256']
assert manifest['solver_source_commit']==selected['solver_source_commit']
assert manifest['selected_gains']==prior['newly_solved']
local={(extended.focus.sha(p/'manifest.json'),extended.focus.sha(p/'core_minimization_audit.json')) for p in args.profiles}
recorded={(p['manifest_sha256'],p['report_sha256']) for p in manifest['trials']}
assert local==recorded and len(local)==len(args.profiles)==len(manifest['trials'])
winner_digest=next(p['manifest_sha256'] for p in manifest['trials'] if p['path']==manifest['selected_trial'])
assert winner_digest==extended.focus.sha(winner/'manifest.json')
expected={(r,g['objective'],g['name']):g['cost'] for r in (1,2,3) for g in prior['newly_solved']}
seen=set();records=[]
for item in saved['cases']:
 key=(item['repeat'],item['objective'],item['name'])
 assert key in expected and key not in seen
 seen.add(key)
 case=root/'cases'/f'repeat-{key[0]}'/key[1]/key[2]
 provenance=dict(line.split('=',1) for line in (case/'logs/manifest.txt').read_text().splitlines() if '=' in line)
 assert provenance['binary_sha256']==manifest['binary_sha256']
 assert provenance['git_commit']==manifest['runner_commit'] and provenance['git_dirty']=='0'
 assert provenance['selected_instances']==key[2] and provenance['objective']==key[1]
 assert provenance['instance_timeout_seconds']==str(manifest['timeout_seconds'])
 assert provenance['ram_limit_kb']==str(manifest['ram_kb'])
 for field,value in manifest['definition'].items():
  if field not in ('solver','kind'):assert provenance['maxsatddd_'+field]==value
 result=extended.assess_case(case,'Core-confirm',key[1],key[2],manifest['timeout_seconds'],manifest['definition'])
 assert not result['errors'] and result['proven'],result['errors']
 assert extended.common.same_number(result['solve']['cost'],expected[key])
 assert item['proven'] and item['reproduced']
 assert extended.common.same_number(item['cost'],expected[key]) and extended.common.same_number(item['expected_cost'],expected[key])
 assert abs(result['time']-item['seconds'])<1e-10
 records.append(dict(item,lb=result['solve']['lb'],ub=result['solve']['ub'],raw_sha256=extended.focus.sha(case/f'{key[1]}.json')))
assert seen==set(expected) and len(records)==saved['completed_runs']==saved['expected_runs']==index['completed_runs']
assert saved['complete'] and saved['confirmed'] and not saved['errors'] and index['complete']
summary=[]
for gain in prior['newly_solved']:
 times=[r['seconds'] for r in records if r['objective']==gain['objective'] and r['name']==gain['name']]
 summary.append(dict(objective=gain['objective'],name=gain['name'],cost=gain['cost'],repeats=len(times),
                     median_seconds=statistics.median(times),minimum_seconds=min(times),maximum_seconds=max(times)))
print(json.dumps(dict(schema='independent-v16-confirmation-audit-v1',audit_passed=True,complete=True,
    confirmed=True,completed_runs=len(records),expected_runs=len(expected),submission_passed=False,
    scope='six repeated gains only; no full-dataset or regression claim',summary=summary,cases=records),indent=2))
