import sys,csv
sys.path.insert(0,'quick_scripts/analyze')
import extended_timeout_experiments as e
rows=[]
for name in ['origA8','trackA11','trackA12','stationA11','stationA12']:
 trains=e.common.parse_txt_instance(name)
 base=[]
 for route in trains:
  ts=[]
  for i,v in enumerate(route):ts.append(max(v['earliest'],ts[-1]+route[i-1]['travel'] if i else v['earliest']))
  base.append(ts)
 pairs=[]
 for ti,r in enumerate(trains):
  for tj in range(ti+1,len(trains)):
   for vi,v in enumerate(r):
    for vj,u in enumerate(trains[tj]):
     if v['resource'] is not None and v['resource']==u['resource']:pairs.append(((ti,vi),(tj,vj)))
 for objective in e.audit.OBJECTIVES:
  clauses=0;points=set();costly_pairs=0
  for a,b in pairs:
   costly=0
   for first,second in [(a,b),(b,a)]:
    ti,vi=first;tj,vj=second
    bound=base[ti][vi+1] if vi+1<len(trains[ti]) else base[ti][vi]+trains[ti][vi]['travel']
    branch=False
    for k in range(vj,len(trains[tj])):
     v=trains[tj][k];bound=max(bound,base[tj][k])
     if v['aimed'] is not None:
      cost=e.common.delay_cost(objective,bound-v['aimed']);initial=e.common.delay_cost(objective,base[tj][k]-v['aimed'])
      if cost>initial:
       clauses+=1;points.add((tj,k,cost));branch=True
     bound+=v['travel']
    costly+=int(branch)
   costly_pairs+=int(costly==2)
  rows.append(dict(instance=name,objective=objective,resource_order_pairs=len(pairs),initial_proved_clauses=clauses,unique_cost_levels=len(points),pairs_with_cost_on_both_directions=costly_pairs))
with open('/tmp/master_seed_counts.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(open('/tmp/master_seed_counts.csv').read())
