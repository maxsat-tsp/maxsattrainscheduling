"""Reuse published 120 s baselines without claiming old schedule validation."""
from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path

import audit_journal_campaign as common
from published_conference_reference import SOURCE_COMMIT

PREFIXES = {
    "MaxSAT-Journal": "MaxSAT_Baseline_RC2",
    "CSOnet": "MaxSAT_Default_RC2",
    "BigM-Gurobi": "MILP_BigM_Gurobi",
    "BigM-CPLEX": "MILP_BigM_CPLEX",
}


def number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def close(left, right):
    return (left is not None and right is not None
            and abs(left - right) <= 1e-6 * max(1.0, abs(left), abs(right)))


def canonical_name(value):
    if isinstance(value, str):
        for prefix, replacement in (("addtrack", "track"), ("addstation", "station"), ("original", "orig")):
            if value.startswith(prefix):
                return replacement + value[len(prefix):]
    return value


def load_file(path: Path, tag: str, objective: str) -> tuple[list[dict], list[str]]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    errors = []
    names = [canonical_name(row.get("name")) for row in rows]
    if len(names) != 72 or set(names) != set(common.EXPECTED_NAMES):
        errors.append(f"{path}: expected exactly 72 unique canonical instance names")
    records = []
    for row in rows:
        name, status = canonical_name(row.get("name")), row.get("status")
        lower, upper, cost, seconds = (number(row.get(key)) for key in ("lb", "ub", "cost", "total_time"))
        row_errors = []
        if status not in common.ALLOWED_STATUSES or status in common.FATAL_STATUSES:
            row_errors.append(f"unknown/fatal published status {status}")
        if row.get("delay_cost_type") != common.OBJECTIVE_LABELS[objective]:
            row_errors.append("published objective does not match filename")
        if seconds is None or seconds < 0:
            row_errors.append("invalid published total_time")
        if lower is not None and upper is not None and lower > upper and not close(lower, upper):
            row_errors.append("published lower bound exceeds upper bound")
        if status == "ok" and not close(cost, upper):
            row_errors.append("published cost does not match upper bound")
        # In MILP CSVs, status=ok also covers feasible but unproved runs.
        proven = status == "ok" and not row_errors and close(cost, upper) and close(lower, upper)
        errors.extend(f"{path}:{name}: {message}" for message in row_errors)
        records.append(dict(tag=tag, objective=objective, name=name, status=status,
                            proven=proven, time=min(seconds, 120.0) if seconds is not None else 120.0,
                            errors=row_errors, solve=dict(cost=cost, lb=lower, ub=upper,
                                                         total_time=seconds, status=status),
                            schedule_independently_verified=False,
                            config=dict(tag=tag, kind="published", result_source="published-csv-120")))
    return records, errors


def load_directory(root: Path) -> tuple[list[dict], dict]:
    records, errors, hashes = [], [], {}
    for tag, prefix in PREFIXES.items():
        for objective in common.OBJECTIVES:
            path = root / f"{prefix}_{objective}_120s.csv"
            try:
                hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                items, issues = load_file(path, tag, objective)
            except (OSError, ValueError) as error:
                errors.append(f"cannot read {path}: {error}")
                continue
            records.extend(items)
            errors.extend(issues)
    # Costs reported as optimal by different published baselines must agree.
    costs = {}
    for record in records:
        if record["proven"]:
            key = record["objective"], record["name"]
            costs.setdefault(key, {})[record["tag"]] = record["solve"]["cost"]
    conflicts = []
    for key, by_method in costs.items():
        if any(not close(left, right) for left in by_method.values() for right in by_method.values()):
            errors.append(f"published optimal costs disagree for {key}")
            conflicts.append(dict(objective=key[0], name=key[1], cost_by_method=by_method))
    return records, dict(source_data_commit=SOURCE_COMMIT, source_directory=str(root),
                         timeout_seconds=120, file_sha256=hashes, errors=errors,
                         cost_conflicts=conflicts,
                         schedule_independently_verified=False,
                         runtime_comparability_assumed=True,
                         verification_scope="reported costs, bounds, instance names and runtime; "
                                            "schedule validity is taken from the published experiment",
                         binary_commit="unknown")


def compare_new_costs(records: list[dict], references: list[dict]) -> list[dict]:
    by_key = {}
    for r in references:
        if r["proven"]:
            by_key.setdefault((r["objective"], r["name"]), []).append(r["solve"]["cost"])
    # A disputed published value must not be treated as an oracle for a new solver.
    costs = {key: values[0] for key, values in by_key.items()
             if all(close(values[0], value) for value in values)}
    return [dict(tag=r["tag"], objective=r["objective"], name=r["name"],
                 status="cost-mismatch", errors=["new optimum differs from a published baseline"])
            for r in records if r["proven"] and r["config"].get("kind") != "published"
            and (r["objective"], r["name"]) in costs
            and not close(r["solve"].get("cost"), costs[(r["objective"], r["name"])])]
