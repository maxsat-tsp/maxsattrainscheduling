#!/usr/bin/env python3
"""Freeze only completed cases without changing or pausing a running campaign."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def snapshot(root: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("preserve the earlier snapshot; use a new output path")
    # Reports are written by atomic rename. Cases listed in a captured report
    # have already finished and will not be mutated by the campaign runner.
    raw_report = (root/"extended_audit.json").read_bytes()
    report = json.loads(raw_report)
    files = {"extended_audit.json": raw_report,
             "plan.json": (root/"plan.json").read_bytes(),
             "manifest.json": (root/"manifest.json").read_bytes()}
    plan = json.loads(files["plan.json"])
    allowed = {(method, objective, name)
               for method in json.loads(files["manifest.json"])["methods"]
               for objective, names in plan["instances_by_objective"].items() for name in names}
    seen = set()
    for item in report["case_bounds"]:
        method, objective, name = item["method"], item["objective"], item["name"]
        key = (method, objective, name)
        if key not in allowed or key in seen:
            raise ValueError("unexpected or duplicate completed case in report")
        seen.add(key)
        case = root/"cases"/method/objective/name
        for path in sorted(case.rglob("*")):
            if path.is_symlink():
                raise ValueError("a case must not contain symlinks")
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path.read_bytes()
        if (case/f"{objective}.json").relative_to(root).as_posix() not in files:
            raise ValueError("completed case has no raw result")
    if len(seen) != report["completed_runs"]:
        raise ValueError("completed case count differs from the captured report")
    metadata = dict(schema="extended-timeout-snapshot-v1", complete=report["complete"],
                    completed_runs=len(seen), expected_runs=report["expected_runs"],
                    file_sha256={name:hashlib.sha256(content).hexdigest() for name,content in files.items()})
    files["snapshot.json"] = (json.dumps(metadata, indent=2)+"\n").encode()
    with tarfile.open(output, "w:gz") as archive:
        for name, content in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    return dict(completed_runs=len(seen), expected_runs=report["expected_runs"],
                complete=report["complete"], sha256=hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.results, args.output), indent=2))
