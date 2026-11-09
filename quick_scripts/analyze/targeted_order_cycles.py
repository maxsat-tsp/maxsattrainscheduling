#!/usr/bin/env python3
"""Test one optional MaxSAT component on unresolved full-dataset pairs."""
from __future__ import annotations
import argparse,json,os,subprocess,time
from pathlib import Path
from types import SimpleNamespace
import extended_timeout_experiments as extended

TAG='Order-Cycles'
ASSUMPTION_COMPONENTS = {'assumptions-full': 'full', 'assumptions-geometric': 'geometric'}

def validate_build(build,commit,binary,reuse=False):
    if build['binary_sha256']!=extended.focus.sha(binary):
        raise ValueError('binary differs from its recorded build')
    if build['git_commit']!=commit and not reuse:
        raise ValueError('use --reuse-build to retain a separately recorded solver source')
    return build['git_commit']

def candidate_config(source,component='order-cycles'):
    config=source['definition']
    if config.get('solver')!='maxsat_ddd_ladder_sc' or config.get('resource_orders')!='true':
        raise ValueError('cycle cuts require the existing resource-order candidate')
    if component in ASSUMPTION_COMPONENTS:
        if config.get('assumptions') != 'legacy':
            raise ValueError('assumption contrast requires the legacy V17 reference')
        return dict(config, assumptions=ASSUMPTION_COMPONENTS[component])
    if component == 'core-trim':
        if config.get('core_trim_checks', '0') != '0':
            raise ValueError('reference already enables core trimming')
        if config.get('backend') != 'minisat' or int(config.get('core_minimize_conflicts','0')) <= 0:
            raise ValueError('bounded core trimming requires MiniSAT and a positive conflict budget')
        return dict(config, core_trim_checks='3')
    if component=='order-master-seeds':
        return dict(candidate_config(source,'order-master-batch'),order_master_seed_costs='true')
    if component=='order-master-batch':
        return dict(candidate_config(source,'order-master-levels-full'),order_master_batch_cuts='true')
    if component=='order-master-levels-full':
        if config.get('assumptions')!='legacy':raise ValueError('full-assumption master contrast requires legacy source scheduling')
        return dict(candidate_config(source,'order-master-levels'),assumptions='full')
    if component=='order-master-levels':
        return dict(candidate_config(source,'order-master'),order_master_cost_levels='true')
    if component=='order-paths-full':
        if config.get('assumptions')!='legacy':raise ValueError('full-assumption contrast requires the legacy assumption reference')
        return dict(candidate_config(source,'order-paths'),assumptions='full')
    field={'order-cycles':'order_cycle_cuts','initial-cost':'extract_initial_cost','order-paths':'order_path_cuts','order-master':'order_master'}.get(component)
    if field is None:raise ValueError('unsupported single-component experiment')
    if config.get(field,'false')!='false':
        raise ValueError('reference already enables the component being tested')
    return dict(config,**{field:'true'})

def experiment_config(source,component,backend=None,core_conflicts=None):
    config=candidate_config(source,component)
    if backend is not None:
        if backend not in ('minisat','cadical'):raise ValueError('unsupported comparison backend')
        config['backend']=backend
    if core_conflicts is not None:
        if type(core_conflicts) is not int or not 0<=core_conflicts<=2**31-1:raise ValueError('invalid core conflict budget')
        config['core_minimize_conflicts']=str(core_conflicts)
        if core_conflicts==0:
            # The native core-exhaustion path is intentionally MiniSAT-only
            # and requires a positive conflict budget. Backend contrasts with
            # an unlimited minimization budget must disable that path equally.
            config['core_exhaust_checks']='0'
    if config.get('backend')=='cadical' and int(config.get('core_minimize_checks','0'))>0 and int(config.get('core_minimize_conflicts','0'))!=0:
        raise ValueError('the conflict cap is MiniSAT-specific; explicitly use a common zero (unlimited) cap')
    return config

