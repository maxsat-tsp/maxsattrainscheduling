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
    if not data.get('complete') or data.get('errors') or data.get('completed_runs') != 216:
        raise ValueError('reference must be a complete, clean 216-pair audit')
    pairs = [(row['objective'], row['name']) for row in data['case_bounds']]
    wanted = {(objective, name) for objective in OBJECTIVES
              for name in aglr.journal_audit.EXPECTED_NAMES}
    if len(pairs) != 216 or set(pairs) != wanted:
        raise ValueError('reference contains missing, duplicate, or unknown pairs')
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
    if any(coverage[o] != sum(bool(row['proven']) for row in data['case_bounds']
                             if row['objective'] == o) for o in OBJECTIVES):
        raise ValueError('reference coverage differs from case-level results')
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


def checked_timeout_record(record: dict, directory: Path, config: dict, timeout: float) -> dict:
    """Missing telemetry needs a matching launch manifest; a mismatch never does.

    An outer timeout may kill the solver before it can flush its statistics.
    Keep every other validation error, including any *present* wrong setting.
    """
    result = dict(record, errors=list(record.get('errors', [])))
    solve = record.get('solve', {})
    if record.get('status') != 'external_timeout' or solve.get('process_exit_code') != 124:
        return result
    manifest_path = directory / (record['objective'] + '.logs') / 'manifest.txt'
    try:
        launch = config_from_file(manifest_path)
        expected = {'solver': config['solver'], 'objective': record['objective'],
                    'instance_timeout_seconds': str(int(timeout))}
        for key in ('assumptions', 'backend', 'sparse_costs', 'resource_orders',
                    'order_transitivity', 'core_minimize_checks',
                    'core_minimize_conflicts', 'core_exhaust_checks'):
            if key in config:
                expected['maxsatddd_' + key] = config[key]
        for key in ('policy', 'min_growth', 'fraction', 'max_wait', 'rescue_progress',
                    'heuristic_period', 'heuristic_min_gap', 'use_objective_bound', 'filter_duplicates'):
            if key in config:
                expected['aglr_' + key] = config[key]
        if any(launch.get(key) != value for key, value in expected.items()):
            raise ValueError('external timeout launch settings do not match')
        if record['name'] not in launch.get('selected_instances', '').split(','):
            raise ValueError('external timeout instance is absent from launch manifest')
        wall = aglr.finite_number(solve.get('process_wall_time_seconds'))
        outer = aglr.finite_number(launch.get('external_timeout_seconds'))
        if wall is None or outer is None or outer < timeout or wall < outer - 0.5:
            raise ValueError('external timeout has no matching wall-time evidence')
    except (OSError, KeyError, ValueError) as error:
        result['errors'].append(str(error))
        return result
    removable = {'nonzero process exit 124'}
    # Missing values can be explained by the matching process manifest.
    # Values present in JSON still have to match the locked configuration.
    for key in expected:
        telemetry = key.replace('maxsatddd_', 'maxsat_', 1)
        if key.startswith(('maxsatddd_', 'aglr_')) and telemetry not in solve:
            removable.add(telemetry + ' differs from the locked configuration')
    result['errors'] = [error for error in result['errors'] if error not in removable]
    result['external_timeout_launch_verified'] = True
    return result


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
    records = [checked_timeout_record(record, args.variant, config, args.timeout) for record in records]
    for record in records:
        if record['status'] in aglr.FATAL_STATUSES:
            record['errors'].append('fatal solver status ' + record['status'])
        if record['solve'].get('solution') is not None and record['status'] != 'ok':
            record['errors'].extend(aglr.journal_audit.independently_verify_solution(
                record['name'], record['objective'], record['solve']))
        by_objective[record["objective"]].append(record)
        errors.extend(
            f"{record['objective']}/{record['name']}: {message}"
            for message in record.get("errors", [])
        )
    for objective in OBJECTIVES:
        names = [record["name"] for record in by_objective[objective]]
        if sorted(names) != sorted(expected[objective]):
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
        "full_coverage_validated": False,
        "submission_passed": False,
        "scope": "Unresolved pairs only. Projected coverage assumes no regression on the 203 untested solved pairs.",
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
