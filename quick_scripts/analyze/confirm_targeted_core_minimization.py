#!/usr/bin/env python3
"""Confirm gains three times after both bounded-core parameter trials finish."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import audit_targeted_core_minimization as checker
import extended_timeout_experiments as extended


def choose(trials, reference):
    audited = [(root, checker.audit_saved(root, reference)) for root in trials]
    if not audited or any(not report["complete"] or not report["audit_passed"] for _, report in audited):
        raise ValueError("finish and independently audit every parameter trial before confirmation")
    manifests = [json.loads((root/"manifest.json").read_text()) for root, _ in audited]
    for field in ("instances_by_objective", "timeout_seconds", "dataset_sha256", "binary_sha256", "solver_source_commit"):
        if any(manifest[field] != manifests[0][field] for manifest in manifests):
            raise ValueError(f"parameter trials differ in {field}")
    def rank(item):
        root, report = item
        penalty_sum = sum(row["instances"]*row["par2_seconds"] for row in report["summary"])
        return (-len(report["newly_solved"]), penalty_sum, root.name)
    return min(audited, key=rank)


def run(args):
    if not 0 < args.round_seconds <= 21600:
        raise ValueError("one round must be at most six hours")
    root, source_report = choose(args.trials, args.reference)
    source = json.loads((root/"manifest.json").read_text())
    if extended.focus.sha(args.binary) != source["binary_sha256"]:
        raise ValueError("confirmation binary differs from the selected trial")
    runner = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=extended.REPO, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=extended.REPO).strip():
        raise ValueError("commit the confirmation runner first")
    config = source["definition"]
    selection = source_report["newly_solved"]
    destination = args.results.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    locked = dict(schema="targeted-core-confirmation-v1", captured_utc=datetime.now(timezone.utc).isoformat(),
                  selected_trial=str(root.resolve()), trials=[dict(path=str(path.resolve()),
                      manifest_sha256=extended.focus.sha(path/"manifest.json"),
                      report_sha256=extended.focus.sha(path/"core_minimization_audit.json")) for path in args.trials],
                  runner_commit=runner, solver_source_commit=source["solver_source_commit"],
                  binary_sha256=source["binary_sha256"], dataset_sha256=source["dataset_sha256"],
                  definition=config, selected_gains=selection, repeats=3, timeout_seconds=source["timeout_seconds"],
                  ram_kb=args.ram_kb, cpu_affinity=sorted(os.sched_getaffinity(0)), sequential=True,
                  submission_passed=False)
    manifest_path = destination/"manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        locked["captured_utc"] = previous["captured_utc"]
        if locked != previous:
            raise ValueError("resume would change confirmation inputs or resources")
    else:
        extended.save(manifest_path, locked)
    runtime = SimpleNamespace(timeout=source["timeout_seconds"], binary=args.binary.resolve(), ram_kb=args.ram_kb,
                              method_definitions={"Core-confirm": config})
    deadline = time.monotonic()+args.round_seconds
    records = []
    expected = [(repeat, item) for repeat in range(1, 4) for item in selection]
    for repeat, item in expected:
        objective, name = item["objective"], item["name"]
        case = destination/"cases"/f"repeat-{repeat}"/objective/name
        if not (case/f"{objective}.json").exists():
            if deadline-time.monotonic() < runtime.timeout+90:
                break
            print(f"Confirm repeat-{repeat}: {objective}/{name}", flush=True)
            extended.run_case("Core-confirm", objective, name, runtime, case)
        record = extended.assess_case(case, "Core-confirm", objective, name, runtime.timeout, config)
        if record["errors"] or record["status"] in extended.audit.FATAL_STATUSES:
            raise ValueError(f"invalid confirmation {repeat}/{objective}/{name}: {record['errors']}")
        same_cost = record["proven"] and extended.common.same_number(record["solve"]["cost"], item["cost"])
        if record["proven"] and not same_cost:
            raise ValueError("independently validated optimum changed during confirmation")
        records.append(dict(repeat=repeat, objective=objective, name=name, proven=record["proven"],
                            expected_cost=item["cost"], cost=record["solve"].get("cost"),
                            seconds=record["time"], reproduced=same_cost))
        report = dict(schema=locked["schema"], expected_runs=len(expected), completed_runs=len(records),
                      complete=len(records) == len(expected), selected_trial=locked["selected_trial"],
                      confirmed=bool(expected) and len(records) == len(expected) and all(r["reproduced"] for r in records),
                      errors=[], submission_passed=False,
                      scope="three sequential repeats of gains only; no regression or full-dataset claim", cases=records)
        extended.save(destination/"confirmation_audit.json", report)
    if not expected:
        extended.save(destination/"confirmation_audit.json", dict(schema=locked["schema"], expected_runs=0,
            completed_runs=0, complete=True, confirmed=False, errors=[], submission_passed=False,
            scope="no gains to confirm", cases=[]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, nargs="+", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--ram-kb", type=int, default=6000000)
    parser.add_argument("--round-seconds", type=int, default=21600)
    args = parser.parse_args()
    try:
        run(args)
    except BaseException as error:
        if args.results.exists():
            extended.save(args.results/"failure.json", dict(error=str(error) or type(error).__name__))
        raise


if __name__ == "__main__":
    main()
