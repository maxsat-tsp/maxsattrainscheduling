#!/usr/bin/env python3
"""Derive a shorter-cutoff view without modifying or rerunning source results.

The time basis is uniformly total_time (seconds). Final bounds/schedules from
after the cutoff are discarded from censored rows; they are not gap-at-cutoff
evidence. Original failures remain failures, even when a JSON was written.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import audit_journal_campaign as common
from summarize_conference import matching_optimal_bounds


def censor_solve(name: str, objective: str, source: dict, cutoff: float) -> dict:
    solve = copy.deepcopy(source)
    elapsed = float(solve["total_time"])
    source_cutoff = float(solve["timeout_seconds"])
    if not all(math.isfinite(x) for x in (elapsed, cutoff, source_cutoff)) or elapsed < 0 or not 0 < cutoff <= source_cutoff:
        raise ValueError("Cutoff must be positive, finite and no greater than the source cutoff")
    status = solve.get("status")
    if status not in common.ALLOWED_STATUSES:
        raise ValueError(f"Unsupported source status: {status!r}")
    if status == "ok":
        errors = common.independently_verify_solution(name, objective, solve)
        if errors or not matching_optimal_bounds(solve):
            raise ValueError(f"{name}/{objective}: invalid source optimum: {errors}")
    provenance = {
        "source_status": status, "source_total_time": elapsed,
        "source_timeout_seconds": source_cutoff, "derived_cutoff_seconds": cutoff,
        "time_basis": "total_time_seconds", "is_exact_rerun": False,
        "source_process_exit_recorded": "process_exit_code" in solve,
    }
    failed = status in common.FATAL_STATUSES or solve.get("process_exit_code", 0) != 0
    if failed:
        if status == "ok":
            solve["status"] = {139: "segfault", 134: "aborted", 101: "panic"}.get(solve["process_exit_code"], "failed")
        solve.update(provenance)
        solve["timeout_seconds"] = cutoff
        return solve
    if status == "ok" and elapsed <= cutoff:
        solve.update(provenance)
        solve["timeout_seconds"] = cutoff
        solve["censored"] = False
        solve["bounds_at_cutoff_available"] = True
        return solve

    # Keep no dynamic telemetry or final 150-second bounds in a 120-second
    # timeout row. The source JSON and its SHA-256 remain in the manifest.
    result = {
        "solver_name": solve.get("solver_name"),
        "delay_cost_type": solve.get("delay_cost_type", common.OBJECTIVE_LABELS[objective]),
        "status": "timeout" if status in {"ok", "timeout", "external_timeout"} else status,
        "timeout_seconds": cutoff, "total_time": min(elapsed, cutoff),
        "lb": None, "ub": None, "cost": None,
        "censored": True, "bounds_at_cutoff_available": False,
        **provenance,
    }
    if "process_exit_code" in solve:
        result["process_exit_code"] = solve["process_exit_code"]
    return result


def derive(source: Path, destination: Path, cutoff: float, pattern: str, tag: str, allow_partial: bool = False) -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError("Destination must differ from the original data directory")
    outputs, files, missing = {}, {}, []
    for objective in common.OBJECTIVES:
        path = source / pattern.format(objective=objective)
        if not path.is_file():
            missing.append(objective)
            if allow_partial:
                continue
            raise ValueError(f"Missing source objective: {path}")
        raw = path.read_bytes()
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise ValueError(f"Expected a JSON list in {path}")
        names = [row.get("name") for row in rows]
        if len(names) != len(set(names)) or set(names) - set(common.EXPECTED_NAMES):
            raise ValueError(f"Duplicate or unexpected names in {path}")
        if not allow_partial and (len(names) != 72 or set(names) != set(common.EXPECTED_NAMES)):
            raise ValueError(f"Expected 72 source instances in {path}")
        derived = []
        for row in rows:
            item = copy.deepcopy(row)
            if len(item["solves"]) != 1:
                raise ValueError("Expected one solver per source row")
            item["solves"] = [censor_solve(item["name"], objective, item["solves"][0], cutoff)]
            derived.append(item)
        outputs[f"{objective}.json"] = json.dumps(derived, indent=2) + "\n"
        records = [row["solves"][0] for row in derived]
        files[objective] = {
            "source": str(path.resolve()), "source_sha256": hashlib.sha256(raw).hexdigest(),
            "instances": len(rows), "missing_instances": sorted(set(common.EXPECTED_NAMES) - set(names)),
            "optimal_within_cutoff": sum(s["status"] == "ok" for s in records),
            "censored": sum(s.get("censored", False) for s in records),
            "fatal": sum(s["status"] in common.FATAL_STATUSES for s in records),
            "par2_seconds": sum(s["total_time"] if s["status"] == "ok" else 2 * cutoff for s in records) / len(records) if records else None,
        }
    manifest = {
        "derived_cutoff_seconds": cutoff, "time_basis": "total_time_seconds",
        "is_exact_rerun": False, "files": files, "missing_objectives": missing,
        "converter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "notes": ["Source data were not modified", "Post-cutoff bounds and schedules are not evidence at the shorter cutoff", "Missing process-exit evidence is not a proof of crash-free execution"],
    }
    outputs["censor_manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    outputs["config.txt"] = f"tag={tag}\nkind=exact\npolicy=legacy\ntimeout_seconds={cutoff:g}\ninstances=\nderived=true\n"
    # Check the complete output set before writing, so an existing run is never
    # silently replaced with different data or a different cutoff.
    for name, text in outputs.items():
        path = destination / name
        if path.exists() and path.read_text() != text:
            raise ValueError(f"Use a new destination; existing derived file differs: {path}")
    destination.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (destination / name).write_text(text)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--cutoff", type=float, default=120)
    parser.add_argument("--pattern", default="{objective}.json")
    parser.add_argument("--tag", default="CSOnet-censored")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    manifest = derive(args.source, args.destination, args.cutoff, args.pattern, args.tag, args.allow_partial)
    for objective, info in manifest["files"].items():
        print(f"{objective}: {info['optimal_within_cutoff']}/{info['instances']}, PAR-2={info['par2_seconds']:.6f}s, fatal={info['fatal']}")
    if manifest["missing_objectives"]:
        print("Incomplete objectives:", manifest["missing_objectives"])


if __name__ == "__main__":
    main()
