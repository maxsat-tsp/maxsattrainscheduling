#!/usr/bin/env python3
"""Run and independently check the Big-M CPLEX baseline for all 216 cases.

The runner is resumable. Multiple workers may process disjoint cases, but
their timings are diagnostic; a final sequential timing pass is still needed
for a runtime comparison.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import extended_timeout_experiments as extended


def records_for(root: Path, timeout: int) -> list[dict]:
    result = []
    for objective in extended.audit.OBJECTIVES:
        for name in extended.common.EXPECTED_NAMES:
            case = root / "cases" / "BigM-CPLEX" / objective / name
            result.append(extended.assess_case(root=case, method="BigM-CPLEX",
                                               objective=objective, name=name,
                                               cutoff=timeout,
                                               definition=extended.METHODS["BigM-CPLEX"]))
    return result


def write_summary(root: Path, records: list[dict]) -> None:
    fields = ["objective", "name", "status", "proven", "time", "cost", "lb", "ub", "errors"]
    with (root / "cplex_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            solve = row.get("solve", {})
            writer.writerow({
                "objective": row["objective"],
                "name": row["name"],
                "status": row["status"],
                "proven": row["proven"],
                "time": row["time"],
                "cost": solve.get("cost"),
                "lb": solve.get("lb"),
                "ub": solve.get("ub"),
                "errors": ";".join(row.get("errors", [])),
            })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--export-binary", type=Path, required=True)
    parser.add_argument("--cplex-binary", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--ram-kb", type=int, default=6_000_000)
    parser.add_argument("--worker-index", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.timeout <= 0 or args.workers <= 0 or not 0 <= args.worker_index < args.workers:
        parser.error("invalid timeout or worker selection")

    root = args.results.resolve()
    root.mkdir(parents=True, exist_ok=True)
    tasks = [(objective, name)
             for objective in extended.audit.OBJECTIVES
             for name in extended.common.EXPECTED_NAMES]
    tasks = [task for index, task in enumerate(tasks) if index % args.workers == args.worker_index]
    runtime = type("Runtime", (), {
        "timeout": args.timeout,
        "ram_kb": args.ram_kb,
        "binary": args.binary,
        "export_binary": args.export_binary,
        "cplex_binary": args.cplex_binary,
    })()
    completed = []
    try:
        for objective, name in tasks:
            case = root / "cases" / "BigM-CPLEX" / objective / name
            result_file = case / f"{objective}.json"
            invalid_marker = case / "invalid.json"
            if invalid_marker.exists():
                print(f"worker={args.worker_index} reusing invalid marker {objective}/{name}", flush=True)
                continue
            if not result_file.exists():
                print(f"worker={args.worker_index} running {objective}/{name}", flush=True)
                try:
                    extended.run_case("BigM-CPLEX", objective, name, runtime, case)
                except ValueError as error:
                    # Keep the CPLEX log, LP and solution for diagnosis, but
                    # do not let one invalid incumbent stop the full table.
                    case.mkdir(parents=True, exist_ok=True)
                    invalid_marker.write_text(json.dumps({
                        "objective": objective,
                        "name": name,
                        "status": "invalid",
                        "timeout_seconds": args.timeout,
                        "error": str(error),
                    }, indent=2) + "\n")
                    print(f"worker={args.worker_index} INVALID {objective}/{name}: {error}", flush=True)
                    continue
            record = extended.assess_case(case, "BigM-CPLEX", objective, name,
                                          args.timeout, extended.METHODS["BigM-CPLEX"])
            if record["errors"]:
                raise RuntimeError(f"{objective}/{name}: {record['errors']}")
            completed.append(record)
            print(f"worker={args.worker_index} checked {objective}/{name} status={record['status']} proven={record['proven']}", flush=True)
        (root / f"worker_{args.worker_index}.json").write_text(json.dumps({
            "worker_index": args.worker_index,
            "workers": args.workers,
            "timeout": args.timeout,
            "completed": len(completed),
        }, indent=2) + "\n")
        return 0
    except BaseException as error:
        (root / f"worker_{args.worker_index}_failure.json").write_text(json.dumps({
            "worker_index": args.worker_index,
            "error": str(error),
            "completed": len(completed),
        }, indent=2) + "\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
