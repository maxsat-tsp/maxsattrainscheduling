#!/usr/bin/env python3
"""Measure only pairs without a saved proof at the next comparison cutoff."""

import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
from types import SimpleNamespace

import bound_quality
from compare_search_bounds import cutoff_reference
import extended_timeout_experiments as ex
from inventory_gurobi_reference import summarize
import run_cplex_reference_tail as cplex
import run_gurobi_reference_tail as gurobi
import run_long_baseline_cases as controls
import run_sat_bound_search as search

DATA = controls.RESEARCH/'v45_long600_20261121'
GUROBI = controls.RESEARCH/'baseline_inventory_20261110'
SAT = 'SAT'
ALL_PAIRS = {(o,n) for o in ex.audit.OBJECTIVES for n in ex.common.EXPECTED_NAMES}
SAT_CPUS = {0, 1, 4, 5}
GUROBI_METHOD = 'BigM-Gurobi'


def read(path):
    return json.loads(path.read_text())


@contextmanager
def extracted(path):
    receipt = read(path.parent/'archive_hashes.json')
    if ex.focus.sha(path) != receipt[path.name]:
        raise ValueError(f'archive hash changed: {path}')
    with tempfile.TemporaryDirectory(prefix='cutoff-reference-') as folder:
        root = Path(folder).resolve()
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                dest = (root/member.name).resolve()
                if root not in dest.parents or not (member.isfile() or member.isdir()):
                    raise ValueError('unsafe cutoff reference archive')
            archive.extractall(root)
        yield root


def full_sat(root, args):
    hard, followup = root/'hard', root/'followup'
    hm, fm = read(hard/'manifest.json'), read(followup/'manifest.json')
    search.same_method(hm, fm)
    baseline, _ = search.baseline_for_manifest(hm, args.reference, args.diagnostics)
    records, _ = bound_quality.combine_full(
        search.audit(hard, args.reference, args.diagnostics),
        search.audit(followup, args.reference, args.diagnostics), baseline)
    return records, hm


def pick_sat(args, prior, v45):
    old_proofs = {(r['objective'],r['name']) for r in prior if r['proven']}
    if args.v47 is None:
        return prior, v45, 'V45', 1200
    if not (args.v47/'COMPLETED').is_file() or (args.v47/'FAILED').exists():
        raise ValueError('V47 must have a clean completion marker')
    if not (args.v47/'full-evaluation.json').is_file():
        return prior, v45, 'V45', 1200
    records, method = full_sat(args.v47, args)
    if method['threshold_session'] != 'reuse-offset-tree' or method['timeout_seconds'] != 600:
        raise ValueError('V47 completion has a different protocol')
    proofs = {(r['objective'],r['name']) for r in records if r['proven']}
    if not old_proofs < proofs:
        return prior, v45, 'V45', 1200
    return records, method, 'V47', 600 if len(proofs) >= 209 else 1200


def v49_reproduced(root, reference, diagnostics):
    if not (root/'COMPLETED').is_file() or (root/'FAILED').exists():
        raise ValueError('V49 must have a clean completion marker')
    hard = root/'hard'
    manifest = read(hard/'manifest.json')
    if manifest['threshold_session']!='reuse-pair-budget' or manifest['timeout_seconds']!=1200:
        raise ValueError('V49 completed with a different protocol')
    report = search.audit(hard,reference,diagnostics)
    if not report['audit_passed'] or not report['complete']:
        raise ValueError('V49 hard set is incomplete')
    if not report['newly_solved']:
        return False
    followup = root/'followup'
    search.same_method(manifest,read(followup/'manifest.json'))
    replay = search.audit(followup,reference,diagnostics)
    if not replay['audit_passed'] or (not replay['complete'] and not (followup/'followup_stopped.json').is_file()):
        raise ValueError('V49 confirmation lacks a terminal audit')
    repeats = {(r['objective'],r['name'],r['repeat']):r for r in replay['records'] if r['repeat']}
    for r in report['newly_solved']:
        trials = [repeats.get((r['objective'],r['name'],i)) for i in (1,2,3)]
        if all(trial is not None and trial['proven'] and trial['cost']==r['cost'] for trial in trials):
            return True
    return False


