#!/usr/bin/env python3
"""Finish the 300-second coverage inventory using the corrected Big-M LPs."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import time

import extended_timeout_experiments as ex
from inventory_gurobi_reference import summarize
from rebuild_cplex_recheck import audit_native
from run_gurobi_reference_tail import checked_bounds

CUTOFF = 300
RAM_KB = 6_000_000
SETTINGS = (
    'set threads 4', 'set mip tolerances integrality 1e-9',
    'set simplex tolerances feasibility 1e-9', 'set emphasis numerical y',
    'set mip tolerances mipgap 0', 'set mip tolerances absmipgap 0',
)
DATA = ex.REPO / 'results/sat_research/cplex_full_120_20261108'
ORIGINAL = DATA / 'raw_snapshot.tar.gz'
CORRECTION = DATA / 'bound_recheck_20261109/raw_snapshot.tar.gz'
REFERENCE = ex.REPO / 'results/sat_research/v42_sat_bound_search_20261109/full_evaluation.json'
TIGHT_TRACK = ('infsteps180', 'trackA8')


def recover_track_proof(archive, prefix):
    folder = DATA/'tight_fix'
    receipts = json.loads((DATA/'archive_hashes.json').read_text())
    lp_name = 'InstanceA8_bigm_infsteps180.lp'
    for name in (lp_name, 'cplex.log', 'schedule.sol'):
        file = folder/name
        if ex.focus.sha(file) != receipts[str(file.relative_to(DATA))]:
            raise ValueError('changed trackA8 correction')
    lp = folder/lp_name
    if hashlib.sha256(archive.extractfile(prefix+lp.name).read()).hexdigest() != ex.focus.sha(lp):
        raise ValueError('trackA8 correction changed the LP')
    solve = ex.cplex_result(folder/'schedule.sol',folder/'cplex.log','trackA8','infsteps180',120,120)
    if not ex.audit.bounds_prove_optimal(solve) or solve['cost'] != 146:
        raise ValueError('trackA8 correction no longer proves the optimum')
    return solve


def source_material():
    corrected = audit_native(CORRECTION, ORIGINAL)
    fixed = (corrected['manifest']['objective'], corrected['manifest']['name'])
    known = json.loads(REFERENCE.read_text())
    reference = {(r['objective'], r['name']): r for r in known['cases']}
    expected = {(o, n) for o in ex.audit.OBJECTIVES for n in ex.common.EXPECTED_NAMES}
    if (set(reference) != expected or len(known['cases']) != len(expected)
            or not known.get('candidate_audit_passed') or not known['full_comparison']['complete']):
        raise ValueError('expected checked V42 reference')
    records, tasks = [], []
    with tarfile.open(ORIGINAL) as archive:
        members = archive.getmembers()
        for objective, name in sorted(expected):
            prefix = f'cases/BigM-CPLEX/{objective}/{name}/'
            raw_name = prefix + objective + '.json'
            if (objective,name) == TIGHT_TRACK:
                solve = recover_track_proof(archive,prefix)
                raw_name = 'tight_fix/schedule.sol'
            else:
                raw = json.load(archive.extractfile(raw_name))
                if len(raw) != 1 or raw[0]['name'] != name or len(raw[0]['solves']) != 1:
                    raise ValueError('unexpected original CPLEX case identity')
                solve = raw[0]['solves'][0]
            if (objective, name) == fixed:
                solve = dict(corrected['solve'], total_time=corrected['solve']['total_time'] + solve['build_time'])
                raw_name = CORRECTION.name + '#tight_recheck'
            status = solve['status']
            if status not in ('ok','timeout'):
                raise ValueError('original CPLEX case is invalid')
            time_used = solve['total_time']
            if not math.isfinite(time_used) or time_used < 0:
                raise ValueError('original CPLEX time is invalid')
            proof = status == 'ok' and ex.audit.bounds_prove_optimal(solve) and time_used <= 120
            checked_bounds(dict(proven=proof,solve=solve), reference[objective,name])
            if solve.get('solution') is not None:
                errors = ex.common.independently_verify_solution(name, objective, solve)
                if errors:
                    raise ValueError(f'{objective}/{name}: {errors}')
            if proof and solve.get('solution') is None:
                raise ValueError('reused proof lacks a feasible schedule')
            records.append(dict(objective=objective,name=name,status=status,seconds=time_used,
                timeout_seconds=120,proven=proof,upper_witness_verified=proof,source=raw_name))
            if not proof:
                lp, = [m for m in members if m.isfile() and m.name.startswith(prefix) and m.name.endswith('.lp')]
                build = solve['build_time']
                if not math.isfinite(build) or not 0 <= build < 120:
                    raise ValueError('original LP export time is invalid')
                tasks.append(dict(objective=objective,name=name,lp_member=lp.name,
                    lp_sha256=hashlib.sha256(archive.extractfile(lp).read()).hexdigest(),
                    export_seconds=build))
    inventory = summarize(records,120)
    if not inventory['complete'] or inventory['total'] != 205 or len(tasks) != 11:
        raise ValueError('corrected CPLEX source must contain 205 proofs and 11 timeouts')
    return records, tasks, reference


def case_path(root, task):
    return root/'cases'/task['objective']/task['name']


def replay_case(case, task, reference):
    receipt = json.loads((case/'completion.json').read_text())
    objective, name = task['objective'], task['name']
    outputs = {name: ex.focus.sha(case/name) for name in ('model.lp', 'cplex.log', 'result.json')}
    if (case/'schedule.sol').exists():
        outputs['schedule.sol'] = ex.focus.sha(case/'schedule.sol')
    if outputs != receipt['files'] or outputs['model.lp'] != task['lp_sha256']:
        raise ValueError('CPLEX receipt or original model differs')
    solve = json.loads((case/'result.json').read_text())
    rebuilt = ex.cplex_result(case/'schedule.sol',case/'cplex.log',name,objective,CUTOFF,solve['total_time'])
    if rebuilt != solve:
        raise ValueError('CPLEX result differs from its native output')
    seconds = solve['total_time']
    if not math.isfinite(seconds) or not 0 <= seconds <= CUTOFF + 35:
        raise ValueError('CPLEX elapsed time is invalid')
    proven = solve['status']=='ok' and ex.audit.bounds_prove_optimal(solve) and seconds <= CUTOFF
    checked_bounds(dict(proven=proven,solve=solve),reference[objective,name])
    return dict(objective=objective,name=name,status=solve['status'],seconds=seconds,
        timeout_seconds=CUTOFF,proven=proven,upper_witness_verified=proven,
        source=f"tail/{objective}/{name}",lb=solve.get('lb'),ub=solve.get('ub'),cost=solve.get('cost'))


def audit(root, material):
    reused,tasks,reference = material
    manifest = json.loads((root/'manifest.json').read_text())
    if (manifest['tasks'] != tasks or manifest['settings'] != list(SETTINGS)
            or manifest['dataset_sha256'] != ex.focus.dataset_hash()
            or manifest['original_sha256'] != ex.focus.sha(ORIGINAL)
            or manifest['correction_sha256'] != ex.focus.sha(CORRECTION)
            or manifest['source_receipts_sha256'] != ex.focus.sha(DATA/'archive_hashes.json')
            or manifest['reference_sha256'] != ex.focus.sha(REFERENCE)):
        raise ValueError('CPLEX baseline sources or settings changed')
    records = [replay_case(case_path(root,task),task,reference) for task in tasks
               if (case_path(root,task)/'completion.json').exists()]
    inventory = summarize(reused + records,CUTOFF)
    return dict(audit_passed=True,complete=inventory['complete'] and len(records)==len(tasks),
        inventory=inventory, cases=records, expected_runs=len(tasks), completed_runs=len(records),
        reused_proven=205,runtime_comparable=False)


def run(root, cplex, round_seconds):
    material = source_material()
    _,tasks,_ = material
    manifest = dict(schema='cplex-reference-tail-v1', tasks=tasks, settings=list(SETTINGS),
        timeout_seconds=CUTOFF, ram_kb=RAM_KB, cpu_affinity=sorted(os.sched_getaffinity(0)),
        runner_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip(),
        cplex_sha256=ex.focus.sha(cplex),dataset_sha256=ex.focus.dataset_hash(),
        original_sha256=ex.focus.sha(ORIGINAL),correction_sha256=ex.focus.sha(CORRECTION),
        source_receipts_sha256=ex.focus.sha(DATA/'archive_hashes.json'),
        reference_sha256=ex.focus.sha(REFERENCE),timeout_includes_original_export=True)
    root.mkdir(parents=True,exist_ok=True)
    path = root/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError('unsafe CPLEX resume')
    ex.save(path,manifest)
    deadline = time.monotonic() + round_seconds
    with tarfile.open(ORIGINAL) as archive:
        for task in tasks:
            case = case_path(root,task)
            if (case/'completion.json').is_file():
                continue
            if deadline-time.monotonic()<CUTOFF+40:
                break
            if case.exists():
                raise ValueError('interrupted CPLEX case needs review')
            case.mkdir(parents=True)
            (case/'model.lp').write_bytes(archive.extractfile(task['lp_member']).read())
            objective,name = task['objective'],task['name']
            print(f'CPLEX 300 s {objective}/{name}',flush=True)
            solve_seconds = CUTOFF - task['export_seconds']
            command = [str(cplex),'-c','read model.lp',*SETTINGS,
                       f'set timelimit {solve_seconds:.6f}','optimize',
                       'display solution bestbound','write schedule.sol','quit']
            elapsed = ex.execute(command,case,case/'cplex.log',solve_seconds+30,os.environ,RAM_KB)
            solve = ex.cplex_result(case/'schedule.sol',case/'cplex.log',name,objective,CUTOFF,
                                    task['export_seconds'] + elapsed)
            ex.save(case/'result.json',solve)
            files = ['model.lp','cplex.log','result.json']
            if (case/'schedule.sol').exists():
                files.append('schedule.sol')
            ex.save(case/'completion.json',dict(files={f:ex.focus.sha(case/f) for f in files}))
            ex.save(root/'audit.json',audit(root,material))
    ex.save(root/'audit.json',audit(root,material))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('run','audit'))
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--cplex',type=Path)
    parser.add_argument('--round-seconds',type=int,default=21600)
    args = parser.parse_args()
    if args.action=='run':
        if args.cplex is None or not 0 < args.round_seconds <= 21600:
            parser.error('provide CPLEX and a round limit of at most six hours')
        run(args.results.resolve(),args.cplex.resolve(),args.round_seconds)
    else:
        print(json.dumps(audit(args.results.resolve(),source_material()),indent=2))
