#!/usr/bin/env python3
"""Test four core-reduction checks only on unresolved MiniSAT candidate cases."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import compare_sat_backends as dual
import extended_timeout_experiments as extended

TAG="Orders-Transitive-Mincore"


def select(reference):
    source=json.loads((reference/"manifest.json").read_text())
    dual.audit_saved(reference,write=False)
    selected={o:[] for o in extended.audit.OBJECTIVES}
    for task in dual.tasks(source["plan"]):
        if task[:2]!=("minisat","Orders-Transitive"):
            continue
        if not (dual.case_root(reference,task)/"measurement.json").exists():
            raise ValueError("finish the MiniSAT candidate before selecting unresolved cases")
        if not dual.assess(reference,task,source)["proven"]:
            selected[task[2]].append(task[3])
    return {o:[n for n in extended.common.EXPECTED_NAMES if n in selected[o]] for o in selected}


def run(args):
    if not 0<args.round_seconds<=21600:
        raise ValueError("one round must be at most six hours")
    source=json.loads((args.reference/"manifest.json").read_text())
    selection=select(args.reference)
    if not any(selection.values()):
        raise ValueError("there are no unresolved MiniSAT candidate cases")
    build=json.loads(args.build_manifest.read_text())
    if extended.focus.sha(args.binary)!=build["binary_sha256"]:
        raise ValueError("binary differs from its recorded build")
    if subprocess.check_output(["git","status","--porcelain","--untracked-files=all"],cwd=extended.REPO).strip():
        raise ValueError("commit the experiment code first")
    config=dict(dual.definition(source["plan"],"minisat","Orders-Transitive"),core_minimize_checks="4")
    root=args.results.resolve()
    root.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema="targeted-core-minimization-v1",timeout_seconds=source["plan"]["timeout_seconds"],
        instances_by_objective=selection,definition=config,binary_sha256=build["binary_sha256"],
        solver_source_commit=build["git_commit"],
        runner_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=extended.REPO,text=True).strip(),
        reference=str(args.reference.resolve()),reference_manifest_sha256=extended.focus.sha(args.reference/"manifest.json"),
        reference_report_sha256=extended.focus.sha(args.reference/"backend_comparison.json"),
        dataset_sha256=extended.focus.dataset_hash(),ram_kb=args.ram_kb,
        cpu_affinity=sorted(os.sched_getaffinity(0)),submission_passed=False)
    if (root/"manifest.json").exists() and json.loads((root/"manifest.json").read_text())!=manifest:
        raise ValueError("resume would change the selected cases, binary or experiment settings")
    extended.save(root/"manifest.json",manifest)
    oracle={}
    for task in dual.tasks(source["plan"]):
        if (dual.case_root(args.reference,task)/"measurement.json").exists():
            record=dual.assess(args.reference,task,source)
            if record["proven"]: oracle[task[2:]]=record["solve"]["cost"]
    runtime=SimpleNamespace(timeout=manifest["timeout_seconds"],binary=args.binary.resolve(),ram_kb=args.ram_kb,
                            method_definitions={TAG:config})
    deadline=time.monotonic()+args.round_seconds
    records=[]
    expected=[(o,n) for o,names in selection.items() for n in names]
    for objective,name in expected:
        case=root/"cases"/objective/name
        if not (case/f"{objective}.json").exists():
            if deadline-time.monotonic()<runtime.timeout+90: break
            print(f"Core minimization: {objective}/{name}",flush=True)
            extended.run_case(TAG,objective,name,runtime,case)
        record=extended.assess_case(case,TAG,objective,name,runtime.timeout,config)
        if record["errors"] or record["status"] in extended.audit.FATAL_STATUSES:
            raise ValueError(f"invalid result {objective}/{name}: {record['errors']}")
        if record["proven"] and (objective,name) in oracle and not extended.common.same_number(record["solve"]["cost"],oracle[objective,name]):
            raise ValueError("optimum differs from an independently verified reference")
        records.append(record)
        report=dict(schema=manifest["schema"],expected_runs=len(expected),completed_runs=len(records),
                    complete=len(records)==len(expected),errors=[],submission_passed=False,
                    scope="unresolved cases only; losses on previously solved cases have not been tested",
                    newly_solved=[dict(objective=r["objective"],name=r["name"],cost=r["solve"]["cost"],seconds=r["time"])
                                  for r in records if r["proven"]],
                    summary=extended.audit.summarize(records,runtime.timeout))
        extended.save(root/"core_minimization_audit.json",report)
        extended.audit.write_csv(root/"core_minimization_summary.csv",report["summary"])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference",type=Path,required=True)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--build-manifest",type=Path,required=True)
    parser.add_argument("--results",type=Path,required=True)
    parser.add_argument("--ram-kb",type=int,default=6000000)
    parser.add_argument("--round-seconds",type=int,default=21600)
    run(parser.parse_args())


if __name__=="__main__": main()
