from collections import defaultdict, deque
from pathlib import Path
import sys,json,time
sys.path.insert(0,'quick_scripts/analyze')
import run_sat_bound_search as search
common=search.ex.common

def tighten(name,objective,solution,cost):
 search.validate_schedule(name,objective,solution,cost)
 trains=common.parse_txt_instance(name);offset=[];old=[];values=[];edges=[];groups=defaultdict(list)
 for ti,train in enumerate(trains):
  off=len(values);offset.append(off);old.extend(solution[ti]);values.extend([v['earliest'] for v in train]+[train[-1]['earliest']+train[-1]['travel']])
  for vi,v in enumerate(train):
   edges.append((off+vi,off+vi+1,v['travel']))
   if v['resource'] is not None:groups[v['resource']].append((solution[ti][vi],solution[ti][vi+1],ti,vi))
 for group in groups.values():
  group.sort()
  for a,b in zip(group,group[1:]):
   assert a[1]<=b[0]
   edges.append((offset[a[2]]+a[3]+1,offset[b[2]]+b[3],0))
 adj=[[] for _ in values]
 for u,v,w in edges:
  assert old[u]+w<=old[v]
  adj[u].append((v,w))
 q=deque(range(len(values)));queued=set(q)
 while q:
  u=q.popleft();queued.remove(u)
  for v,w in adj[u]:
   nextval=values[u]+w
   if values[v]<nextval:
    assert nextval<=old[v]
    values[v]=nextval
    if v not in queued:q.append(v);queued.add(v)
 sol=[values[o:o+len(trains[ti])+1] for ti,o in enumerate(offset)]
 newcost=sum(common.delay_cost(objective,sol[ti][vi]-v['aimed']) for ti,t in enumerate(trains) for vi,v in enumerate(t) if v['aimed'] is not None)
 search.validate_schedule(name,objective,sol,newcost)
 assert newcost<=cost
 return newcost,sol

rows=[]
for label,root in [('V42',Path('/tmp/v42-complete')),('V43',Path('/tmp/v43-progress'))]:
 for p in sorted((root/'hard/cases').rglob('result.json')):
  d=json.loads(p.read_text());name=p.parent.parent.name;o=d['objective']
  candidates=[('final',d['solution'],d['cost'])]+[('SAT-'+str(i),q['solution'],q['cost']) for i,q in enumerate(d['queries']) if q['outcome']=='sat']
  for c,sol,cost in candidates:
   now=time.monotonic();new,news=tighten(name,o,sol,cost);elapsed=time.monotonic()-now
   rows.append(dict(run=label,objective=o,name=name,stage=c,before=cost,after=new,gain=cost-new,seconds=elapsed,solution=news))
Path('/tmp/v43-slack-probe.json').write_text(json.dumps(dict(scope='offline fixed-order retiming of checked SAT witnesses only; not an optimizer run or coverage claim',rows=rows),indent=2)+'\n')
print(json.dumps([{k:v for k,v in r.items() if k!='solution'} for r in rows],indent=2))
