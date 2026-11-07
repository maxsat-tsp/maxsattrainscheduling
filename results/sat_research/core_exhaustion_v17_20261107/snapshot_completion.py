from pathlib import Path
import hashlib,io,json,sys,tarfile
root,output=map(Path,sys.argv[1:]);assert not output.exists()
report_name='full_audit.json' if (root/'full_audit.json').exists() else 'hardset_audit.json'
files={name:(root/name).read_bytes() for name in ('manifest.json',report_name,'summary.csv')}
manifest=json.loads(files['manifest.json']);report=json.loads(files[report_name])
expected={(o,n) for o,names in manifest['instances_by_objective'].items() for n in names}
seen={(r['objective'],r['name']) for r in report['case_bounds']}
assert report['complete'] and not report['errors']
assert seen==expected and len(seen)==len(report['case_bounds'])==report['completed_runs']==report['expected_runs']
for objective,name in sorted(expected):
 for path in sorted((root/'cases'/objective/name).rglob('*')):
  assert not path.is_symlink()
  if path.is_file():files[path.relative_to(root).as_posix()]=path.read_bytes()
files['snapshot.json']=(json.dumps(dict(schema='core-completion-snapshot-v1',report=report_name,completed_runs=len(seen),
 file_sha256={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}),indent=2)+'\n').encode()
with output.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as archive:
 for name,content in files.items():
  entry=tarfile.TarInfo(name);entry.size=len(content);archive.addfile(entry,io.BytesIO(content))
print(json.dumps(dict(completed_runs=len(seen),sha256=hashlib.sha256(output.read_bytes()).hexdigest())))