def checked_gurobi_rows(known, sources):
    inventory = GUROBI/'gurobi_inventory.json'
    snapshot = GUROBI/'gurobi_tail_snapshot.tar.gz'
    tail600 = DATA/'gurobi600_tail_snapshot.tar.gz'
    sources.extend((inventory,snapshot,tail600,cplex.REFERENCE))
    rows = read(inventory)['records']
    with extracted(snapshot) as root:
        report = gurobi.audit(root,inventory_override=inventory,reference_override=cplex.REFERENCE)
        if not report['complete']:
            raise ValueError('Gurobi 300-second tail is incomplete')
        rows.extend(dict(r,timeout_seconds=300,upper_witness_verified=r['proven'])
                    for r in report['cases'])
    with extracted(tail600) as root:
        (stage,) = root.iterdir()
        lock = read(stage/'manifest.json')
        o,n = lock['objective'],lock['name']
        case = stage/'case'
        if (not (stage/'COMPLETED').is_file() or lock['dataset_sha256']!=ex.focus.dataset_hash()
                or lock['timeout_seconds']!=600 or controls.case_evidence(
                    case,'BigM-Gurobi',o,n,lock)!=read(case/'completion.json')):
            raise ValueError('Gurobi final 600-second evidence changed')
        rows.append(controls.checked_case(case,'BigM-Gurobi',o,n,lock,known[o,n]))
    return rows


def material(args):
    extended = getattr(args,'baseline_1200',None)
    snapshot = DATA/'complete_snapshot.tar.gz'
    sources = [snapshot, controls.BASELINE_SNAPSHOT, *(controls.RESEARCH/p for p in controls.SAT_SOURCES),
               cplex.ORIGINAL,cplex.CORRECTION,cplex.DATA/'archive_hashes.json']
    with extracted(snapshot) as old:
        if not (old/'COMPLETED').is_file():
            raise ValueError('V45 full evidence is incomplete')
        prior, v45 = full_sat(old, args)
        known = {(r['objective'],r['name']):r for r in prior}
        expected_ddd = read(old/'controls/BigM-Gurobi/manifest.json')['binary_sha256']
        expected_cplex = read(old/'controls/BigM-CPLEX/manifest.json')['binary_sha256']
        records, sat_lock, label, cutoff = pick_sat(args, prior, v45)
        rows = controls.baseline_rows(controls.BASELINE_SNAPSHOT)
        rows['BigM-Gurobi'] = checked_gurobi_rows(known, sources)
        cp = cplex.source_material()
        cp_tail = cplex.audit(args.cplex_reference,cp)
        if not cp_tail['complete']:
            raise ValueError('CPLEX 300-second reference is incomplete')
        rows['BigM-CPLEX'] = cp[0] + cp_tail['cases']
        sources.extend([args.cplex_reference/'manifest.json', *sorted(args.cplex_reference.rglob('completion.json'))])
        for method, row in controls.audit_archived_controls(old,old/'control-recovery',known):
            rows[method].append(row)

    rows[SAT] = [dict(r,timeout_seconds=600,upper_witness_verified=r['proven']) for r in records]
    longer = None
    if extended is not None:
        if label!='V45' or cutoff!=1200:
            raise ValueError('the 2400-second protocol extends V45 and its audited controls')
        longer = cutoff_reference(extended,1200)
        if longer['sat_method']!='V45':
            raise ValueError('the 1200-second controls use another candidate')
        sources.append(extended)
        cutoff = 2400
        for method, observations in longer['measurements'].items():
            rows[method].extend(dict(r,timeout_seconds=1200,upper_witness_verified=True)
                                for r in observations if r['proven'])
    if args.v47 is not None:
        sources.append(args.v47/'hard/manifest.json')
        if (args.v47/'full-evaluation.json').is_file():
            sources.extend(args.v47/f for f in ('full-evaluation.json','followup/manifest.json'))
    entries = {}
    for method, observations in rows.items():
        # Independently audited proof rows from shorter runs are valid for
        # coverage. Late proofs and failed launches are never carried over.
        observations = [dict(r,source=method) for r in observations]
        reuse = controls.first_checked_proofs(observations,ALL_PAIRS,cutoff if longer is not None else controls.CUTOFF)
        reused = {pair:{k:r[k] for k in ('objective','name','cost','seconds','timeout_seconds','proven')}
                  for pair,r in reuse.items()}
        if method.startswith('BigM-') and len(reused)!=208:
            raise ValueError(f'incomplete known MILP proofs for {method}')
        if longer is not None:
            if len(reused)!=longer['summary'][method]['proven']:
                raise ValueError(f'cannot rebuild the previous proof coverage for {method}')
            if any(r['cost']!=longer['verified_optima'].get(o+'/'+n) for (o,n),r in reused.items()):
                raise ValueError(f'previous optimum differs for {method}')
        at_600 = summarize(observations,600)
        tasks = sorted(ALL_PAIRS-reused.keys()) if cutoff>600 else [
            tuple(pair) for pair in at_600['missing_at_cutoff']]
        if method=='BigM-CPLEX' and not set(tasks)<={(r['objective'],r['name']) for r in cp[1]}:
            raise ValueError('a scheduled CPLEX case is missing its frozen LP')
        entries[method] = dict(reused=sorted(reused.values(),key=lambda r:(r['objective'],r['name'])),
                               tasks=[list(p) for p in tasks],
                               censored_at_600=at_600['observed_no_proof_at_cutoff'] if cutoff==600 else [])
    plan = dict(label=label,timeout_seconds=cutoff,dataset_sha256=ex.focus.dataset_hash(),methods=entries,
                expected_baseline_binaries={'ddd':expected_ddd,'BigM-CPLEX':expected_cplex},
                source_sha256={str(p):ex.focus.sha(p) for p in sources})
    return plan, sat_lock, known, {(r['objective'],r['name']):r for r in cp[1]}


