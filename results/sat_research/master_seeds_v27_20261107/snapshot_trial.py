from pathlib import Path
import hashlib,io,json,sys,tarfile
root,output=map(Path,sys.argv[1:]);assert not output.exists()
manifest=(root/'manifest.json').read_bytes();m=json.loads(manifest)
report_name={'targeted-initial-cost-v1':'initial_cost_audit.json','targeted-order-cycles-v1':'order_cycles_audit.json','targeted-order-paths-v1':'order_paths_audit.json','targeted-order-paths-full-v1':'order_paths_full_audit.json','targeted-order-master-v1':'order_master_audit.json','targeted-order-master-levels-v1':'order_master_levels_audit.json','targeted-order-master-levels-full-v1':'order_master_levels_full_audit.json','targeted-order-master-batch-v1':'order_master_batch_audit.json','targeted-order-master-seeds-v1':'order_master_seeds_audit.json'}[m['schema']]
report=(root/report_name).read_bytes();r=json.loads(report)
expected=[(o,n) for o,names in m['instances_by_objective'].items() for n in names]
assert type(r['completed_runs']) is int and 0<=r['completed_runs']<=len(expected)
assert r['expected_runs']==len(expected) and r['complete']==(len(expected)==r['completed_runs'])
files={'manifest.json':manifest,report_name:report,'build_manifest.json':(root/'build_manifest.json').read_bytes()}
for o,n in expected[:r['completed_runs']]:
 for path in sorted((root/'cases'/o/n).rglob('*')):
  assert not path.is_symlink()
  if path.is_file():files[path.relative_to(root).as_posix()]=path.read_bytes()
 for_required=f'cases/{o}/{n}/{o}.json'
 assert for_required in files
if (root/'failure.json').exists():files['failure.json']=(root/'failure.json').read_bytes()
metadata=dict(schema='targeted-component-snapshot-v1',report=report_name,completed_runs=r['completed_runs'],complete=r['complete'],
 file_sha256={name:hashlib.sha256(data).hexdigest() for name,data in files.items()})
files['snapshot.json']=(json.dumps(metadata,indent=2)+'\n').encode()
with output.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as archive:
 for name,data in files.items():
  entry=tarfile.TarInfo(name);entry.size=len(data);archive.addfile(entry,io.BytesIO(data))
print(json.dumps(dict(completed_runs=r['completed_runs'],sha256=hashlib.sha256(output.read_bytes()).hexdigest())))
