#!/usr/bin/env python3
"""Separate finding a schedule, proving optimality and moving RC2 bounds.

Oracle-assisted diagnostics are never included in solved coverage.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import time

import extended_timeout_experiments as ex
import targeted_order_cycles as trial

MODES = ('at-opt', 'below-opt', 'oracle-ub', 'control')
MIP_SOLVERS = {'BigMLazy', 'BigM_CPLEX_Eager'}


def integer(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not an objective value')
    try:number = float(value)
    except (TypeError,ValueError) as error:
        raise ValueError('missing or invalid MIP cost/bound') from error
    if not math.isfinite(number) or number < 0 or abs(number-round(number)) > 1e-6:
        raise ValueError('MIP cost or bound is not a nonnegative integer')
    return int(round(number))


def mip_oracles(selection, files):
    found = {}
    for objective, path in files:
        rows = ex.common.load_rows(path)
        names = [name for name, _ in rows]
        if len(names) != len(set(names)) or not set(names).issubset(ex.common.EXPECTED_NAMES):
            raise ValueError('duplicate or unknown MIP instance')
        for name, solve in rows:
            if name not in selection.get(objective, []) or solve.get('status') != 'ok':
                continue
            if solve.get('solver_name') not in MIP_SOLVERS:
                raise ValueError('oracle was not produced by a supported Big-M solver')
            if solve.get('process_exit_code', 0) != 0:
                raise ValueError('MIP process did not exit cleanly')
            cost, lb, ub = [integer(solve.get(k)) for k in ('cost', 'lb', 'ub')]
            if cost != lb or cost != ub:
                raise ValueError('MIP status=ok without a proved optimum')
            errors = ex.common.independently_verify_solution(name, objective, solve)
            if errors:
                raise ValueError(str(errors))
            key = (objective, name)
            if key in found and found[key]['optimum'] != cost:
                raise ValueError('MIP optima disagree')
            if key not in found:
                found[key] = dict(objective=objective, name=name, optimum=cost,
                    solution=solve['solution'], solver=solve['solver_name'],
                    source_file=str(path.resolve()), source_sha256=ex.focus.sha(path))
    if not found:
        raise ValueError('no unresolved MaxSAT case has an independently checked Big-M optimum')
    return [found[key] for key in sorted(found)]


def check_result(record, oracle, mode, cutoff):
    if record.get('schema') != 'bound-diagnostic-v1' or record.get('mode') != mode:
        raise ValueError('wrong diagnostic schema or mode')
    if record.get('objective') != oracle['objective'] or record.get('oracle_optimum') != oracle['optimum']:
        raise ValueError('diagnostic objective or oracle changed')
    if record.get('submission_eligible') is not False or record.get('diagnostic_only') is not True:
        raise ValueError('oracle-assisted run is not clearly separated from coverage')
    if record.get('timeout_seconds') != cutoff:
        raise ValueError('timeout changed')
    if record.get('maxsat_backend') != 'minisat' or 'MiniSAT' not in record.get('maxsat_backend_signature', ''):
        raise ValueError('wrong native SAT backend')
    definition = dict(maxsat_resource_orders=True, maxsat_order_transitivity=True,
        maxsat_assumptions='legacy',maxsat_sparse_costs=False,
        maxsat_core_minimize_checks=4, maxsat_core_minimize_conflicts=100,
        maxsat_core_exhaust_checks=4, maxsat_core_trim_checks=0, maxsat_am1_checks=0)
    if any(record.get(k) != v for k,v in definition.items()):
        raise ValueError('diagnostic is not using the locked V17 configuration')
    target = oracle['optimum']-(mode=='below-opt') if mode in ('at-opt','below-opt') else None
    if record.get('diagnostic_target') != target:
        raise ValueError('wrong fixed objective threshold')
    if record.get('maxsat_objective_bound') != (target is not None):
        raise ValueError('wrong use of the hard objective bound')
    supplied = oracle['optimum'] if mode == 'oracle-ub' else None
    if record.get('diagnostic_supplied_ub') != supplied:
        raise ValueError('wrong oracle upper bound')
    status = record.get('status')
    expected = 'sat' if mode == 'at-opt' else 'unsat' if mode == 'below-opt' else 'optimal'
    if status not in ('timeout', expected):
        raise ValueError(f'unexpected diagnostic result: {mode}/{status}')
    seconds = record.get('seconds')
    if not isinstance(seconds, (int,float)) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('invalid runtime')
    if status == 'timeout' and seconds < cutoff-0.5:
        raise ValueError('timeout ended before its deadline')
    if status in ('sat', 'optimal'):
        errors = ex.common.independently_verify_solution(oracle['name'], oracle['objective'], record)
        if errors or record.get('cost') != oracle['optimum']:
            raise ValueError(f'invalid or nonoptimal diagnostic schedule: {errors}')
    if status == 'sat' and record.get('diagnostic_outcome') != 'sat':
        raise ValueError('SAT outcome evidence missing')
    if status == 'optimal' and (record.get('lb') != oracle['optimum'] or record.get('ub') != oracle['optimum']):
        raise ValueError('RC2 did not independently close the bound')
    if status == 'unsat' and record.get('diagnostic_outcome') != 'unsat':
        raise ValueError('UNSAT outcome evidence missing')
    if target is not None and status != 'timeout' and record.get('maxsat_core_literals') != 0:
        raise ValueError('fixed-bound decision performed RC2 core optimization')
    return dict(objective=oracle['objective'], name=oracle['name'], optimum=oracle['optimum'],
        mode=mode, status=status, seconds=seconds, lower_bound=record.get('lb',record.get('diagnostic_lb')),
        upper_bound=record.get('ub',record.get('diagnostic_ub')),
        sat_seconds=record.get('native_sat_seconds'), sat_calls=record.get('native_sat_calls'),
        iterations=record.get('iterations',record.get('diagnostic_iterations')),
        variables=record.get('variables'), clauses=record.get('clauses'))


def audit(root, reference=None):
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest['dataset_sha256'] != ex.focus.dataset_hash():
        raise ValueError('dataset changed')
    if reference is not None:
        _,selection,digests=trial.load_reference(reference)
        if (selection != manifest['unresolved_selection'] or digests != manifest['reference_raw_sha256']
                or ex.focus.sha(reference/'manifest.json') != manifest['reference_manifest_sha256']
                or ex.focus.sha(reference/'full_audit.json') != manifest['reference_audit_sha256']):
            raise ValueError('MaxSAT reference changed')
    for oracle in manifest['oracles']:
        source=root/'mip_sources'/(oracle['source_sha256']+'.json')
        if ex.focus.sha(source) != oracle['source_sha256']:
            raise ValueError('Big-M source changed')
        rebuilt=mip_oracles({oracle['objective']:[oracle['name']]},[(oracle['objective'],source)])
        if len(rebuilt)!=1 or any(rebuilt[0][k] != oracle[k] for k in
                ('objective','name','optimum','solution','solver','source_sha256')):
            raise ValueError('oracle does not match an independently verified Big-M result')
    records=[]
    for oracle in manifest['oracles']:
        for mode in manifest['modes']:
            case=root/'cases'/oracle['objective']/oracle['name']/mode
            path=case/'result.json'
            if not path.exists():
                continue
            launch=json.loads((case/'launch.json').read_text())
            if launch != dict(binary_sha256=manifest['binary_sha256'], commit=manifest['commit'],
                objective=oracle['objective'], name=oracle['name'], mode=mode, optimum=oracle['optimum'],
                timeout=manifest['timeout_seconds'], ram_kb=manifest['ram_kb'],
                instance_sha256=ex.focus.sha(ex.common.instance_path(oracle['name'])),
                oracle_sha256=ex.focus.sha(case/'oracle.json') if mode=='oracle-ub' else None):
                raise ValueError('case launch differs from locked provenance')
            evidence=json.loads((case/'completion.json').read_text())
            if evidence.get('returncode') != 0 or evidence.get('result_sha256') != ex.focus.sha(path):
                raise ValueError('failed diagnostic process or modified result')
            trace=case/'result.trace.jsonl'
            if evidence.get('trace_sha256') != ex.focus.sha(trace):
                raise ValueError('progress trace changed')
            entries=[json.loads(line) for line in trace.read_text().splitlines()]
            if not entries or entries[0]['lb'] != 0:
                raise ValueError('RC2 lower bound was not initialized independently')
            record=check_result(json.loads(path.read_text()),oracle,mode,manifest['timeout_seconds'])
            records.append(record)
    expected=len(manifest['oracles'])*len(manifest['modes'])
    return dict(schema='bound-diagnostics-audit-v1',complete=len(records)==expected,
        expected_runs=expected,completed_runs=len(records),audit_passed=True,records=records,
        submission_eligible=False,scope='oracle-assisted diagnosis only; no new coverage claim')


def run(args):
    source,selection,digests=trial.load_reference(args.reference)
    oracles=mip_oracles(selection,[(o,Path(p)) for o,p in args.mip])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():
        raise ValueError('commit diagnostic code before running')
    root=args.results.resolve();root.mkdir(parents=True,exist_ok=True)
    build=json.loads(args.build_manifest.read_text())
    binary_sha=ex.focus.sha(args.binary)
    if build['git_commit'] != commit or build['binary_sha256'] != binary_sha:
        raise ValueError('build manifest does not match pinned source/binary')
    manifest=dict(schema='bound-diagnostics-v1',commit=commit,binary_sha256=binary_sha,
        dataset_sha256=ex.focus.dataset_hash(),reference_manifest_sha256=ex.focus.sha(args.reference/'manifest.json'),
        reference_audit_sha256=ex.focus.sha(args.reference/'full_audit.json'),
        reference_raw_sha256=digests,build_manifest_sha256=ex.focus.sha(args.build_manifest),
        script_sha256=ex.focus.sha(Path(__file__)),timeout_seconds=source['timeout_seconds'],
        ram_kb=source['ram_kb'],modes=list(MODES),oracles=oracles,
        unresolved_selection=selection,cpu_affinity=sorted(os.sched_getaffinity(0)),submission_eligible=False)
    if (root/'manifest.json').exists() and json.loads((root/'manifest.json').read_text())!=manifest:
        raise ValueError('unsafe resume: source, data, oracle, binary or parameters changed')
    ex.save(root/'manifest.json',manifest)
    (root/'build_manifest.json').write_bytes(args.build_manifest.read_bytes())
    # Keep exact oracle source files available for independent rechecking.
    for oracle in oracles:
        path=root/'mip_sources'/(oracle['source_sha256']+'.json')
        path.parent.mkdir(exist_ok=True)
        if not path.exists():path.write_bytes(Path(oracle['source_file']).read_bytes())
    deadline=time.monotonic()+args.round_seconds
    for oracle in oracles:
        for mode in MODES:
            case=root/'cases'/oracle['objective']/oracle['name']/mode
            if (case/'result.json').exists():
                audit(root) # Reuse only completed, audited cases.
                continue
            if deadline-time.monotonic()<manifest['timeout_seconds']+60:
                ex.save(root/'audit.json',audit(root));return
            case.mkdir(parents=True,exist_ok=True)
            if (case/'launch.json').exists():
                raise ValueError('interrupted case must be preserved and reviewed before rerunning')
            command=[str(args.binary.resolve()),'--instance',str(ex.common.instance_path(oracle['name'])),
                '--objective',oracle['objective'],'--mode',mode,'--optimum',str(oracle['optimum']),
                '--timeout',str(manifest['timeout_seconds']),'--output',str(case/'result.json')]
            if mode=='oracle-ub':
                ex.save(case/'oracle.json',oracle['solution'])
                command.extend(['--oracle-schedule',str(case/'oracle.json')])
            ex.save(case/'launch.json',dict(binary_sha256=binary_sha,commit=commit,
                objective=oracle['objective'],name=oracle['name'],mode=mode,optimum=oracle['optimum'],
                timeout=manifest['timeout_seconds'],ram_kb=manifest['ram_kb'],
                instance_sha256=ex.focus.sha(ex.common.instance_path(oracle['name'])),
                oracle_sha256=ex.focus.sha(case/'oracle.json') if mode=='oracle-ub' else None))
            print(f'{oracle["objective"]}/{oracle["name"]} opt={oracle["optimum"]} {mode}',flush=True)
            def limits():
                amount=manifest['ram_kb']*1024
                resource.setrlimit(resource.RLIMIT_AS,(amount,amount))
            with (case/'stdout.log').open('w') as out,(case/'stderr.log').open('w') as err:
                completed=subprocess.run(command,cwd=ex.REPO,stdout=out,stderr=err,preexec_fn=limits,
                    timeout=manifest['timeout_seconds']+45)
            ex.save(case/'completion.json',dict(returncode=completed.returncode,
                result_sha256=ex.focus.sha(case/'result.json'),
                trace_sha256=ex.focus.sha(case/'result.trace.jsonl')))
            ex.save(root/'audit.json',audit(root))
    print(json.dumps(audit(root),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','audit'])
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--mip',nargs=2,action='append',metavar=('OBJECTIVE','JSON'))
    parser.add_argument('--binary',type=Path)
    parser.add_argument('--build-manifest',type=Path)
    parser.add_argument('--round-seconds',type=int,default=18000)
    args=parser.parse_args()
    if args.action=='audit':print(json.dumps(audit(args.results,args.reference),indent=2));return
    if not all([args.reference,args.mip,args.binary,args.build_manifest]) or not 0<args.round_seconds<=21600:
        parser.error('run needs reference, MIP inputs, binary and build manifest; round <=21600s')
    try:run(args)
    except BaseException as error:
        if args.results.exists():ex.save(args.results/'failure.json',dict(error=str(error) or type(error).__name__))
        raise


if __name__=='__main__':main()
