#!/usr/bin/env python3
"""Test bounded RC2 core improvements only on unresolved MiniSAT cases."""
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


def tag_for(config):
    conflicts=int(config.get("core_minimize_conflicts",0))
    tag=TAG if not conflicts else f"{TAG}-C{conflicts}"
    exhaust=int(config.get("core_exhaust_checks",0))
    return tag if not exhaust else f"{tag}-E{exhaust}"


def unresolved_after_trials(reference, trials, regression_reference=None):
    # Import lazily: the independent auditor also imports this module.
    from confirm_targeted_core_minimization import choose
    for path in trials:
        previous=json.loads((path/"manifest.json").read_text())
        if int(previous["definition"].get("core_exhaust_checks",0)):
            raise ValueError("this trial must extend the original V16 configurations")
    best, report=choose(trials,reference)
    prior=json.loads((best/"manifest.json").read_text())
    gains={(item["objective"],item["name"]) for item in report["newly_solved"]}
    selected={o:[n for n in names if (o,n) not in gains] for o,names in select(reference).items()}
    evidence=dict(trials=sorted([dict(manifest_sha256=extended.focus.sha(path/"manifest.json"),
                              report_sha256=extended.focus.sha(path/"core_minimization_audit.json")) for path in trials],
                              key=lambda item:item["manifest_sha256"]),
                  selected_manifest_sha256=extended.focus.sha(best/"manifest.json"))
    if regression_reference is not None:
        import core_regression_reference
        losses,regression=core_regression_reference.audit(regression_reference,reference,prior,
                                                        evidence["selected_manifest_sha256"])
        for item in losses:selected[item["objective"]].append(item["name"])
        selected={o:[n for n in extended.common.EXPECTED_NAMES if any(item['objective']==o and item['name']==n for item in losses)]
                    +[n for n in extended.common.EXPECTED_NAMES if n in names and not any(item['objective']==o and item['name']==n for item in losses)]
                  for o,names in selected.items()}
        evidence["regression"]=regression
    return selected,prior["definition"],evidence


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
    exhaust=getattr(args,"core_exhaust_checks",0)
    previous_trials=getattr(args,"previous_trials",None)
    regression_reference=getattr(args,"regression_reference",None)
    prior_config=None
    if exhaust<0 or bool(exhaust)!=bool(previous_trials):
        raise ValueError("core exhaustion requires completed prior trials, and vice versa")
    if regression_reference is not None and not previous_trials:
        raise ValueError("a regression reference requires the prior parameter trials")
    if previous_trials:
        selection,prior_config,previous=unresolved_after_trials(args.reference,previous_trials,regression_reference)
    if not any(selection.values()):
        raise ValueError("there are no unresolved MiniSAT candidate cases")
    build=json.loads(args.build_manifest.read_text())
    if extended.focus.sha(args.binary)!=build["binary_sha256"]:
        raise ValueError("binary differs from its recorded build")
    if subprocess.check_output(["git","status","--porcelain","--untracked-files=all"],cwd=extended.REPO).strip():
        raise ValueError("commit the experiment code first")
    conflicts=getattr(args,"core_conflicts",0)
    if prior_config is not None:
        conflicts=int(prior_config["core_minimize_conflicts"])
    if not 0<=conflicts<=2147483647:
        raise ValueError("core conflict budget must fit a nonnegative i32")
    config=dict(dual.definition(source["plan"],"minisat","Orders-Transitive"),core_minimize_checks="4")
    if conflicts: config["core_minimize_conflicts"]=str(conflicts)
    if exhaust: config["core_exhaust_checks"]=str(exhaust)
    tag=tag_for(config)
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
    if previous_trials: manifest["previous_trials"]=previous
    if (root/"manifest.json").exists() and json.loads((root/"manifest.json").read_text())!=manifest:
        raise ValueError("resume would change the selected cases, binary or experiment settings")
    extended.save(root/"manifest.json",manifest)
    oracle={}
    for task in dual.tasks(source["plan"]):
        if (dual.case_root(args.reference,task)/"measurement.json").exists():
            record=dual.assess(args.reference,task,source)
            if record["proven"]: oracle[task[2:]]=record["solve"]["cost"]
    runtime=SimpleNamespace(timeout=manifest["timeout_seconds"],binary=args.binary.resolve(),ram_kb=args.ram_kb,
                            method_definitions={tag:config})
    deadline=time.monotonic()+args.round_seconds
    records=[]
    expected=[(o,n) for o,names in selection.items() for n in names]
    for objective,name in expected:
        case=root/"cases"/objective/name
        if not (case/f"{objective}.json").exists():
            if deadline-time.monotonic()<runtime.timeout+90: break
            print(f"Core minimization: {objective}/{name}",flush=True)
            extended.run_case(tag,objective,name,runtime,case)
        record=extended.assess_case(case,tag,objective,name,runtime.timeout,config)
        if record["errors"] or record["status"] in extended.audit.FATAL_STATUSES:
            raise ValueError(f"invalid result {objective}/{name}: {record['errors']}")
        if record["proven"] and (objective,name) in oracle and not extended.common.same_number(record["solve"]["cost"],oracle[objective,name]):
            raise ValueError("optimum differs from an independently verified reference")
        records.append(record)
        report=dict(schema=manifest["schema"],expected_runs=len(expected),completed_runs=len(records),
                    complete=len(records)==len(expected),errors=[],submission_passed=False,
                    scope=("unresolved cases and audited regression losses only; other solved cases have not been retested" if regression_reference is not None
                           else "unresolved cases only; losses on previously solved cases have not been tested"),
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
    parser.add_argument("--core-conflicts",type=int,default=0)
    parser.add_argument("--core-exhaust-checks",type=int,default=0)
    parser.add_argument("--previous-trials",type=Path,nargs="+")
    parser.add_argument("--regression-reference",type=Path)
    parser.add_argument("--round-seconds",type=int,default=21600)
    args=parser.parse_args()
    try:
        run(args)
    except BaseException as error:
        if args.results.exists():
            extended.save(args.results/"failure.json",dict(error=str(error) or type(error).__name__))
        raise


if __name__=="__main__": main()
