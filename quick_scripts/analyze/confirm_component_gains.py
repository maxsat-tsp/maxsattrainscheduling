#!/usr/bin/env python3
"""Confirm gains of one audited component, then regress its previously solved pairs."""
from __future__ import annotations
import argparse,json,os,subprocess,time
from pathlib import Path
from types import SimpleNamespace
import extended_timeout_experiments as extended
import targeted_order_cycles as trial

def reference_costs(root):
    manifest,_,_=trial.load_reference(root)
    saved=json.loads((root/'full_audit.json').read_text())
    return manifest,[dict(objective=r['objective'],name=r['name'],cost=r['cost']) for r in saved['case_bounds'] if r['proven']]

def plan_for(source,report,reference):
    if not report.get('complete') or not report.get('audit_passed') or report.get('errors'):
        raise ValueError('component trial must be complete and independently audited')
    gains=report['newly_solved']
    if len({(r['objective'],r['name']) for r in gains})!=len(gains):raise ValueError('duplicate gains')
    for gain in gains:
        if gain['objective'] not in source['instances_by_objective'] or gain['name'] not in source['instances_by_objective'][gain['objective']]:
            raise ValueError('gain is outside the locked unresolved selection')
    _,solved=reference_costs(reference)
    if source.get('objective_filter') is not None:
        trial.filtered_selection(source['instances_by_objective'],source['objective_filter'])
        solved=[r for r in solved if r['objective'] in source['objective_filter']]
    confirmations=[dict(stage='confirmation',repeat=r,objective=g['objective'],name=g['name'],cost=g['cost'])
                   for r in [1,2,3] for g in gains]
    regressions=[dict(stage='regression',repeat=0,**r) for r in solved]
    return gains,confirmations,regressions