def measurement_context(mode,paired_run_id):
    if mode not in ('serial','paired-screen'):raise ValueError('unsupported measurement context')
    if mode=='paired-screen':
        if not isinstance(paired_run_id,str) or not paired_run_id.strip():raise ValueError('paired screen needs a shared run ID')
        return dict(measurement_context=mode,paired_run_id=paired_run_id)
    if paired_run_id is not None:raise ValueError('a serial run cannot have a paired run ID')
    return {}

def schema_for(component):
    if component=='core-trim':return 'targeted-core-trim-v1'
    if component in ASSUMPTION_COMPONENTS:return 'targeted-' + component + '-v1'
    if component=='order-master-seeds':return 'targeted-order-master-seeds-v1'
    if component=='order-master-batch':return 'targeted-order-master-batch-v1'
    if component=='order-master-levels-full':return 'targeted-order-master-levels-full-v1'
    if component=='order-master-levels':return 'targeted-order-master-levels-v1'
    return {'order-cycles':'targeted-order-cycles-v1','initial-cost':'targeted-initial-cost-v1','order-paths':'targeted-order-paths-v1','order-paths-full':'targeted-order-paths-full-v1','order-master':'targeted-order-master-v1'}[component]

def report_name(component):
    if component=='core-trim':return 'core_trim_audit.json'
    if component in ASSUMPTION_COMPONENTS:return component.replace('-', '_') + '_audit.json'
    if component=='order-master-seeds':return 'order_master_seeds_audit.json'
    if component=='order-master-batch':return 'order_master_batch_audit.json'
    if component=='order-master-levels-full':return 'order_master_levels_full_audit.json'
    if component=='order-master-levels':return 'order_master_levels_audit.json'
    return {'order-cycles':'order_cycles_audit.json','initial-cost':'initial_cost_audit.json','order-paths':'order_paths_audit.json','order-paths-full':'order_paths_full_audit.json','order-master':'order_master_audit.json'}[component]

def tag_for(component):
    if component=='core-trim':return 'V17-Core-Trim'
    if component in ASSUMPTION_COMPONENTS:return 'V17-' + component
    if component=='order-master-seeds':return 'Order-Master-Seeds'
    if component=='order-master-batch':return 'Order-Master-Batch'
    if component=='order-master-levels-full':return 'Order-Master-Levels-Full'
    if component=='order-master-levels':return 'Order-Master-Levels'
    return {'order-cycles':TAG,'initial-cost':'Initial-Cost','order-paths':'Order-Paths','order-paths-full':'Order-Paths-Full','order-master':'Order-Master'}[component]

def verify_snapshot(root):
    path=root/'snapshot.json'
    if not path.exists():return
    index=json.loads(path.read_text())
    reports={report_name(c) for c in ['order-cycles','initial-cost','order-paths','order-paths-full','order-master','order-master-levels','order-master-levels-full','order-master-batch','order-master-seeds','core-trim', *ASSUMPTION_COMPONENTS]}
    if index.get('schema')!='targeted-component-snapshot-v1' or index.get('report') not in reports:
        raise ValueError('unsupported component snapshot')
    hashes=index['file_sha256']
    if not {'manifest.json','build_manifest.json',index['report']}.issubset(hashes):raise ValueError('snapshot lacks its source or report')
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('snapshot contains a symlink')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=set(hashes)|{'snapshot.json'}:raise ValueError('snapshot has missing or unrecorded artifacts')
    for name,digest in hashes.items():
        target=(root/name).resolve()
        if not target.is_relative_to(root.resolve()) or extended.focus.sha(target)!=digest:
            raise ValueError(f'changed snapshot artifact: {name}')
    report=json.loads((root/index['report']).read_text())
    if any(index[k]!=report[k] for k in ['completed_runs','complete']):raise ValueError('snapshot completeness differs from report')