def register_optima(rows):
    optima = {}
    for row in rows:
        if row['proven']:
            pair = row['objective'],row['name']
            if optima.setdefault(pair,row['cost']) != row['cost']:
                raise ValueError(f'proved optima disagree at {pair}')
    return optima


def load_prior(root, lock):
    path = root/'manifest.json'
    prior = read(path)
    expected = {k:v for k,v in lock.items() if k not in ('runner_commit','source_sha256')}
    matched = {k:v for k,v in prior.items() if k not in ('runner_commit','source_sha256')}
    # The previous worktree lives at <repo>/results/aglr/<run>. The
    # references outside both worktrees keep their absolute names.
    old_repo = root.parents[2]

    def sources(manifest, repo):
        return {str(Path(path).relative_to(repo)) if Path(path).is_relative_to(repo) else path: sha
                for path, sha in manifest['source_sha256'].items()}

    if expected != matched or sources(lock,ex.REPO) != sources(prior,old_repo):
        raise ValueError('prior extension protocol or reference hashes differ')
    return prior


def prepare_lock(plan, sat_lock, args):
    v47_binary = args.v47/'solver/sat_bound_search' if args.v47 is not None else None
    sat_binary = args.v45_binary if plan['label']=='V45' else v47_binary
    if ex.focus.sha(sat_binary)!=sat_lock['binary_sha256']:
        raise ValueError('frozen SAT binary hash changed')
    binary_hashes = {SAT:sat_lock['binary_sha256'],'ddd':ex.focus.sha(args.ddd),
                     'BigM-CPLEX':ex.focus.sha(args.cplex)}
    if any(binary_hashes[k]!=v for k,v in plan['expected_baseline_binaries'].items()):
        raise ValueError('baseline executable differs from the 600-second protocol')
    runner = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():
        raise ValueError('extension requires a clean pinned checkout')
    lock = dict(plan,runner_commit=runner,binaries=binary_hashes,
                cpu_affinity=sorted(os.sched_getaffinity(0)),sat_cpu_affinity=sorted(SAT_CPUS),
                sat_commit=sat_lock['commit'],sat_session=sat_lock['threshold_session'],
                rc2_warmup_seconds=sat_lock['rc2_warmup_seconds'],
                ram_kb=cplex.RAM_KB,threads_milp=4,uses_optimum_oracle=False)
    if args.prior_results is not None:
        prior = args.prior_results.resolve()
        current = args.results.resolve()
        if prior==current or prior in current.parents or current in prior.parents:
            raise ValueError('recovery requires a separate results directory')
        load_prior(prior,lock)
        lock['prior_results'] = dict(root=str(prior),manifest_sha256=ex.focus.sha(prior/'manifest.json'),
                                     audit_sha256=ex.focus.sha(prior/'audit.json'))
    manifest = args.results/'manifest.json'
    if not manifest.is_file():
        ex.save(manifest,lock)
    if read(manifest) != lock:
        raise ValueError('unsafe extension resume')
    return sat_binary, lock


