#!/usr/bin/env python3
"""Recheck a disputed CPLEX bound on the original LP with tight tolerances."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import extended_timeout_experiments as ex
import run_sat_bound_search as search


def run(args):
    witness=json.loads(args.witness.read_text())
    search.validate_schedule(args.name,args.objective,witness['solution'],witness['cost'])
    root=args.output.resolve()
    if root.exists():raise ValueError('choose a new diagnostic directory; preserve earlier evidence')
    root.mkdir(parents=True)
    lp=root/args.lp.name;shutil.copyfile(args.lp,lp)
    shutil.copyfile(args.witness,root/'independent_witness.json')
    solution=root/'schedule.sol'
    command=[str(args.cplex.resolve()),'-c',f'read {lp}','set threads 4',
        'set mip tolerances integrality 1e-9','set simplex tolerances feasibility 1e-9',
        'set emphasis numerical y','set mip tolerances mipgap 0','set mip tolerances absmipgap 0',
        f'set timelimit {args.timeout}','optimize','display solution bestbound',f'write {solution}','quit']
    ex.save(root/'manifest.json',dict(schema='cplex-disputed-bound-recheck-v1',objective=args.objective,
        name=args.name,lp_sha256=ex.focus.sha(lp),witness_sha256=ex.focus.sha(args.witness),
        cplex_sha256=ex.focus.sha(args.cplex),dataset_sha256=ex.focus.dataset_hash(),
        evaluator_sha256=ex.focus.sha(Path(__file__)),timeout_seconds=args.timeout,command=command,
        uses_witness_inside_solver=False))
    started=time.monotonic()
    with (root/'cplex.log').open('w') as log:
        result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=args.timeout+45)
    if result.returncode:raise ValueError('CPLEX failed; preserve the diagnostic log')
    solve=ex.cplex_result(solution,root/'cplex.log',args.name,args.objective,args.timeout,time.monotonic()-started)
    ex.save(root/(args.objective+'.json'),[dict(name=args.name,solves=[solve])])
    ex.save(root/'audit.json',dict(incumbent_independently_verified=solve.get('valid',False),
        witness_cost=witness['cost'],reported_lb=solve.get('lb'),reported_ub=solve.get('ub'),
        contradicts_verified_witness=solve.get('lb',0)>witness['cost'],
        submission_passed=False,scope='diagnosis on the original LP, not a replacement full baseline'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('lp','witness','cplex','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--objective',choices=ex.audit.OBJECTIVES,required=True);p.add_argument('--name',required=True)
    p.add_argument('--timeout',type=int,default=120)
    args=p.parse_args()
    if args.timeout<=0 or args.name not in ex.common.EXPECTED_NAMES:p.error('invalid name or timeout')
    if args.output.exists():p.error('choose a new diagnostic directory; preserve earlier evidence')
    try:run(args)
    except BaseException as error:
        if args.output.is_dir():ex.save(args.output/'failure.json',dict(error=str(error)))
        raise
