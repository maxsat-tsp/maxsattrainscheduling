"""Complete the long-cutoff controls on the candidate's frozen hard set."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import time
from types import SimpleNamespace

import extended_timeout_experiments as ex
import run_cplex_reference_tail as cp
from bound_quality import interval
from inventory_gurobi_reference import build_pool
from report_threshold_cutoffs import baseline_rows, SAT_SOURCES
from run_gurobi_reference_tail import checked_bounds

CUTOFF = 600
METHODS = ('BigM-Gurobi', 'BigM-CPLEX', 'CSOnet', 'MaxSAT-Journal')
RESEARCH = ex.REPO/'results/sat_research'
BASELINE_SNAPSHOT = RESEARCH/'v45_sat_bound_search_20261120/sat_baselines120_snapshot.tar.gz'
GUROBI_RAW = {
    'finsteps123': RESEARCH/'baseline_inventory_20261110/gurobi_finsteps123_source.json',
    'cont': RESEARCH/'v39_bound_diagnostics_20261109/gurobi_cont_source.json',
    'infsteps180': RESEARCH/'v40_sat_bound_search_20261109/gurobi_infsteps180_source.json',
}


def first_checked_proofs(rows, pairs):
    proofs = {}
    for row in rows:
        key = row['objective'],row['name']
        if key not in pairs or not row.get('proven') or not row.get('upper_witness_verified'):
            continue
        cost, seconds = row.get('cost'), row.get('seconds')
        if (isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost)
                or int(cost) != cost or cost < 0 or not isinstance(seconds,(int,float))
                or not math.isfinite(seconds) or seconds < 0):
            raise ValueError(f'invalid reusable proof for {key}')
        if seconds > min(CUTOFF,row['timeout_seconds']):
            continue
        if key in proofs and proofs[key]['cost'] != cost:
            raise ValueError(f'checked proof costs disagree for {key}')
        proofs.setdefault(key, dict(row, lb=cost, ub=cost, reused=True))
    return proofs


def plan_material(method, pairs, cplex_reference):
    cplex_tasks = {}
    if method == 'BigM-CPLEX':
        material = cp.source_material()
        proof_rows, tasks, _ = material
        cplex_tasks = {(r['objective'],r['name']):r for r in tasks}
        sources = [cp.ORIGINAL, cp.CORRECTION, cp.DATA/'archive_hashes.json']
        if cplex_reference is not None and (cplex_reference/'manifest.json').is_file():
            report = cp.audit(cplex_reference,material)
            proof_rows += [dict(row, source=str(cplex_reference/row['source'].replace('tail/','cases/',1)/'result.json'))
                           for row in report['cases']]
            sources.append(cplex_reference/'manifest.json')
            sources += [cplex_reference/'cases'/r['objective']/r['name']/'completion.json' for r in report['cases']]
    elif method == 'BigM-Gurobi':
        sources = [*GUROBI_RAW.values(),*(RESEARCH/p for p in SAT_SOURCES)]
        pool = build_pool(GUROBI_RAW.items(),sources[3:])
        proof_rows = pool.records
    else:
        sources = [BASELINE_SNAPSHOT,*(RESEARCH/p for p in SAT_SOURCES)]
        proof_rows = baseline_rows(BASELINE_SNAPSHOT)[method]
    return first_checked_proofs(proof_rows,pairs), cplex_tasks, {str(p):ex.focus.sha(p) for p in sources}


def case_record(case, method, row, known):
    solve = row['solve']
    if row['errors'] or row['status'] not in ('ok','timeout'):
        raise ValueError(f'{method} failed audit at {case}: {row["errors"]}')
    seconds = row['time']
    if not math.isfinite(seconds) or (row['status']=='timeout' and seconds < CUTOFF - 0.5):
        raise ValueError('baseline stopped before the measured cutoff')
    proven = row['status']=='ok' and row['proven'] and ex.audit.bounds_prove_optimal(solve) and seconds <= CUTOFF
    checked_bounds(dict(proven=proven,solve=solve),known)
    return dict(objective=row['objective'],name=row['name'],status=row['status'],seconds=seconds,
        timeout_seconds=CUTOFF,proven=proven,upper_witness_verified=solve.get('solution') is not None,
        source=str(case),lb=solve.get('lb'),ub=solve.get('ub'),cost=solve.get('cost'),reused=False)


def measured_case(args, case, o, n, cplex_tasks, known):
    if args.method == 'BigM-CPLEX':
        with tarfile.open(cp.ORIGINAL) as archive:
            task = cplex_tasks[o,n]
            lp = archive.extractfile(task['lp_member']).read()
        solve = cp.execute_saved_lp(args.cplex,case,task,lp,CUTOFF)
        ex.save(case/(o+'.json'),[dict(name=n,solves=[solve])])
    else:
        ex.run_case(args.method,o,n,SimpleNamespace(timeout=CUTOFF,ram_kb=cp.RAM_KB,binary=args.binary),case)
    row = ex.assess_case(case,args.method,o,n,CUTOFF)
    return case_record(case,args.method,row,known)


def case_evidence(case, method, objective, name, lock):
    files = [objective+'.json']
    if method == 'BigM-CPLEX':
        files += ['model.lp','cplex.log']
        if (case/'schedule.sol').exists():
            files.append('schedule.sol')
    else:
        path = 'logs/manifest.txt'
        fields = dict(line.split('=',1) for line in (case/path).read_text().splitlines() if '=' in line)
        expected = dict(binary_sha256=lock['binary_sha256'],git_commit=lock['runner_commit'],
            solver=ex.METHODS[method]['solver'],objective=objective,selected_instances=name,
            instance_timeout_seconds=str(CUTOFF),ram_limit_kb=str(cp.RAM_KB))
        if any(fields.get(k) != v for k,v in expected.items()):
            raise ValueError('baseline run does not match its manifest')
        files.append(path)
    return {file:ex.focus.sha(case/file) for file in files}


def run(args):
    candidate = json.loads(args.candidate_manifest.read_text())
    pairs = [(r['objective'],r['name']) for r in candidate['tasks']]
    if (candidate['dataset_sha256'] != ex.focus.dataset_hash() or candidate['timeout_seconds'] != CUTOFF
            or len(pairs) != 11 or len(set(pairs)) != 11 or any(r['repeat'] != 0 for r in candidate['tasks'])):
        raise ValueError('expected the locked eleven-pair candidate screening manifest')
    clean = subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO)
    if clean.strip():
        raise ValueError('baseline runner must use a clean pinned source')
    proofs, cplex_tasks, sources = plan_material(args.method, set(pairs), args.cplex_reference)
    reference = json.loads(cp.REFERENCE.read_text())
    known = {(r['objective'],r['name']):r for r in reference['cases']}
    root = args.results.resolve()
    root.mkdir(parents=True,exist_ok=True)
    lock = dict(method=args.method,timeout_seconds=CUTOFF,ram_kb=cp.RAM_KB,threads_milp=4,
        candidate_manifest_sha256=ex.focus.sha(args.candidate_manifest),
        runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip(),
        binary_sha256=ex.focus.sha(args.cplex if args.method=='BigM-CPLEX' else args.binary),
        cpu_affinity=sorted(os.sched_getaffinity(0)),dataset_sha256=candidate['dataset_sha256'],
        sources=sources, tasks=[dict(objective=o,name=n,reused_proof=proofs.get((o,n))) for o,n in pairs])
    manifest = root/'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text()) != lock:
        raise ValueError('unsafe baseline resume')
    ex.save(manifest,lock)
    records = []
    deadline = time.monotonic() + args.round_seconds
    for o,n in pairs:
        if (o,n) in proofs:
            record = proofs[o,n]
            checked_bounds(dict(proven=True,solve=record),known[o,n])
        else:
            case = root/'cases'/o/n
            receipt = case/'completion.json'
            if receipt.is_file():
                saved = json.loads(receipt.read_text())
                if saved['files'] != case_evidence(case,args.method,o,n,lock):
                    raise ValueError('completed baseline result changed')
                record = case_record(case,args.method,ex.assess_case(case,args.method,o,n,CUTOFF),known[o,n])
            else:
                if time.monotonic() > deadline - CUTOFF - 90:
                    break
                if case.exists():
                    raise ValueError(f'interrupted baseline requires review: {case}')
                case.mkdir(parents=True)
                print(f'{args.method} at {CUTOFF}s: {o}/{n}',flush=True)
                record = measured_case(args,case,o,n,cplex_tasks,known[o,n])
                ex.save(receipt,dict(files=case_evidence(case,args.method,o,n,lock)))
        interval(record.get('lb'),record.get('ub'))
        records.append(record)
        ex.save(root/'audit.json',dict(audit_passed=True,method=args.method,timeout_seconds=CUTOFF,
            complete=len(records)==len(pairs),expected_runs=len(pairs),completed_runs=len(records),
            proven=sum(r['proven'] for r in records),reused=sum(r['reused'] for r in records),
            runtime_comparable=all(not r['reused'] for r in records),cases=records))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method',choices=METHODS,required=True)
    for name in ('candidate-manifest','results','binary','cplex'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--cplex-reference',type=Path)
    parser.add_argument('--round-seconds',type=int,default=21000)
    args=parser.parse_args()
    if not CUTOFF + 90 < args.round_seconds <= 21600:
        parser.error('the round must allow one full case and last at most six hours')
    run(args)