def load_reference(root):
    manifest=json.loads((root/'manifest.json').read_text());saved=json.loads((root/'full_audit.json').read_text())
    if manifest.get('schema')!='completed-core-full-v1' or not saved.get('complete') or saved.get('errors'):
        raise ValueError('reference must be a completed, clean full-dataset evaluation')
    if manifest['dataset_sha256']!=extended.focus.dataset_hash():raise ValueError('reference dataset changed')
    selection=manifest['instances_by_objective']
    if set(selection)!=set(extended.audit.OBJECTIVES) or any(names!=extended.common.EXPECTED_NAMES for names in selection.values()):
        raise ValueError('reference must contain exactly 72 names for each objective')
    records=[];digests={}
    for objective,names in selection.items():
        for name in names:
            case=root/'cases'/objective/name;path=case/f'{objective}.json'
            digest=extended.focus.sha(path);receipt=json.loads((case/'measurement.json').read_text())
            if receipt['raw_sha256']!=digest or receipt['binary_sha256']!=manifest['binary_sha256'] or receipt['definition']!=manifest['definition']:
                raise ValueError('reference receipt differs from its raw result or method')
            digests[f'{objective}/{name}']=digest
            record=extended.assess_case(case,'Core-E4-full216',objective,name,manifest['timeout_seconds'],manifest['definition'])
            if record['errors'] or record['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(record['errors']))
            records.append(record)
    rebuilt=[dict(objective=r['objective'],name=r['name'],status=r['status'],proven=r['proven'],seconds=r['time'],
                  cost=r['solve'].get('cost'),lb=r['solve'].get('lb'),ub=r['solve'].get('ub')) for r in records]
    if rebuilt!=saved['case_bounds'] or len(records)!=saved['completed_runs'] or saved['expected_runs']!=3*len(extended.common.EXPECTED_NAMES):
        raise ValueError('reference report differs from raw results')
    if not extended.reports_match(extended.audit.summarize(records,manifest['timeout_seconds']),saved['summary']):
        raise ValueError('reference summary differs from raw results')
    unresolved={o:[r['name'] for r in records if r['objective']==o and not r['proven']] for o in extended.audit.OBJECTIVES}
    return manifest,unresolved,digests

def filtered_selection(selection,objectives=None):
    """Keep all objective keys, recording excluded objectives as empty lists."""
    if objectives is None:return {o:list(names) for o,names in selection.items()}
    if not objectives or len(set(objectives))!=len(objectives) or not set(objectives)<=set(selection):
        raise ValueError('objective filter must contain distinct, supported objectives')
    return {o:list(names) if o in objectives else [] for o,names in selection.items()}

def audit_saved(root,reference):
    verify_snapshot(root)
    source,selection,digests=load_reference(reference)
    manifest=json.loads((root/'manifest.json').read_text());component=manifest.get('component','order-cycles')
    selection=filtered_selection(selection,manifest.get('objective_filter'))
    if measurement_context(manifest.get('measurement_context','serial'),manifest.get('paired_run_id'))!={
        k:manifest[k] for k in ('measurement_context','paired_run_id') if k in manifest}:
        raise ValueError('measurement context changed')
    saved=json.loads((root/report_name(component)).read_text())
    if manifest['schema']!=schema_for(component) or manifest['instances_by_objective']!=selection:
        raise ValueError('selection differs from unresolved reference pairs')
    for field,file in [('reference_manifest_sha256','manifest.json'),('reference_report_sha256','full_audit.json')]:
        if manifest[field]!=extended.focus.sha(reference/file):raise ValueError('reference changed')
    config=experiment_config(source,component,manifest.get('backend_override'),manifest.get('core_conflicts_override'))
    if manifest['reference_raw_sha256']!=digests or manifest['definition']!=config:raise ValueError('method or raw references changed')
    if manifest['timeout_seconds']!=source['timeout_seconds'] or manifest['ram_kb']!=source['ram_kb']:
        raise ValueError('candidate and reference must use the same timeout and RAM')
    if manifest['dataset_sha256']!=source['dataset_sha256']:raise ValueError('dataset changed')
    build=json.loads((root/'build_manifest.json').read_text())
    if extended.focus.sha(root/'build_manifest.json')!=manifest['build_manifest_sha256'] or build['git_commit']!=manifest['solver_source_commit'] or build['binary_sha256']!=manifest['binary_sha256']:
        raise ValueError('build evidence differs from recorded source or binary')
    if (root/'failure.json').exists():raise ValueError('preserve and inspect the recorded campaign failure')
    expected=[(o,n) for o,names in selection.items() for n in names];records=[]
    count=saved['completed_runs']
    if type(count) is not int or not 0<=count<=len(expected):raise ValueError('invalid completed count')
    for objective,name in expected[:count]:
        case=root/'cases'/objective/name
        provenance=dict(l.split('=',1) for l in (case/'logs/manifest.txt').read_text().splitlines() if '=' in l)
        locked=dict(binary_sha256=manifest['binary_sha256'],git_commit=manifest['runner_commit'],git_dirty='0',
            solver=manifest['definition']['solver'],objective=objective,selected_instances=name,selected_instance_count='1',
            instance_timeout_seconds=str(manifest['timeout_seconds']),ram_limit_kb=str(manifest['ram_kb']))
        locked.update({'maxsatddd_'+k:v for k,v in manifest['definition'].items() if k not in ('solver','kind')})
        if any(provenance.get(k)!=v for k,v in locked.items()):raise ValueError('case provenance changed')
        record=extended.assess_case(case,tag_for(component),objective,name,manifest['timeout_seconds'],manifest['definition'])
        if record['errors'] or record['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(record['errors']))
        records.append(record)
    rebuilt=report_for(records,expected,manifest['timeout_seconds'],component)
    if not extended.reports_match(rebuilt,saved):raise ValueError('trial report differs from independently checked results')
    return dict(rebuilt,audit_passed=True)

def report_for(records,expected,timeout,component='order-cycles'):
    return dict(schema=schema_for(component),expected_runs=len(expected),completed_runs=len(records),
        complete=len(records)==len(expected),errors=[],submission_passed=False,
        scope='unresolved pairs only; previously solved candidate pairs require regression before a full-coverage claim',
        newly_solved=[dict(objective=r['objective'],name=r['name'],cost=r['solve']['cost'],seconds=r['time']) for r in records if r['proven']],
        summary=extended.audit.summarize(records,timeout))

def run(args):
    source,selection,digests=load_reference(args.reference)
    selection=filtered_selection(selection,args.objectives)
    if not any(selection.values()):raise ValueError('no unresolved pairs remain')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=extended.REPO).strip():
        raise ValueError('commit the experiment code first')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=extended.REPO,text=True).strip()
    build=json.loads(args.build_manifest.read_text())
    solver_source=validate_build(build,commit,args.binary,args.reuse_build)
    context=measurement_context(args.measurement_context,args.paired_run_id)
    config=experiment_config(source,args.component,args.backend,args.core_minimize_conflicts)
    root=args.results.resolve();root.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema=schema_for(args.component),component=args.component,runner_commit=commit,solver_source_commit=solver_source,
        definition=config,instances_by_objective=selection,timeout_seconds=source['timeout_seconds'],ram_kb=source['ram_kb'],
        binary_sha256=extended.focus.sha(args.binary),reference_manifest_sha256=extended.focus.sha(args.reference/'manifest.json'),
        reference_report_sha256=extended.focus.sha(args.reference/'full_audit.json'),reference_raw_sha256=digests,
        dataset_sha256=extended.focus.dataset_hash(),cargo_lock_sha256=extended.focus.sha(extended.REPO/'Cargo.lock'),
        run_script_sha256=extended.focus.sha(extended.REPO/'quick_scripts/run_all_txt_instances_limited.sh'),
        runner_script_sha256=extended.focus.sha(Path(__file__)),cpu_affinity=sorted(os.sched_getaffinity(0)),
        build_manifest_sha256=extended.focus.sha(args.build_manifest),
        salvers=extended.dependency_state(extended.REPO.parent/'salvers'),
        ipamir=extended.dependency_state(extended.REPO.parent/'ipamir-rs'),submission_passed=False)
    manifest.update(context)
    if args.backend is not None:manifest['backend_override']=args.backend
    if args.core_minimize_conflicts is not None:manifest['core_conflicts_override']=args.core_minimize_conflicts
    if args.objectives is not None:
        manifest['objective_filter']=[o for o in selection if o in args.objectives]
    if (root/'manifest.json').exists() and json.loads((root/'manifest.json').read_text())!=manifest:
        raise ValueError('resume would change the source, binary, dataset, dependencies or parameters')
    extended.save(root/'manifest.json',manifest)
    (root/'build_manifest.json').write_bytes(args.build_manifest.read_bytes())
    expected=[(o,n) for o,names in selection.items() for n in names];records=[]
    tag=tag_for(args.component)
    runtime=SimpleNamespace(timeout=manifest['timeout_seconds'],ram_kb=manifest['ram_kb'],binary=args.binary,method_definitions={tag:config})
    deadline=time.monotonic()+args.round_seconds
    for objective,name in expected:
        case=root/'cases'/objective/name
        if not (case/f'{objective}.json').exists():
            if deadline-time.monotonic()<runtime.timeout+90:break
            print(f'{tag}: {objective}/{name}',flush=True);extended.run_case(tag,objective,name,runtime,case)
        result=extended.assess_case(case,tag,objective,name,runtime.timeout,config)
        if result['errors'] or result['status'] in extended.audit.FATAL_STATUSES:raise ValueError(str(result['errors']))
        records.append(result);report=report_for(records,expected,runtime.timeout,args.component)
        extended.save(root/report_name(args.component),report);extended.audit.write_csv(root/'summary.csv',report['summary'])
    print(json.dumps(audit_saved(root,args.reference),indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['run','audit'])
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--binary',type=Path);parser.add_argument('--round-seconds',type=int,default=21600)
    parser.add_argument('--build-manifest',type=Path)
    parser.add_argument('--component',choices=['order-cycles','initial-cost','order-paths','order-paths-full','order-master','order-master-levels','order-master-levels-full','order-master-batch','order-master-seeds','core-trim', *ASSUMPTION_COMPONENTS],default='order-cycles')
    parser.add_argument('--reuse-build',action='store_true',help='reuse the hashed binary while retaining its own source commit')
    parser.add_argument('--objectives',nargs='+',choices=extended.audit.OBJECTIVES,
        help='screen only these objectives; excluded pairs remain unresolved and cannot count as gains')
    parser.add_argument('--backend',choices=['minisat','cadical'],help='change only the SAT backend in the locked method')
    parser.add_argument('--core-minimize-conflicts',type=int,
        help='zero means unlimited; needed for a common budget with the CaDiCaL adapter')
    parser.add_argument('--measurement-context',choices=['serial','paired-screen'],default='serial')
    parser.add_argument('--paired-run-id',help='shared ID of two concurrent backend screens; their timings remain diagnostic')
    args=parser.parse_args()
    if args.action=='audit':print(json.dumps(audit_saved(args.results,args.reference),indent=2));return
    if args.binary is None or args.build_manifest is None or not 0<args.round_seconds<=21600:
        parser.error('run needs --binary, --build-manifest and a round limit <=21600 seconds')
    try:run(args)
    except BaseException as error:
        if args.results.exists():extended.save(args.results/'failure.json',dict(error=str(error) or type(error).__name__))
        raise

if __name__=='__main__':main()
