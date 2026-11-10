#!/usr/bin/env python3
"""Gate autonomous threshold search on native proofs and real-instance smokes."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import run_sat_bound_search as search
import extended_timeout_experiments as ex
import targeted_order_cycles as trial


def validate(root,reference,policy='bisect',warmup=0,polish_checks=0):
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ex.REPO).strip():
        raise ValueError('preflight requires a clean pinned source')
    counts={}
    checks=[('rust-search-tests',11 if policy=='upper' else 10 if warmup>0 else 6 if policy=='close-upper' else 5),('rust-objective-tests',5)]
    if polish_checks>0:checks.append(('rust-polish-tests',8))
    if warmup>0:checks.extend([('rust-rc2-tests',1),('rust-legacy-tests',1)])
    for name,minimum in checks:
        m=re.search(r'test result: ok\. (\d+) passed; 0 failed;',(root/(name+'.log')).read_text())
        if not m or int(m[1])<minimum:raise ValueError('native search/objective tests failed')
        counts[name]=int(m[1])
    text=(root/'python-tests.log').read_text();m=re.search(r'Ran (\d+) tests',text)
    if not m or int(m[1])<(191 if polish_checks>0 else 144) or '\nOK\n' not in text:raise ValueError('auditor tests failed')
    counts['python']=int(m[1]);binary=root/'solver/sat_bound_search'
    help_text=subprocess.check_output([str(binary),'--help'],text=True)
    if '--optimum' in help_text or '--oracle-schedule' in help_text:raise ValueError('solver accepts oracle input')
    if policy!='bisect' and '--threshold-policy' not in help_text:raise ValueError('binary lacks the requested query policy')
    if warmup>0 and '--rc2-warmup-seconds' not in help_text:raise ValueError('binary lacks RC2 warmup')
    if polish_checks>0 and '--incumbent-polish-checks' not in help_text:raise ValueError('binary lacks incumbent polishing')
    source,_,_=trial.load_reference(reference);known=search.reference_costs(reference,None)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ex.REPO,text=True).strip()
    reports=[]
    for objective in ex.audit.OBJECTIVES:
        case=root/'smoke'/objective
        search.run_case(binary,30,source['ram_kb'],commit,case,objective,'origA1',0,policy,warmup,polish_checks)
        report,_=search.check_result(json.load(open(case/'result.json')),'origA1',objective,30,known[objective,'origA1'])
        if not report['proven']:raise ValueError('easy real-instance smoke did not prove optimality')
        if report['threshold_policy']!=policy:raise ValueError('smoke used a different query policy')
        if report['rc2_warmup_seconds']!=warmup:raise ValueError('smoke used a different warmup allocation')
        if report['incumbent_polish_checks']!=polish_checks:raise ValueError('smoke used a different polish check limit')
        reports.append(report)
    # Exercise native deadline unwinding with a real hard problem. A valid
    # timeout must retain its independently checked initial/updated incumbent.
    case=root/'deadline-probe'
    search.run_case(binary,0.05,source['ram_kb'],commit,case,'cont','origA8',0,policy,warmup,polish_checks)
    probe,_=search.check_result(json.load(open(case/'result.json')),'origA8','cont',0.05)
    if probe['status']!='timeout':raise ValueError('deadline probe unexpectedly skipped the timeout path')
    handoff=None
    if warmup>0:
        case=root/'handoff-probe'
        search.run_case(binary,30,source['ram_kb'],commit,case,'cont','origA1',0,policy,1e-6,polish_checks)
        raw=json.loads((case/'result.json').read_text())
        handoff,_=search.check_result(raw,'origA1','cont',30,known['cont','origA1'])
        if not handoff['proven'] or raw['warmup']['status']!='timeout' or not raw['queries']:
            raise ValueError('native RC2-to-SAT handoff did not prove the easy optimum')
    build=dict(git_commit=commit,binary_sha256=ex.focus.sha(binary),cargo_lock_sha256=ex.focus.sha(ex.REPO/'Cargo.lock'),
        tests=counts,salvers=ex.dependency_state(ex.REPO.parent/'salvers'),ipamir=ex.dependency_state(ex.REPO.parent/'ipamir-rs'),
        tested_source_sha256={str(p.relative_to(ex.REPO)):ex.focus.sha(p) for p in sorted((ex.REPO/'src').rglob('*.rs'))})
    ex.save(root/'build_manifest.json',build)
    ex.save(root/'preflight.json',dict(audit_passed=True,tests=counts,smokes=reports,deadline_probe=probe,
        uses_optimum_oracle=False,submission_passed=False,threshold_policy=policy,rc2_warmup_seconds=warmup,handoff_probe=handoff,incumbent_polish_checks=polish_checks))
    print(json.dumps(dict(preflight_passed=True,tests=counts,smokes=reports)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--threshold-policy',choices=['bisect','close-upper','upper'],default='bisect')
    p.add_argument('--rc2-warmup-seconds',type=float,default=0)
    p.add_argument('--incumbent-polish-checks',type=int,default=0)
    a=p.parse_args();validate(a.root.resolve(),a.reference.resolve(),a.threshold_policy,a.rc2_warmup_seconds,a.incumbent_polish_checks)
