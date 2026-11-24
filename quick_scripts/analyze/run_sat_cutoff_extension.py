#!/usr/bin/env python3
"""Measure only pairs without a saved proof at the next comparison cutoff."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
from types import SimpleNamespace

import bound_quality
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
    if args.v47 is not None:
        sources.append(args.v47/'hard/manifest.json')
        if (args.v47/'full-evaluation.json').is_file():
            sources.extend(args.v47/f for f in ('full-evaluation.json','followup/manifest.json'))
    entries = {}
    for method, observations in rows.items():
        # Independently audited proof rows from shorter runs are valid for
        # coverage. Late proofs and failed launches are never carried over.
        observations = [dict(r,source=method) for r in observations]
        reuse = controls.first_checked_proofs(observations, ALL_PAIRS)
        reused = {pair:{k:r[k] for k in ('objective','name','cost','seconds','timeout_seconds','proven')}
                  for pair,r in reuse.items()}
        if method.startswith('BigM-') and len(reused)!=208:
            raise ValueError(f'incomplete known MILP proofs for {method}')
        at_600 = summarize(observations,600)
        tasks = sorted(ALL_PAIRS-reused.keys()) if cutoff==1200 else [
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
    manifest = args.results/'manifest.json'
    if not manifest.is_file():
        ex.save(manifest,lock)
    if read(manifest) != lock:
        raise ValueError('unsafe extension resume')
    return sat_binary, lock


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
    if not receipt.is_file():
        if not run:
            return None
        if case.exists():
            raise ValueError(f'interrupted baseline case requires review: {case}')
        case.mkdir(parents=True)
        print(f'{method} at {cutoff}s {o}/{n}',flush=True)
        controls.measured_case(SimpleNamespace(method=method,timeout=cutoff,binary=args.ddd,cplex=args.cplex),
                               case,o,n,lp_tasks)
    evidence = controls.case_evidence(case,method,o,n,profile)
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


def report(lock, measured):
    summary = {}
    proven = {}
    for method, data in lock['methods'].items():
        rows = data['reused']+measured[method]
        covered = {(r['objective'],r['name']) for r in rows if r['proven']}
        proven[method] = len(covered)
        summary[method] = dict(proven=len(covered),
            coverage={o:sum(p[0]==o for p in covered) for o in ex.audit.OBJECTIVES},
            reused=len(data['reused']),measured=len(measured[method]),expected=len(data['tasks']),
            external_timeouts=sum(r['status']=='external_timeout' for r in measured[method]),
            complete=len(measured[method])==len(data['tasks']))
    complete = all(s['complete'] for s in summary.values())
    return dict(audit_passed=True,complete=complete,timeout_seconds=lock['timeout_seconds'],
        sat_method=lock['label'],summary=summary,measurements=measured,runtime_comparable=False,
        beats_all_baselines=complete and proven[SAT]>max(v for m,v in proven.items() if m!=SAT))


def run(args):
    plan, sat_lock, known, lp_tasks = material(args)
    args.results.mkdir(parents=True,exist_ok=True)
    sat_binary, lock = prepare_lock(plan,sat_lock,args)
    deadline = time.monotonic()+args.round_seconds
    methods = (SAT,*controls.METHODS)
    measured = {method:[] for method in methods}
    reused = [r for data in lock['methods'].values() for r in data['reused']]
    optima = register_optima(reused)
    # Replay every committed observation, including stages finished in a
    # previous service invocation, before scheduling more work.
    for method in methods:
        for pair in map(tuple,lock['methods'][method]['tasks']):
            row = measure(args,method,pair,args.results/'cases',lock,sat_lock,sat_binary,known,optima=optima,
                          lp_tasks=lp_tasks,run=False)
            if row is not None:
                measured[method].append(row)
    optima = register_optima(reused+[r for rows in measured.values() for r in rows])
    for method in methods:
        if method in (SAT,'CSOnet','MaxSAT-Journal'):
            os.sched_setaffinity(0,SAT_CPUS)
        else:
            os.sched_setaffinity(0,set(lock['cpu_affinity']))
        done = {(r['objective'],r['name']) for r in measured[method]}
        for pair in map(tuple,lock['methods'][method]['tasks']):
            if pair in done:
                continue
            if time.monotonic()>deadline-lock['timeout_seconds']-90:
                ex.save(args.results/'audit.json',report(lock,measured))
                return 75
            row = measure(args,method,pair,args.results/'cases',lock,sat_lock,sat_binary,known,lp_tasks,optima)
            if row['proven'] and optima.setdefault(pair,row['cost'])!=row['cost']:
                raise ValueError(f'proved optima disagree at {pair}')
            measured[method].append(row)
            ex.save(args.results/'audit.json',report(lock,measured))
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
    p.add_argument('--round-seconds',type=int,default=21000)
    a = p.parse_args()
    if a.action=='plan':
        plan, _, _, _ = material(a)
        print(json.dumps(dict(label=plan['label'],cutoff=plan['timeout_seconds'],
            methods={m:dict(prior=len(v['reused']),tasks=v['tasks']) for m,v in plan['methods'].items()}),indent=2))
        return 0
    if any(getattr(a,k) is None for k in ('v45_binary','ddd','cplex','results')) or not 0<a.round_seconds<=21600:
        p.error('run requires frozen executable paths, hash, output and a valid phase budget')
    return run(a)


if __name__=='__main__':
    raise SystemExit(main())
