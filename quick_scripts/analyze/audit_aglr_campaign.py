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
import summarize_conference as conference_audit
import published_conference_reference as published_reference


OBJECTIVES = ("finsteps123", "infsteps180", "cont")
FATAL_STATUSES = journal_audit.FATAL_STATUSES
DEFAULT_CONFERENCE_COVERAGE = {"finsteps123": 72, "infsteps180": 68, "cont": 60}


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
            if solve.get("process_exit_code", 0) != 0:
                errors.append(f"nonzero process exit {solve['process_exit_code']}")
            if config.get("process_exit_required") == "true" and "process_exit_code" not in solve:
                errors.append("process exit evidence is missing")
            if "assumptions" in config and solve.get("maxsat_assumptions") != config["assumptions"]:
                errors.append("maxsat_assumptions differs from the locked configuration")
            if "sparse_costs" in config and str(solve.get("maxsat_sparse_costs")).lower() != config["sparse_costs"].lower():
                errors.append("maxsat_sparse_costs differs from the locked configuration")
            if config.get("process_exit_required") == "true" and config.get("policy") in {"adaptive", "all-scanned"}:
                for key in ("policy", "min_growth", "fraction", "max_wait", "rescue_progress", "heuristic_period", "heuristic_min_gap", "use_objective_bound", "filter_duplicates"):
                    if key not in config:
                        continue
                    actual = solve.get(f"aglr_{key}")
                    expected = config[key]
                    numeric = key in {"min_growth", "fraction", "max_wait", "heuristic_period", "heuristic_min_gap"}
                    matches = journal_audit.same_number(actual, expected) if numeric else str(actual).lower() == str(expected).lower()
                    if not matches:
                        errors.append(f"aglr_{key} differs from the locked configuration")
            if not journal_audit.same_number(solve.get("timeout_seconds"), timeout):
                errors.append(f"timeout_seconds does not match campaign cutoff {timeout}")
            if status == "ok":
                errors.extend(
                    journal_audit.independently_verify_solution(name, objective, solve)
                )
                if kind != "milp" and not bounds_prove_optimal(solve):
                    errors.append(
                        f"{kind} returned status=ok without matching lower/upper bounds"
                    )
                if not journal_audit.same_number(solve.get("cost"), solve.get("ub")):
                    errors.append("status=ok requires cost=ub")
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
        matches = sorted(cplex_dir.glob(f"results_bigm_{objective}_{timeout:g}s.csv"))
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
            if row.get("timeout_seconds") and not journal_audit.same_number(row["timeout_seconds"], timeout):
                errors.append("CPLEX timeout differs from campaign cutoff")
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
                "rescue_progress": config.get("rescue_progress", "bound-or-heuristic"),
                "heuristic_period": config.get("heuristic_period", "1"),
                "heuristic_min_gap": config.get("heuristic_min_gap", "0"),
                "use_objective_bound": config.get("use_objective_bound", "false"),
                "filter_duplicates": config.get("filter_duplicates", "false"),
                "assumptions": config.get("assumptions", "legacy"),
                "sparse_costs": config.get("sparse_costs", "false"),
                "conference_coverage": "",
                "coverage_delta": "",
                "conference_par2_seconds": "",
                "conference_par2": "",
                "par2_delta_seconds": "",
                "par2_delta": "",
                "paired_runtime_seconds": "",
                "paired_runtime": "",
                "paired_instances": 0,
            }
        )
    return rows


