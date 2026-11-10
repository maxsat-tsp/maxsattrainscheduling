#!/usr/bin/env python3
"""Complete only the missing Gurobi cutoff cases, preserving all earlier runs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
from types import SimpleNamespace

import extended_timeout_experiments as ex
from inventory_gurobi_reference import summarize


def checked_bounds(row,reference):
    solve=row['solve'];lo=ex.audit.finite_number(solve.get('lb'));hi=ex.audit.finite_number(solve.get('ub'))
    if ((lo is not None and lo>reference['ub']+1e-6) or (hi is not None and hi<reference['lb']-1e-6)
            or (row['proven'] and reference['proven'] and solve.get('cost')!=reference['cost'])):
        raise ValueError('new MILP bounds contradict the audited SAT reference')


def audit(root):
    m=json.loads((root/'manifest.json').read_text());inventory=Path(m['inventory'])
    if ex.focus.sha(inventory)!=m['inventory_sha256'] or m['dataset_sha256']!=ex.focus.dataset_hash():raise ValueError('inventory or dataset changed')
    old=json.loads(inventory.read_text())
    if m['tasks']!=old['at_target']['missing_at_cutoff']:raise ValueError('tail selection changed')
    checked=Path(m['checked_reference'])
    if ex.focus.sha(checked)!=m['checked_reference_sha256']:raise ValueError('checked reference changed')
    reference=json.loads(checked.read_text())
    if not reference.get('candidate_audit_passed') or not (reference.get('full_comparison') or {}).get('complete'):raise ValueError('reference is not an audited full search')
    known={(r['objective'],r['name']):r for r in reference['cases']}
    if len(reference['cases'])!=216 or set(known)!={(o,n) for o in ex.audit.OBJECTIVES for n in ex.common.EXPECTED_NAMES}:raise ValueError('incomplete checked reference')
    records=list(old['records']);completed=[]
    for o,n in m['tasks']:
        case=root/'cases/BigM-Gurobi'/o/n
        if not (case/'completion.json').exists():continue
        receipt=json.loads((case/'completion.json').read_text())
        if receipt['raw_sha256']!=ex.focus.sha(case/(o+'.json')):raise ValueError('changed Gurobi tail result')
        provenance=dict(line.split('=',1) for line in (case/'logs/manifest.txt').read_text().splitlines() if '=' in line)
        expected=dict(git_commit=m['runner_commit'],binary_sha256=m['binary_sha256'],solver='bigm_lazy',
            objective=o,selected_instances=n,selected_instance_count='1',instance_timeout_seconds=str(m['timeout_seconds']),ram_limit_kb=str(m['ram_kb']))
        if any(provenance.get(k)!=v for k,v in expected.items()):raise ValueError('tail provenance differs from its manifest')
        row=ex.assess_case(case,'BigM-Gurobi',o,n,m['timeout_seconds'])
        if row['errors'] or row['status'] in ex.audit.FATAL_STATUSES:raise ValueError(str(row['errors']))
        checked_bounds(row,known[o,n])
        solve=row['solve'];completed.append(dict(objective=o,name=n,status=row['status'],proven=row['proven'],seconds=row['time'],lb=solve.get('lb'),ub=solve.get('ub'),cost=solve.get('cost')))
        records.append(dict(objective=o,name=n,status=row['status'],proven=row['proven'],seconds=row['time'],
            timeout_seconds=m['timeout_seconds'],upper_witness_verified=row['proven'],source=str(case/(o+'.json'))))
    summary=summarize(records,m['timeout_seconds'])
    return dict(schema='gurobi-reference-tail-audit-v1',audit_passed=True,complete=len(completed)==len(m['tasks']) and summary['complete'],
        completed_runs=len(completed),expected_runs=len(m['tasks']),cases=completed,
        inventory=summary,submission_passed=False,runtime_comparable=False,
        scope='coverage from audited reused fast proofs plus the missing long-cutoff observations; versions/hardware assumptions remain explicit')


def run(a):
    inventory=json.loads(a.inventory.read_text());cutoff=inventory['cutoff_seconds']
    if inventory['dataset_sha256']!=ex.focus.dataset_hash() or cutoff!=300:raise ValueError('wrong tail protocol')
    with tarfile.open(a.build_evidence) as t:build=json.load(t.extractfile('./build_manifest.json'))
    if build['ordinary_binary_sha256']!=ex.focus.sha(a.binary):raise ValueError('ordinary binary differs from native build evidence')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():raise ValueError('commit the tail runner first')
    tasks=inventory['at_target']['missing_at_cutoff']
    if len(tasks)!=len({tuple(t) for t in tasks}) or any(o not in ex.audit.OBJECTIVES or n not in ex.common.EXPECTED_NAMES for o,n in tasks):raise ValueError('invalid tail selection')
    m=dict(schema='gurobi-reference-tail-v1',runner_commit=commit,binary_source_commit=build['git_commit'],
        binary_sha256=ex.focus.sha(a.binary),build_evidence_sha256=ex.focus.sha(a.build_evidence),
        inventory=str(a.inventory.resolve()),inventory_sha256=ex.focus.sha(a.inventory),
        dataset_sha256=ex.focus.dataset_hash(),timeout_seconds=cutoff,ram_kb=6000000,tasks=tasks,
        cpu_affinity=sorted(os.sched_getaffinity(0)),
        checked_reference=str(a.checked_reference.resolve()),checked_reference_sha256=ex.focus.sha(a.checked_reference),
        reference_is_not_solver_input=True,
        case_git_commit_describes_runner=True,runtime_comparable=False)
    a.results.mkdir(parents=True,exist_ok=True)
    if (a.results/'manifest.json').exists() and json.loads((a.results/'manifest.json').read_text())!=m:raise ValueError('unsafe tail resume')
    ex.save(a.results/'manifest.json',m)
    runtime=SimpleNamespace(timeout=cutoff,ram_kb=m['ram_kb'],binary=a.binary)
    deadline=time.monotonic()+a.round_seconds
    for o,n in tasks:
        case=a.results/'cases/BigM-Gurobi'/o/n;raw=case/(o+'.json')
        if not (case/'completion.json').exists():
            if raw.exists() or (case/'logs').exists():raise ValueError('interrupted baseline case needs review')
            if deadline-time.monotonic()<cutoff+60:break
            print('Gurobi tail',o,n,flush=True);ex.run_case('BigM-Gurobi',o,n,runtime,case)
            row=ex.assess_case(case,'BigM-Gurobi',o,n,cutoff)
            if row['errors'] or row['status'] in ex.audit.FATAL_STATUSES:raise ValueError(str(row['errors']))
            ex.save(case/'completion.json',dict(raw_sha256=ex.focus.sha(raw)))
        ex.save(a.results/'audit.json',audit(a.results))
    ex.save(a.results/'audit.json',audit(a.results))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['run','audit'])
    p.add_argument('--results',type=Path,required=True);p.add_argument('--inventory',type=Path)
    p.add_argument('--binary',type=Path);p.add_argument('--build-evidence',type=Path)
    p.add_argument('--checked-reference',type=Path,default=ex.REPO/'results/sat_research/v42_sat_bound_search_20261109/full_evaluation.json')
    p.add_argument('--round-seconds',type=int,default=18000);a=p.parse_args()
    if a.action=='audit':print(json.dumps(audit(a.results),indent=2))
    else:
        if any(x is None for x in (a.inventory,a.binary,a.build_evidence)) or not 0<a.round_seconds<=21600:p.error('missing build/input or invalid round budget')
        try:run(a)
        except BaseException as error:
            if a.results.is_dir():ex.save(a.results/'failure.json',dict(error=str(error)))
            raise
