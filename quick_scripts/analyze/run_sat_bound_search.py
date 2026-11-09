#!/usr/bin/env python3
"""Run/audit autonomous SAT threshold search. Reference costs never reach the solver."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import time

import diagnose_optimal_bounds as diagnostic
import extended_timeout_experiments as ex
import targeted_order_cycles as trial
import bound_quality


def initial_lower(name,objective):
    total=0
    for train in ex.common.parse_txt_instance(name):
        following=None
        for visit in train:
            earliest=visit['earliest'] if following is None else max(visit['earliest'],following)
            if visit['aimed'] is not None:total+=ex.common.delay_cost(objective,earliest-visit['aimed'])
            following=earliest+visit['travel']
    return total


def validate_schedule(name,objective,solution,cost):
    if type(cost) is not int or cost<0:raise ValueError('invalid schedule cost')
    errors=ex.common.independently_verify_solution(name,objective,dict(solution=solution,cost=cost))
    if errors:raise ValueError(str(errors))


def query_target(lower,upper,policy='bisect'):
    if policy not in ('bisect','close-upper'):raise ValueError('unsupported threshold policy')
    if not 0<=lower<upper:raise ValueError('query interval is already closed or invalid')
    return upper-1 if policy=='close-upper' and 100*(upper-lower)<=5*max(1,upper) else lower+(upper-lower-1)//2


def check_result(result,name,objective,cutoff,known_optimum=None):
    policy=result.get('threshold_policy','bisect')
    solver={'bisect':'SAT-Bisect-Restart','close-upper':'SAT-CloseUpper-Restart'}.get(policy)
    if (solver is None or result.get('schema')!='sat-bound-search-v1' or result.get('solver_name')!=solver
            or result.get('uses_optimum_oracle') is not False or result.get('objective')!=objective):
        raise ValueError('wrong optimizer or oracle provenance')
    if result.get('maxsat_backend')!='minisat' or 'MiniSAT' not in result.get('maxsat_backend_signature',''):
        raise ValueError('wrong SAT backend')
    if result.get('timeout_seconds')!=cutoff:raise ValueError('wrong cutoff')
    seconds=result.get('total_time')
    if not isinstance(seconds,(float,int)) or not math.isfinite(seconds) or seconds<0:
        raise ValueError('invalid elapsed time')
    lower=initial_lower(name,objective);upper=result.get('initial_ub')
    if result.get('initial_lb')!=lower:raise ValueError('initial LB is not the input-only chain bound')
    validate_schedule(name,objective,result.get('initial_solution'),upper)
    if lower>upper:raise ValueError('initial bounds cross')
    queries=result.get('queries');unknown=False;spent=0.0;last_remaining=float('inf');trace=[]
    if not isinstance(queries,list):raise ValueError('missing query ledger')
    for q in queries:
        if unknown:raise ValueError('continued after UNKNOWN')
        if lower>=upper:raise ValueError('queried after the gap closed')
        target=query_target(lower,upper,policy)
        if (q.get('lower_before'),q.get('upper_before'),q.get('target'))!=(lower,upper,target):
            raise ValueError('threshold or pre-query interval changed')
        remaining=q.get('remaining_seconds');elapsed=q.get('seconds')
        if (not isinstance(remaining,(int,float)) or not math.isfinite(remaining) or remaining<=0
                or remaining>cutoff-spent+0.05 or remaining>=last_remaining):
            raise ValueError('per-instance time budget was reset or invalid')
        if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<0:
            raise ValueError('invalid query time')
        spent+=elapsed;last_remaining=remaining
        if q.get('native_budgeted_calls')!=0:raise ValueError('threshold decision used a core conflict budget')
        evidence=q.get('threshold_evidence',{})
        required=dict(threshold_target=target,maxsat_objective_bound=True,
            maxsat_resource_orders=True,maxsat_order_transitivity=True,maxsat_sparse_costs=False)
        if any(evidence.get(k)!=v for k,v in required.items()):raise ValueError('wrong fixed-bound query definition')
        if any(k.startswith('diagnostic_') for k in evidence):raise ValueError('diagnostic oracle metadata leaked into optimizer')
        answer=q.get('outcome')
        if answer=='sat':
            cost=q.get('cost');validate_schedule(name,objective,q.get('solution'),cost)
            if not lower<=cost<=target:raise ValueError('SAT schedule does not fit its threshold')
            if evidence.get('threshold_outcome')!='sat':raise ValueError('SAT outcome missing')
            upper=cost
        elif answer=='unsat':
            if evidence.get('threshold_outcome')!='unsat' or q.get('cost') is not None or q.get('solution') is not None:
                raise ValueError('UNSAT evidence is invalid')
            if known_optimum is not None and target>=known_optimum:
                raise ValueError('UNSAT contradicts an independently proved reference optimum')
            lower=target+1
        elif answer=='unknown':
            if q.get('cost') is not None or q.get('solution') is not None:
                raise ValueError('UNKNOWN cannot update an incumbent')
            unknown=True
        else:raise ValueError('unsupported decision result')
        if answer!='unknown' and evidence.get('maxsat_core_literals')!=0:
            raise ValueError('threshold decision entered RC2 core optimization')
        trace.append(dict(query=q,lb=lower,ub=upper))
    if spent>seconds+0.1:raise ValueError('query times exceed the global elapsed time')
    validate_schedule(name,objective,result.get('solution'),result.get('cost'))
    if (result.get('lb'),result.get('ub'),result.get('cost'))!=(lower,upper,upper):
        raise ValueError('reported final bounds do not replay from the proofs')
    if known_optimum is not None and not lower<=known_optimum<=upper:
        raise ValueError('bounds contradict the reference optimum')
    status=result.get('status')
    if status=='ok':
        if lower!=upper or unknown or seconds>cutoff:raise ValueError('unproved or late optimum')
    elif status=='timeout':
        if seconds<cutoff-0.5:raise ValueError('premature timeout')
    else:raise ValueError('fatal optimizer status: '+str(status))
    return dict(objective=objective,name=name,status=status,proven=status=='ok',seconds=seconds,
        lb=lower,ub=upper,cost=upper,queries=len(queries),sat_calls=sum(q['native_sat_calls'] for q in queries),threshold_policy=policy),trace


def reference_costs(reference,diagnostic_root):
    costs={(r['objective'],r['name']):r['cost'] for r in
        json.load(open(reference/'full_audit.json'))['case_bounds'] if r['proven']}
    if diagnostic_root is not None:
        report=diagnostic.audit(diagnostic_root/'trial',reference)
        if not report['complete']:raise ValueError('V39 is not complete')
        for row in json.load(open(diagnostic_root/'trial/manifest.json'))['oracles']:
            costs[row['objective'],row['name']]=row['optimum']
    return costs


def tasks_for(reference):
    _,selection,_=trial.load_reference(reference)
    # The same method is run on every unresolved pair. Promising cont cases
    # come first so a controlled round can expose a gain early.
    pairs=[(o,n) for o in ('cont','infsteps180','finsteps123') for n in selection[o]]
    priority={('cont','origA8'):0,('cont','stationA1'):1,('cont','stationA2'):2}
    return sorted(pairs,key=lambda p:(priority.get(p,3),pairs.index(p)))


def hard_tasks(reference,extras=()):
    existing=tasks_for(reference);extras=[tuple(p) for p in extras]
    if len(extras)!=len(set(extras)) or any(p in existing or p[0] not in ex.audit.OBJECTIVES or p[1] not in ex.common.EXPECTED_NAMES for p in extras):
        raise ValueError('extra cases must be distinct supported pairs outside the original hard set')
    return extras+existing


def audit(root,reference,diagnostic_root=None):
    manifest=json.load(open(root/'manifest.json'))
    if manifest.get('schema')!='sat-bound-search-campaign-v1' or manifest.get('uses_optimum_oracle') is not False:
        raise ValueError('invalid campaign definition or oracle provenance')
    if manifest['dataset_sha256']!=ex.focus.dataset_hash():raise ValueError('dataset changed')
    if manifest['reference_manifest_sha256']!=ex.focus.sha(reference/'manifest.json'):
        raise ValueError('reference changed')
    build=json.load(open(root/'build_manifest.json'))
    if (ex.focus.sha(root/'build_manifest.json')!=manifest['build_manifest_sha256']
            or build['git_commit']!=manifest['commit'] or build['binary_sha256']!=manifest['binary_sha256']):
        raise ValueError('build evidence differs from the locked source/binary')
    keys=[(t['objective'],t['name'],t['repeat']) for t in manifest['tasks']]
    if len(keys)!=len(set(keys)):raise ValueError('duplicate campaign tasks')
    if manifest.get('followup') is None and keys!=[(o,n,0) for o,n in hard_tasks(reference,manifest.get('extra_instances',()))]:
        raise ValueError('hard-set selection differs from the unresolved reference pairs')
    known=reference_costs(reference,diagnostic_root);records=[]
    for task in manifest['tasks']:
        objective,name,repeat=task['objective'],task['name'],task['repeat']
        case=root/'cases'/objective/name/str(repeat);result=case/'result.json'
        if not result.exists():continue
        launch=json.load(open(case/'launch.json'))
        expected=dict(binary_sha256=manifest['binary_sha256'],commit=manifest['commit'],
            objective=objective,name=name,repeat=repeat,timeout=manifest['timeout_seconds'],
            ram_kb=manifest['ram_kb'],instance_sha256=ex.focus.sha(ex.common.instance_path(name)))
        if 'threshold_policy' in manifest:expected['threshold_policy']=manifest['threshold_policy']
        if launch!=expected:raise ValueError('launch provenance changed')
        done=json.load(open(case/'completion.json'))
        if done.get('returncode')!=0 or done.get('result_sha256')!=ex.focus.sha(result):
            raise ValueError('failed process or changed result')
        if done.get('trace_sha256')!=ex.focus.sha(case/'result.trace.jsonl'):raise ValueError('trace changed')
        row,trace=check_result(json.load(open(result)),name,objective,manifest['timeout_seconds'],known.get((objective,name)))
        if row['threshold_policy']!=manifest.get('threshold_policy','bisect'):raise ValueError('query policy differs from campaign')
        if trace!=[json.loads(line) for line in (case/'result.trace.jsonl').read_text().splitlines()]:
            raise ValueError('progress trace does not match replayed results')
        records.append(dict(row,repeat=repeat))
    hard=set(tasks_for(reference))
    quality=bound_quality.summarize([dict(r,bounds_verified=True) for r in records if r['repeat']==0])
    return dict(schema='sat-bound-search-audit-v1',audit_passed=True,complete=len(records)==len(manifest['tasks']),
        completed_runs=len(records),expected_runs=len(manifest['tasks']),records=records,
        newly_solved=[r for r in records if r['proven'] and r['repeat']==0 and
                      (r['objective'],r['name']) in hard],
        evaluation_priorities=list(bound_quality.PRIORITIES),bound_quality=quality,
        bound_quality_scope='completed nonrepeat cases in this phase; confirmations are separate',
        submission_passed=False,scope='selected pairs only; full coverage requires regression')


def run_case(binary,cutoff,ram_kb,commit,case,objective,name,repeat,policy=None):
    case.mkdir(parents=True,exist_ok=True)
    if (case/'result.json').exists():return
    if (case/'launch.json').exists():raise ValueError('interrupted case needs review; never overwrite it')
    launch=dict(binary_sha256=ex.focus.sha(binary),commit=commit,objective=objective,
        name=name,repeat=repeat,timeout=cutoff,ram_kb=ram_kb,instance_sha256=ex.focus.sha(ex.common.instance_path(name)))
    if policy is not None:launch['threshold_policy']=policy
    ex.save(case/'launch.json',launch)
    def limits():resource.setrlimit(resource.RLIMIT_AS,(ram_kb*1024,ram_kb*1024))
    command=[str(binary.resolve()),'--instance',str(ex.common.instance_path(name)),
        '--objective',objective,'--timeout',str(cutoff),'--output',str(case/'result.json')]
    if policy is not None:command+=['--threshold-policy',policy]
    with (case/'stdout.log').open('w') as out,(case/'stderr.log').open('w') as err:
        result=subprocess.run(command,cwd=ex.REPO,stdout=out,stderr=err,preexec_fn=limits,timeout=cutoff+45)
    ex.save(case/'completion.json',dict(returncode=result.returncode,
        result_sha256=ex.focus.sha(case/'result.json'),trace_sha256=ex.focus.sha(case/'result.trace.jsonl')))


def run(args):
    source,_,_=trial.load_reference(args.reference)
    tasks=[dict(objective=o,name=n,repeat=0) for o,n in hard_tasks(args.reference,args.extra_instance)]
    if args.followup is not None:
        previous=audit(args.followup,args.reference,args.diagnostic_root)
        if not previous['complete'] or not previous['newly_solved']:raise ValueError('followup needs an audited complete gain')
        tasks=[dict(objective=r['objective'],name=r['name'],repeat=i) for r in previous['newly_solved'] for i in (1,2,3)]
        old=json.load(open(args.reference/'full_audit.json'))['case_bounds']
        measured={(r['objective'],r['name']) for r in previous['records'] if not r['repeat']}
        tasks += [dict(objective=r['objective'],name=r['name'],repeat=0) for r in old if r['proven'] and (r['objective'],r['name']) not in measured]
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():
        raise ValueError('commit the search before running')
    build=json.load(open(args.build_manifest))
    if build['git_commit']!=commit or build['binary_sha256']!=ex.focus.sha(args.binary):raise ValueError('build mismatch')
    root=args.results.resolve();root.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema='sat-bound-search-campaign-v1',commit=commit,binary_sha256=ex.focus.sha(args.binary),
        build_manifest_sha256=ex.focus.sha(args.build_manifest),dataset_sha256=ex.focus.dataset_hash(),
        reference_manifest_sha256=ex.focus.sha(args.reference/'manifest.json'),tasks=tasks,
        timeout_seconds=source['timeout_seconds'],ram_kb=source['ram_kb'],cpu_affinity=sorted(os.sched_getaffinity(0)),
        source_script_sha256=ex.focus.sha(Path(__file__)),followup=str(args.followup) if args.followup else None,
        uses_optimum_oracle=False,threshold_policy=args.threshold_policy,extra_instances=args.extra_instance)
    if (root/'manifest.json').exists() and json.load(open(root/'manifest.json'))!=manifest:raise ValueError('unsafe resume')
    ex.save(root/'manifest.json',manifest);(root/'build_manifest.json').write_bytes(args.build_manifest.read_bytes())
    deadline=time.monotonic()+args.round_seconds
    for task in tasks:
        o,n,i=task['objective'],task['name'],task['repeat'];case=root/'cases'/o/n/str(i)
        if not (case/'result.json').exists() and deadline-time.monotonic()<source['timeout_seconds']+60:break
        print(f'SAT search ({args.threshold_policy}) {o}/{n} repeat={i}',flush=True)
        run_case(args.binary,source['timeout_seconds'],source['ram_kb'],commit,case,o,n,i,args.threshold_policy)
        report=audit(root,args.reference,args.diagnostic_root);ex.save(root/'audit.json',report)
        if args.followup is not None and i>0 and not report['records'][-1]['proven']:
            ex.save(root/'followup_stopped.json',dict(reason='a newly solved pair did not repeat',objective=o,name=n,repeat=i))
            break
    ex.save(root/'audit.json',audit(root,args.reference,args.diagnostic_root))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['run','audit'])
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--results',type=Path,required=True)
    p.add_argument('--diagnostic-root',type=Path);p.add_argument('--binary',type=Path)
    p.add_argument('--build-manifest',type=Path);p.add_argument('--followup',type=Path)
    p.add_argument('--threshold-policy',choices=['bisect','close-upper'],default='bisect')
    p.add_argument('--extra-instance',nargs=2,action='append',default=[],metavar=('OBJECTIVE','NAME'))
    p.add_argument('--round-seconds',type=int,default=18000);a=p.parse_args()
    if a.action=='audit':print(json.dumps(audit(a.results,a.reference,a.diagnostic_root),indent=2));return
    if a.binary is None or a.build_manifest is None or not 0<a.round_seconds<=21600:p.error('missing build or invalid round budget')
    try:run(a)
    except BaseException as error:
        if a.results.exists():ex.save(a.results/'failure.json',dict(error=str(error) or type(error).__name__))
        raise


if __name__=='__main__':main()
