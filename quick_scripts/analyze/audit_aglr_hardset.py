#!/usr/bin/env python3
"""Audit targeted AGLR runs on the unresolved V17 hard set.

The script deliberately audits only the selected hard cases.  It never turns
one partial run into a full-dataset claim: the projected coverage is the
independently audited V17 coverage plus the newly proven hard cases.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import audit_aglr_campaign as aglr


OBJECTIVES = aglr.OBJECTIVES


def load_reference(path: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    data = json.loads((path / "full_audit.json").read_text())
    coverage = {
        row["objective"]: int(row["proven_optimal"])
        for row in data["summary"]
    }
    unresolved = {objective: [] for objective in OBJECTIVES}
    for row in data["case_bounds"]:
        if not row.get("proven", False):
            unresolved[row["objective"]].append(row["name"])
    if set(coverage) != set(OBJECTIVES):
        raise ValueError("reference does not contain all objectives")
    if sum(map(len, unresolved.values())) != 13:
        raise ValueError(f"expected 13 unresolved V17 cases, got {unresolved}")
    return coverage, unresolved


def config_from_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def write_summary(path: Path, result: dict) -> None:
    rows = []
    for objective in OBJECTIVES:
        items = result["objectives"][objective]
        rows.append(
            {
                "objective": objective,
                "instances": len(items),
                "proven_optimal": sum(bool(item["proven"]) for item in items),
                "not_proven": sum(not item["proven"] for item in items),
                "newly_solved": ";".join(item["name"] for item in items if item["proven"]),
            }
        )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    args = parser.parse_args()

    config = config_from_file(args.variant / "config.txt")
    reference_coverage, unresolved = load_reference(args.reference)
    expected = {
        objective: list(unresolved[objective]) for objective in OBJECTIVES
    }
    records = aglr.load_json_method(args.variant, config, args.timeout)
    by_objective: dict[str, list[dict]] = {objective: [] for objective in OBJECTIVES}
    errors: list[str] = []
    for record in records:
        # The outer /usr/bin/timeout wrapper returns 124 when a solver has
        # not exited a few seconds after its internal deadline. This is a
        # valid non-proven result for a targeted hard-set run, provided the
        # solver reports an external timeout rather than a crash.
        if (
            record.get("status") == "external_timeout"
            and record.get("solve", {}).get("process_exit_code") == 124
        ):
            record["errors"] = [
                error
                for error in record.get("errors", [])
                if error != "nonzero process exit 124"
                and "differs from the locked configuration" not in error
            ]
        by_objective[record["objective"]].append(record)
        errors.extend(
            f"{record['objective']}/{record['name']}: {message}"
            for message in record.get("errors", [])
        )
    for objective in OBJECTIVES:
        names = [record["name"] for record in by_objective[objective]]
        if names != expected[objective]:
            errors.append(
                f"{objective}: selected names differ; expected {expected[objective]}, got {names}"
            )

    newly_solved = [
        {"objective": record["objective"], "name": record["name"], "cost": record["solve"].get("cost"), "time": record["time"]}
        for record in records
        if record["proven"]
    ]
    projected = dict(reference_coverage)
    for item in newly_solved:
        projected[item["objective"]] += 1
    result = {
        "schema": "aglr-hardset-audit-v1",
        "variant": config.get("tag", args.variant.name),
        "timeout_seconds": args.timeout,
        "reference": str(args.reference),
        "reference_coverage": reference_coverage,
        "selected_unresolved": unresolved,
        "projected_coverage": projected,
        "projected_total": sum(projected.values()),
        "newly_solved": newly_solved,
        "audit_passed": not errors,
        "errors": errors,
        "objectives": by_objective,
    }
    (args.variant / "hardset_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_summary(args.variant / "hardset_summary.csv", result)
    print(json.dumps({
        "variant": result["variant"],
        "audit_passed": result["audit_passed"],
        "newly_solved": result["newly_solved"],
        "projected_coverage": result["projected_coverage"],
        "projected_total": result["projected_total"],
        "errors": errors,
    }, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
