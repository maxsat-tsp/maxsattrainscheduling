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
import shutil
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


def methods_for(plan: dict) -> dict:
    backend = plan.get("sat_backend", "minisat")
    if backend not in {"minisat", "cadical"}:
        raise ValueError("unsupported common MaxSAT backend")
    base = {tag: (dict(cfg, backend="cadical") if backend == "cadical"
                  and tag in {"Orders-Transitive", "CSOnet", "MaxSAT-Journal"} else cfg)
            for tag,cfg in METHODS.items()}
    variant = plan.get("candidate_variant")
    if variant is None:
        return base
    if variant != "mincore4" or plan.get("candidate_tag") != "Orders-Transitive-Mincore":
        raise ValueError("unsupported extended-timeout candidate variant")
    return {("Orders-Transitive-Mincore" if tag == "Orders-Transitive" else tag):
            (dict(cfg, core_minimize_checks="4") if tag == "Orders-Transitive"
             else dict(cfg, result_source="reused-audited-same-timeout"))
            for tag, cfg in base.items()}


def save(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def build_plan(manifest: Path, reference: Path, cutoff: int, sat_backend: str = "cadical") -> dict:
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
                sat_backend=sat_backend, conference_sat_backend="not-verified-from-binary-provenance",
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
    methods_for(plan)
    return selected


def tasks_for(plan: dict) -> list[tuple[str, str, str]]:
    selected = validate_plan(plan)
    pairs = [(o, n) for o in audit.OBJECTIVES for n in selected[o]]
    rng = random.Random(20261106)
    rng.shuffle(pairs)
    tasks = []
    for objective, name in pairs:
        methods = list(methods_for(plan))
        rng.shuffle(methods)
        tasks.extend((method, objective, name) for method in methods)
    return tasks


def method_config(method: str, selection: dict, cutoff: int, definition: dict | None = None) -> dict:
    return dict(METHODS[method] if definition is None else definition, tag=method, timeout_seconds=str(cutoff),
                process_exit_required="true", parallelism="1",
                instances_by_objective=json.dumps(selection, separators=(",", ":")))


def assess_case(root: Path, method: str, objective: str, name: str, cutoff: int, definition: dict | None = None) -> dict:
    selection = {o: [name] if o == objective else [] for o in audit.OBJECTIVES}
    records = audit.load_json_method(root, method_config(method, selection, cutoff, definition), cutoff)
    if len(records) != 1 or records[0]["name"] != name:
        raise ValueError("a case must contain exactly its planned objective and instance")
    record = records[0]
    solve = record["solve"]
    if solve.get("solution") is not None and record["status"] != "ok":
        record["errors"].extend(common.independently_verify_solution(name, objective, solve))
    evidence_path = root/"reused_from.json"
    if evidence_path.exists():
        evidence = json.loads(evidence_path.read_text())
        if focus.sha(root/f"{objective}.json") != evidence.get("sha256") or evidence.get("measured_again") is not False:
            raise ValueError("reused case bytes or provenance changed")
        record["config"]["result_source"] = "reused-audited-same-timeout"
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
    definitions = methods_for(plan)
    candidate_tag = plan.get("candidate_tag", "Orders-Transitive")
    by_pair = defaultdict(set)
    for record in records:
        by_pair[record["objective"], record["name"]].add(record["tag"])
    common_pairs = {key for key, tags in by_pair.items() if tags == set(definitions)}
    comparable = [r for r in records if (r["objective"], r["name"]) in common_pairs]
    comparisons = []
    candidate = {(r["objective"], r["name"]): r for r in records if r["tag"] == candidate_tag}
    for baseline in definitions:
        if baseline == candidate_tag:
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
    report = dict(scope=plan["scope"], timeout_seconds=cutoff,
                expected_runs=len(expected), completed_runs=len(records),
                complete=len(records) == len(expected), errors=errors,
                submission_passed=False, full_validation_required=True,
                summary=audit.summarize(records, cutoff),
                common_completed_pairs=len(common_pairs),
                comparable_summary=audit.summarize(comparable, cutoff), comparisons=comparisons,
                completed_after_120=[dict(method=r["tag"], objective=r["objective"], name=r["name"],
                                         seconds=r["time"], cost=r["solve"].get("cost"))
                                     for r in records if r["proven"] and r["time"] > 120],
                case_bounds=[dict(method=r["tag"], objective=r["objective"], name=r["name"],
                                  status=r["status"], proven=r["proven"], seconds=r["time"],
                                  reported_lb=r["solve"].get("lb"), reported_ub=r["solve"].get("ub"))
                             for r in records],
                missing=[list(k) for k in tasks_for(plan) if k not in set(keys)])
    if plan.get("candidate_variant") is not None:
        report.update(measured_runs=sum(r["tag"] == candidate_tag for r in records),
                      reused_baseline_runs=sum(r["tag"] != candidate_tag for r in records))
    else:
        reused_milp = sum(r["tag"] in {"BigM-Gurobi", "BigM-CPLEX"}
                         and r.get("config",{}).get("result_source") == "reused-audited-same-timeout"
                         for r in records)
        if reused_milp:
            report.update(reused_milp_runs=reused_milp, measured_runs=len(records)-reused_milp)
    return report


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
        cfg = getattr(args, "method_definitions", METHODS)[method]
        env.update(BIN=str(args.binary.resolve()), SOLVER=cfg["solver"], OBJECTIVE=objective,
                   INSTANCE_NAMES=name, INSTANCE_ORDER_SEED="20261106", INSTANCE_TIMEOUT_SECS=str(cutoff),
                   RAM_LIMIT_KB=str(args.ram_kb), JSON_OUT=str(root/f"{objective}.json"),
                   RUN_LOG_DIR=str(root/"logs"), RERUN_NON_OK="0")
        for key, suffix in (("assumptions", "ASSUMPTIONS"), ("backend", "BACKEND"),
                            ("sparse_costs", "SPARSE_COSTS"), ("resource_orders", "RESOURCE_ORDERS"),
                            ("order_transitivity", "ORDER_TRANSITIVITY"),
                            ("order_cycle_cuts", "ORDER_CYCLE_CUTS"),
                            ("order_path_cuts", "ORDER_PATH_CUTS"),
                            ("order_master", "ORDER_MASTER"),
                            ("extract_initial_cost", "EXTRACT_INITIAL_COST"),
                            ("objective_bound", "OBJECTIVE_BOUND"), ("residual_hardening", "RESIDUAL_HARDENING"),
                            ("core_minimize_checks", "CORE_MINIMIZE_CHECKS"),
                            ("core_minimize_conflicts", "CORE_MINIMIZE_CONFLICTS"),
                            ("core_exhaust_checks", "CORE_EXHAUST_CHECKS")):
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


def reports_match(left, right, field: str = "") -> bool:
    """Permit machine-rounding differences only in derived runtime statistics."""
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(reports_match(left[k], right[k], k) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(reports_match(a, b, field) for a,b in zip(left,right))
    if field in {"par2_seconds", "median_solved_seconds", "mean_selected_growth", "paired_geomean_speedup"}:
        if isinstance(left, (int,float)) and isinstance(right, (int,float)):
            return math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-12)
    return left == right


def audit_saved(root: Path) -> dict:
    """Rebuild the report from a completed run or an immutable partial snapshot."""
    snapshot = root/"snapshot.json"
    if snapshot.exists():
        metadata = json.loads(snapshot.read_text())
        if metadata.get("schema") != "extended-timeout-snapshot-v1":
            raise ValueError("unsupported snapshot schema")
        for name, expected_hash in metadata["file_sha256"].items():
            path = (root/name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or focus.sha(path) != expected_hash:
                raise ValueError(f"missing or changed snapshot artifact {name}")
    plan = json.loads((root/"plan.json").read_text())
    validate_plan(plan)
    locked = json.loads((root/"manifest.json").read_text())
    canonical_plan = json.dumps(plan, indent=2) + "\n"
    if locked["plan_sha256"] != hashlib.sha256(canonical_plan.encode()).hexdigest():
        raise ValueError("saved plan does not match the locked source manifest")
    definitions = methods_for(plan)
    if locked.get("methods") != definitions:
        raise ValueError("saved method settings differ from this auditor")
    if locked.get("milp_reuse"):
        for file,key in (("milp_reuse_manifest.json","manifest_sha256"),
                         ("milp_reuse_audit.json","report_sha256")):
            if focus.sha(root/file) != locked["milp_reuse"][key]:
                raise ValueError("reused MILP provenance changed")
    if plan.get("candidate_variant") is not None:
        for file, key in (("reference_manifest.json", "reference_manifest_sha256"),
                          ("reference_audit.json", "reference_audit_sha256")):
            if focus.sha(root/file) != plan[key]:
                raise ValueError("saved baseline provenance differs from the frozen reference")
    original = json.loads((root/"extended_audit.json").read_text())
    if original.get("expected_runs") != len(tasks_for(plan)):
        raise ValueError("saved report has an incorrect planned run count")
    records = []
    for item in original["case_bounds"]:
        method, objective, name = item["method"], item["objective"], item["name"]
        if (method, objective, name) not in set(tasks_for(plan)):
            raise ValueError("saved report contains an unplanned case")
        records.append(assess_case(root/"cases"/method/objective/name,
                                   method, objective, name, plan["timeout_seconds"], definitions[method]))
        if plan.get("candidate_variant") is not None and method != plan["candidate_tag"]:
            case = root/"cases"/method/objective/name
            evidence = json.loads((case/"reused_from.json").read_text())
            if focus.sha(case/f"{objective}.json") != evidence["sha256"] or (
                evidence["manifest_sha256"] != plan["reference_manifest_sha256"]
                or evidence["report_sha256"] != plan["reference_audit_sha256"]
                or evidence.get("measured_again") is not False
            ):
                raise ValueError("reused baseline bytes or provenance changed")
        if locked.get("milp_reuse") and (root/"cases"/method/objective/name/"reused_from.json").exists():
            evidence = json.loads((root/"cases"/method/objective/name/"reused_from.json").read_text())
            if method not in {"BigM-Gurobi", "BigM-CPLEX"} or any(
                evidence[key] != locked["milp_reuse"][ref]
                for key,ref in (("manifest_sha256","manifest_sha256"),("report_sha256","report_sha256"))
            ):
                raise ValueError("only matching MILP cases may cross the SAT-backend correction")
    rebuilt = summarize(plan, records)
    if not reports_match(rebuilt, original):
        raise ValueError("saved report differs from the independently regenerated result")
    if rebuilt["errors"]:
        raise ValueError(f"saved result failed independent audit: {rebuilt['errors']}")
    audit.write_csv(root/"extended_summary.csv", rebuilt["summary"])
    audit.write_csv(root/"extended_comparable_summary.csv", rebuilt["comparable_summary"])
    return rebuilt


def candidate_plan(reference: Path) -> dict:
    report = audit_saved(reference)
    if not report["complete"]:
        raise ValueError("finish and audit the baseline campaign before reusing it")
    plan = json.loads((reference/"plan.json").read_text())
    if plan.get("candidate_variant") is not None:
        raise ValueError("reuse must come from the original five-method comparison")
    plan.update(candidate_variant="mincore4", candidate_tag="Orders-Transitive-Mincore",
                reference_manifest_sha256=focus.sha(reference/"manifest.json"),
                reference_audit_sha256=focus.sha(reference/"extended_audit.json"),
                scope="new candidate measured at the same cutoff; four audited baseline runs reused; no full-dataset claim")
    validate_plan(plan)
    return plan


def reuse_case(source: Path, destination: Path, plan: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    evidence = dict(source=str(source.resolve()), sha256=focus.sha(source),
                    manifest_sha256=plan["reference_manifest_sha256"],
                    report_sha256=plan["reference_audit_sha256"], measured_again=False)
    evidence_path = destination.parent/"reused_from.json"
    if destination.exists():
        if focus.sha(destination) != evidence["sha256"] or json.loads(evidence_path.read_text()) != evidence:
            raise ValueError("resume would replace a changed baseline result")
    else:
        shutil.copy2(source, destination)
        save(evidence_path, evidence)


def reusable_milp_cases(reference: Path, plan: dict, definitions: dict) -> tuple[set, dict]:
    report = audit_saved(reference)
    manifest = json.loads((reference/"manifest.json").read_text())
    source_plan = json.loads((reference/"plan.json").read_text())
    if source_plan["timeout_seconds"] != plan["timeout_seconds"] or source_plan["dataset_sha256"] != plan["dataset_sha256"]:
        raise ValueError("MILP reuse requires the identical cutoff and dataset")
    for method in ("BigM-Gurobi", "BigM-CPLEX"):
        if manifest["methods"][method] != definitions[method]:
            raise ValueError("MILP settings changed across the backend correction")
    selected = set(tasks_for(plan))
    return ({(r["method"],r["objective"],r["name"]) for r in report["case_bounds"]
             if r["method"] in {"BigM-Gurobi", "BigM-CPLEX"}
             and (r["method"],r["objective"],r["name"]) in selected}, manifest)


def run(args) -> None:
    plan = json.loads(args.plan.read_text())
    selected = validate_plan(plan)
    if args.timeout != plan["timeout_seconds"]:
        raise ValueError("runner cutoff must equal the frozen plan cutoff")
    definitions = methods_for(plan)
    args.method_definitions = definitions
    reference = getattr(args, "reference_results", None)
    milp_reference = getattr(args, "reuse_milp_from", None)
    if reference is not None and milp_reference is not None:
        raise ValueError("choose either a complete baseline reference or selective MILP reuse")
    reusable = set()
    if milp_reference is not None:
        reusable, source_manifest = reusable_milp_cases(milp_reference,plan,definitions)
    if (plan.get("candidate_variant") is not None) != (reference is not None):
        raise ValueError("a new candidate requires its locked baseline reference")
    if reference is not None:
        if candidate_plan(reference) != plan:
            raise ValueError("baseline reference differs from the frozen candidate plan")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=REPO).strip():
        raise ValueError("commit source changes before starting the campaign")
    root = args.results.resolve()
    root.mkdir(parents=True, exist_ok=True)
    locked = dict(plan_sha256=focus.sha(args.plan), git_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        binary_sha256=focus.sha(args.binary), export_binary_sha256=focus.sha(args.export_binary),
        cplex_binary_sha256=focus.sha(args.cplex_binary), ram_kb=args.ram_kb,
        methods=definitions, sequential=True, threads_milp=4,
        cargo_lock_sha256=focus.sha(REPO/"Cargo.lock"), python=sys.version,
        platform=platform.platform(), machine=sorted(set(line for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith(("model name", "cpu family", "model\t", "stepping"))))
            if Path("/proc/cpuinfo").exists() else platform.processor(),
        memory=Path("/proc/meminfo").read_text().splitlines()[0] if Path("/proc/meminfo").exists() else None,
        salvers=dependency_state(REPO.parent/"salvers"), ipamir=dependency_state(REPO.parent/"ipamir-rs"))
    if milp_reference is not None:
        for field in ("ram_kb", "platform", "machine", "memory", "threads_milp"):
            if source_manifest[field] != locked[field]:
                raise ValueError(f"MILP reuse environment changed: {field}")
        locked["milp_reuse"] = dict(source=str(milp_reference.resolve()),
            manifest_sha256=focus.sha(milp_reference/"manifest.json"),
            report_sha256=focus.sha(milp_reference/"extended_audit.json"))
    manifest = root/"manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != locked:
        raise ValueError("resume would change source, dependencies, binaries, environment or parameters")
    save(manifest, locked)
    save(root/"plan.json", plan)
    if milp_reference is not None:
        for source,target in (("manifest.json","milp_reuse_manifest.json"),
                              ("extended_audit.json","milp_reuse_audit.json")):
            shutil.copy2(milp_reference/source,root/target)
    if reference is not None:
        for source, target in (("manifest.json", "reference_manifest.json"),
                               ("extended_audit.json", "reference_audit.json")):
            shutil.copy2(reference/source, root/target)
    deadline = time.monotonic()+args.round_seconds
    records = []
    for method, objective, name in tasks_for(plan):
        case = root/"cases"/method/objective/name
        result = case/f"{objective}.json"
        if (method,objective,name) in reusable:
            reuse_case(milp_reference/"cases"/method/objective/name/f"{objective}.json", result,
                       dict(reference_manifest_sha256=locked["milp_reuse"]["manifest_sha256"],
                            reference_audit_sha256=locked["milp_reuse"]["report_sha256"]))
        elif reference is not None and method != plan["candidate_tag"]:
            reuse_case(reference/"cases"/method/objective/name/f"{objective}.json", result, plan)
        elif not result.exists():
            # Leave enough room to finish one instance and write the audit.
            if deadline-time.monotonic() < args.timeout+90:
                break
            print(f"Running {method}/{objective}/{name} at {args.timeout}s", flush=True)
            run_case(method, objective, name, args, case)
        record = assess_case(case, method, objective, name, args.timeout, definitions[method])
        records.append(record)
        report = summarize(plan, records)
        save(root/"extended_audit.json", report)
        if report["errors"]:
            raise ValueError(f"audit failed; preserve raw data and inspect {root/'extended_audit.json'}")
    report = summarize(plan, records)
    save(root/"extended_audit.json", report)
    audit.write_csv(root/"extended_summary.csv", report["summary"])
    audit.write_csv(root/"extended_comparable_summary.csv", report["comparable_summary"])
    print(json.dumps({k: report[k] for k in ("completed_runs", "expected_runs", "complete", "errors")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    builder = sub.add_parser("plan")
    builder.add_argument("--focus-manifest", type=Path, required=True)
    builder.add_argument("--reference", type=Path, default=Path("results"))
    builder.add_argument("--timeout", type=int, default=300)
    builder.add_argument("--sat-backend", choices=["minisat", "cadical"], default="cadical")
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
    runner.add_argument("--reference-results", type=Path)
    runner.add_argument("--reuse-milp-from", type=Path)
    trial = sub.add_parser("candidate-plan")
    trial.add_argument("--reference-results", type=Path, required=True)
    trial.add_argument("--output", type=Path, required=True)
    saved = sub.add_parser("audit-saved")
    saved.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        if args.output.exists():
            raise ValueError("keep the old selection immutable")
        plan = build_plan(args.focus_manifest, args.reference, args.timeout, args.sat_backend)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save(args.output, plan)
        print(json.dumps(plan["instances_by_objective"], indent=2))
    elif args.action == "candidate-plan":
        if args.output.exists():
            raise ValueError("preserve the frozen candidate plan")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save(args.output, candidate_plan(args.reference_results))
    elif args.action == "audit-saved":
        report = audit_saved(args.results)
        print(json.dumps({k:report[k] for k in ("completed_runs", "expected_runs", "complete", "errors", "common_completed_pairs")}))
    else:
        run(args)


if __name__ == "__main__":
    main()
