#!/usr/bin/env python3
"""Freeze or independently audit a partial/completed bounded-core trial."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

import compare_sat_backends as dual
import extended_timeout_experiments as extended
import targeted_core_minimization as targeted


def planned_cases(manifest):
    if manifest.get("schema") != "targeted-core-minimization-v1":
        raise ValueError("unsupported targeted-core manifest")
    selection = manifest["instances_by_objective"]
    if set(selection) != set(extended.audit.OBJECTIVES):
        raise ValueError("declare all three objectives, including skipped ones")
    for names in selection.values():
        if not isinstance(names, list) or len(names) != len(set(names)) or any(
                name not in extended.common.EXPECTED_NAMES for name in names):
            raise ValueError("unexpected or duplicate selected instance")
    return [(objective, name) for objective in extended.audit.OBJECTIVES
            for name in selection[objective]]


def completed_cases(manifest, report):
    expected = planned_cases(manifest)
    count = report.get("completed_runs")
    if type(count) is not int or not 0 <= count <= len(expected):
        raise ValueError("invalid completed case count")
    if report.get("expected_runs") != len(expected) or report.get("complete") != (count == len(expected)):
        raise ValueError("saved report has inconsistent completeness")
    # The runner processes this fixed order and atomically saves after each case.
    return expected[:count]


def snapshot(root: Path, output: Path):
    if output.exists():
        raise ValueError("preserve the earlier snapshot; choose a new output")
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("write snapshots outside the running result directory")
    files = {name: (root/name).read_bytes()
             for name in ("manifest.json", "core_minimization_audit.json")}
    manifest, report = (json.loads(files[name]) for name in
                        ("manifest.json", "core_minimization_audit.json"))
    completed = completed_cases(manifest, report)
    for objective, name in completed:
        case = root/"cases"/objective/name
        for path in sorted(case.rglob("*")):
            if path.is_symlink():
                raise ValueError("case artifacts cannot be symlinks")
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path.read_bytes()
        if f"cases/{objective}/{name}/{objective}.json" not in files:
            raise ValueError("reported completed case has no raw result")
    if (root/"failure.json").exists():
        files["failure.json"] = (root/"failure.json").read_bytes()
    metadata = dict(schema="targeted-core-snapshot-v1", completed_runs=len(completed),
                    expected_runs=report["expected_runs"], complete=report["complete"],
                    file_sha256={name: hashlib.sha256(content).hexdigest()
                                 for name, content in files.items()})
    files["snapshot.json"] = (json.dumps(metadata, indent=2)+"\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    return dict(completed_runs=len(completed), expected_runs=report["expected_runs"],
                complete=report["complete"], sha256=extended.focus.sha(output))


def verify_snapshot(root):
    path = root/"snapshot.json"
    if not path.exists():
        return
    metadata = json.loads(path.read_text())
    if metadata.get("schema") != "targeted-core-snapshot-v1":
        raise ValueError("unsupported targeted-core snapshot")
    hashes = metadata["file_sha256"]
    if not {"manifest.json", "core_minimization_audit.json"}.issubset(hashes):
        raise ValueError("snapshot is missing its locked manifest or report")
    report = json.loads((root/"core_minimization_audit.json").read_text())
    if any(metadata.get(field) != report.get(field)
           for field in ("completed_runs", "expected_runs", "complete")):
        raise ValueError("snapshot completeness differs from its report")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(hashes) | {"snapshot.json"}:
        raise ValueError("snapshot contains unrecorded or missing artifacts")
    for name, digest in hashes.items():
        target = (root/name).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file() or extended.focus.sha(target) != digest:
            raise ValueError(f"missing or changed snapshot artifact {name}")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("snapshot contains a symlink")


def audit_saved(root: Path, reference: Path, previous_trials=None, regression_reference=None):
    verify_snapshot(root)
    manifest = json.loads((root/"manifest.json").read_text())
    saved = json.loads((root/"core_minimization_audit.json").read_text())
    completed = completed_cases(manifest, saved)
    for filename, field in (("manifest.json", "reference_manifest_sha256"),
                            ("backend_comparison.json", "reference_report_sha256")):
        if extended.focus.sha(reference/filename) != manifest[field]:
            raise ValueError("reference differs from the source locked for this trial")
    if manifest["dataset_sha256"] != extended.focus.dataset_hash():
        raise ValueError("dataset differs from the locked trial")
    selection=targeted.select(reference)
    if manifest.get("previous_trials"):
        if not previous_trials:
            raise ValueError("provide the prior V16 trials to audit the new selection")
        if bool(manifest["previous_trials"].get("regression"))!=(regression_reference is not None):
            raise ValueError("provide exactly the regression reference frozen for this trial")
        selection,previous_config,evidence=targeted.unresolved_after_trials(reference,previous_trials,regression_reference)
        if evidence!=manifest["previous_trials"]:
            raise ValueError("prior trial hashes differ from the frozen selection")
        if manifest["definition"].get("core_minimize_conflicts")!=previous_config.get("core_minimize_conflicts"):
            raise ValueError("exhaustion changed the selected native conflict budget")
    elif previous_trials:
        raise ValueError("this historical trial does not declare any prior V16 trials")
    if manifest["instances_by_objective"] != selection:
        raise ValueError("selection differs from unresolved reference cases")
    source = json.loads((reference/"manifest.json").read_text())
    config = dict(dual.definition(source["plan"], "minisat", "Orders-Transitive"),
                  core_minimize_checks="4")
    conflicts = int(manifest["definition"].get("core_minimize_conflicts", 0))
    if not 0 <= conflicts <= 2147483647:
        raise ValueError("invalid native conflict budget")
    if conflicts:
        config["core_minimize_conflicts"] = str(conflicts)
    exhaust=int(manifest["definition"].get("core_exhaust_checks",0))
    if exhaust<0 or bool(exhaust)!=bool(manifest.get("previous_trials")):
        raise ValueError("exhaustion must declare its audited predecessor trials")
    if exhaust: config["core_exhaust_checks"]=str(exhaust)
    if manifest["definition"] != config or manifest["timeout_seconds"] != source["plan"]["timeout_seconds"]:
        raise ValueError("method or cutoff differs from the frozen comparison")
    tag = targeted.tag_for(config)
    oracle = {}
    for task in dual.tasks(source["plan"]):
        if (dual.case_root(reference, task)/"measurement.json").exists():
            record = dual.assess(reference, task, source)
            if record["proven"]:
                oracle[task[2:]] = record["solve"]["cost"]
    records = []
    errors = []
    for objective, name in completed:
        case = root/"cases"/objective/name
        lines = (case/"logs/manifest.txt").read_text().splitlines()
        provenance = dict(line.split("=", 1) for line in lines if "=" in line)
        expected = dict(binary_sha256=manifest["binary_sha256"], git_commit=manifest["runner_commit"],
                        git_dirty="0", solver=config["solver"], objective=objective,
                        selected_instances=name, selected_instance_count="1",
                        instance_timeout_seconds=str(manifest["timeout_seconds"]),
                        ram_limit_kb=str(manifest["ram_kb"]))
        expected.update({"maxsatddd_"+key: value for key, value in config.items()
                         if key not in {"solver", "kind"}})
        if any(provenance.get(key) != value for key, value in expected.items()):
            raise ValueError(f"case provenance differs from manifest: {objective}/{name}")
        record = extended.assess_case(case, tag, objective, name, manifest["timeout_seconds"], config)
        if record["errors"] or record["status"] in extended.audit.FATAL_STATUSES:
            errors.append(dict(objective=objective, name=name, status=record["status"], errors=record["errors"]))
        if record["proven"] and (objective, name) in oracle and not extended.common.same_number(
                record["solve"]["cost"], oracle[objective, name]):
            errors.append(dict(objective=objective, name=name, status="optimal-cost-disagreement"))
        records.append(record)
    result = dict(schema=manifest["schema"], expected_runs=len(planned_cases(manifest)),
                  completed_runs=len(records), complete=saved["complete"], errors=errors,
                  submission_passed=False,
                  scope=("unresolved cases and audited regression losses only; other solved cases have not been retested" if regression_reference is not None
                         else "unresolved cases only; losses on previously solved cases have not been tested"),
                  newly_solved=[dict(objective=r["objective"], name=r["name"], cost=r["solve"]["cost"], seconds=r["time"])
                                for r in records if r["proven"]],
                  summary=extended.audit.summarize(records, manifest["timeout_seconds"]))
    if not extended.reports_match(result, saved):
        raise ValueError("saved report differs from independently audited raw results")
    if (root/"failure.json").exists():
        errors.append(dict(status="campaign-failure", details=json.loads((root/"failure.json").read_text())))
    result["audit_passed"] = not errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freezer = commands.add_parser("snapshot")
    freezer.add_argument("results", type=Path)
    freezer.add_argument("output", type=Path)
    checker = commands.add_parser("audit")
    checker.add_argument("results", type=Path)
    checker.add_argument("--reference", type=Path, required=True)
    checker.add_argument("--previous-trials", type=Path, nargs="+")
    checker.add_argument("--regression-reference",type=Path)
    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot(args.results, args.output)
    else:
        result = audit_saved(args.results, args.reference, args.previous_trials,args.regression_reference)
    print(json.dumps(result, indent=2))
    if result.get("audit_passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
