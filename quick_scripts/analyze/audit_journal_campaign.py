#!/usr/bin/env python3
"""Validate and summarize the one-run journal experiment campaign.

This script uses only the Python standard library.  It has two modes:

1. Validate one aggregated JSON file immediately after it is produced.
2. Audit a complete campaign directory and write submission-oriented summaries.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path


OBJECTIVES = ("finsteps123", "infsteps180", "cont")
OBJECTIVE_LABELS = {
    "finsteps123": "FiniteSteps123",
    "infsteps180": "InfiniteSteps180",
    "cont": "Continuous",
}
CONFIGS = ("RC2-Base", "RC2+B", "RC2+R", "RC2+B+R")
EXPECTED_NAMES = [
    f"{prefix}{line}{number}"
    for prefix in ("orig", "track", "station")
    for line in ("A", "B")
    for number in range(1, 13)
]
ALLOWED_STATUSES = {
    "ok",
    "timeout",
    "no_solution",
    "oom",
    "gurobi_error",
    "invalid_solution",
    "external_timeout",
    "killed",
    "aborted",
    "segfault",
    "panic",
    "failed",
}
FATAL_STATUSES = {
    "no_solution",
    "gurobi_error",
    "invalid_solution",
    "aborted",
    "segfault",
    "panic",
    "failed",
}
TELEMETRY_FIELDS = (
    "iterations",
    "num_time_points",
    "num_vars_total",
    "num_clauses_total",
    "refinement_detected_total",
    "refinement_selected_total",
    "refinement_new_points_total",
    "forced_orders_total",
    "refinement_scan_time_seconds",
    "refinement_selection_time_seconds",
    "refinement_apply_time_seconds",
    "cost_encoding_time_seconds",
    "validation_time_seconds",
    "solver_time",
    "total_time",
    "lb",
    "ub",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def instance_path(name: str) -> Path:
    prefixes = {
        "orig": "original",
        "track": "addtracktime",
        "station": "addstationtime",
    }
    for prefix, directory in prefixes.items():
        if name.startswith(prefix):
            return REPOSITORY_ROOT / "instances" / directory / f"Instance{name[len(prefix):]}.txt"
    raise ValueError(f"unknown instance name {name!r}")


def parse_key_value(field: str) -> tuple[str, int]:
    key, separator, value = field.partition("=")
    if not separator:
        raise ValueError(f"malformed field {field!r}")
    return key, int(value)


@lru_cache(maxsize=None)
def parse_txt_instance(name: str) -> list[list[dict]]:
    """Rebuild the relevant Problem fields without using the Rust parser."""
    path = instance_path(name)
    text = path.read_text()
    blocks = [block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]
    trains: list[list[dict]] = []
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError(f"{path}: train block has no visits")
        visits: list[dict] = []
        next_earliest = None
        visit_lines = lines[1:]
        for row_index, line in enumerate(visit_lines):
            fields = line.split()
            if len(fields) < 6:
                raise ValueError(f"{path}: malformed visit line {line!r}")
            track = fields[0]
            values = dict(parse_key_value(field) for field in fields[2:])
            aimed = values["AimedDepartureTime"]
            wait = values["WaitTime"]
            base = values["BaseTime"]
            run = values["RunTime"]
            earliest_in = base - wait if next_earliest is None else next_earliest
            is_last_track = row_index + 1 == len(visit_lines)
            visits.append(
                {
                    "earliest": earliest_in,
                    "travel": wait,
                    "aimed": None,
                    "resource": None,
                }
            )
            visits.append(
                {
                    "earliest": base,
                    "travel": run,
                    "aimed": aimed if is_last_track else None,
                    "resource": track,
                }
            )
            next_earliest = base + run
        previous = visits[-1]
        visits.append(
            {
                "earliest": previous["earliest"] + previous["travel"],
                "travel": 0,
                "aimed": None,
                "resource": None,
            }
        )
        trains.append(visits)
    return trains


def delay_cost(objective: str, delay: int) -> int:
    delay = max(0, delay)
    if objective == "cont":
        return delay
    if objective == "infsteps180":
        return (delay + 179) // 180
    if objective == "finsteps123":
        if delay > 360:
            return 3
        if delay > 180:
            return 2
        if delay > 0:
            return 1
        return 0
    raise ValueError(f"unsupported objective {objective!r}")


def independently_verify_solution(name: str, objective: str, solve: dict) -> list[str]:
    errors: list[str] = []
    try:
        trains = parse_txt_instance(name)
    except (OSError, ValueError, KeyError) as exc:
        return [f"cannot parse source instance independently: {exc}"]
    solution = solve.get("solution")
    if not isinstance(solution, list) or len(solution) != len(trains):
        return ["missing solution or wrong number of trains"]

    occupations: list[tuple[str, int, int, int, int]] = []
    computed_cost = 0
    for train_index, (visits, times) in enumerate(zip(trains, solution)):
        if not isinstance(times, list) or len(times) != len(visits) + 1:
            errors.append(f"train {train_index}: wrong number of event times")
            continue
        if any(not isinstance(value, int) or isinstance(value, bool) for value in times):
            errors.append(f"train {train_index}: event times must be integers")
            continue
        for visit_index, visit in enumerate(visits):
            entry, exit_time = times[visit_index], times[visit_index + 1]
            if entry < visit["earliest"]:
                errors.append(
                    f"train {train_index} visit {visit_index}: entry before earliest"
                )
            if entry + visit["travel"] > exit_time:
                errors.append(
                    f"train {train_index} visit {visit_index}: insufficient travel time"
                )
            if visit["aimed"] is not None:
                computed_cost += delay_cost(objective, entry - visit["aimed"])
            if visit["resource"] is not None:
                occupations.append(
                    (visit["resource"], entry, exit_time, train_index, visit_index)
                )

    by_resource: dict[str, list[tuple[str, int, int, int, int]]] = {}
    for occupation in occupations:
        by_resource.setdefault(occupation[0], []).append(occupation)
    for resource, intervals in by_resource.items():
        intervals.sort(key=lambda item: (item[1], item[2], item[3], item[4]))
        latest = intervals[0]
        for current in intervals[1:]:
            if current[1] < latest[2]:
                errors.append(
                    f"resource {resource} overlaps at "
                    f"train/visit {latest[3:]!r} and {current[3:]!r}"
                )
            if current[2] > latest[2]:
                latest = current

    if not same_number(computed_cost, solve.get("cost")):
        errors.append(
            f"independent cost={computed_cost}, recorded cost={solve.get('cost')!r}"
        )
    return errors


def expected_settings(config: str, budget: int, max_wait: int) -> dict:
    if config not in CONFIGS:
        raise ValueError(f"unknown config: {config}")
    uses_bounds = config in {"RC2+B", "RC2+B+R"}
    uses_budget = config in {"RC2+R", "RC2+B+R"}
    return {
        "maxsat_rc2_bound_mode": "chain-cost-forced" if uses_bounds else "off",
        "maxsat_rc2_refinement_budget": str(budget) if uses_budget else "all",
        "maxsat_rc2_max_wait_iterations": max_wait,
        "maxsat_rc2_full_scan": True,
        "maxsat_rc2_validate_before_return": True,
    }


def load_rows(path: Path) -> list[tuple[str, dict]]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("top-level JSON value must be a list")
    rows: list[tuple[str, dict]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("each problem entry must be an object")
        name = item.get("name")
        solves = item.get("solves")
        if not isinstance(name, str):
            raise ValueError("problem name must be a string")
        if not isinstance(solves, list) or len(solves) != 1 or not isinstance(solves[0], dict):
            raise ValueError(f"{name}: expected exactly one solve object")
        rows.append((name, solves[0]))
    return rows


def same_number(left, right, tolerance: float = 1e-9) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def nonnegative_finite_number(value) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number >= 0
    except (TypeError, ValueError):
        return False


def validate_file(
    path: Path,
    config: str,
    objective: str,
    timeout: float,
    budget: int,
    max_wait: int,
    expected_names: list[str] | None = None,
) -> tuple[list[tuple[str, dict]], list[str]]:
    errors: list[str] = []
    try:
        rows = load_rows(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"{path}: cannot read result JSON: {exc}"]

    wanted_names = EXPECTED_NAMES if expected_names is None else expected_names
    names = [name for name, _ in rows]
    if names != wanted_names:
        counts = Counter(names)
        missing = sorted(set(wanted_names) - set(names))
        unexpected = sorted(set(names) - set(wanted_names))
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        errors.append(
            f"{path}: unexpected instance list or order; "
            f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}"
        )

    expected = expected_settings(config, budget, max_wait)
    for name, solve in rows:
        status = solve.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{path}:{name}: unsupported status {status!r}")
            continue
        if status in FATAL_STATUSES:
            errors.append(f"{path}:{name}: fatal run status {status!r}")

        if "external_status" in solve:
            if solve.get("external_status") != status:
                errors.append(f"{path}:{name}: external_status does not match status")
            continue

        if solve.get("solver_name") != "MaxsatRc2":
            errors.append(
                f"{path}:{name}: solver_name={solve.get('solver_name')!r}, expected 'MaxsatRc2'"
            )
        if solve.get("delay_cost_type") != OBJECTIVE_LABELS[objective]:
            errors.append(
                f"{path}:{name}: delay_cost_type={solve.get('delay_cost_type')!r}, "
                f"expected {OBJECTIVE_LABELS[objective]!r}"
            )
        for field, wanted in expected.items():
            if solve.get(field) != wanted:
                errors.append(
                    f"{path}:{name}: {field}={solve.get(field)!r}, expected {wanted!r}"
                )
        if not same_number(solve.get("timeout_seconds"), timeout):
            errors.append(
                f"{path}:{name}: timeout_seconds={solve.get('timeout_seconds')!r}, "
                f"expected {timeout}"
            )

        if status in {"ok", "timeout"}:
            for field in TELEMETRY_FIELDS:
                if field not in solve:
                    errors.append(f"{path}:{name}: missing telemetry field {field}")
            for field in TELEMETRY_FIELDS:
                if field in solve and not nonnegative_finite_number(solve[field]):
                    errors.append(
                        f"{path}:{name}: telemetry field {field} must be finite and nonnegative"
                    )
            if solve.get("value_trace_version") != 1:
                errors.append(f"{path}:{name}: value_trace_version must be 1")
            if not isinstance(solve.get("value_trace"), list) or not solve["value_trace"]:
                errors.append(f"{path}:{name}: missing value_trace")

        if status == "ok":
            cost, lower, upper = solve.get("cost"), solve.get("lb"), solve.get("ub")
            if cost is None or lower is None or upper is None:
                errors.append(f"{path}:{name}: ok result lacks cost/lb/ub")
            elif not (same_number(cost, lower) and same_number(cost, upper)):
                errors.append(
                    f"{path}:{name}: ok result has cost/lb/ub={cost!r}/{lower!r}/{upper!r}"
                )
            trace = solve.get("value_trace")
            if not isinstance(trace, list) or not trace:
                pass
            else:
                elapsed = []
                for event_index, event in enumerate(trace):
                    if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                        errors.append(
                            f"{path}:{name}: malformed value_trace event {event_index}"
                        )
                        continue
                    try:
                        event_time = float(event["elapsed_ms"])
                        if not math.isfinite(event_time):
                            raise ValueError("non-finite elapsed_ms")
                        elapsed.append(event_time)
                    except (KeyError, TypeError, ValueError):
                        errors.append(
                            f"{path}:{name}: value_trace event {event_index} lacks elapsed_ms"
                        )
                if elapsed and (elapsed != sorted(elapsed) or min(elapsed) < 0):
                    errors.append(f"{path}:{name}: value_trace times are not monotone")
                final_event = trace[-1] if isinstance(trace[-1], dict) else {}
                if final_event.get("event") != "optimal" or not same_number(
                    final_event.get("value"), cost
                ):
                    errors.append(
                        f"{path}:{name}: value_trace does not end at the proven optimum"
                    )
            for field in (
                "time_to_first_solution_ms",
                "time_to_best_value_ms",
                "time_to_prove_best_value_ms",
                "time_to_optimality_ms",
            ):
                if field not in solve:
                    errors.append(f"{path}:{name}: missing {field}")
            for error in independently_verify_solution(name, objective, solve):
                errors.append(f"{path}:{name}: independent verification: {error}")

    return rows, errors


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def elapsed_seconds(solve: dict) -> float | None:
    value = solve.get("sol_time")
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def audit_campaign(campaign_dir: Path) -> int:
    campaign_file = campaign_dir / "campaign.txt"
    if not campaign_file.is_file():
        print(f"ERROR: missing {campaign_file}", file=sys.stderr)
        return 2
    campaign = read_key_values(campaign_file)
    try:
        timeout = float(campaign["timeout_seconds"])
        budget = int(campaign["refinement_budget"])
    except (KeyError, ValueError) as exc:
        print(f"ERROR: invalid campaign metadata: {exc}", file=sys.stderr)
        return 2

    campaign_checks = {
        "repetitions": "1",
        "instances_per_objective": "72",
        "objectives": ",".join(OBJECTIVES),
    }

    all_data: dict[tuple[str, str], dict[str, dict]] = {}
    errors: list[str] = []
    for field, expected in campaign_checks.items():
        if campaign.get(field) != expected:
            errors.append(
                f"{campaign_file}: {field}={campaign.get(field)!r}, expected {expected!r}"
            )
    campaign_configs = tuple(
        value for value in campaign.get("configs", "").split(",") if value
    )
    if (
        not campaign_configs
        or len(set(campaign_configs)) != len(campaign_configs)
        or any(config not in CONFIGS for config in campaign_configs)
    ):
        errors.append(
            f"{campaign_file}: configs must be a non-empty, unique subset of {CONFIGS}"
        )
    hashes: dict[str, str] = {}
    manifest_hashes: dict[str, str] = {}
    manifest_values: list[tuple[Path, dict[str, str]]] = []
    summary_rows: list[dict] = []

    for config in campaign_configs:
        config_dir = campaign_dir / config
        config_file = config_dir / "config.txt"
        if not config_file.is_file():
            errors.append(f"missing {config_file}")
            continue
        config_meta = read_key_values(config_file)
        try:
            max_wait = int(config_meta["max_wait_iterations"])
        except (KeyError, ValueError):
            errors.append(f"{config_file}: missing or invalid max_wait_iterations")
            continue

        wanted = expected_settings(config, budget, max_wait)
        config_checks = {
            "config": config,
            "bound_mode": wanted["maxsat_rc2_bound_mode"],
            "refinement_budget": wanted["maxsat_rc2_refinement_budget"],
            "timeout_seconds": str(int(timeout)) if timeout.is_integer() else str(timeout),
            "external_timeout_grace_seconds": campaign.get(
                "external_timeout_grace_seconds", ""
            ),
        }
        for field, expected in config_checks.items():
            if config_meta.get(field) != expected:
                errors.append(
                    f"{config_file}: {field}={config_meta.get(field)!r}, expected {expected!r}"
                )

        for objective in OBJECTIVES:
            manifest_path = config_dir / f"{objective}.logs" / "manifest.txt"
            if not manifest_path.is_file():
                errors.append(f"missing {manifest_path}")
            else:
                manifest = read_key_values(manifest_path)
                manifest_values.append((manifest_path, manifest))
                manifest_hashes[str(manifest_path.relative_to(campaign_dir))] = (
                    hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                )
                manifest_checks = {
                    "git_commit": campaign.get("git_commit"),
                    "git_dirty": "0",
                    "solver": "maxsat_rc2",
                    "objective": objective,
                    "instance_timeout_seconds": config_meta.get("timeout_seconds"),
                    "external_timeout_grace_seconds": config_meta.get(
                        "external_timeout_grace_seconds"
                    ),
                    "maxsat_rc2_bound_mode": wanted["maxsat_rc2_bound_mode"],
                    "maxsat_rc2_refinement_budget": wanted[
                        "maxsat_rc2_refinement_budget"
                    ],
                    "maxsat_rc2_max_wait_iterations": str(max_wait),
                    "maxsat_rc2_full_scan": "true",
                    "maxsat_rc2_validate_before_return": "true",
                    "dataset_file_count": "72",
                }
                for field, expected in manifest_checks.items():
                    if manifest.get(field) != expected:
                        errors.append(
                            f"{manifest_path}: {field}={manifest.get(field)!r}, "
                            f"expected {expected!r}"
                        )
                for field in (
                    "binary_sha256",
                    "cargo_lock_sha256",
                    "dataset_sha256",
                    "salvers_state_sha256",
                    "ipamir_state_sha256",
                    "timeout_binary_sha256",
                    "rustc",
                    "gurobi",
                    "cpu_model",
                    "logical_cpus",
                    "memory_bytes",
                    "system",
                ):
                    if manifest.get(field) in {None, "", "unavailable"}:
                        errors.append(f"{manifest_path}: missing usable {field}")

                source_diff = manifest_path.parent / "source.diff"
                if not source_diff.is_file() or source_diff.stat().st_size != 0:
                    errors.append(
                        f"{source_diff}: main repository must have been clean at run time"
                    )

            path = config_dir / f"{config}_{objective}.json"
            rows, file_errors = validate_file(
                path, config, objective, timeout, budget, max_wait
            )
            errors.extend(file_errors)
            if not rows:
                continue
            hashes[str(path.relative_to(campaign_dir))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            by_name = {name: solve for name, solve in rows}
            all_data[config, objective] = by_name

            statuses = Counter(solve.get("status") for solve in by_name.values())
            ok_times = [
                seconds
                for solve in by_name.values()
                if solve.get("status") == "ok"
                for seconds in [elapsed_seconds(solve)]
                if seconds is not None
            ]
            par2_terms = []
            for solve in by_name.values():
                seconds = elapsed_seconds(solve)
                if solve.get("status") == "ok" and seconds is not None and seconds <= timeout:
                    par2_terms.append(seconds)
                else:
                    par2_terms.append(2.0 * timeout)
            summary_rows.append(
                {
                    "config": config,
                    "objective": objective,
                    "n": len(by_name),
                    "ok": statuses["ok"],
                    "timeout": statuses["timeout"] + statuses["external_timeout"],
                    "panic": statuses["panic"],
                    "invalid_solution": statuses["invalid_solution"],
                    "oom": statuses["oom"] + statuses["killed"],
                    "other_failure": len(by_name)
                    - statuses["ok"]
                    - statuses["timeout"]
                    - statuses["external_timeout"]
                    - statuses["panic"]
                    - statuses["invalid_solution"]
                    - statuses["oom"]
                    - statuses["killed"],
                    "median_ok_ms": (
                        1000.0 * median_or_none(ok_times) if ok_times else ""
                    ),
                    "par2_seconds": statistics.mean(par2_terms),
                }
            )

    stable_manifest_fields = (
        "git_commit",
        "binary_sha256",
        "cargo_lock_sha256",
        "dataset_file_count",
        "dataset_sha256",
        "run_script_sha256",
        "salvers_git_commit",
        "salvers_state_sha256",
        "salvers_git_dirty_count",
        "ipamir_git_commit",
        "ipamir_state_sha256",
        "ipamir_git_dirty_count",
        "timeout_binary_sha256",
        "rustc",
        "gurobi",
        "cpu_model",
        "logical_cpus",
        "memory_bytes",
        "system",
    )
    if manifest_values:
        reference_path, reference = manifest_values[0]
        for path, manifest in manifest_values[1:]:
            for field in stable_manifest_fields:
                if manifest.get(field) != reference.get(field):
                    errors.append(
                        f"{path}: {field} differs from {reference_path}"
                    )

    paired_rows: list[dict] = []
    cost_mismatches: list[dict] = []
    for objective in OBJECTIVES:
        for left_index, left in enumerate(campaign_configs):
            for right in campaign_configs[left_index + 1 :]:
                left_data = all_data.get((left, objective))
                right_data = all_data.get((right, objective))
                if left_data is None or right_data is None:
                    continue
                common = [
                    name
                    for name in EXPECTED_NAMES
                    if left_data[name].get("status") == "ok"
                    and right_data[name].get("status") == "ok"
                ]
                left_times = [elapsed_seconds(left_data[name]) for name in common]
                right_times = [elapsed_seconds(right_data[name]) for name in common]
                valid_pairs = [
                    (a, b)
                    for a, b in zip(left_times, right_times)
                    if a is not None and b is not None and a > 0 and b > 0
                ]
                ratios = [a / b for a, b in valid_pairs]
                for name in common:
                    left_cost = left_data[name].get("cost")
                    right_cost = right_data[name].get("cost")
                    if not same_number(left_cost, right_cost):
                        cost_mismatches.append(
                            {
                                "objective": objective,
                                "left": left,
                                "right": right,
                                "instance": name,
                                "left_cost": left_cost,
                                "right_cost": right_cost,
                            }
                        )
                paired_rows.append(
                    {
                        "objective": objective,
                        "left": left,
                        "right": right,
                        "common_ok_n": len(common),
                        "left_median_ms": (
                            1000.0 * statistics.median(a for a, _ in valid_pairs)
                            if valid_pairs
                            else ""
                        ),
                        "right_median_ms": (
                            1000.0 * statistics.median(b for _, b in valid_pairs)
                            if valid_pairs
                            else ""
                        ),
                        "right_faster_n": sum(a > b for a, b in valid_pairs),
                        "median_left_over_right": median_or_none(ratios) or "",
                    }
                )

    if cost_mismatches:
        errors.append(f"{len(cost_mismatches)} paired ok results have different costs")

    audit = {
        "campaign": campaign,
        "files_sha256": hashes,
        "manifests_sha256": manifest_hashes,
        "errors": errors,
        "cost_mismatches": cost_mismatches,
        "par2_definition": "ok runtime if <= T; 2T for every other outcome",
        "runtime_field": "sol_time milliseconds, converted to seconds",
        "independent_solution_verification": (
            "every ok schedule was reconstructed from the TXT instance and checked in Python"
        ),
    }
    write_csv(campaign_dir / "journal_summary.csv", summary_rows)
    write_csv(campaign_dir / "journal_paired_comparisons.csv", paired_rows)
    (campaign_dir / "journal_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    )

    print(f"Audited {len(all_data)} result files in {campaign_dir}")
    print(f"Wrote {campaign_dir / 'journal_summary.csv'}")
    print(f"Wrote {campaign_dir / 'journal_paired_comparisons.csv'}")
    print(f"Wrote {campaign_dir / 'journal_audit.json'}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_dir", nargs="?", type=Path)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--config", choices=CONFIGS)
    parser.add_argument("--objective", choices=OBJECTIVES)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--max-wait", type=int, default=5)
    parser.add_argument("--instance-name")
    args = parser.parse_args()

    if args.file is not None:
        required = {
            "--config": args.config,
            "--objective": args.objective,
            "--timeout": args.timeout,
            "--budget": args.budget,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error(f"file mode requires {', '.join(missing)}")
        _, errors = validate_file(
            args.file,
            args.config,
            args.objective,
            args.timeout,
            args.budget,
            args.max_wait,
            [args.instance_name] if args.instance_name else None,
        )
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(
            f"Validated {args.file}: instance list, configuration and telemetry OK"
        )
        return 0

    if args.campaign_dir is None:
        parser.error("provide a campaign directory or --file")
    return audit_campaign(args.campaign_dir)


if __name__ == "__main__":
    raise SystemExit(main())