def gurobi_failure(case, pair, profile, evidence):
    o,n = pair
    rows = ex.common.load_rows(case/(o+'.json'))
    if len(rows)!=1 or rows[0][0]!=n:
        raise ValueError('Gurobi failure has the wrong identity')
    raw = rows[0][1]
    if raw.get('status') != 'gurobi_error':
        return None
    fields = controls.launch_fields(case,GUROBI_METHOD,o,n,profile)
    elapsed = raw.get('process_wall_time_seconds')
    cutoff = profile['timeout_seconds']
    per_case = case/'logs/instances'/(n+'.json')
    logs = [case/'logs'/f'{n}.{stream}.log' for stream in ('stdout','stderr')]
    code = raw.get('gurobi_error_code')
    if (raw.get('solver_name')!='BigMLazy' or raw.get('process_exit_code')!=0
            or raw.get('external_status') is not None or raw.get('timeout_seconds')!=cutoff
            or fields.get('selected_instance_count')!='1'
            or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0
            or (code is not None and type(code) is not int)
            or per_case.with_suffix('.raw.json').exists() or ex.common.load_rows(per_case)!=rows
            or any(b'panicked at' in log.read_bytes() for log in logs)):
        raise ValueError('Gurobi failure lacks matching native evidence')
    for path in (per_case,*logs):
        evidence[str(path.relative_to(case))] = ex.focus.sha(path)
    return dict(method=GUROBI_METHOD,objective=o,name=n,status='gurobi_error',seconds=elapsed,
                timeout_seconds=cutoff,gurobi_error_code=code,source=str(case))


