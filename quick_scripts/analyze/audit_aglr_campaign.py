#!/usr/bin/env python3
"""Audit AGLR tuning and full campaigns with a coverage-first ranking."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import audit_journal_campaign as journal_audit


OBJECTIVES = ("finsteps123", "infsteps180", "cont")
FATAL_STATUSES = journal_audit.FATAL_STATUSES


def read_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def bounds_prove_optimal(solve: dict) -> bool:
    lb = finite_number(solve.get("lb"))
    ub = finite_number(solve.get("ub"))
    if lb is None or ub is None:
        return False
    tolerance = 1e-6 * max(1.0, abs(lb), abs(ub))
    return abs(ub - lb) <= tolerance


def recorded_validation_passed(solve: dict) -> bool:
    """Accept explicit validation evidence, never infer validity from status."""
    value = solve.get("valid", solve.get("validation_status"))
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "ok", "valid", "passed"}


def canonical_name(name: str) -> str:
    """Normalize names emitted by the separate CPLEX runner."""
    aliases = (("addtrack", "track"), ("addstation", "station"), ("original", "orig"))
    for old, new in aliases:
        if name.startswith(old):
            return new + name[len(old) :]
    return name


def expected_names(config: dict[str, str]) -> list[str]:
    raw = config.get("instances", "").strip()
    if not raw:
        return journal_audit.EXPECTED_NAMES
    requested = [canonical_name(name) for name in raw.split(",") if name]
    requested_set = set(requested)
    return [name for name in journal_audit.EXPECTED_NAMES if name in requested_set]


def missing_record(tag: str, objective: str, name: str, timeout: float, message: str) -> dict:
    return {
        "tag": tag,
        "objective": objective,
        "name": name,
        "status": "missing",
        "proven": False,
        "time": timeout,
        "errors": [message],
        "solve": {},
    }


def elapsed_seconds(solve: dict, timeout: float) -> float:
    total = finite_number(solve.get("total_time"))
    if total is not None and total >= 0:
        return min(total, timeout)
    milliseconds = finite_number(solve.get("sol_time"))
    if milliseconds is not None and milliseconds >= 0:
        return min(milliseconds / 1000.0, timeout)
    return timeout


def load_json_method(config_dir: Path, config: dict[str, str], timeout: float) -> list[dict]:
    records: list[dict] = []
    tag = config["tag"]
    kind = config.get("kind", "exact")
    wanted = expected_names(config)
    for objective in OBJECTIVES:
        path = config_dir / f"{objective}.json"
        if not path.is_file():
            records.extend(
                missing_record(tag, objective, name, timeout, f"missing {path}")
                for name in wanted
            )
            continue
        try:
            rows = journal_audit.load_rows(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            records.extend(
                missing_record(tag, objective, name, timeout, f"cannot read {path}: {exc}")
                for name in wanted
            )
            continue
        names = [canonical_name(name) for name, _ in rows]
        counts = Counter(names)
        for name in wanted:
            if counts[name] == 0:
                records.append(
                    missing_record(tag, objective, name, timeout, f"{path}: missing {name}")
                )
        for (raw_name, solve), name in zip(rows, names):
            status = solve.get("status")
            errors: list[str] = []
            if name not in wanted:
                errors.append(f"unexpected instance name {raw_name!r}")
            if counts[name] > 1:
                errors.append(f"duplicate instance name {name!r}")
            if status not in journal_audit.ALLOWED_STATUSES:
                errors.append(f"unsupported status {status!r}")
            if status == "ok":
                errors.extend(
                    journal_audit.independently_verify_solution(name, objective, solve)
                )
                if kind != "milp" and not bounds_prove_optimal(solve):
                    errors.append(
                        f"{kind} returned status=ok without matching lower/upper bounds"
                    )
            proven = (
                status == "ok"
                and not errors
                and (kind != "milp" or bounds_prove_optimal(solve))
            )
            records.append(
                {
                    "tag": tag,
                    "objective": objective,
                    "name": name,
                    "status": status,
                    "proven": proven,
                    "time": elapsed_seconds(solve, timeout),
                    "errors": errors,
                    "solve": solve,
                    "config": config,
                }
            )
    return records


def load_cplex(campaign_dir: Path, timeout: float) -> list[dict]:
    records: list[dict] = []
    cplex_dir = campaign_dir / "CPLEX"
    for objective in OBJECTIVES:
        matches = sorted(cplex_dir.glob(f"results_bigm_{objective}_*s.csv"))
        if not matches:
            continue
        path = matches[-1]
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        names = [canonical_name(row.get("name", "<missing-name>")) for row in rows]
        counts = Counter(names)
        for name in journal_audit.EXPECTED_NAMES:
            if counts[name] == 0:
                records.append(
                    missing_record(
                        "BigM-CPLEX", objective, name, timeout, f"{path}: missing {name}"
                    )
                )
        for row, name in zip(rows, names):
            status = row.get("status")
            solve = dict(row)
            solve["lb"] = finite_number(row.get("lb"))
            solve["ub"] = finite_number(row.get("ub"))
            errors = []
            if name not in journal_audit.EXPECTED_NAMES:
                errors.append(f"unexpected CPLEX instance name {row.get('name')!r}")
            if counts[name] > 1:
                errors.append(f"duplicate CPLEX instance name {name!r}")
            if status not in journal_audit.ALLOWED_STATUSES:
                errors.append(f"unsupported CPLEX status {status!r}")
            if status == "ok" and not recorded_validation_passed(solve):
                errors.append(
                    "CPLEX status=ok lacks explicit valid=true evidence from the "
                    "schedule validator"
                )
            records.append(
                {
                    "tag": "BigM-CPLEX",
                    "objective": objective,
                    "name": name,
                    "status": status,
                    "proven": (
                        status == "ok"
                        and not errors
                        and recorded_validation_passed(solve)
                        and bounds_prove_optimal(solve)
                    ),
                    "time": elapsed_seconds(solve, timeout),
                    "errors": errors,
                    "solve": solve,
                    "config": {"tag": "BigM-CPLEX", "kind": "milp"},
                }
            )
    return records


def summarize(records: list[dict], timeout: float) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        groups[(record["tag"], record["objective"])].append(record)

    rows = []
    for (tag, objective), items in sorted(groups.items()):
        proven_times = [item["time"] for item in items if item["proven"]]
        par2 = sum(item["time"] if item["proven"] else 2 * timeout for item in items) / len(items)
        telemetry = [item["solve"] for item in items if item["proven"]]
        selected_growth = [
            value
            for solve in telemetry
            if (value := finite_number(solve.get("aglr_selected_growth"))) is not None
        ]
        config = next((item.get("config", {}) for item in items if item.get("config")), {})
        rows.append(
            {
                "tag": tag,
                "objective": objective,
                "instances": len(items),
                "proven_optimal": len(proven_times),
                "not_proven": len(items) - len(proven_times),
                "median_solved_seconds": statistics.median(proven_times) if proven_times else "",
                "par2_seconds": par2,
                "mean_selected_growth": statistics.fmean(selected_growth)
                if selected_growth
                else "",
                "policy": config.get("policy", ""),
                "min_growth": config.get("min_growth", ""),
                "fraction": config.get("fraction", ""),
                "max_wait": config.get("max_wait", ""),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def ranking(summary: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in summary:
        if row.get("policy") == "adaptive":
            grouped[row["tag"]].append(row)
    ranked = []
    for tag, rows in grouped.items():
        if {row["objective"] for row in rows} != set(OBJECTIVES):
            continue
        sample = rows[0]
        ranked.append(
            {
                "rank": 0,
                "tag": tag,
                "min_growth": sample["min_growth"],
                "fraction": sample["fraction"],
                "max_wait": sample["max_wait"],
                "proven_total": sum(int(row["proven_optimal"]) for row in rows),
                "par2_sum": sum(float(row["par2_seconds"]) for row in rows),
                "selected_growth_sum": sum(
                    float(row["mean_selected_growth"] or 0.0) for row in rows
                ),
            }
        )
    ranked.sort(
        key=lambda row: (
            -row["proven_total"],
            row["par2_sum"],
            row["selected_growth_sum"],
            -float(row["fraction"]),
            row["tag"],
        )
    )
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return ranked


def evaluate_gate(summary: list[dict]) -> dict:
    lookup = {(row["tag"], row["objective"]): row for row in summary}
    targets = {"finsteps123": 72, "infsteps180": 69, "cont": 68}
    reasons: list[str] = []
    for objective, target in targets.items():
        row = lookup.get(("AGLR", objective))
        if row is None or int(row["instances"]) != 72:
            reasons.append(f"AGLR/{objective}: incomplete 72-instance result")
        elif int(row["proven_optimal"]) < target:
            reasons.append(
                f"AGLR/{objective}: {row['proven_optimal']} proven, target {target}"
            )

    fin = lookup.get(("AGLR", "finsteps123"))
    baseline_fin = [
        row
        for (tag, objective), row in lookup.items()
        if tag != "AGLR" and objective == "finsteps123" and int(row["instances"]) == 72
    ]
    if fin and baseline_fin and int(fin["proven_optimal"]) == 72:
        best_baseline_par2 = min(float(row["par2_seconds"]) for row in baseline_fin)
        if float(fin["par2_seconds"]) >= best_baseline_par2:
            reasons.append(
                "AGLR/finsteps123: PAR-2 does not beat the best complete baseline "
                f"({fin['par2_seconds']:.6f} >= {best_baseline_par2:.6f})"
            )
    else:
        reasons.append("Cannot compare finsteps123 PAR-2 against all complete baselines")

    required = ("MaxSAT-Journal", "CSOnet", "BigM-Gurobi", "BigM-CPLEX")
    for tag in required:
        incomplete = [
            objective
            for objective in OBJECTIVES
            if (tag, objective) not in lookup
            or int(lookup[(tag, objective)]["instances"]) != 72
        ]
        if incomplete:
            reasons.append(
                f"{tag}: missing or incomplete objectives: {', '.join(incomplete)}"
            )
    return {"passed": not reasons, "reasons": reasons, "targets": targets}


def confirmation_instances(records: list[dict]) -> list[str]:
    by_method = {(r["tag"], r["objective"], r["name"]): r for r in records}
    names = set()
    for objective in OBJECTIVES:
        objective_names = {
            name for tag, obj, name in by_method if tag == "AGLR" and obj == objective
        }
        for name in objective_names:
            aglr = by_method[("AGLR", objective, name)]
            baselines = [
                record
                for (tag, obj, candidate_name), record in by_method.items()
                if tag != "AGLR" and obj == objective and candidate_name == name
            ]
            if aglr["time"] > 30 or any(
                aglr["proven"] != baseline["proven"] for baseline in baselines
            ):
                names.add(name)
    canonical = journal_audit.EXPECTED_NAMES
    return [name for name in canonical if name in names]


def audit_confirmations(records: list[dict], reference_full: Path, timeout: float) -> list[dict]:
    """Require every repeated run to reproduce each proven AGLR optimum."""
    config_path = reference_full / "AGLR" / "config.txt"
    if not config_path.is_file():
        return [
            {
                "tag": "confirmation",
                "objective": "<all>",
                "name": "<reference>",
                "status": "missing",
                "errors": [f"missing full-campaign reference {config_path}"],
            }
        ]
    reference = load_json_method(config_path.parent, read_config(config_path), timeout)
    expected = {
        (record["objective"], record["name"]): record
        for record in reference
        if record["proven"]
    }
    repeats: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        if record["tag"].startswith("AGLR-confirm-"):
            repeats[(record["objective"], record["name"])].append(record)

    errors = []
    for key, reference_record in expected.items():
        if key not in repeats:
            continue
        objective, name = key
        items = repeats[key]
        if len(items) != 3:
            errors.append(
                {
                    "tag": "confirmation",
                    "objective": objective,
                    "name": name,
                    "status": "incomplete",
                    "errors": [f"expected 3 repeats, found {len(items)}"],
                }
            )
            continue
        reference_cost = reference_record["solve"].get("cost")
        bad = [
            item
            for item in items
            if not item["proven"]
            or not journal_audit.same_number(item["solve"].get("cost"), reference_cost)
        ]
        if bad:
            errors.append(
                {
                    "tag": "confirmation",
                    "objective": objective,
                    "name": name,
                    "status": "not-reproduced",
                    "errors": [
                        f"{len(bad)}/3 repeats did not reproduce proven cost {reference_cost}"
                    ],
                }
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_dir", type=Path)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--reference-full", type=Path)
    args = parser.parse_args()
    campaign_dir = args.campaign_dir.resolve()

    records: list[dict] = []
    for config_path in sorted(campaign_dir.glob("*/config.txt")):
        config = read_config(config_path)
        if "tag" in config:
            records.extend(load_json_method(config_path.parent, config, args.timeout))
    records.extend(load_cplex(campaign_dir, args.timeout))

    summary = summarize(records, args.timeout)
    ranked = ranking(summary)
    errors = [
        {
            "tag": record["tag"],
            "objective": record["objective"],
            "name": record["name"],
            "status": record["status"],
            "errors": record["errors"],
        }
        for record in records
        if record["errors"] or record["status"] in FATAL_STATUSES
    ]
    if args.reference_full is not None:
        errors.extend(
            audit_confirmations(records, args.reference_full.resolve(), args.timeout)
        )
    gate = evaluate_gate(summary) if any(row["tag"] == "AGLR" for row in summary) else None
    if gate is not None and errors:
        gate["passed"] = False
        gate["reasons"].insert(0, f"Independent audit found {len(errors)} invalid/fatal records")

    write_csv(campaign_dir / "aglr_summary.csv", summary)
    write_csv(campaign_dir / "aglr_ranking.csv", ranked)
    (campaign_dir / "aglr_audit.json").write_text(
        json.dumps({"errors": errors, "gate": gate}, indent=2)
    )
    confirm = confirmation_instances(records)
    (campaign_dir / "confirm_instances.txt").write_text("\n".join(confirm) + ("\n" if confirm else ""))

    print(f"Wrote {campaign_dir / 'aglr_summary.csv'}")
    if ranked:
        print(
            "Best AGLR: "
            f"{ranked[0]['tag']} (proven={ranked[0]['proven_total']}, "
            f"PAR2 sum={ranked[0]['par2_sum']:.3f})"
        )
    if errors:
        print(f"Audit found {len(errors)} invalid/fatal records")
        return 2
    if gate is not None:
        print("Submission gate: " + ("PASS" if gate["passed"] else "NOT YET"))
        for reason in gate["reasons"]:
            print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
