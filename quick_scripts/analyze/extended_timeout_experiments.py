#!/usr/bin/env python3
"""Compare SAT and MILP on one frozen difficult set at a larger common cutoff."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import audit_aglr_campaign as audit
import audit_journal_campaign as common
import focused_experiments as focus
import published_baselines as published

REPO = Path(__file__).resolve().parents[2]
METHODS = {
    "Orders-Transitive": dict(solver="maxsat_ddd_ladder_sc", kind="exact", assumptions="legacy",
                              backend="minisat", sparse_costs="false", resource_orders="true",
                              order_transitivity="true", objective_bound="false", residual_hardening="false"),
    "CSOnet": dict(solver="maxsat_ddd_ladder_sc", kind="exact", assumptions="legacy",
                    backend="minisat", sparse_costs="false", resource_orders="false",
                    order_transitivity="false", objective_bound="false", residual_hardening="false"),
    "MaxSAT-Journal": dict(solver="maxsat_ddd", kind="exact"),
    "BigM-Gurobi": dict(solver="bigm_lazy", kind="milp"),
    "BigM-CPLEX": dict(solver="cplex-eager", kind="milp"),
}


def save(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def build_plan(manifest: Path, reference: Path, cutoff: int) -> dict:
    if cutoff <= 120:
        raise ValueError("extended-timeout experiments require a cutoff above 120 seconds")
    frozen = json.loads(manifest.read_text())
    selected = {o: set(names) for o, names in focus.validate_manifest(frozen).items()}
    rows, metadata = published.load_directory(reference)
    # Two CPLEX costs in the published data are disputed. Keep that evidence,
    # but do not use either disputed value to reject a newly verified optimum.
    structural = [e for e in metadata["errors"] if not e.startswith("published optimal costs disagree")]
    if structural:
        raise ValueError(str(structural))
    reference_coverage = {}
    for tag in published.PREFIXES:
        reference_coverage[tag] = {}
        for objective in audit.OBJECTIVES:
            items = [r for r in rows if r["tag"] == tag and r["objective"] == objective]
            proven = [r for r in items if r["proven"] and r["solve"]["total_time"] <= 120]
            reference_coverage[tag][objective] = [r["name"] for r in proven]
            selected[objective].update(r["name"] for r in items if r not in proven)
    return dict(schema="extended-timeout-v1", timeout_seconds=cutoff, selection_cutoff_seconds=120,
                instances_by_objective={o: [n for n in common.EXPECTED_NAMES if n in selected[o]]
                                        for o in audit.OBJECTIVES},
                dataset_sha256=focus.dataset_hash(), focus_manifest_sha256=focus.sha(manifest),
                published_file_sha256=metadata["file_sha256"],
                published_cost_conflicts=metadata["cost_conflicts"],
                reference_proven_at_120=reference_coverage,
                scope="all methods rerun on the same selected pairs; no full-dataset claim")


def validate_plan(plan: dict) -> dict:
    if plan.get("schema") != "extended-timeout-v1" or plan.get("selection_cutoff_seconds") != 120:
        raise ValueError("invalid extended-timeout plan")
    if not isinstance(plan.get("timeout_seconds"), int) or plan["timeout_seconds"] <= 120:
        raise ValueError("cutoff must be an integer greater than 120")
    cfg = dict(instances_by_objective=json.dumps(plan["instances_by_objective"]))
    selected = {o: audit.expected_names(cfg, o) for o in audit.OBJECTIVES}
    if focus.dataset_hash() != plan.get("dataset_sha256"):
        raise ValueError("dataset changed after selecting the difficult instances")
    return selected


def tasks_for(plan: dict) -> list[tuple[str, str, str]]:
    selected = validate_plan(plan)
    pairs = [(o, n) for o in audit.OBJECTIVES for n in selected[o]]
    rng = random.Random(20261106)
    rng.shuffle(pairs)
    tasks = []
    for objective, name in pairs:
        methods = list(METHODS)
        rng.shuffle(methods)
        tasks.extend((method, objective, name) for method in methods)
    return tasks


def method_config(method: str, selection: dict, cutoff: int) -> dict:
    return dict(METHODS[method], tag=method, timeout_seconds=str(cutoff),
                process_exit_required="true", parallelism="1",
                instances_by_objective=json.dumps(selection, separators=(",", ":")))


def assess_case(root: Path, method: str, objective: str, name: str, cutoff: int) -> dict:
    selection = {o: [name] if o == objective else [] for o in audit.OBJECTIVES}
    records = audit.load_json_method(root, method_config(method, selection, cutoff), cutoff)
    if len(records) != 1 or records[0]["name"] != name:
        raise ValueError("a case must contain exactly its planned objective and instance")
    record = records[0]
    solve = record["solve"]
    if solve.get("solution") is not None and record["status"] != "ok":
        record["errors"].extend(common.independently_verify_solution(name, objective, solve))
    return record


def summarize(plan: dict, records: list[dict]) -> dict:
    expected = set(tasks_for(plan))
    keys = [(r["tag"], r["objective"], r["name"]) for r in records]
    if len(keys) != len(set(keys)) or not set(keys).issubset(expected):
        raise ValueError("duplicate or unexpected result in extended-timeout campaign")
    errors = [dict(method=r["tag"], objective=r["objective"], name=r["name"],
                   status=r["status"], errors=r["errors"])
              for r in records if r["errors"] or r["status"] in audit.FATAL_STATUSES]
    # Disagreeing independently verified proofs always block this campaign.
    optima = defaultdict(dict)
    for record in records:
        if record["proven"]:
            optima[record["objective"], record["name"]][record["tag"]] = record["solve"]["cost"]
    for (objective, name), costs in optima.items():
        values = list(costs.values())
        if any(not common.same_number(values[0], v) for v in values[1:]):
            errors.append(dict(objective=objective, name=name, status="cost-disagreement", costs=costs))
    cutoff = plan["timeout_seconds"]
    comparisons = []
    candidate = {(r["objective"], r["name"]): r for r in records if r["tag"] == "Orders-Transitive"}
    for baseline in METHODS:
        if baseline == "Orders-Transitive":
            continue
        reference = {(r["objective"], r["name"]): r for r in records if r["tag"] == baseline}
        paired = sorted(set(candidate) & set(reference))
        both = [key for key in paired if candidate[key]["proven"] and reference[key]["proven"]]
        ratios = [math.log(reference[k]["time"] / candidate[k]["time"]) for k in both
                  if candidate[k]["time"] > 0 and reference[k]["time"] > 0]
        comparisons.append(dict(baseline=baseline, paired_completed=len(paired),
            gained=[list(k) for k in paired if candidate[k]["proven"] and not reference[k]["proven"]],
            lost=[list(k) for k in paired if reference[k]["proven"] and not candidate[k]["proven"]],
            paired_solved=len(both), paired_geomean_speedup=math.exp(sum(ratios)/len(ratios)) if ratios else None))
    return dict(scope=plan["scope"], timeout_seconds=cutoff,
                expected_runs=len(expected), completed_runs=len(records),
                complete=len(records) == len(expected), errors=errors,
                submission_passed=False, full_validation_required=True,
                summary=audit.summarize(records, cutoff), comparisons=comparisons,
                missing=[list(k) for k in tasks_for(plan) if k not in set(keys)])


def execute(command: list[str], cwd: Path, log: Path, limit: float, env: dict, ram_kb: int) -> float:
    import resource
    def limits():
        if ram_kb:
            resource.setrlimit(resource.RLIMIT_AS, (ram_kb*1024, ram_kb*1024))
    started = time.monotonic()
    with log.open("wb") as stream:
        process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=True, preexec_fn=limits)
        try:
            code = process.wait(timeout=limit)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if code:
        raise RuntimeError(f"process exit={code}; see {log}")
    return time.monotonic() - started


def cplex_result(solution: Path, log: Path, name: str, objective: str,
                 cutoff: int, elapsed: float) -> dict:
    import re
    text = log.read_text(errors="replace")
    solve = dict(status="timeout", timeout_seconds=cutoff, total_time=elapsed,
                 process_exit_code=0, solver_name="BigM_CPLEX_Eager", cplex_threads=4,
                 cplex_relative_gap=0, cplex_absolute_gap=0)
    if not solution.exists():
        if "Time limit exceeded" not in text:
            raise ValueError("CPLEX produced no schedule without a documented time limit")
        return solve
    root = ET.parse(solution).getroot()
    header = root.find("header")
    if header is None:
        raise ValueError("CPLEX solution header is missing")
    solve["native_status"] = dict(header.attrib)
    if header.get("primalFeasible") == "0":
        if "Time limit exceeded" not in text:
            raise ValueError("CPLEX has no primal feasible solution without a time limit")
        return solve
    variables = {v.attrib["name"]: float(v.attrib["value"]) for v in root.findall("./variables/variable")}
    trains = common.parse_txt_instance(name)
    schedule = []
    cost = 0
    for ti, visits in enumerate(trains):
        # Integer lags permit rounding all times upwards. Validate the rounded
        # schedule independently and require the objective to remain exact.
        times = [math.ceil(variables[f"t_{ti}_{vi}"] - 1e-7) for vi in range(len(visits))]
        times.append(times[-1] + visits[-1]["travel"])
        schedule.append(times)
        cost += sum(common.delay_cost(objective, times[vi]-v["aimed"])
                    for vi, v in enumerate(visits) if v["aimed"] is not None)
    solve.update(solution=schedule, cost=cost, ub=cost,
                 internal_cost=float(header.attrib["objectiveValue"]))
    if not common.same_number(cost, solve["internal_cost"]):
        raise ValueError("CPLEX rounded schedule cost differs from its objective")
    errors = common.independently_verify_solution(name, objective, solve)
    if errors:
        raise ValueError(f"CPLEX schedule validation failed: {errors}")
    solve["valid"] = True
    bounds = re.findall(r"Current MIP best bound\s*=\s*([-+\d.eE]+)", text)
    if bounds:
        solve["lb"] = float(bounds[-1])
    # 101 means exact integer optimality; tolerance-optimal status 102 alone
    # cannot establish a matching lower bound.
    if header.get("solutionStatusValue") == "101":
        solve.update(status="ok", lb=cost)
    elif audit.bounds_prove_optimal(solve):
        solve["status"] = "ok"
    return solve


def run_case(method: str, objective: str, name: str, args, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    cutoff = args.timeout
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGLR_", "MAXSATDDD_", "MAXSAT_RC2_", "SATDDD_"))}
    if method != "BigM-CPLEX":
        cfg = METHODS[method]
        env.update(BIN=str(args.binary.resolve()), SOLVER=cfg["solver"], OBJECTIVE=objective,
                   INSTANCE_NAMES=name, INSTANCE_ORDER_SEED="20261106", INSTANCE_TIMEOUT_SECS=str(cutoff),
                   RAM_LIMIT_KB=str(args.ram_kb), JSON_OUT=str(root/f"{objective}.json"),
                   RUN_LOG_DIR=str(root/"logs"), RERUN_NON_OK="0")
        for key, suffix in (("assumptions", "ASSUMPTIONS"), ("backend", "BACKEND"),
                            ("sparse_costs", "SPARSE_COSTS"), ("resource_orders", "RESOURCE_ORDERS"),
                            ("order_transitivity", "ORDER_TRANSITIVITY"),
                            ("objective_bound", "OBJECTIVE_BOUND"), ("residual_hardening", "RESIDUAL_HARDENING")):
            if key in cfg:
                env["MAXSATDDD_" + suffix] = cfg[key]
        execute(["bash", "quick_scripts/run_all_txt_instances_limited.sh"], REPO, root/"runner.log",
                cutoff+65, env, 0)
    else:
        instance = common.instance_path(name)
        build_time = execute([str(args.export_binary), str(instance), "bigm", objective, str(root)],
                             REPO, root/"build.log", 60, env, args.ram_kb)
        lp = root/f"{instance.stem}_bigm_{objective}.lp"
        solution = root/"schedule.sol"
        if solution.exists():
            raise ValueError("preserve an existing CPLEX schedule; use a new case directory")
        started = time.monotonic()
        execute([str(args.cplex_binary), "-c", f"read {lp}", "set threads 4",
                 "set mip tolerances mipgap 0", "set mip tolerances absmipgap 0",
                 f"set timelimit {max(0.001, cutoff-build_time):.6f}", "optimize",
                 "display solution bestbound", f"write {solution}", "quit"],
                root, root/"cplex.log", cutoff-build_time+30, env, args.ram_kb)
        solve = cplex_result(solution, root/"cplex.log", name, objective,
                             cutoff, build_time+time.monotonic()-started)
        solve["build_time"] = build_time
        save(root/f"{objective}.json", [dict(name=name, solves=[solve])])


def dependency_state(path: Path) -> dict:
    def git(*command):
        return subprocess.check_output(["git", "-C", str(path), *command])
    dirty = git("status", "--porcelain", "--untracked-files=all")
    return dict(commit=git("rev-parse", "HEAD").decode().strip(),
                status=dirty.decode(), diff_sha256=hashlib.sha256(git("diff", "--binary")).hexdigest())


def run(args) -> None:
    plan = json.loads(args.plan.read_text())
    selected = validate_plan(plan)
    if args.timeout != plan["timeout_seconds"]:
        raise ValueError("runner cutoff must equal the frozen plan cutoff")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=REPO).strip():
        raise ValueError("commit source changes before starting the campaign")
    root = args.results.resolve()
    root.mkdir(parents=True, exist_ok=True)
    locked = dict(plan_sha256=focus.sha(args.plan), git_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        binary_sha256=focus.sha(args.binary), export_binary_sha256=focus.sha(args.export_binary),
        cplex_binary_sha256=focus.sha(args.cplex_binary), ram_kb=args.ram_kb,
        methods=METHODS, sequential=True, threads_milp=4,
        cargo_lock_sha256=focus.sha(REPO/"Cargo.lock"), python=sys.version,
        platform=platform.platform(), machine=sorted(set(line for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith(("model name", "cpu family", "model\t", "stepping"))))
            if Path("/proc/cpuinfo").exists() else platform.processor(),
        memory=Path("/proc/meminfo").read_text().splitlines()[0] if Path("/proc/meminfo").exists() else None,
        salvers=dependency_state(REPO.parent/"salvers"), ipamir=dependency_state(REPO.parent/"ipamir-rs"))
    manifest = root/"manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != locked:
        raise ValueError("resume would change source, dependencies, binaries, environment or parameters")
    save(manifest, locked)
    save(root/"plan.json", plan)
    deadline = time.monotonic()+args.round_seconds
    records = []
    for method, objective, name in tasks_for(plan):
        case = root/"cases"/method/objective/name
        result = case/f"{objective}.json"
        if not result.exists():
            # Leave enough room to finish one instance and write the audit.
            if deadline-time.monotonic() < args.timeout+90:
                break
            print(f"Running {method}/{objective}/{name} at {args.timeout}s", flush=True)
            run_case(method, objective, name, args, case)
        record = assess_case(case, method, objective, name, args.timeout)
        records.append(record)
        report = summarize(plan, records)
        save(root/"extended_audit.json", report)
        if report["errors"]:
            raise ValueError(f"audit failed; preserve raw data and inspect {root/'extended_audit.json'}")
    report = summarize(plan, records)
    save(root/"extended_audit.json", report)
    audit.write_csv(root/"extended_summary.csv", report["summary"])
    print(json.dumps({k: report[k] for k in ("completed_runs", "expected_runs", "complete", "errors")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    builder = sub.add_parser("plan")
    builder.add_argument("--focus-manifest", type=Path, required=True)
    builder.add_argument("--reference", type=Path, default=Path("results"))
    builder.add_argument("--timeout", type=int, default=300)
    builder.add_argument("--output", type=Path, required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--plan", type=Path, required=True)
    runner.add_argument("--binary", type=Path, required=True)
    runner.add_argument("--export-binary", type=Path, required=True)
    runner.add_argument("--cplex-binary", type=Path, required=True)
    runner.add_argument("--results", type=Path, required=True)
    runner.add_argument("--timeout", type=int, default=300)
    runner.add_argument("--round-seconds", type=int, default=21600)
    runner.add_argument("--ram-kb", type=int, default=15000000)
    args = parser.parse_args()
    if args.action == "plan":
        if args.output.exists():
            raise ValueError("keep the old selection immutable")
        plan = build_plan(args.focus_manifest, args.reference, args.timeout)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save(args.output, plan)
        print(json.dumps(plan["instances_by_objective"], indent=2))
    else:
        run(args)


if __name__ == "__main__":
    main()
