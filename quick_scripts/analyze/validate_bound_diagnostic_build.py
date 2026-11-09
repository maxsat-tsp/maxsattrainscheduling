#!/usr/bin/env python3
"""Native test evidence, twelve real-instance diagnoses and legacy smokes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import diagnose_optimal_bounds as diag
import extended_timeout_experiments as ex
import targeted_order_cycles as trial


def validate(root, reference):
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():
        raise ValueError('preflight requires clean pinned source')
    counts={}
    for name, minimum in [('rust-diagnostic-tests',3),('rust-objective-tests',4)]:
        text=(root/(name+'.log')).read_text()
        match=re.search(r'test result: ok\. (\d+) passed; 0 failed;',text)
        if match is None or int(match[1])<minimum:
            raise ValueError('native SAT diagnostics/arithmetic tests did not pass')
        counts[name]=int(match[1])
    text=(root/'python-tests.log').read_text()
    match=re.search(r'Ran (\d+) tests',text)
    if match is None or int(match[1])<136 or '\nOK\n' not in text:
        raise ValueError('Python audit tests did not pass')
    counts['python']=int(match[1])
    binary=root/'solver/bound_diagnostic'
    config,_,_=trial.load_reference(reference)
    reports=[]
    for objective in ex.audit.OBJECTIVES:
        path=reference/'cases'/objective/'origA1'/f'{objective}.json'
        rows=ex.common.load_rows(path)
        solve=next(s for name,s in rows if name=='origA1')
        oracle=dict(objective=objective,name='origA1',optimum=solve['cost'],solution=solve['solution'])
        # The ordinary CLI must still reproduce the V17 optimum.
        case=root/'legacy-smoke'/objective
        runtime=SimpleNamespace(timeout=30,ram_kb=6000000,binary=root/'solver/ddd',
            method_definitions={'legacy':config['definition']})
        if not (case/f'{objective}.json').exists():ex.run_case('legacy',objective,'origA1',runtime,case)
        legacy=ex.assess_case(case,'legacy',objective,'origA1',30,config['definition'])
        if legacy['errors'] or not legacy['proven'] or legacy['solve']['cost']!=oracle['optimum']:
            raise ValueError('ordinary V17 CLI regression failed')
        for mode in diag.MODES:
            case=root/'smoke'/objective/mode;case.mkdir(parents=True,exist_ok=True)
            output=case/'result.json'
            command=[str(binary),'--instance',str(ex.common.instance_path('origA1')),
                '--objective',objective,'--mode',mode,'--optimum',str(oracle['optimum']),
                '--timeout','30','--output',str(output)]
            if mode=='oracle-ub':
                ex.save(case/'oracle.json',oracle['solution'])
                command.extend(['--oracle-schedule',str(case/'oracle.json')])
            if not output.exists():
                with (case/'stdout.log').open('w') as out,(case/'stderr.log').open('w') as err:
                    subprocess.run(command,stdout=out,stderr=err,cwd=ex.REPO,check=True,timeout=75)
            record=diag.check_result(json.loads(output.read_text()),oracle,mode,30)
            if mode in ('control','oracle-ub') and record['status']=='timeout':
                raise ValueError('ordinary easy-instance optimization timed out')
            reports.append(record)
    build=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip(),
        binary_sha256=ex.focus.sha(binary),ordinary_binary_sha256=ex.focus.sha(root/'solver/ddd'),
        cargo_lock_sha256=ex.focus.sha(ex.REPO/'Cargo.lock'),test_counts=counts,
        test_log_sha256={name:ex.focus.sha(root/(name+'.log')) for name in
                        ('rust-diagnostic-tests','rust-objective-tests','python-tests')},
        salvers=ex.dependency_state(ex.REPO.parent/'salvers'),
        ipamir=ex.dependency_state(ex.REPO.parent/'ipamir-rs'),
        tested_source_sha256={str(p.relative_to(ex.REPO)):ex.focus.sha(p)
                              for p in sorted((ex.REPO/'src').rglob('*.rs'))})
    ex.save(root/'build_manifest.json',build)
    ex.save(root/'preflight.json',dict(audit_passed=True,reports=reports,
        tests=counts,legacy_smokes=3,diagnostic_smokes=12,submission_eligible=False))
    print(json.dumps(dict(preflight_passed=True,tests=counts,reports=reports)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    args=p.parse_args();validate(args.root.resolve(),args.reference.resolve())
