from pathlib import Path
import hashlib,io,json,sys,tarfile

root,output=map(Path,sys.argv[1:]);assert not output.exists()
files={name:(root/name).read_bytes() for name in ('manifest.json','regression_audit.json')}
manifest=json.loads(files['manifest.json']);report=json.loads(files['regression_audit.json'])
assert report['complete'] and len(report['cases'])==report['completed_runs']==report['expected_runs']
expected={(p['objective'],p['name']) for p in manifest['selection']};seen=set()
for item in report['cases']:
 key=item['objective'],item['name'];assert key in expected and key not in seen;seen.add(key)
 for path in sorted((root/'cases'/key[0]/key[1]).rglob('*')):
  assert not path.is_symlink()
  if path.is_file():files[path.relative_to(root).as_posix()]=path.read_bytes()
assert seen==expected
files['snapshot.json']=(json.dumps(dict(schema='core-regression-snapshot-v1',complete=True,
 completed_runs=len(seen),file_sha256={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}),indent=2)+'\n').encode()
with output.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as archive:
 for name,content in files.items():
  entry=tarfile.TarInfo(name);entry.size=len(content);archive.addfile(entry,io.BytesIO(content))
print(json.dumps(dict(completed_runs=len(seen),sha256=hashlib.sha256(output.read_bytes()).hexdigest())))