def measure(args, method, pair, root, lock, sat_lock, sat_binary, known, lp_tasks, optima, repeat=0, run=True):
    o,n = pair
    cutoff = lock['timeout_seconds']
    stage = root/method/o/n
    if method==SAT:
        case = stage/str(repeat)
        profile = dict(sat_lock,timeout_seconds=cutoff)
        if not (case/'completion.json').exists():
            if not run:
                return None
            if case.exists():
                raise ValueError(f'interrupted SAT case requires review: {case}')
            print(f'{method} at {cutoff}s {o}/{n} repeat={repeat}',flush=True)
            search.run_case(sat_binary,cutoff,profile['ram_kb'],profile['commit'],case,o,n,repeat,
                profile['threshold_policy'],profile['rc2_warmup_seconds'],
                profile['incumbent_polish_checks'],profile['threshold_session'])
        return search.audit_case(case,profile,o,n,repeat,optima.get(pair))

    profile = dict(lock,binary_sha256=lock['binaries']['BigM-CPLEX' if method=='BigM-CPLEX' else 'ddd'])
    case = stage
    receipt = case/'completion.json'
    failure_receipt = case/'failure.json'
    if receipt.is_file() and failure_receipt.is_file():
        raise ValueError('baseline has both completion and failure receipts')
    if not receipt.is_file() and not failure_receipt.is_file():
        if not run:
            return None
        if case.exists():
            raise ValueError(f'interrupted baseline case requires review: {case}')
        case.mkdir(parents=True)
        print(f'{method} at {cutoff}s {o}/{n}',flush=True)
        controls.measured_case(SimpleNamespace(method=method,timeout=cutoff,binary=args.ddd,cplex=args.cplex),
                               case,o,n,lp_tasks)
    evidence = controls.case_evidence(case,method,o,n,profile)
    failure = gurobi_failure(case,pair,profile,evidence) if method==GUROBI_METHOD else None
    if failure is not None:
        if receipt.is_file():
            raise ValueError('Gurobi failure cannot have a completion receipt')
        if failure_receipt.is_file():
            if read(failure_receipt)['files']!=evidence:
                raise ValueError('saved Gurobi failure evidence changed')
        else:
            ex.save(failure_receipt,dict(files=evidence))
        return failure
    if failure_receipt.is_file():
        raise ValueError('Gurobi failure receipt no longer matches its result')
    if method=='BigM-CPLEX' and evidence['model.lp']!=lp_tasks[pair]['lp_sha256']:
        raise ValueError('CPLEX cutoff run used a different LP')
    if receipt.is_file() and read(receipt)['files']!=evidence:
        raise ValueError('saved cutoff evidence changed')
    row = controls.checked_case(case,method,o,n,profile,known[pair])
    if row['status']=='ok' and not row['proven']:
        if row['seconds']<=cutoff:
            raise ValueError('cutoff run returned without an exact proof or documented timeout')
        row['status'] = 'late_proof'
    if not receipt.is_file():
        ex.save(receipt,dict(files=evidence))
    return row


def report(lock, measured, failures=()):
    summary = {}
    proven = {}
    for method, data in lock['methods'].items():
        rows = data['reused']+measured[method]
        covered = {(r['objective'],r['name']) for r in rows if r['proven']}
        proven[method] = len(covered)
        summary[method] = dict(proven=len(covered),
            coverage={o:sum(p[0]==o for p in covered) for o in ex.audit.OBJECTIVES},
            reused=len(data['reused']),measured=len(measured[method]),expected=len(data['tasks']),
            replayed=sum(r.get('replayed_from_prior',False) for r in measured[method]),
            external_timeouts=sum(r['status']=='external_timeout' for r in measured[method]),
            complete=len(measured[method])==len(data['tasks']))
    complete = all(s['complete'] for s in summary.values())
    return dict(audit_passed=True,complete=complete,timeout_seconds=lock['timeout_seconds'],
        sat_method=lock['label'],summary=summary,measurements=measured,failed_cases=list(failures),runtime_comparable=False,
        beats_all_baselines=complete and proven[SAT]>max(v for m,v in proven.items() if m!=SAT))


def replay_prior(args, lock, sat_lock, known, lp_tasks, optima):
    methods = (SAT,*controls.METHODS)
    saved = {method:[] for method in methods}
    provenance = lock.get('prior_results')
    if provenance is None:
        return saved
    root = Path(provenance['root'])
    manifest, audit = root/'manifest.json', root/'audit.json'
    if (ex.focus.sha(manifest)!=provenance['manifest_sha256']
            or ex.focus.sha(audit)!=provenance['audit_sha256']):
        raise ValueError('prior manifest or audit changed')
    previous = read(manifest)
    expected = read(audit)
    if not expected['audit_passed'] or set(expected['measurements'])!=set(methods):
        raise ValueError('prior audit has invalid status or methods')
    for method in methods:
        for pair in map(tuple,lock['methods'][method]['tasks']):
            row = measure(args,method,pair,root/'cases',previous,sat_lock,None,known,lp_tasks,optima,run=False)
            if row is not None and row['status']!='gurobi_error':
                saved[method].append(row)
    if not ex.reports_match(saved,expected['measurements']):
        raise ValueError('prior observations do not match their saved audit')
    for rows in saved.values():
        for row in rows:
            row['replayed_from_prior'] = True
    return saved


