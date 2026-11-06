#!/usr/bin/env python3
"""Resume a two-backend development trial; retain raw historical measurements."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

import extended_timeout_experiments as extended

BACKENDS = ("minisat", "cadical")
ROLES = ("Orders-Transitive", "CSOnet", "MaxSAT-Journal")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def key(item):
    return tuple(item[field] for field in ("backend", "method", "objective", "name"))


def tasks(plan):
    selected = extended.validate_plan(plan)
    pairs = [(objective, name) for objective, names in selected.items() for name in names]
    random.Random(20261106).shuffle(pairs)
    result = [(backend, role, objective, name)
              for objective, name in pairs for role in ROLES for backend in BACKENDS]
    return result


def definition(plan, backend, role):
    return dict(extended.methods_for(dict(plan, sat_backend=backend))[role], backend=backend)


def same_definition(left, right):
    # Older journal records did not emit a backend field; their locked plan
    # and verified dispatch identify MiniSAT. No other parameter is inferred.
    return dict(left, backend=left.get("backend", "minisat")) == dict(
        right, backend=right.get("backend", "minisat"))


def validate_groups(groups, topology, available):
    if set(groups) != set(BACKENDS) or any(not g or len(g) != len(set(g)) for g in groups.values()):
        raise ValueError("declare nonempty distinct CPU lists for both backends")
    used = set().union(*map(set, groups.values()))
    if not used.issubset(available):
        raise ValueError("CPU assignment contains an unavailable CPU")
    physical = [{topology[cpu] for cpu in groups[backend]} for backend in BACKENDS]
    if physical[0] & physical[1]:
        raise ValueError("the two backends must not share a physical core or SMT siblings")
    if len(physical[0]) != len(physical[1]) or len(groups["minisat"]) != len(groups["cadical"]):
        raise ValueError("both backends require the same number of physical cores and CPUs")


def cpu_topology(cpus):
    result = {}
    for cpu in cpus:
        directory = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        result[cpu] = tuple(int((directory / field).read_text())
                            for field in ("physical_package_id", "core_id"))
    return result


def load_reference(root, backend, plan):
    report = extended.audit_saved(root)
    source_plan = json.loads((root/"plan.json").read_text())
    source = json.loads((root/"manifest.json").read_text())
    for field in ("instances_by_objective", "timeout_seconds", "dataset_sha256"):
        if source_plan[field] != plan[field]:
            raise ValueError(f"reference differs in {field}")
    if source_plan.get("sat_backend", "minisat") != backend:
        raise ValueError("reference has the wrong SAT backend")
    imports = []
    for item in report["case_bounds"]:
        role = item["method"]
        if role not in ROLES:
            continue  # MILP is independent of the SAT backend and is not rerun here.
        config = source["methods"][role]
        if not same_definition(config, definition(plan, backend, role)):
            raise ValueError("reference changes a method component as well as its backend")
        path = root/"cases"/role/item["objective"]/item["name"]/f"{item['objective']}.json"
        imports.append(dict(backend=backend, method=role, objective=item["objective"], name=item["name"],
            sha256=extended.focus.sha(path), source=str(path.resolve()), definition=config,
            source_commit=source["git_commit"], binary_sha256=source["binary_sha256"],
            execution_mode="historical-sequential", ram_kb=source["ram_kb"]))
    return dict(source=str(root.resolve()), manifest_sha256=extended.focus.sha(root/"manifest.json"),
                audit_sha256=extended.focus.sha(root/"extended_audit.json")), imports


def case_root(root, task):
    return root.joinpath("cases", *task)


def assess(root, task, manifest):
    backend, role, objective, name = task
    directory = case_root(root, task)
    receipt = json.loads((directory/"measurement.json").read_text())
    expected_import = next((r for r in manifest["imports"] if key(r) == task), None)
    if expected_import is not None:
        if receipt != expected_import:
            raise ValueError("imported result provenance changed")
        config = expected_import["definition"]
    else:
        expected = dict(backend=backend, method=role, objective=objective, name=name,
                        source_commit=manifest["solver_source_commit"],
                        binary_sha256=manifest["binary_sha256"], execution_mode="parallel-development",
                        cpu_affinity=manifest["cpu_groups"][backend], ram_kb=manifest["ram_kb"])
        if any(receipt.get(field) != value for field, value in expected.items()):
            raise ValueError("new result differs from the locked backend/binary/resource assignment")
        config = definition(manifest["plan"], backend, role)
    if extended.focus.sha(directory/f"{objective}.json") != receipt.get("sha256"):
        raise ValueError("raw measurement bytes changed")
    record = extended.assess_case(directory, role, objective, name,
                                  manifest["plan"]["timeout_seconds"], config)
    if record["errors"] or record["status"] in extended.audit.FATAL_STATUSES:
        raise ValueError(f"invalid {task}: {record['errors']}")
    if record["solve"].get("maxsat_backend", backend) != backend:
        raise ValueError("runtime SAT backend differs from its reference")
    record.update(backend=backend, method=role, measurement=receipt)
    record["was_reused"] = expected_import is not None
    return record


def summarize(plan, records):
    expected = set(tasks(plan))
    indexed = {key(r): r for r in records}
    if len(indexed) != len(records) or not set(indexed).issubset(expected):
        raise ValueError("duplicate or unexpected backend measurement")
    optima = defaultdict(list)
    for record in records:
        if record["errors"]:
            raise ValueError("invalid record cannot enter a backend ranking")
        if record["proven"]:
            optima[record["objective"], record["name"]].append(record["solve"]["cost"])
    if any(any(not extended.common.same_number(values[0], v) for v in values[1:])
           for values in optima.values()):
        raise ValueError("verified optimal costs disagree between methods or backends")
    cutoff = plan["timeout_seconds"]
    rows, parallel_rows = [], []
    for role in ROLES:
        for objective in extended.audit.OBJECTIVES:
            names = plan["instances_by_objective"][objective]
            paired = [name for name in names if all((b,role,objective,name) in indexed for b in BACKENDS)]
            parallel = [name for name in paired if all(
                indexed[b,role,objective,name]["measurement"]["execution_mode"] == "parallel-development"
                for b in BACKENDS) and len({indexed[b,role,objective,name]["measurement"]["binary_sha256"]
                                          for b in BACKENDS}) == 1]
            for sample, destination in ((paired,rows), (parallel,parallel_rows)):
                if not sample:
                    continue
                row = dict(method=role, objective=objective, paired_completed=len(sample), planned=len(names))
                for backend in BACKENDS:
                    values = [indexed[backend,role,objective,name] for name in sample]
                    solved = [r["time"] for r in values if r["proven"]]
                    row[backend+"_optimal"] = len(solved)
                    row[backend+"_par2_seconds"] = sum(r["time"] if r["proven"] else 2*cutoff for r in values)/len(values)
                    row[backend+"_median_solved_seconds"] = statistics.median(solved) if solved else None
                row["cadical_gained"] = [name for name in sample if indexed["cadical",role,objective,name]["proven"]
                                         and not indexed["minisat",role,objective,name]["proven"]]
                row["cadical_lost"] = [name for name in sample if indexed["minisat",role,objective,name]["proven"]
                                       and not indexed["cadical",role,objective,name]["proven"]]
                scores = {b:(-row[b+"_optimal"],row[b+"_par2_seconds"]) for b in BACKENDS}
                row["preferred_backend"] = "tie" if scores["minisat"]==scores["cadical"] else min(scores,key=scores.get)
                row["complete_for_objective"] = len(sample)==len(names)
                destination.append(row)
    return dict(schema="sat-backend-comparison-v1", expected_runs=len(expected), completed_runs=len(records),
        complete=len(indexed)==len(expected), errors=[], submission_passed=False,
        scope="31 difficult pairs if using the frozen research plan; not full-dataset coverage",
        ranking="coverage first; PAR-2 is secondary development evidence; confirm final timings sequentially",
        runtime_note="historical sequential times and new parallel-development times retain separate provenance",
        comparison=rows, matching_binary_parallel_comparison=parallel_rows,
        progress=[dict(backend=b, completed=sum(r["backend"]==b for r in records),
                       reused=sum(r["backend"]==b and r.get("was_reused",
                           r["measurement"]["execution_mode"]=="historical-sequential") for r in records))
                  for b in BACKENDS],
        missing=[list(t) for t in tasks(plan) if t not in indexed])


def audit_saved(root, *, write=True):
    manifest = json.loads((root/"manifest.json").read_text())
    records = [assess(root,t,manifest) for t in tasks(manifest["plan"])
               if (case_root(root,t)/"measurement.json").exists()]
    report = summarize(manifest["plan"], records)
    if write:
        extended.save(root/"backend_comparison.json", report)
        extended.audit.write_csv(root/"backend_comparison.csv", report["comparison"])
        extended.audit.write_csv(root/"backend_parallel_same_binary.csv", report["matching_binary_parallel_comparison"])
    return report


def load_completed_trial(root, plan):
    """Reuse valid completed receipts even if a later case stopped the trial."""
    source=json.loads((root/"manifest.json").read_text())
    for field in ("instances_by_objective","timeout_seconds","dataset_sha256"):
        if source["plan"][field]!=plan[field]:
            raise ValueError(f"completed trial differs in {field}")
    report=audit_saved(root,write=False)
    original_imports={key(item):item for item in source["imports"]}
    imports=[]
    for task in tasks(plan):
        directory=case_root(root,task)
        if not (directory/"measurement.json").exists():
            continue  # A failed or interrupted result without a receipt is never reused.
        record=assess(root,task,source)
        metadata=record["measurement"]
        config=original_imports[task]["definition"] if task in original_imports else definition(source["plan"],task[0],task[1])
        if not same_definition(config,definition(plan,task[0],task[1])):
            raise ValueError("completed trial changed the method configuration")
        imports.append(dict(metadata,source=str((directory/f"{task[2]}.json").resolve()),
                            definition=config,source_measurement=metadata))
    return dict(source=str(root.resolve()),manifest_sha256=extended.focus.sha(root/"manifest.json"),
                report_sha256=extended.focus.sha(root/"backend_comparison.json"),
                independently_verified_completed=report["completed_runs"]),imports


def worker(root, backend, seconds):
    manifest = json.loads((root/"manifest.json").read_text())
    if sorted(os.sched_getaffinity(0)) != manifest["cpu_groups"][backend]:
        raise ValueError("worker CPU affinity differs from its manifest")
    if extended.focus.sha(Path(manifest["binary"])) != manifest["binary_sha256"]:
        raise ValueError("worker binary changed")
    deadline = time.monotonic()+seconds
    args = SimpleNamespace(timeout=manifest["plan"]["timeout_seconds"], binary=Path(manifest["binary"]),
                           ram_kb=manifest["ram_kb"], method_definitions={r:definition(manifest["plan"],backend,r) for r in ROLES})
    for task in tasks(manifest["plan"]):
        if task[0] != backend:
            continue
        directory = case_root(root, task)
        if (directory/"measurement.json").exists():
            assess(root,task,manifest)
            continue
        if deadline-time.monotonic() < args.timeout+90:
            break
        if directory.exists() and not (directory/f"{task[2]}.json").exists():
            # An interrupted process without a final result is preserved, never overwritten.
            interrupted = root/"interrupted"/backend/f"{task[1]}-{task[2]}-{task[3]}-{time.time_ns()}"
            interrupted.parent.mkdir(parents=True,exist_ok=True)
            directory.rename(interrupted)
        started = stamp()
        if not (directory/f"{task[2]}.json").exists():
            print(f"Running {'/'.join(task)}", flush=True)
            extended.run_case(task[1],task[2],task[3],args,directory)
        config = args.method_definitions[task[1]]
        record = extended.assess_case(directory,task[1],task[2],task[3],args.timeout,config)
        if record["errors"] or record["status"] in extended.audit.FATAL_STATUSES:
            raise ValueError(f"invalid new result {task}: {record['errors']}")
        receipt = dict(backend=backend,method=task[1],objective=task[2],name=task[3],
            source_commit=manifest["solver_source_commit"],binary_sha256=manifest["binary_sha256"],
            execution_mode="parallel-development",cpu_affinity=manifest["cpu_groups"][backend],ram_kb=manifest["ram_kb"],
            started_utc=started,finished_utc=stamp(),sha256=extended.focus.sha(directory/f"{task[2]}.json"))
        extended.save(directory/"measurement.json",receipt)


def initialize(args):
    plan = json.loads(args.plan.read_text())
    tasks(plan)
    groups = {b:sorted(int(c) for c in getattr(args,b+"_cpus").split(",")) for b in BACKENDS}
    if not set().union(*map(set,groups.values())).issubset(os.sched_getaffinity(0)):
        raise ValueError("CPU assignment contains an unavailable CPU")
    topology = cpu_topology(set().union(*map(set,groups.values())))
    validate_groups(groups,topology,os.sched_getaffinity(0))
    total_memory_kb = int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1])
    if args.ram_kb <= 0 or 2*args.ram_kb > total_memory_kb-2000000:
        raise ValueError("reserve at least 2 GB of RAM outside the two solver limits")
    if not 0 < args.round_seconds <= 21600:
        raise ValueError("one controlled round must be at most six hours")
    if subprocess.check_output(["git","status","--porcelain","--untracked-files=all"],cwd=extended.REPO).strip():
        raise ValueError("commit the runner and its plan before starting")
    solver = json.loads(args.solver_manifest.read_text())
    if extended.focus.sha(args.binary) != solver["binary_sha256"]:
        raise ValueError("binary differs from its recorded build")
    if solver["cargo_lock_sha256"] != extended.focus.sha(extended.REPO/"Cargo.lock"):
        raise ValueError("dependencies differ from the recorded solver build")
    dependencies={name:extended.dependency_state(extended.REPO.parent/directory)
                  for name,directory in (("salvers","salvers"),("ipamir","ipamir-rs"))}
    if any(dependencies[name]!=solver[name] for name in dependencies):
        raise ValueError("external dependencies differ from the recorded solver build")
    references, imports = {}, []
    for backend in BACKENDS:
        reference, cases = load_reference(getattr(args,backend+"_reference"), backend, plan)
        references[backend] = reference
        imports.extend(cases)
    completed_trial=getattr(args,"completed_trial",None)
    if completed_trial is not None:
        reference,cases=load_completed_trial(completed_trial,plan)
        references["completed_trial"]=reference
        merged={key(item):item for item in imports}
        for item in cases:
            old=merged.get(key(item))
            if old is not None and old["sha256"]!=item["sha256"]:
                raise ValueError("the two references disagree on the same completed case")
            merged[key(item)]=item
        imports=list(merged.values())
    manifest = dict(schema="sat-backend-parallel-v1", plan=plan, cpu_groups=groups,
        physical_core_groups={b:sorted({topology[c] for c in groups[b]}) for b in BACKENDS},
        ram_kb=args.ram_kb, binary=str(args.binary.resolve()),binary_sha256=solver["binary_sha256"],
        solver_source_commit=solver["git_commit"], solver_manifest_sha256=extended.focus.sha(args.solver_manifest),
        runner_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=extended.REPO,text=True).strip(),
        platform=platform.platform(),python=sys.version, memory_kb=total_memory_kb,dependencies=dependencies,
        cargo_lock_sha256=solver["cargo_lock_sha256"],references=references, imports=imports,
        historical_version_assumption="accepted for development reuse by user; individual commits and hashes retained",
        execution_mode="two parallel backend workers on disjoint physical cores; final timings confirmed sequentially")
    # JSON is the canonical representation (including tuples in CPU topology).
    manifest = json.loads(json.dumps(manifest))
    root = args.results.resolve()
    root.mkdir(parents=True,exist_ok=True)
    if (root/"manifest.json").exists() and json.loads((root/"manifest.json").read_text()) != manifest:
        raise ValueError("resume would change binary, source, references, dataset, CPUs or RAM")
    extended.save(root/"manifest.json",manifest)
    for item in imports:
        directory=case_root(root,key(item))
        directory.mkdir(parents=True,exist_ok=True)
        destination=directory/f"{item['objective']}.json"
        if destination.exists():
            if extended.focus.sha(destination) != item["sha256"]:
                raise ValueError("resume would overwrite an imported measurement")
        else:
            shutil.copy2(item["source"],destination)
        receipt=directory/"measurement.json"
        if receipt.exists() and json.loads(receipt.read_text()) != item:
            raise ValueError("import provenance changed during resume")
        extended.save(receipt,item)
    return root, manifest


def interrupted(_signal, _frame):
    raise KeyboardInterrupt


def run(args):
    root, manifest = initialize(args)
    workers=[]
    try:
        for backend in BACKENDS:
            log=(root/f"{backend}.log").open("ab")
            command=["taskset","-c", ",".join(map(str,manifest["cpu_groups"][backend])),sys.executable,
                     str(Path(__file__).resolve()),"worker","--results",str(root),"--backend",backend,
                     "--round-seconds",str(args.round_seconds)]
            workers.append((subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True),log))
        deadline=time.monotonic()+args.round_seconds+60
        while True:
            report=audit_saved(root)
            print(json.dumps({k:report[k] for k in ("completed_runs","expected_runs","complete","progress")}),flush=True)
            if any(p.poll() not in (None,0) for p,_ in workers):
                raise RuntimeError("a backend worker failed; preserve raw data and inspect its log")
            if all(p.poll() is not None for p,_ in workers):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("round exceeded its controlled deadline")
            time.sleep(20)
        audit_saved(root)
    except BaseException as error:
        extended.save(root/"failure.json",dict(time_utc=stamp(),error=str(error) or type(error).__name__))
        raise
    finally:
        for process,log in workers:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
            log.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    runner=sub.add_parser("run")
    runner.add_argument("--plan",type=Path,required=True)
    runner.add_argument("--binary",type=Path,required=True)
    runner.add_argument("--solver-manifest",type=Path,required=True)
    runner.add_argument("--minisat-reference",type=Path,required=True)
    runner.add_argument("--cadical-reference",type=Path,required=True)
    runner.add_argument("--completed-trial",type=Path)
    runner.add_argument("--minisat-cpus",default="0,1,4,5")
    runner.add_argument("--cadical-cpus",default="2,3,6,7")
    runner.add_argument("--ram-kb",type=int,default=6000000)
    runner.add_argument("--round-seconds",type=int,default=21600)
    runner.add_argument("--results",type=Path,required=True)
    working=sub.add_parser("worker")
    working.add_argument("--results",type=Path,required=True)
    working.add_argument("--backend",choices=BACKENDS,required=True)
    working.add_argument("--round-seconds",type=int,required=True)
    auditing=sub.add_parser("audit")
    auditing.add_argument("results",type=Path)
    args=parser.parse_args()
    signal.signal(signal.SIGTERM,interrupted)
    if args.action=="run": run(args)
    elif args.action=="worker": worker(args.results,args.backend,args.round_seconds)
    else:
        # Read-only audit can run alongside the campaign's single report writer.
        report=audit_saved(args.results,write=False)
        print(json.dumps({k:report[k] for k in ("completed_runs","expected_runs","complete","progress")}))


if __name__=="__main__":
    main()