def run(args):
    audited=trial.audit_saved(args.trial,args.reference)
    source=json.loads((args.trial/'manifest.json').read_text())
    if extended.focus.sha(args.binary)!=source['binary_sha256']:raise ValueError('confirmation binary changed')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=extended.REPO).strip():
        raise ValueError('commit the runner before confirmation')
    gains,confirmations,regressions=plan_for(source,audited,args.reference)
    root=args.results;root.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema='component-gain-followup-v1',runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        solver_source_commit=source['solver_source_commit'],binary_sha256=source['binary_sha256'],definition=source['definition'],
        source_manifest_sha256=extended.focus.sha(args.trial/'manifest.json'),
        source_report_sha256=extended.focus.sha(args.trial/trial.report_name(source.get('component','order-cycles'))),
        reference_manifest_sha256=extended.focus.sha(args.reference/'manifest.json'),reference_report_sha256=extended.focus.sha(args.reference/'full_audit.json'),
        dataset_sha256=extended.focus.dataset_hash(),timeout_seconds=source['timeout_seconds'],ram_kb=source['ram_kb'],
        cpu_affinity=sorted(os.sched_getaffinity(0)),repeats=3,selected_gains=gains,confirmation_plan=confirmations,regression_plan=regressions,
        script_sha256=extended.focus.sha(Path(__file__)),submission_passed=False)
    if source.get('objective_filter') is not None:manifest['objective_filter']=source['objective_filter']
    if (root/'manifest.json').exists() and json.loads((root/'manifest.json').read_text())!=manifest:raise ValueError('followup resume would change its source or selection')
    extended.save(root/'manifest.json',manifest)
    runtime=SimpleNamespace(timeout=source['timeout_seconds'],ram_kb=source['ram_kb'],binary=args.binary,method_definitions={'Component-followup':source['definition']})
    deadline=time.monotonic()+args.round_seconds;records=[]
    for stage,items in [('confirmation',confirmations),('regression',regressions if gains else [])]:
        if stage=='regression' and (len(records)!=len(confirmations) or not all(r['retained'] for r in records)):break
        for task in items:
            case=root/'cases'/stage/f'repeat-{task["repeat"]}'/task['objective']/task['name']
            path=case/f'{task["objective"]}.json'
            if not path.exists():
                if deadline-time.monotonic()<runtime.timeout+90:break
                print(f'{stage} {task["repeat"]}: {task["objective"]}/{task["name"]}',flush=True)
                extended.run_case('Component-followup',task['objective'],task['name'],runtime,case)
            result=extended.assess_case(case,'Component-followup',task['objective'],task['name'],runtime.timeout,source['definition'])
            if result['errors'] or result['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(result['errors']))
            if result['proven'] and not extended.common.same_number(result['solve']['cost'],task['cost']):raise ValueError('proved optimum changed during followup')
            records.append(dict(task,status=result['status'],proven=result['proven'],retained=result['proven'],seconds=result['time'],
                actual_cost=result['solve'].get('cost'),lb=result['solve'].get('lb'),ub=result['solve'].get('ub'),sha256=extended.focus.sha(path)))
            report=report_for(manifest,records);extended.save(root/'followup_audit.json',report)
        if sum(r['stage']==stage for r in records)!=len(items):break
    report=report_for(manifest,records);extended.save(root/'followup_audit.json',report)
    print(json.dumps(report,indent=2))

def report_for(manifest,records):
    confirmed=[r for r in records if r['stage']=='confirmation'];regressed=[r for r in records if r['stage']=='regression']
    expected=len(manifest['confirmation_plan'])+(len(manifest['regression_plan']) if manifest['selected_gains'] else 0)
    confirmation_complete=len(confirmed)==len(manifest['confirmation_plan'])
    gains_confirmed=bool(manifest['selected_gains']) and confirmation_complete and all(r['retained'] for r in confirmed)
    regression_complete=bool(manifest['selected_gains']) and len(regressed)==len(manifest['regression_plan'])
    report=dict(schema=manifest['schema'],selected_gains=manifest['selected_gains'],expected_runs=expected,completed_runs=len(records),
        complete=len(records)==expected,confirmation_complete=confirmation_complete,
        confirmed=gains_confirmed,
        regression_complete=regression_complete,regression_passed=gains_confirmed and regression_complete and all(r['retained'] for r in regressed),
        lost=[dict(objective=r['objective'],name=r['name']) for r in regressed if not r['retained']],
        confirmation_failures=[dict(repeat=r['repeat'],objective=r['objective'],name=r['name']) for r in confirmed if not r['retained']],
        cases=records,errors=[],submission_passed=False,scope='gain confirmations and previously solved-pair regression only; full-table construction and independent audit remain separate')
    if manifest.get('objective_filter') is not None:
        report.update(objective_filter=manifest['objective_filter'],full_reference_regression=False,
            scope='objective-filtered confirmations and regression only; excluded objectives require separate full-table evaluation')
    return report

def audit_saved(root,source_root,reference):
    audited=trial.audit_saved(source_root,reference);source=json.loads((source_root/'manifest.json').read_text())
    manifest=json.loads((root/'manifest.json').read_text());saved=json.loads((root/'followup_audit.json').read_text())
    gains,confirmations,regressions=plan_for(source,audited,reference)
    if (root/'failure.json').exists():raise ValueError('followup retains a recorded failure')
    if manifest.get('objective_filter')!=source.get('objective_filter'):raise ValueError('followup objective scope changed')
    for key in ['solver_source_commit','binary_sha256','definition','timeout_seconds','ram_kb','dataset_sha256']:
        if manifest[key]!=source[key]:raise ValueError('followup configuration changed')
    for field,path in [('source_manifest_sha256',source_root/'manifest.json'),
        ('source_report_sha256',source_root/trial.report_name(source.get('component','order-cycles'))),
        ('reference_manifest_sha256',reference/'manifest.json'),('reference_report_sha256',reference/'full_audit.json')]:
        if manifest[field]!=extended.focus.sha(path):raise ValueError('followup reference hash changed')
    if manifest['selected_gains']!=gains or manifest['confirmation_plan']!=confirmations or manifest['regression_plan']!=regressions:
        raise ValueError('followup plan differs from audited source cases')
    expected=confirmations+(regressions if gains else []);count=saved['completed_runs']
    if type(count) is not int or not 0<=count<=len(expected):raise ValueError('invalid followup count')
    records=[]
    for task in expected[:count]:
        if task['stage']=='regression' and not all(r['retained'] for r in records if r['stage']=='confirmation'):
            raise ValueError('regression began before all gains reproduced')
        case=root/'cases'/task['stage']/f'repeat-{task["repeat"]}'/task['objective']/task['name'];path=case/f'{task["objective"]}.json'
        provenance=dict(l.split('=',1) for l in (case/'logs/manifest.txt').read_text().splitlines() if '=' in l)
        locked=dict(binary_sha256=manifest['binary_sha256'],git_commit=manifest['runner_commit'],git_dirty='0',solver=manifest['definition']['solver'],
            objective=task['objective'],selected_instances=task['name'],selected_instance_count='1',
            instance_timeout_seconds=str(manifest['timeout_seconds']),ram_limit_kb=str(manifest['ram_kb']))
        locked.update({'maxsatddd_'+k:v for k,v in manifest['definition'].items() if k not in ('solver','kind')})
        if any(provenance.get(k)!=v for k,v in locked.items()):raise ValueError('followup case provenance changed')
        result=extended.assess_case(case,'Component-followup',task['objective'],task['name'],manifest['timeout_seconds'],manifest['definition'])
        if result['errors'] or result['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(result['errors']))
        if result['proven'] and not extended.common.same_number(result['solve']['cost'],task['cost']):raise ValueError('followup optimum differs')
        records.append(dict(task,status=result['status'],proven=result['proven'],retained=result['proven'],seconds=result['time'],
            actual_cost=result['solve'].get('cost'),lb=result['solve'].get('lb'),ub=result['solve'].get('ub'),sha256=extended.focus.sha(path)))
    rebuilt=report_for(manifest,records)
    if not extended.reports_match(rebuilt,saved):raise ValueError('followup report differs from raw results')
    return dict(rebuilt,audit_passed=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--binary',type=Path);p.add_argument('--results',type=Path,required=True);p.add_argument('--round-seconds',type=int,default=14000)
    p.add_argument('--audit',action='store_true')
    args=p.parse_args()
    if not 0<args.round_seconds<=21600:p.error('round limit must be 1..21600 seconds')
    if args.audit:print(json.dumps(audit_saved(args.results,args.trial,args.reference),indent=2));return
    if args.binary is None:p.error('run requires --binary')
    try:run(args)
    except BaseException as error:
        if args.results.exists():extended.save(args.results/'failure.json',dict(error=str(error) or type(error).__name__))
        raise

if __name__=='__main__':main()