def diagnose_gurobi(args, lock, failures, known, deadline):
    if args.diagnostic_ddd is None:
        return 76
    root = args.results/'diagnostics'
    root.mkdir(exist_ok=True)
    profile = dict(lock,binary_sha256=ex.focus.sha(args.diagnostic_ddd),diagnostic_only=True)
    if profile['binary_sha256']==lock['binaries']['ddd']:
        raise ValueError('Gurobi diagnostic must use the instrumented binary')
    identity = {k:profile[k] for k in ('runner_commit','binary_sha256','timeout_seconds','ram_kb',
                                      'cpu_affinity','threads_milp','diagnostic_only')}
    identity['tasks'] = [[f['objective'],f['name']] for f in failures]
    manifest = root/'manifest.json'
    if not manifest.exists():
        ex.save(manifest,identity)
    if read(manifest)!=identity:
        raise ValueError('Gurobi diagnostic protocol changed')
    os.sched_setaffinity(0,set(lock['cpu_affinity']))
    observations = []
    for o,n in map(tuple,identity['tasks']):
        case = root/'cases'/o/n
        receipt = case/'diagnostic.json'
        if not receipt.exists():
            if time.monotonic()>deadline-lock['timeout_seconds']-90:
                return 75
            if case.exists():
                raise ValueError(f'interrupted Gurobi diagnostic: {case}')
            print(f'Gurobi diagnostic {o}/{n}',flush=True)
            ex.run_case(GUROBI_METHOD,o,n,
                        SimpleNamespace(timeout=lock['timeout_seconds'],ram_kb=lock['ram_kb'],binary=args.diagnostic_ddd),
                        case)
        evidence = controls.case_evidence(case,GUROBI_METHOD,o,n,profile)
        row = gurobi_failure(case,(o,n),profile,evidence)
        if row is None:
            row = controls.checked_case(case,GUROBI_METHOD,o,n,profile,known[o,n])
        if receipt.is_file() and read(receipt)['files']!=evidence:
            raise ValueError('saved Gurobi diagnostic evidence changed')
        if not receipt.is_file():
            ex.save(receipt,dict(files=evidence))
        observations.append(row)
        ex.save(root/'audit.json',dict(diagnostic_only=True,observations=observations))
    (args.results/'BLOCKED').touch()
    return 77


