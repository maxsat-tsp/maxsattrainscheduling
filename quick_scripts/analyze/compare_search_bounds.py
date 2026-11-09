#!/usr/bin/env python3
"""Compare audited search intervals with a frozen pool of previous results.

References only enter this evaluator, never the solver command or its bounds.
Pooled intervals are comparison evidence, not the coverage of a portfolio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
import shutil
import tempfile
import statistics

import bound_quality as quality
import run_sat_bound_search as search
import extended_timeout_experiments as ex
import targeted_order_cycles as trial
import diagnose_optimal_bounds as diagnostic
import audit_targeted_core_minimization as core_history
import rebuild_cplex_recheck as cplex_recheck

RESEARCH=ex.REPO/'results/sat_research'
ALLOWED={'Orders-Transitive','CSOnet','MaxSAT-Journal','BigM-Gurobi','BigM-CPLEX'}


def logged_bounds(text):
    lows=[int(x) for x in re.findall(r'^\s*(?:EXHAUST )?LB=(\d+)\b',text,re.M)]
    highs=[int(x) for x in re.findall(r'^HEUR\.FEAS\.\s+(\d+)\b',text,re.M)]
    return max(lows) if lows else None,min(highs) if highs else None


class Pool:
    def __init__(self,selection):
        self.selection=set(selection);self.records=[];self.sources={};self.excluded=[];self.conflicts=[]

    def track(self,path):
        path=Path(path);self.sources[str(path.resolve())]=ex.focus.sha(path)

    def add(self,objective,name,lb,ub,method,budget,source,validation):
        if (objective,name) not in self.selection:return
        lo,hi=quality.interval(lb,ub)
        if lo is None and hi is None:return
        record=dict(objective=objective,name=name,lb=lb,ub=ub,method=method,
            family='milp' if method.startswith('BigM') else 'sat',timeout_seconds=budget,
            source=source,validation=validation)
        self.records.append(record);return record

    def result(self,objective,name,solve,method,budget,source,stdout=''):
        if (objective,name) not in self.selection:return
        if solve.get('status') not in ('ok','timeout') or solve.get('process_exit_code',0)!=0:
            raise ValueError('invalid reference process '+source)
        validation='reported solver bounds; timeout witness absent'
        if solve.get('solution') is not None:
            search.validate_schedule(name,objective,solve['solution'],solve.get('cost'))
            if quality.upper(solve['cost'])!=quality.upper(solve.get('ub')):
                raise ValueError('reference incumbent cost and UB disagree')
            validation='incumbent independently verified; LB is solver-reported'
        lb,ub=solve.get('lb'),solve.get('ub')
        ll,uu=logged_bounds(stdout)
        if ll is not None:lb=max(quality.lower(lb),ll) if quality.lower(lb) is not None else ll
        if uu is not None:ub=min(quality.upper(ub),uu) if quality.upper(ub) is not None else uu
        record=self.add(objective,name,lb,ub,method,budget,source,validation)
        if record is not None:
            record['upper_witness_verified']=(solve.get('solution') is not None
                and quality.upper(ub)==quality.upper(solve.get('cost')))

    def check_reference_consistency(self):
        """Quarantine a reported LB contradicted by a checked feasible schedule.

        Preserve the original LB and its source, retain the valid incumbent,
        and expose the conflict. This does not repair baseline optimality.
        """
        for o,n in self.selection:
            refs=[r for r in self.records if (r['objective'],r['name'])==(o,n)]
            witnesses=[r for r in refs if r.get('upper_witness_verified') and quality.upper(r['ub']) is not None]
            if not witnesses:continue
            best=min(witnesses,key=lambda r:quality.upper(r['ub']));ub=quality.upper(best['ub'])
            for r in refs:
                lb=quality.lower(r['lb'])
                if lb is not None and lb>ub:
                    conflict=dict(objective=o,name=n,source=r['source'],method=r['method'],
                        reported_lb=r['lb'],verified_feasible_ub=ub,witness_source=best['source'])
                    fixes=[q for q in refs if q['method']=='BigM-CPLEX-Tight' and quality.lower(q['lb'])==ub and quality.upper(q['ub'])==ub]
                    if r['method']=='BigM-CPLEX' and fixes:conflict['resolved_by_strict_rerun']=fixes[0]['source']
                    self.conflicts.append(conflict);r['excluded_lower_bound']=r['lb'];r['lb']=None
                    r['lower_bound_quarantined']=True

    def full_v17(self,root):
        manifest,_,_=trial.load_reference(root);self.track(root/'manifest.json');self.track(root/'full_audit.json')
        for objective,names in manifest['instances_by_objective'].items():
            for name in names:
                if (objective,name) not in self.selection:continue
                p=root/'cases'/objective/name;raw=p/f'{objective}.json';self.track(raw)
                logs=p/'logs'/f'{name}.stdout.log';self.track(logs)
                rows=ex.common.load_rows(raw);solve=next(s for n,s in rows if n==name)
                self.result(objective,name,solve,'V17',manifest['timeout_seconds'],str(raw),logs.read_text())

    def v39_controls(self,root,reference):
        report=diagnostic.audit(root/'trial',reference)
        if not report['complete']:raise ValueError('V39 reference is incomplete')
        for row in report['records']:
            if row['mode']!='control':continue # no oracle-assisted run enters the pool
            p=root/'trial/cases'/row['objective']/row['name']/'control/result.json';self.track(p)
            self.add(row['objective'],row['name'],row['lower_bound'],row['upper_bound'],
                'RC2-control',300,str(p),'audited control provenance; timeout witness absent')

    def v17_600(self,root):
        hashes=json.loads((root/'archive_hashes.json').read_text())
        def checked(relative):
            path=(root/relative).resolve()
            if root.resolve() not in path.parents or ex.focus.sha(path)!=hashes[relative]:
                raise ValueError('600-second reference artifact changed')
            self.track(path);return path
        report=json.loads(checked('independent_audit.json').read_text())
        if not report['audit_passed'] or report['errors'] or not report['complete']:
            raise ValueError('600-second reference was not audited')
        for row in report['case_rows']:
            o,n=row['objective'],row['name']
            if (o,n) not in self.selection:continue
            path=checked(row['path']);data=json.loads(path.read_text())
            rows=data if isinstance(data,list) else [data]
            if len(rows)!=1 or rows[0]['name']!=n:raise ValueError('wrong 600-second case identity')
            log=checked(str(Path(row['path']).parent.parent/(n+'.stdout.log')))
            self.result(o,n,rows[0]['solves'][0],'V17',600,str(path),log.read_text())

    def milp_json(self,objective,path):
        self.track(path);seen=set()
        for name,solve in ex.common.load_rows(path):
            if name in seen:raise ValueError('duplicate MILP reference case')
            seen.add(name)
            if (objective,name) not in self.selection:continue
            if solve.get('solver_name')!='BigMLazy':raise ValueError('unsupported Gurobi source')
            self.result(objective,name,solve,'BigM-Gurobi',solve.get('timeout_seconds'),str(path)+'#'+name)

    def archive(self,path,corrected_cplex=False):
        self.track(path)
        with tarfile.open(path) as archive:
            allowed=None
            if not corrected_cplex:
                report=json.load(archive.extractfile('extended_audit.json'))
                if report.get('errors'):raise ValueError('extended reference has audit errors')
                allowed={(r['method'],r['objective'],r['name']) for r in report['case_bounds']}
            pattern=re.compile(r'^cases/([^/]+)/(finsteps123|infsteps180|cont)/([^/]+)/\2\.json$')
            for member in archive.getmembers():
                match=pattern.match(member.name)
                if not match:continue
                method,objective,name=match.groups()
                if method not in ALLOWED or (objective,name) not in self.selection:continue
                if allowed is not None and (method,objective,name) not in allowed:continue
                if not member.isfile():raise ValueError('reference case is not a regular file')
                raw=archive.extractfile(member).read();rows=json.loads(raw)
                if len(rows)!=1 or rows[0]['name']!=name:raise ValueError('reference case identity mismatch')
                solve=rows[0]['solves'][0]
                logs=''
                logname=str(Path(member.name).parent/'logs'/(name+'.stdout.log'))
                if method in ('CSOnet','MaxSAT-Journal','Orders-Transitive'):
                    try:logs=archive.extractfile(logname).read().decode()
                    except KeyError:pass
                self.result(objective,name,solve,method,solve.get('timeout_seconds'),
                    str(path)+'#'+member.name+'@'+hashlib.sha256(raw).hexdigest(),logs)

    def targeted_history(self,reference):
        """Recover useful progress from previously audited targeted variants."""
        for path in sorted(RESEARCH.rglob('raw_snapshot.tar.gz')):
            with tarfile.open(path) as archive:
                roots=[]
                for member in archive.getmembers():
                    if not member.isfile() or Path(member.name).name!='manifest.json':continue
                    manifest=json.load(archive.extractfile(member))
                    if str(manifest.get('schema','')).startswith('targeted-'):
                        roots.append((Path(member.name).parent,manifest))
                if not roots:continue
                self.track(path)
                with tempfile.TemporaryDirectory(prefix='prior-bound-reference-') as folder:
                    base=Path(folder)
                    for member in archive.getmembers():
                        if not any(prefix==Path('.') or prefix in Path(member.name).parents for prefix,_ in roots):continue
                        dest=(base/member.name).resolve()
                        if (dest!=base.resolve() and base.resolve() not in dest.parents) or member.issym() or member.islnk():
                            raise ValueError('unsafe historical reference archive')
                        archive.extract(member,base)
                    for prefix,manifest in roots:
                        root=base/prefix
                        if manifest['schema']=='targeted-core-confirmation-v1':
                            # These historical repetitions are not independent
                            # cases and concern already solved B instances.
                            report=json.loads((root/'confirmation_audit.json').read_text())
                            continue
                        if manifest['schema']=='targeted-core-minimization-v1':
                            if not (root/'snapshot.json').is_file():
                                self.excluded.append(dict(source=str(path),reason='historical archive has no snapshot hash receipt'))
                                continue
                            self.core_snapshot(root,manifest,path,prefix)
                            continue
                        try:report=trial.audit_saved(root,reference)
                        except (ValueError,KeyError,FileNotFoundError) as error:
                            self.excluded.append(dict(source=str(path)+'#'+str(prefix),reason=str(error)));continue
                        pairs=[(o,n) for o,names in manifest['instances_by_objective'].items() for n in names]
                        for o,n in pairs[:report['completed_runs']]:
                            if (o,n) not in self.selection:continue
                            case=root/'cases'/o/n;raw=case/f'{o}.json'
                            rows=ex.common.load_rows(raw);solve=next(s for name,s in rows if name==n)
                            log=case/'logs'/(n+'.stdout.log')
                            self.result(o,n,solve,trial.tag_for(manifest.get('component','order-cycles')),
                                manifest['timeout_seconds'],str(path)+'#'+str(prefix/'cases'/o/n),log.read_text() if log.exists() else '')

    def core_snapshot(self,root,manifest,path,prefix):
        """Recheck old bounded-core evidence without inventing its parent run.

        Snapshot hashes, dataset, per-case launch provenance and raw outcomes
        are checked here. The historical selection procedure is not rerun;
        these are comparison bounds, never new coverage or new measurements.
        """
        if not (root/'snapshot.json').is_file():raise ValueError('unlocked historical core snapshot')
        core_history.verify_snapshot(root)
        saved=json.loads((root/'core_minimization_audit.json').read_text())
        pairs=core_history.completed_cases(manifest,saved)
        if saved.get('errors') or manifest['dataset_sha256']!=ex.focus.dataset_hash():
            raise ValueError('invalid historical bounded-core evidence')
        config=manifest['definition'];tag=core_history.targeted.tag_for(config)
        for o,n in pairs:
            if (o,n) not in self.selection:continue
            case=root/'cases'/o/n
            provenance=dict(line.split('=',1) for line in (case/'logs/manifest.txt').read_text().splitlines() if '=' in line)
            expected=dict(binary_sha256=manifest['binary_sha256'],git_commit=manifest['runner_commit'],
                git_dirty='0',solver=config['solver'],objective=o,selected_instances=n,
                selected_instance_count='1',instance_timeout_seconds=str(manifest['timeout_seconds']),
                ram_limit_kb=str(manifest['ram_kb']))
            expected.update({'maxsatddd_'+k:v for k,v in config.items() if k not in ('solver','kind')})
            if any(provenance.get(k)!=v for k,v in expected.items()):
                raise ValueError('historical core case provenance changed')
            record=ex.assess_case(case,tag,o,n,manifest['timeout_seconds'],config)
            if record['errors'] or record['status'] in ex.audit.FATAL_STATUSES:
                raise ValueError('historical core outcome failed independent verification')
            log=case/'logs'/(n+'.stdout.log')
            self.result(o,n,record['solve'],tag,manifest['timeout_seconds'],
                str(path)+'#'+str(prefix/'cases'/o/n),log.read_text() if log.exists() else '')

    def search_history(self,reference,diagnostics,exclude_binary):
        """Earlier autonomous searches are now part of the known-bound pool."""
        for path in sorted(RESEARCH.glob('v*_sat_bound_search_*/complete_snapshot.tar.gz')):
            with tempfile.TemporaryDirectory(prefix='previous-sat-search-') as folder:
                root=Path(folder)
                with tarfile.open(path) as archive:
                    for member in archive.getmembers():
                        dest=(root/member.name).resolve()
                        if root.resolve() not in dest.parents or member.issym() or member.islnk():
                            raise ValueError('unsafe previous search archive')
                    archive.extractall(root)
                manifest=json.loads((root/'hard/manifest.json').read_text())
                if manifest['binary_sha256']==exclude_binary:continue
                hard=search.audit(root/'hard',reference,diagnostics)
                followup=search.audit(root/'followup',reference,diagnostics)
                baseline=json.loads((reference/'full_audit.json').read_text())['case_bounds']
                records,_=combine_full(hard,followup,baseline);self.track(path)
                if manifest['binary_sha256']!=json.loads((root/'followup/manifest.json').read_text())['binary_sha256']:
                    raise ValueError('historical search mixes binaries')
                for r in records:
                    record=self.add(r['objective'],r['name'],r['lb'],r['ub'],'SAT-search-'+manifest['commit'][:7],
                        manifest['timeout_seconds'],str(path)+'#'+r['objective']+'/'+r['name'],
                        'query ledger replayed; every incumbent independently checked')
                    if record is not None:record['upper_witness_verified']=True

    def cplex_rechecks(self):
        original=RESEARCH/'cplex_full_120_20261108/raw_snapshot.tar.gz'
        for path in sorted(RESEARCH.glob('cplex_full_120_20261108/bound_recheck_*/raw_snapshot.tar.gz')):
            checked=cplex_recheck.audit_native(path,original);m=checked['manifest']
            self.track(path);self.track(original)
            self.result(m['objective'],m['name'],checked['solve'],'BigM-CPLEX-Tight',
                m['timeout_seconds'],str(path)+'#tight_recheck')


def comparison_report(records,pool,expected):
    for objective,name in pool.selection:
        for family in ('all','sat'):
            quality.envelope([r for r in pool.records if (r['objective'],r['name'])==(objective,name)
                and (family=='all' or r['family']=='sat')])
    rows=[]
    for r in records:
        if r['repeat']!=0:continue
        row=dict(r,relative_gap=quality.relative_gap(r['lb'],r['ub']))
        for scope in ('all','sat'):
            refs=[x for x in pool.records if (x['objective'],x['name'])==(r['objective'],r['name'])
                and (scope=='all' or x['family']=='sat')]
            env=quality.envelope(refs);comparison=quality.compare(r['lb'],r['ub'],env['lb'],env['ub'])
            row[scope+'_reference']=dict(env,cutoffs=sorted({x['timeout_seconds'] for x in refs if x['timeout_seconds'] is not None}))
            row[scope+'_comparison']=comparison
        rows.append(row)
    pending=[r for r in rows if not r['proven']]
    summary=quality.summarize([dict(r,bounds_verified=True) for r in rows])
    summary.update(proven_optimal=sum(r['proven'] for r in rows),completed_instances=len(rows),expected_instances=expected,
        new_best_bound_cases=sum(r['all_comparison']['new_bound'] for r in pending),
        sat_bound_improvement_cases=sum(r['sat_comparison']['new_bound'] for r in pending),
        new_best_lb_cases=sum(r['all_comparison']['lb_improved'] for r in pending),
        new_best_ub_cases=sum(r['all_comparison']['ub_improved'] for r in pending))
    return dict(schema='coverage-bounds-runtime-evaluation-v1',priorities=list(quality.PRIORITIES),
        complete=len(rows)==expected,ranking_eligible=len(rows)==expected,
        summary=summary,cases=rows,reference_records=pool.records,
        source_sha256=pool.sources,reference_pool_is_not_a_solver=True,submission_passed=False,
        scope='best available bounds in the listed imported references; mixed cutoffs are explicit, not an equal-time SOTA claim',
        bound_validation='candidate intervals replayed; reference witnesses checked when present, reported log bounds retained conservatively as comparison bars',
        candidate_bounds_replaced_by_reference=False)


def combine_full(hard,followup,baseline):
    """Require actual coverage of all 216 pairs by the same frozen method."""
    if not hard['complete'] or not followup['complete']:
        raise ValueError('complete hard and regression phases are required')
    gains={(r['objective'],r['name']):r['cost'] for r in hard['newly_solved']}
    hard_pairs={(r['objective'],r['name']) for r in hard['records'] if not r['repeat']}
    expected={(r['objective'],r['name'],0) for r in baseline if r['proven'] and (r['objective'],r['name']) not in hard_pairs}
    expected|={(o,n,i) for o,n in gains for i in (1,2,3)}
    actual=[(r['objective'],r['name'],r['repeat']) for r in followup['records']]
    if len(actual)!=len(set(actual)) or set(actual)!=expected:
        raise ValueError('confirmation/regression membership is missing, duplicated or unexpected')
    confirmations=[r for r in followup['records'] if r['repeat']]
    if any(not r['proven'] or r['cost']!=gains[r['objective'],r['name']] for r in confirmations):
        raise ValueError('new gain did not reproduce in every confirmation')
    records=[r for r in hard['records']+followup['records'] if not r['repeat']]
    pairs=[(r['objective'],r['name']) for r in records]
    if len(pairs)!=len(set(pairs)) or set(pairs)!={(r['objective'],r['name']) for r in baseline}:
        raise ValueError('full evaluation has missing or duplicated pairs')
    return records,confirmations


def full_comparison(records,baseline,cutoff,confirmations):
    previous={(r['objective'],r['name']):r for r in baseline};summary=[];gains=[];losses=[]
    for r in records:
        old=previous[r['objective'],r['name']]
        if r['proven'] and old['proven'] and r['cost']!=old['cost']:
            raise ValueError('full optimum contradicts the reference')
        if r['proven'] and not old['proven']:gains.append(dict(objective=r['objective'],name=r['name'],cost=r['cost']))
        if old['proven'] and not r['proven']:losses.append(dict(objective=r['objective'],name=r['name'],lb=r['lb'],ub=r['ub']))
    for o in ex.audit.OBJECTIVES:
        rows=[r for r in records if r['objective']==o];old=[r for r in baseline if r['objective']==o]
        paired=[r for r in rows if r['proven'] and previous[o,r['name']]['proven']]
        times=[r['seconds'] for r in rows if r['proven']]
        summary.append(dict(objective=o,instances=len(rows),proven_optimal=len(times),
            baseline_optimal=sum(r['proven'] for r in old),
            coverage_delta=len(times)-sum(r['proven'] for r in old),
            par2_seconds=sum(r['seconds'] if r['proven'] else 2*cutoff for r in rows)/len(rows),
            baseline_par2_seconds=sum(r['seconds'] if r['proven'] else 2*cutoff for r in old)/len(old),
            median_solved_seconds=statistics.median(times) if times else None,
            paired_instances=len(paired),paired_candidate_seconds=sum(r['seconds'] for r in paired),
            paired_baseline_seconds=sum(previous[o,r['name']]['seconds'] for r in paired)))
    return dict(summary=summary,gained=gains,lost=losses,confirmations=confirmations,
        complete=True,cutoff_seconds=cutoff,baseline='V17 full300',
        coverage_total_delta=sum(r['coverage_delta'] for r in summary),
        coverage_nonregression=all(r['coverage_delta']>=0 for r in summary),
        scope='one frozen method on every pair; no mixing with baseline solutions')


def evaluate(args,candidate):
    audited=search.audit(candidate,args.reference,args.diagnostics)
    records=audited['records'];expected=audited['expected_runs'];full=None
    followup=getattr(args,'followup',None)
    if followup is not None:
        fm=json.loads((followup/'manifest.json').read_text());hm=json.loads((candidate/'manifest.json').read_text())
        if not fm.get('followup') or any(fm[k]!=hm[k] for k in ('commit','binary_sha256','build_manifest_sha256','dataset_sha256','timeout_seconds','ram_kb','cpu_affinity')) or fm.get('threshold_policy','bisect')!=hm.get('threshold_policy','bisect'):
            raise ValueError('full evaluation mixes methods or resource limits')
        fa=search.audit(followup,args.reference,args.diagnostics)
        baseline=json.loads((args.reference/'full_audit.json').read_text())['case_bounds']
        records,confirmations=combine_full(audited,fa,baseline);expected=len(baseline)
        full=full_comparison(records,baseline,hm['timeout_seconds'],confirmations)
    selection=([(o,n) for o in ex.audit.OBJECTIVES for n in ex.common.EXPECTED_NAMES] if full else
        [(t['objective'],t['name']) for t in json.loads((candidate/'manifest.json').read_text())['tasks'] if not t['repeat']])
    pool=Pool(selection)
    if args.reference_pool is not None and args.reference_pool.exists():
        receipt=args.reference_pool.with_suffix('.sha256')
        if not receipt.exists() or receipt.read_text().strip()!=ex.focus.sha(args.reference_pool):
            raise ValueError('frozen reference pool hash changed')
        cached=json.loads(args.reference_pool.read_text())
        if cached.get('schema')!='frozen-bound-reference-pool-v2' or cached['dataset_sha256']!=ex.focus.dataset_hash() or {tuple(p) for p in cached['selection']}!=pool.selection:
            raise ValueError('frozen bound reference pool changed dataset or selection')
        pool.records=cached['records'];pool.sources=cached['sources'];pool.excluded=cached['excluded'];pool.conflicts=cached['conflicts']
    else:
        pool.full_v17(args.reference);pool.v39_controls(args.diagnostics,args.reference)
        pool.v17_600(args.sat600)
        for objective,path in args.gurobi_json:pool.milp_json(objective,Path(path))
        pool.archive(args.cplex_archive,corrected_cplex=True)
        for path in args.extended_archive:pool.archive(path)
        pool.targeted_history(args.reference)
        pool.search_history(args.reference,args.diagnostics,json.loads((candidate/'manifest.json').read_text())['binary_sha256'])
        pool.cplex_rechecks()
        pool.check_reference_consistency()
        if args.reference_pool is not None:
            ex.save(args.reference_pool,dict(schema='frozen-bound-reference-pool-v2',
                dataset_sha256=ex.focus.dataset_hash(),selection=sorted(pool.selection),
                records=pool.records,sources=pool.sources,excluded=pool.excluded,conflicts=pool.conflicts))
            args.reference_pool.with_suffix('.sha256').write_text(ex.focus.sha(args.reference_pool)+'\n')
    report=comparison_report(records,pool,expected)
    report['full_comparison']=full
    report['candidate_audit_passed']=audited['audit_passed']
    report['candidate_root']=str(args.candidate.resolve())
    report['candidate_manifest_sha256']=ex.focus.sha(candidate/'manifest.json')
    report['candidate_cutoff_seconds']=json.loads((candidate/'manifest.json').read_text())['timeout_seconds']
    report['candidate_input_sha256']={str(p.relative_to(candidate)):ex.focus.sha(p) for p in candidate.rglob('*')
        if p.is_file() and p.name in ('manifest.json','build_manifest.json','result.json','result.trace.jsonl','launch.json','completion.json')}
    if followup is not None:
        report['followup_input_sha256']={str(p.relative_to(followup)):ex.focus.sha(p) for p in followup.rglob('*')
            if p.is_file() and p.name in ('manifest.json','build_manifest.json','result.json','result.trace.jsonl','launch.json','completion.json')}
    report['evaluator_sha256']=ex.focus.sha(Path(__file__))
    report['excluded_reference_imports']=pool.excluded
    report['reference_bound_conflicts']=pool.conflicts
    report['reference_pool_sha256']=ex.focus.sha(args.reference_pool) if args.reference_pool is not None else None
    ex.save(args.output,report);print(json.dumps(report['summary'],indent=2))


def run(args):
    if not args.completed_only:return evaluate(args,args.candidate)
    # A running solver writes result.json before its completion receipt. Only
    # copy completed cases; never audit a file while that case is still writing.
    with tempfile.TemporaryDirectory(prefix='bound-eval-') as folder:
        target=Path(folder)/'candidate';target.mkdir()
        for name in ('manifest.json','build_manifest.json'):shutil.copyfile(args.candidate/name,target/name)
        manifest=json.loads((target/'manifest.json').read_text())
        for task in manifest['tasks']:
            relative=Path('cases')/task['objective']/task['name']/str(task['repeat'])
            case=args.candidate/relative
            if not (case/'completion.json').is_file():continue
            dest=target/relative;dest.mkdir(parents=True)
            for name in ('result.json','result.trace.jsonl','launch.json','completion.json'):
                if (case/name).is_symlink():raise ValueError('case receipt contains a symlink')
                shutil.copyfile(case/name,dest/name)
        evaluate(args,target)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--diagnostics',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--followup',type=Path,help='completed confirmations and full regression; never reuse old solved cases as candidate results')
    p.add_argument('--completed-only',action='store_true',help='read completed cases of a running campaign without changing it')
    p.add_argument('--reference-pool',type=Path,help='create once, then reuse an immutable pool of earlier bounds')
    p.add_argument('--gurobi-json',nargs=2,action='append',default=[],metavar=('OBJECTIVE','JSON'))
    p.add_argument('--sat600',type=Path,default=RESEARCH/'v17_extended600_20261107')
    p.add_argument('--cplex-archive',type=Path,default=RESEARCH/'cplex_full_120_20261108/raw_snapshot.tar.gz')
    p.add_argument('--extended-archive',type=Path,action='append',default=[
        RESEARCH/'extended_300_20261106/progress_82/raw_snapshot.tar.gz',
        RESEARCH/'cadical_300_20261106/minisat_diagnostic/raw_snapshot.tar.gz'])
    run(p.parse_args())
