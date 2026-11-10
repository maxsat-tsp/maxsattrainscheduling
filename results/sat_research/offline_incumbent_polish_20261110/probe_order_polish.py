from collections import defaultdict,deque
from pathlib import Path
import time,json,sys
sys.path.insert(0,'quick_scripts/analyze')
import run_sat_bound_search as search
c=search.ex.common

def polish(name,obj,solution,cost,seconds=5):
 search.validate_schedule(name,obj,solution,cost);started=time.monotonic();ts=c.parse_txt_instance(name);offs=[];lb=[];chain=[];groups=defaultdict(list)
 for ti,t in enumerate(ts):
  o=len(lb);offs.append(o);lb.extend([v['earliest'] for v in t]+[t[-1]['earliest']+t[-1]['travel']])
  for vi,v in enumerate(t):
   chain.append((o+vi,o+vi+1,v['travel']))
   if v['resource'] is not None:groups[v['resource']].append((solution[ti][vi],solution[ti][vi+1],ti,vi))
 orders=[[(offs[ti]+vi,offs[ti]+vi+1) for _,_,ti,vi in sorted(g)] for _,g in sorted(groups.items())]
 def evaluate():
  adj=[[] for _ in lb];ind=[0]*len(lb)
  for u,v,w in chain:
   adj[u].append((v,w));ind[v]+=1
  for group in orders:
   for a,b in zip(group,group[1:]):adj[a[1]].append((b[0],0));ind[b[0]]+=1
  values=list(lb);q=deque(i for i,d in enumerate(ind) if not d);count=0
  while q:
   u=q.popleft();count+=1
   for v,w in adj[u]:
    values[v]=max(values[v],values[u]+w);ind[v]-=1
    if not ind[v]:q.append(v)
  if count<len(lb):return None
  sol=[values[o:o+len(ts[ti])+1] for ti,o in enumerate(offs)]
  primary=sum(c.delay_cost(obj,sol[ti][vi]-v['aimed']) for ti,t in enumerate(ts) for vi,v in enumerate(t) if v['aimed'] is not None)
  secondary=sum(c.delay_cost('cont',sol[ti][vi]-v['aimed']) for ti,t in enumerate(ts) for vi,v in enumerate(t) if v['aimed'] is not None)
  return (primary,secondary),sol
 best=evaluate()
 if best is None:return None
 initial=best[0];moves=[];checks=0
 for it in range(100):
  nextbest=best;move=None
  for gi,g in enumerate(orders):
   for j in range(len(g)-1):
    if time.monotonic()-started>seconds:break
    g[j],g[j+1]=g[j+1],g[j]
    candidate=evaluate();checks+=1
    g[j],g[j+1]=g[j+1],g[j]
    if candidate is not None and candidate[0]<nextbest[0]:nextbest=candidate;move=gi,j
   if time.monotonic()-started>seconds:break
  if move is None:break
  gi,j=move;orders[gi][j],orders[gi][j+1]=orders[gi][j+1],orders[gi][j];best=nextbest;moves.append(dict(resource=gi,adjacent=j,cost=best[0]))
  if time.monotonic()-started>seconds:break
 search.validate_schedule(name,obj,best[1],best[0][0]);assert best[0][0]<=cost
 return dict(objective=obj,name=name,before=cost,retimed=initial,after=best[0],moves=moves,checks=checks,seconds=time.monotonic()-started,solution=best[1])

