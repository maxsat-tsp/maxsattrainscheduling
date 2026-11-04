#!/usr/bin/env python3
"""Independently audit and summarize the accepted-conference baseline.

The raw JSON/CSV files came from source-data commit c427a10.  Their schedules
are useful as regression oracles after independent validation.  Their runtime
is diagnostic only because the submitted bundle has no machine/binary manifest.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

import audit_journal_campaign as journal_audit


OBJECTIVES = ("finsteps123", "infsteps180", "cont")
CONFIG = "MaxsatScDefault"
SOURCE_DATA_COMMIT = "c427a104c3c6f844e515efb7f898b684553b0f3f"
EXPECTED_SOLVER = "MaxSatDddLadderSc"


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def matching_optimal_bounds(solve: dict) -> bool:
    cost = finite_number(solve.get("cost"))
    lower = finite_number(solve.get("lb"))
    upper = finite_number(solve.get("ub"))
    if cost is None or lower is None or upper is None:
        return False
    tolerance = 1e-6 * max(1.0, abs(cost), abs(lower), abs(upper))
    return abs(cost - lower) <= tolerance and abs(cost - upper) <= tolerance


def expected_path(result_dir: Path, objective: str) -> Path:
    return result_dir / f"{CONFIG}_{objective}.json"


def audit_result_file(path: Path, objective: str) -> tuple[list[dict], list[str], float | None]:
    errors: list[str] = []
    try:
        rows = journal_audit.load_rows(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"{path}: cannot read result JSON: {exc}"], None

    names = [name for name, _ in rows]
    counts = Counter(names)
    if names != journal_audit.EXPECTED_NAMES:
        missing = sorted(set(journal_audit.EXPECTED_NAMES) - set(names))
        unexpected = sorted(set(names) - set(journal_audit.EXPECTED_NAMES))
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        errors.append(
            f"{path}: expected the canonical 72-instance list; "
            f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}"
        )

    timeout_values = {
        value
        for _, solve in rows
        if (value := finite_number(solve.get("timeout_seconds"))) is not None
    }
    timeout = next(iter(timeout_values)) if len(timeout_values) == 1 else None
    if timeout != 150.0:
        errors.append(
            f"{path}: expected one consistent 150-second timeout, found "
            f"{sorted(timeout_values)}"
        )

    records: list[dict] = []
    for name, solve in rows:
        item_errors: list[str] = []
        status = solve.get("status")
        if name not in journal_audit.EXPECTED_NAMES:
            item_errors.append(f"unexpected instance name {name!r}")
        if counts[name] > 1:
            item_errors.append(f"duplicate instance name {name!r}")
        if status not in journal_audit.ALLOWED_STATUSES:
            item_errors.append(f"unsupported status {status!r}")
        elif status in journal_audit.FATAL_STATUSES:
            item_errors.append(f"fatal status {status!r}")

        if solve.get("solver_name") != EXPECTED_SOLVER:
            item_errors.append(
                f"solver_name={solve.get('solver_name')!r}, expected {EXPECTED_SOLVER!r}"
            )
        wanted_label = journal_audit.OBJECTIVE_LABELS[objective]
        if solve.get("delay_cost_type") != wanted_label:
            item_errors.append(
                f"delay_cost_type={solve.get('delay_cost_type')!r}, expected {wanted_label!r}"
            )
        if timeout is not None and not journal_audit.same_number(
            solve.get("timeout_seconds"), timeout
        ):
            item_errors.append(
                f"timeout_seconds={solve.get('timeout_seconds')!r}, expected {timeout}"
            )

        total_time = finite_number(solve.get("total_time"))
        if total_time is None or total_time < 0:
            item_errors.append("total_time must be finite and nonnegative")

        if status == "ok":
            if not matching_optimal_bounds(solve):
                item_errors.append(
                    "status=ok requires matching finite cost, lower bound, and upper bound"
                )
            if name in journal_audit.EXPECTED_NAMES:
                item_errors.extend(
                    f"independent verification: {message}"
                    for message in journal_audit.independently_verify_solution(
                        name, objective, solve
                    )
                )
        elif status in {"timeout", "external_timeout"}:
            lower = finite_number(solve.get("lb"))
            upper = finite_number(solve.get("ub"))
            if lower is None or upper is None or lower > upper:
                item_errors.append("timeout requires finite bounds with lb <= ub")

        errors.extend(f"{path}:{name}: {message}" for message in item_errors)
        records.append(
            {
                "objective": objective,
                "name": name,
                "status": status,
                "verified": status == "ok" and not item_errors,
                "cost": solve.get("cost"),
                "lb": solve.get("lb"),
                "ub": solve.get("ub"),
                "total_time": total_time,
                "errors": item_errors,
            }
        )
    return records, errors, timeout


def summarize_records(records: list[dict], timeout: float) -> dict:
    statuses = Counter(record["status"] for record in records)
    verified = [record for record in records if record["verified"]]
    verified_times = [record["total_time"] for record in verified]
    par2 = statistics.fmean(
        record["total_time"]
        if record["verified"] and record["total_time"] <= timeout
        else 2.0 * timeout
        for record in records
    )
    recognized = sum(statuses.get(status, 0) for status in journal_audit.ALLOWED_STATUSES)
    return {
        "config": CONFIG,
        "objective": records[0]["objective"] if records else "",
        "n": len(records),
        "ok": statuses.get("ok", 0),
        "verified_ok": len(verified),
        "timeout": statuses.get("timeout", 0) + statuses.get("external_timeout", 0),
        "panic": statuses.get("panic", 0),
        "invalid_solution": statuses.get("invalid_solution", 0),
        "oom": statuses.get("oom", 0) + statuses.get("killed", 0),
        "other_failure": len(records) - recognized,
        "median_ok_ms": statistics.median(verified_times) * 1000.0
        if verified_times
        else "",
        "median_ok_seconds": statistics.median(verified_times)
        if verified_times
        else "",
        "par2_seconds": par2,
        "timeout_seconds": timeout,
        "runtime_comparable": False,
    }


def audit_directory(
    result_dir: Path, source_commit: str = SOURCE_DATA_COMMIT
) -> tuple[list[dict], dict, list[dict]]:
    source_directory = str(result_dir)
    result_dir = result_dir.resolve()
    all_records: list[dict] = []
    all_errors: list[str] = []
    summary: list[dict] = []

    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        all_errors.append(
            "Conference data requires a full 40-character hexadecimal source commit"
        )

    for objective in OBJECTIVES:
        records, errors, timeout = audit_result_file(
            expected_path(result_dir, objective), objective
        )
        all_records.extend(records)
        all_errors.extend(errors)
        if records and timeout is not None:
            summary.append(summarize_records(records, timeout))

    manifest_paths = sorted(result_dir.glob("*.logs/manifest.txt"))
    warnings: list[str] = []
    if not manifest_paths:
        warnings.append(
            "No machine/binary manifest was supplied; coverage and verified costs "
            "are reusable, but runtime is diagnostic only."
        )

    audit = {
        "source_data_commit": source_commit,
        "source_directory": source_directory,
        "runtime_comparable": bool(manifest_paths) and not all_errors,
        "manifest_files": [str(path.relative_to(result_dir)) for path in manifest_paths],
        "warnings": warnings,
        "errors": all_errors,
        "verified_optima": {
            objective: sum(
                record["verified"]
                for record in all_records
                if record["objective"] == objective
            )
            for objective in OBJECTIVES
        },
    }
    return summary, audit, all_records


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("summary_out", type=Path, nargs="?")
    parser.add_argument("--audit-out", type=Path)
    parser.add_argument("--source-commit", default=SOURCE_DATA_COMMIT)
    args = parser.parse_args()

    result_dir = args.result_dir
    summary_out = args.summary_out or result_dir / "summary_conference.csv"
    audit_out = args.audit_out or result_dir / "conference_audit.json"
    summary, audit, _ = audit_directory(result_dir, args.source_commit)
    write_csv(summary_out, summary)
    audit_out.write_text(json.dumps(audit, indent=2) + "\n")

    print(f"Wrote {summary_out}")
    print(f"Wrote {audit_out}")
    for warning in audit["warnings"]:
        print(f"WARNING: {warning}")
    if audit["errors"]:
        print(f"Audit found {len(audit['errors'])} errors")
        return 2
    print(f"Verified optima: {audit['verified_optima']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