def run(args):
    plan, sat_lock, known, lp_tasks = material(args)
    args.results.mkdir(parents=True,exist_ok=True)
    sat_binary, lock = prepare_lock(plan,sat_lock,args)
    deadline = time.monotonic()+args.round_seconds
    methods = (SAT,*controls.METHODS)
    reused = [r for data in lock['methods'].values() for r in data['reused']]
    optima = register_optima(reused)
    measured = replay_prior(args,lock,sat_lock,known,lp_tasks,optima)
    failures = []
    # Replay every committed observation, including stages finished in a
    # previous service invocation, before scheduling more work.
    for method in methods:
        replayed = {(r['objective'],r['name']) for r in measured[method]}
        for pair in map(tuple,lock['methods'][method]['tasks']):
            row = measure(args,method,pair,args.results/'cases',lock,sat_lock,sat_binary,known,optima=optima,
                          lp_tasks=lp_tasks,run=False)
            if row is not None:
                if pair in replayed:
                    raise ValueError('case has evidence in both the prior and recovery directories')
                if row['status']=='gurobi_error':
                    failures.append(row)
                else:
                    measured[method].append(row)
    optima = register_optima(reused+[r for rows in measured.values() for r in rows])
    ex.save(args.results/'audit.json',report(lock,measured,failures))
    for method in methods:
        if method in (SAT,'CSOnet','MaxSAT-Journal'):
            os.sched_setaffinity(0,SAT_CPUS)
        else:
            os.sched_setaffinity(0,set(lock['cpu_affinity']))
        done = {(r['objective'],r['name']) for r in measured[method]}
        done.update((r['objective'],r['name']) for r in failures if r['method']==method)
        for pair in map(tuple,lock['methods'][method]['tasks']):
            if pair in done:
                continue
            if time.monotonic()>deadline-lock['timeout_seconds']-90:
                return 75
            row = measure(args,method,pair,args.results/'cases',lock,sat_lock,sat_binary,known,lp_tasks,optima)
            if row['status']=='gurobi_error':
                failures.append(row)
            else:
                if row['proven'] and optima.setdefault(pair,row['cost'])!=row['cost']:
                    raise ValueError(f'proved optima disagree at {pair}')
                measured[method].append(row)
            ex.save(args.results/'audit.json',report(lock,measured,failures))
    if failures:
        return diagnose_gurobi(args,lock,failures,known,deadline)
    result = report(lock,measured)
    if result['beats_all_baselines'] and measured[SAT]:
        os.sched_setaffinity(0,SAT_CPUS)
        result['confirmations'] = []
        for row in measured[SAT]:
            if not row['proven']:
                continue
            pair = row['objective'],row['name']
            for repeat in (1,2,3):
                kwargs = (args,SAT,pair,args.results/'confirmations',lock,sat_lock,sat_binary,known,lp_tasks,optima)
                record = measure(*kwargs,repeat=repeat,run=False)
                if record is None:
                    if time.monotonic()>deadline-lock['timeout_seconds']-90:
                        return 75
                    record = measure(*kwargs,repeat=repeat)
                result['confirmations'].append(record)
        result['proofs_reproduced'] = all(r['proven'] for r in result['confirmations'])
    else:
        result['proofs_reproduced'] = result['beats_all_baselines']
    result['confirmed_win'] = result['beats_all_baselines'] and result['proofs_reproduced']
    ex.save(args.results/'audit.json',result)
    (args.results/'COMPLETED').touch()
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('plan','run'))
    for key in ('reference','diagnostics','cplex-reference','v47','v45-binary','ddd','cplex','results'):
        p.add_argument('--'+key,type=Path,required=key in ('reference','diagnostics','cplex-reference'))
    p.add_argument('--prior-results',type=Path,help='read-only results directory from the previous extension')
    p.add_argument('--diagnostic-ddd',type=Path,help='native error probe used only after valid measurements')
    p.add_argument('--baseline-1200',type=Path,help='completed 1200-second cutoff audit to extend to 2400 seconds')
    p.add_argument('--after-v49',type=Path,help='run the 2400-second protocol only with no reproduced V49 gain')
    p.add_argument('--round-seconds',type=int,default=21000)
    a = p.parse_args()
    if a.action=='plan':
        plan, _, _, _ = material(a)
        print(json.dumps(dict(label=plan['label'],cutoff=plan['timeout_seconds'],
            methods={m:dict(prior=len(v['reused']),tasks=v['tasks']) for m,v in plan['methods'].items()}),indent=2))
        return 0
    if any(getattr(a,k) is None for k in ('v45_binary','ddd','cplex','results')) or not 0<a.round_seconds<=21600:
        p.error('run requires frozen executable paths, hash, output and a valid phase budget')
    if a.after_v49 is not None:
        if a.baseline_1200 is None or a.v47 is not None:
            p.error('the V49 fallback requires the 1200-second baseline audit and no V47 selection')
        if v49_reproduced(a.after_v49,a.reference,a.diagnostics):
            a.results.mkdir(parents=True,exist_ok=True)
            ex.save(a.results/'SKIPPED',dict(reason='V49 reproduced a new optimum'))
            return 0
    return run(a)


if __name__=='__main__':
    raise SystemExit(main())
