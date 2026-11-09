#!/usr/bin/env python3
"""Require native MiniSAT adaptation tests and verified smoke schedules."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import extended_timeout_experiments as ex
import targeted_order_cycles as trial


def validate(root: Path, reference: Path, binary: Path, component: str = 'core-trim') -> None:
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():
        raise ValueError('preflight requires a clean pinned source')
    unit=(root/'rust-core-tests.log').read_text()
    exact=(root/'rust-exhaustive-test.log').read_text()
    python=(root/'python-tests.log').read_text()
    counts=[]
    is_am1 = component == 'intrinsic-am1'
    flag = 'am1_checks' if is_am1 else 'core_trim_checks'
    enabled = '16' if is_am1 else '3'
    counter = 'maxsat_am1_calls' if is_am1 else 'maxsat_core_trim_calls'
    for log,minimum in [(unit,3 if is_am1 else 6),(exact,2 if is_am1 else 1)]:
        match=re.search(r'test result: ok\. (\d+) passed; 0 failed;',log)
        if match is None or int(match[1])<minimum:
            raise ValueError('native core-trimming tests did not pass')
        counts.append(int(match[1]))
    match=re.search(r'Ran (\d+) tests',python)
    if match is None or int(match[1])<128 or '\nOK\n' not in python:
        raise ValueError('Python auditor tests did not pass')
    source,selection,_=trial.load_reference(reference)
    config=trial.candidate_config(source,component)
    binary_hash=ex.focus.sha(binary)
    build=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip(),
        binary_sha256=binary_hash,cargo_lock_sha256=ex.focus.sha(ex.REPO/'Cargo.lock'),
        rust_core_tests_passed=counts[0],rust_exhaustive_tests_passed=counts[1],
        python_tests_passed=int(match[1]),
        salvers=ex.dependency_state(ex.REPO.parent/'salvers'),
        ipamir=ex.dependency_state(ex.REPO.parent/'ipamir-rs'),
        tested_source_sha256={str(p.relative_to(ex.REPO)):ex.focus.sha(p)
                              for p in sorted((ex.REPO/'src').rglob('*.rs'))})
    ex.save(root/'build_manifest.json',build)
    oracle={(r['objective'],r['name']):r['cost'] for r in json.loads((reference/'full_audit.json').read_text())['case_bounds'] if r['proven']}
    reports=[]
    for checks in ['0',enabled]:
        cfg=dict(config,**{flag:checks})
        runtime=SimpleNamespace(timeout=30,ram_kb=6000000,binary=binary,method_definitions={'smoke':cfg})
        for objective in ex.audit.OBJECTIVES:
            case=root/'smoke'/('trim'+checks)/objective
            if not (case/f'{objective}.json').exists():
                ex.run_case('smoke',objective,'origA1',runtime,case)
            record=ex.assess_case(case,'smoke',objective,'origA1',30,cfg)
            if record['errors'] or not record['proven'] or record['solve'].get('cost')!=oracle[objective,'origA1']:
                raise ValueError(f'core-trim smoke failed: {checks}/{objective}: {record["errors"]}')
            if checks=='0' and record['solve'].get(counter)!=0:
                raise ValueError('disabled trimming performed an extra SAT query')
            reports.append(dict(checks=checks,objective=objective,cost=record['solve']['cost'],
                adaptation_calls=record['solve'].get(counter,0),raw_sha256=ex.focus.sha(case/f'{objective}.json')))
    if not any(r['adaptation_calls']>0 for r in reports if r['checks']==enabled):
        raise ValueError('real-case smoke did not exercise trimming')
    runtime=SimpleNamespace(timeout=2,ram_kb=6000000,binary=binary,method_definitions={'probe':config})
    case=root/'deadline-probe'
    if not (case/'infsteps180.json').exists():
        ex.run_case('probe','infsteps180','stationA11',runtime,case)
    probe=ex.assess_case(case,'probe','infsteps180','stationA11',2,config)
    if probe['errors'] or probe['status'] not in ('ok','timeout'):
        raise ValueError(f'deadline probe failed: {probe["errors"]}')
    ex.save(root/'preflight.json',dict(audit_passed=True,component=component,smokes=reports,selection=selection,
        deadline_probe_status=probe['status'],binary_sha256=binary_hash,submission_passed=False))
    print(json.dumps(dict(preflight_passed=True,smokes=reports)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--component',choices=['core-trim','intrinsic-am1'],default='core-trim')
    args=parser.parse_args()
    validate(args.root,args.reference,args.binary.resolve(),args.component)
