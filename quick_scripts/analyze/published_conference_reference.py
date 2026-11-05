"""Read the 120-second CSVs used in the accepted CSOnet camera-ready tables.

These files report costs and bounds, but contain no schedules. We check their
structure and bounds without claiming to independently verify old schedules.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import audit_journal_campaign as common
import summarize_conference as imported

SOURCE_COMMIT = "db0b16f20d97045501e63e4b432a879218a0c180"


def audit_directory(root: Path) -> tuple[list[dict], dict, list[dict]]:
    records, errors, hashes = [], [], {}
    for objective in common.OBJECTIVES:
        path = root / f"MaxSAT_Default_RC2_{objective}_120s.csv"
        try:
            raw = path.read_bytes()
            hashes[path.name] = hashlib.sha256(raw).hexdigest()
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read {path}: {exc}")
            continue
        names = [row.get("name") for row in rows]
        if len(names) != 72 or set(names) != set(common.EXPECTED_NAMES):
            errors.append(f"{path}: expected exactly the canonical 72 unique names")
        for row in rows:
            lower = imported.finite_number(row.get("lb"))
            upper = imported.finite_number(row.get("ub"))
            cost = imported.finite_number(row.get("cost"))
            seconds = imported.finite_number(row.get("total_time"))
            status = row.get("status")
            if status not in common.ALLOWED_STATUSES or status in common.FATAL_STATUSES:
                errors.append(f"{path}:{row.get('name')}: fatal/unknown status {status}")
            if row.get("delay_cost_type") != common.OBJECTIVE_LABELS[objective]:
                errors.append(f"{path}:{row.get('name')}: wrong objective")
            if seconds is None or seconds < 0:
                errors.append(f"{path}:{row.get('name')}: invalid total_time in seconds")
            proven = (status == "ok" and cost is not None and lower is not None and upper is not None
                      and common.same_number(cost, lower) and common.same_number(cost, upper))
            if status == "ok" and not proven:
                errors.append(f"{path}:{row.get('name')}: cost, LB and UB disagree")
            records.append({
                "objective": objective, "name": row.get("name"), "status": status,
                "verified": proven, "schedule_independently_verified": False,
                "cost": cost, "lb": lower, "ub": upper, "total_time": seconds,
                "errors": [],
            })
    summary = [imported.summarize_records([r for r in records if r["objective"] == obj], 120.0)
               for obj in common.OBJECTIVES if any(r["objective"] == obj for r in records)]
    return summary, {
        "source_data_commit": SOURCE_COMMIT, "source_directory": str(root),
        "reference_profile": "published-csv-120", "timeout_seconds": 120,
        "runtime_comparable": False, "verification_scope": "reported costs and bounds; no old schedules supplied",
        "file_sha256": hashes, "errors": errors,
        "verified_optima": {obj: sum(r["verified"] for r in records if r["objective"] == obj) for obj in common.OBJECTIVES},
        "warnings": ["The accepted manuscript specifies 120 seconds. CSV schedules are unavailable; only reported costs and bounds are checked."],
    }, records