def add_conference_metrics(
    summary: list[dict], conference_summary: list[dict] | None,
    records: list[dict] = (), references: list[dict] = (),
    runtime_mode: str = "diagnostic", timeout: float = 150.0,
) -> None:
    if not conference_summary:
        return
    reference = {row["objective"]: row for row in conference_summary}
    for row in summary:
        ref = reference.get(row["objective"])
        if ref is None:
            continue
        selected = [r for r in records if r["tag"] == row["tag"] and r["objective"] == row["objective"]]
        names = {r["name"] for r in selected}
        subset = [r for r in references if r["objective"] == row["objective"] and r["name"] in names]
        coverage = sum(r["verified"] for r in subset) if subset else int(ref["verified_ok"])
        row["conference_coverage"] = coverage
        row["coverage_delta"] = int(row["proven_optimal"]) - coverage
        if runtime_mode != "assumed-equivalent":
            continue
        reference_par2 = (
            statistics.fmean(r["total_time"] if r["verified"] and r["total_time"] <= timeout else 2 * timeout for r in subset)
            if subset else float(ref["par2_seconds"])
        )
        row["conference_par2_seconds"] = reference_par2
        row["conference_par2"] = reference_par2
        row["par2_delta_seconds"] = float(row["par2_seconds"]) - float(
            reference_par2
        )
        row["par2_delta"] = row["par2_delta_seconds"]
        by_name = {r["name"]: r for r in subset if r["verified"]}
        pairs = [(r["time"], by_name[r["name"]]["total_time"]) for r in selected if r["proven"] and r["name"] in by_name]
        if pairs:
            row["paired_runtime_seconds"] = statistics.fmean(a - b for a, b in pairs)
            row["paired_instances"] = len(pairs)
            positive = [(a, b) for a, b in pairs if a > 0 and b > 0]
            if positive:
                row["paired_runtime"] = math.exp(statistics.fmean(math.log(b / a) for a, b in positive))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def ranking(
    summary: list[dict], coverage_targets: dict[str, int] | None = None
) -> list[dict]:
    targets = coverage_targets or DEFAULT_CONFERENCE_COVERAGE
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in summary:
        if row.get("policy") == "adaptive":
            grouped[row["tag"]].append(row)
    ranked = []
    for tag, rows in grouped.items():
        if {row["objective"] for row in rows} != set(OBJECTIVES):
            continue
        sample = rows[0]
        by_objective = {row["objective"]: row for row in rows}
        coverage = {
            objective: int(by_objective[objective]["proven_optimal"])
            for objective in OBJECTIVES
        }
        ranked.append(
            {
                "rank": 0,
                "tag": tag,
                "min_growth": sample["min_growth"],
                "fraction": sample["fraction"],
                "max_wait": sample["max_wait"],
                "rescue_progress": sample.get("rescue_progress", "bound-or-heuristic"),
                "heuristic_period": sample.get("heuristic_period", "1"),
                "heuristic_min_gap": sample.get("heuristic_min_gap", "0"),
                "use_objective_bound": sample.get("use_objective_bound", "false"),
                "filter_duplicates": sample.get("filter_duplicates", "false"),
                "proven_total": sum(int(row["proven_optimal"]) for row in rows),
                "finsteps123_proven": coverage["finsteps123"],
                "infsteps180_proven": coverage["infsteps180"],
                "cont_proven": coverage["cont"],
                "coverage_non_regression": all(
                    coverage[objective] >= int(by_objective[objective].get("conference_coverage") or targets[objective])
                    for objective in OBJECTIVES
                ),
                "par2_sum": sum(float(row["par2_seconds"]) for row in rows),
                "selected_growth_sum": sum(
                    float(row["mean_selected_growth"] or 0.0) for row in rows
                ),
            }
        )
    ranked.sort(
        key=lambda row: (
            not row["coverage_non_regression"],
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


def evaluate_gate(
    summary: list[dict], conference_summary: list[dict] | None = None
) -> dict:
    lookup = {(row["tag"], row["objective"]): row for row in summary}
    targets = dict(DEFAULT_CONFERENCE_COVERAGE)
    conference_par2 = {}
    if conference_summary:
        for row in conference_summary:
            targets[row["objective"]] = int(row["verified_ok"])
            conference_par2[row["objective"]] = float(row["par2_seconds"])
    reasons: list[str] = []
    coverage = {}
    for objective, target in targets.items():
        row = lookup.get(("AGLR", objective))
        if row is None or int(row["instances"]) != 72:
            reasons.append(f"AGLR/{objective}: incomplete 72-instance result")
        else:
            coverage[objective] = int(row["proven_optimal"])
            if coverage[objective] < target:
                reasons.append(
                    f"AGLR/{objective}: {row['proven_optimal']} proven, target {target}"
                )

    total_coverage = sum(coverage.values()) if len(coverage) == 3 else 0
    total_target = sum(targets.values())
    if len(coverage) == 3 and total_coverage <= total_target:
        reasons.append(
            f"AGLR total coverage {total_coverage} does not exceed conference "
            f"coverage {total_target}"
        )

    coverage_passed = not reasons
    required = ("MaxSAT-Journal", "CSOnet", "BigM-Gurobi", "BigM-CPLEX")
    comparisons = []
    complete_baselines = True
    candidate_par2 = sum(float(lookup[("AGLR", objective)]["par2_seconds"])
                         for objective in OBJECTIVES if ("AGLR", objective) in lookup)
    for tag in required:
        incomplete = [
            objective
            for objective in OBJECTIVES
            if (tag, objective) not in lookup
            or int(lookup[(tag, objective)]["instances"]) != 72
        ]
        if incomplete:
            complete_baselines = False
            reasons.append(
                f"{tag}: missing or incomplete objectives: {', '.join(incomplete)}"
            )
        elif len(coverage) == 3:
            baseline_coverage = {o: int(lookup[(tag, o)]["proven_optimal"]) for o in OBJECTIVES}
            baseline_total = sum(baseline_coverage.values())
            baseline_par2 = sum(float(lookup[(tag, o)]["par2_seconds"]) for o in OBJECTIVES)
            better = total_coverage > baseline_total or (
                total_coverage == baseline_total and candidate_par2 < baseline_par2
            )
            comparisons.append(dict(tag=tag, coverage=baseline_coverage, total=baseline_total,
                                    par2_sum=baseline_par2, candidate_better=better))
            if not better:
                reasons.append(f"AGLR does not beat {tag}: total coverage "
                               f"{total_coverage} versus {baseline_total}; "
                               f"PAR-2 sum {candidate_par2:.6f} versus {baseline_par2:.6f}")
    baseline_comparison_passed = (coverage_passed and complete_baselines
                                  and len(comparisons) == len(required)
                                  and all(r["candidate_better"] for r in comparisons))
    par2 = {
        objective: lookup[("AGLR", objective)]["par2_seconds"]
        for objective in OBJECTIVES
        if ("AGLR", objective) in lookup
    }
    return {
        "passed": not reasons,
        "coverage_passed": coverage_passed,
        "baseline_comparison_passed": baseline_comparison_passed,
        "baseline_comparisons": comparisons,
        "reasons": reasons,
        "targets": targets,
        "coverage": coverage,
        "total_coverage": total_coverage,
        "total_target": total_target,
        "conference_par2_seconds": conference_par2,
        "aglr_par2_seconds": par2,
    }


def confirmation_instances(records: list[dict], conference_comparisons: list[dict] = ()) -> list[str]:
    by_method = {(r["tag"], r["objective"], r["name"]): r for r in records}
    names = set()
    for comparison in conference_comparisons:
        if comparison["tag"] == "AGLR" and comparison["reference_verified"] != comparison["campaign_proven"]:
            names.add(comparison["name"])
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


def compare_conference_reference(
    records: list[dict], reference_dir: Path, runtime_mode: str = "diagnostic", profile: str = "auto"
) -> tuple[list[dict], list[dict], dict]:
    """Compare exact results with conference costs and, optionally, runtimes."""
    use_published = profile == "published-csv-120" or (profile == "auto" and (reference_dir / "MaxSAT_Default_RC2_cont_120s.csv").is_file())
    if use_published:
        reference_summary, reference_audit, reference_records = published_reference.audit_directory(reference_dir)
    else:
        reference_summary, reference_audit, reference_records = conference_audit.audit_directory(reference_dir)
    errors = [
        {
            "tag": "Conference-reference",
            "objective": "<all>",
            "name": "<reference>",
            "status": "invalid-reference",
            "errors": [message],
        }
        for message in reference_audit["errors"]
    ]
    reference_by_key = {
        (record["objective"], record["name"]): record
        for record in reference_records
    }
    comparisons: list[dict] = []
    for record in records:
        if record.get("config", {}).get("kind", "exact") != "exact":
            continue
        reference = reference_by_key.get((record["objective"], record["name"]))
        if reference is None:
            outcome = "missing-reference"
            reference_status = "missing"
            reference_verified = False
            reference_cost = ""
        else:
            reference_status = reference["status"]
            reference_verified = reference["verified"]
            reference_cost = reference["cost"] if reference_verified else ""
            if reference_verified and record["proven"]:
                if journal_audit.same_number(
                    record["solve"].get("cost"), reference["cost"]
                ):
                    outcome = "match"
                else:
                    outcome = "cost-mismatch"
                    errors.append(
                        {
                            "tag": record["tag"],
                            "objective": record["objective"],
                            "name": record["name"],
                            "status": "cost-mismatch",
                            "errors": [
                                "proven cost "
                                f"{record['solve'].get('cost')} differs from verified "
                                f"conference cost {reference['cost']}"
                            ],
                        }
                    )
            elif reference_verified:
                outcome = "campaign-not-proven"
            else:
                outcome = "reference-not-proven"
        comparisons.append(
            {
                "tag": record["tag"],
                "objective": record["objective"],
                "name": record["name"],
                "reference_status": reference_status,
                "reference_verified": reference_verified,
                "reference_cost": reference_cost,
                "campaign_status": record["status"],
                "campaign_proven": record["proven"],
                "campaign_cost": record["solve"].get("cost", ""),
                "conference_total_time": (
                    reference.get("total_time", "") if reference else ""
                ),
                "runtime_mode": runtime_mode,
                "comparison": outcome,
            }
        )
    metadata = {
        "source_data_commit": reference_audit["source_data_commit"],
        "source_directory": reference_audit["source_directory"],
        "runtime_comparable": runtime_mode == "assumed-equivalent",
        "runtime_comparability_assumed": runtime_mode == "assumed-equivalent",
        "runtime_provenance_verified": reference_audit["runtime_comparable"],
        "runtime_used_for_gate_or_ranking": runtime_mode == "assumed-equivalent",
        "runtime_mode": runtime_mode,
        "profile": "published-csv-120" if use_published else "imported-json-150",
        "verification_scope": reference_audit.get("verification_scope", "independent schedules, costs and bounds"),
        "summary": reference_summary,
        "records": reference_records,
        "verified_optima": reference_audit["verified_optima"],
        "warnings": reference_audit["warnings"],
    }
    return comparisons, errors, metadata


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
    names_file = reference_full / "confirm_instances.txt"
    selected_names = set(names_file.read_text().split()) if names_file.is_file() else {name for _, name in repeats}
    for key, reference_record in expected.items():
        if key[1] not in selected_names:
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
    parser.add_argument("--conference-reference", type=Path)
    parser.add_argument("--conference-profile", choices=("auto", "published-csv-120", "imported-json-150"), default="auto")
    parser.add_argument(
        "--conference-runtime-mode",
        choices=("diagnostic", "assumed-equivalent"),
        default="diagnostic",
    )
    args = parser.parse_args()
    campaign_dir = args.campaign_dir.resolve()

    records: list[dict] = []
    for config_path in sorted(campaign_dir.glob("*/config.txt")):
        config = read_config(config_path)
        if "tag" in config:
            records.extend(load_json_method(config_path.parent, config, args.timeout))
    records.extend(load_cplex(campaign_dir, args.timeout))

    summary = summarize(records, args.timeout)
    conference_metadata = None
    conference_summary = None
    comparison_errors: list[dict] = []
    comparisons: list[dict] = []
    if args.conference_reference is not None:
        comparisons, comparison_errors, conference_metadata = compare_conference_reference(
            records, args.conference_reference, args.conference_runtime_mode, args.conference_profile
        )
        conference_summary = conference_metadata.get("summary", [])
        add_conference_metrics(summary, conference_summary, records,
                               conference_metadata.pop("records"),
                               args.conference_runtime_mode, args.timeout)
    ranked = ranking(
        summary,
        {
            row["objective"]: int(row["verified_ok"])
            for row in conference_summary or []
        }
        or None,
    )
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
    errors.extend(comparison_errors)
    if args.conference_reference is not None:
        write_csv(campaign_dir / "conference_reference_comparison.csv", comparisons)
    gate = (
        evaluate_gate(summary, conference_summary)
        if any(row["tag"] == "AGLR" for row in summary)
        else None
    )
    if gate is not None and errors:
        gate["passed"] = False
        gate["coverage_passed"] = False
        gate["baseline_comparison_passed"] = False
        gate["reasons"].insert(0, f"Independent audit found {len(errors)} invalid/fatal records")

    write_csv(campaign_dir / "aglr_summary.csv", summary)
    write_csv(campaign_dir / "aglr_ranking.csv", ranked)
    (campaign_dir / "aglr_audit.json").write_text(
        json.dumps(
            {
                "errors": errors,
                "gate": gate,
                "conference_reference": conference_metadata,
            },
            indent=2,
        )
        + "\n"
    )
    confirm = confirmation_instances(records, comparisons)
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
