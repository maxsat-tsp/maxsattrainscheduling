#!/usr/bin/env python3
"""Build and evaluate objective-specific hard-instance trials from audited data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import audit_aglr_campaign as audit
import audit_journal_campaign as common
import published_conference_reference as conference

OBJECTIVES = audit.OBJECTIVES


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dataset_hash() -> str:
    return hashlib.sha256(b"".join((n + ":" + sha(common.instance_path(n))).encode()
                                   for n in common.EXPECTED_NAMES)).hexdigest()


def on_time(record: dict, cutoff: float) -> bool:
    seconds = audit.finite_number(record["solve"].get("total_time"))
    return bool(record["proven"] and seconds is not None and 0 <= seconds <= cutoff)


def load_full(path: Path, cutoff: float) -> dict:
    config = audit.read_config(path / "config.txt")
    if any(audit.expected_names(config, o) != common.EXPECTED_NAMES for o in OBJECTIVES):
        raise ValueError(f"{path}: a complete 72-instance run is required for each objective")
    records = audit.load_json_method(path, config, cutoff)
    errors = [r for r in records if r["errors"] or r["status"] in audit.FATAL_STATUSES]
    if errors:
        raise ValueError(f"{path}: {len(errors)} audit errors; first: {errors[0]}")
    return dict(label=path.parent.name + "/" + config["tag"],
                source_directory=str(path.resolve()), source_commit=config.get("git_commit"),
                binary_sha256=config.get("binary_sha256"),
                file_sha256={f"{o}.json": sha(path / f"{o}.json") for o in OBJECTIVES},
                proven={o: [r["name"] for r in records if r["objective"] == o and on_time(r, cutoff)]
                        for o in OBJECTIVES})


def choose(anchors: list[dict]) -> dict[str, list[str]]:
    if not anchors:
        raise ValueError("at least one audited reference is required")
    return {o: [n for n in common.EXPECTED_NAMES
                if any(n not in a["proven"][o] for a in anchors)] for o in OBJECTIVES}


def validate_manifest(manifest: dict) -> dict[str, list[str]]:
    if manifest.get("schema") != "focused-sat-v1" or manifest.get("timeout_seconds") != 120:
        raise ValueError("expected a focused-sat-v1 selection built at the 120-second cutoff")
    config = {"instances_by_objective": json.dumps(manifest["instances_by_objective"])}
    selection = {o: audit.expected_names(config, o) for o in OBJECTIVES}
    anchors = manifest.get("anchors", [])
    labels = [a["label"] for a in anchors]
    if len(labels) != len(set(labels)) or manifest.get("primary_anchor") not in labels:
        raise ValueError("reference labels must be unique and include the primary anchor")
    for anchor in anchors:
        if set(anchor["proven"]) != set(OBJECTIVES):
            raise ValueError("every anchor must declare three objectives")
        for names in anchor["proven"].values():
            if (not isinstance(names, list) or any(not isinstance(n, str) for n in names)
                    or len(names) != len(set(names)) or not set(names).issubset(common.EXPECTED_NAMES)):
                raise ValueError("invalid proven-instance list in a reference")
    if choose(anchors) != selection:
        raise ValueError("selected names differ from the unresolved union of the locked references")
    return selection


def build(paths: list[Path], reference: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"{output} already exists; keep the old selection immutable")
    anchors = [load_full(path, 120) for path in paths]
    _, metadata, rows = conference.audit_directory(reference)
    if metadata["errors"]:
        raise ValueError(str(metadata["errors"]))
    anchors.append(dict(label="published-CSOnet-120", source_commit=metadata["source_data_commit"],
                        file_sha256=metadata["file_sha256"],
                        verification_scope=metadata["verification_scope"],
                        proven={o: [r["name"] for r in rows if r["objective"] == o
                                    and r["verified"] and r["total_time"] <= 120] for o in OBJECTIVES}))
    selection = choose(anchors)
    manifest = dict(schema="focused-sat-v1", timeout_seconds=120,
                    primary_anchor=anchors[0]["label"], anchors=anchors,
                    instances_by_objective=selection,
                    dataset_sha256=dataset_hash(),
                    scope="idea screening; unrun solved cases are not revalidated")
    validate_manifest(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def comparison(manifest: dict, records: list[dict], cutoff: float) -> dict:
    selected = validate_manifest(manifest)
    if dataset_hash() != manifest.get("dataset_sha256"):
        raise ValueError("dataset differs from the data used to select the focused instances")
    expected = {(o, n) for o in OBJECTIVES for n in selected[o]}
    keys = [(r["objective"], r["name"]) for r in records]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("focus results are missing, duplicate, or outside the locked selection")
    if any(r["errors"] or r["status"] in audit.FATAL_STATUSES for r in records):
        raise ValueError("focus results have audit errors")
    proven = {o: {r["name"] for r in records if r["objective"] == o and on_time(r, cutoff)}
              for o in OBJECTIVES}
    comparisons = []
    for anchor in manifest["anchors"]:
        gains, losses, projected = {}, {}, {}
        for o in OBJECTIVES:
            before, tested = set(anchor["proven"][o]), set(selected[o])
            gains[o] = sorted(proven[o] - before)
            losses[o] = sorted((before & tested) - proven[o])
            projected[o] = len(before) + len(gains[o]) - len(losses[o])
        comparisons.append(dict(anchor=anchor["label"], gained=gains, lost=losses,
                                projected_coverage=projected, projected_total=sum(projected.values())))
    primary = next(c for c in comparisons if c["anchor"] == manifest["primary_anchor"])
    best_total = max(sum(len(a["proven"][o]) for o in OBJECTIVES) for a in manifest["anchors"])
    promising = (cutoff == 120 and primary["projected_total"] > best_total
                 and all(primary["projected_coverage"][o] >= audit.DEFAULT_CONFERENCE_COVERAGE[o]
                         for o in OBJECTIVES)
                 and not any(names for c in comparisons for names in c["lost"].values()))
    return dict(scope="focused-only; projected coverage assumes unrun solved cases are unchanged",
                full_validation_required=True, submission_passed=False,
                promising_for_full=promising, timeout_seconds=cutoff,
                tested_pairs=len(records), tested_by_objective={o: len(selected[o]) for o in OBJECTIVES},
                proven_by_objective={o: len(proven[o]) for o in OBJECTIVES}, comparisons=comparisons)


def run_trial(args) -> None:
    from select_core_variant import variant_for
    manifest = json.loads(args.manifest.read_text())
    selected = validate_manifest(manifest)
    if dataset_hash() != manifest.get("dataset_sha256"):
        raise ValueError("dataset differs from the locked selection")
    repo = Path(__file__).resolve().parents[2]
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo).strip():
        raise ValueError("commit source changes before running a focused trial")
    if args.variant not in {"orders", "orders-transitive", "orders-transitive-full", "orders-transitive-geometric", "orders-transitive-mincore", "orders-transitive-glucose", "orders-transitive-harden", "orders-bound", "orders-sparse", "legacy"}:
        raise ValueError("unsupported focused variant")
    config = dict(tag="Focus-" + args.variant, kind="exact", solver="maxsat_ddd_ladder_sc", policy="legacy",
                  assumptions=("full" if args.variant.endswith("-full") else "geometric" if args.variant.endswith("-geometric") else "legacy"),
                  sparse_costs=str(args.variant == "orders-sparse").lower(),
                  resource_orders=str(args.variant != "legacy").lower(),
                  order_transitivity=str(args.variant in {"orders-transitive", "orders-transitive-full", "orders-transitive-geometric", "orders-transitive-mincore", "orders-transitive-glucose", "orders-transitive-harden"}).lower(),
                  objective_bound=str(args.variant == "orders-bound").lower(),
                  residual_hardening=str(args.variant == "orders-transitive-harden").lower(),
                  core_minimize_checks="4" if args.variant == "orders-transitive-mincore" else "0",
                  backend="glucose" if args.variant.endswith("-glucose") else "minisat",
                  timeout_seconds=str(args.timeout), process_exit_required="true", parallelism="1",
                  instances_by_objective=json.dumps(selected, separators=(",", ":")),
                  focus_manifest_sha256=sha(args.manifest),
                  git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                  binary_sha256=sha(args.binary))
    assert variant_for(config) == args.variant
    root = args.results.resolve()
    target = root / config["tag"]
    target.mkdir(parents=True, exist_ok=True)
    content = "".join(f"{k}={v}\n" for k, v in config.items())
    path = target / "config.txt"
    if path.exists() and path.read_text() != content:
        raise ValueError("resume would change source, binary, selection, cutoff, or parameters")
    path.write_text(content)
    frozen = root / "focus_manifest.json"
    if frozen.exists() and sha(frozen) != sha(args.manifest):
        raise ValueError("results directory already contains another focus selection")
    frozen.write_bytes(args.manifest.read_bytes())
    for objective in OBJECTIVES:
        names = selected[objective]
        if not names:
            print(f"Skip {objective}: no unresolved instances in the locked references", flush=True)
            continue
        env = dict(os.environ, BIN=str(args.binary.resolve()), SOLVER=config["solver"], OBJECTIVE=objective,
                   INSTANCE_NAMES=" ".join(names), INSTANCE_TIMEOUT_SECS=str(args.timeout),
                   INSTANCE_ORDER_SEED="20261106", RAM_LIMIT_KB=str(args.ram_kb),
                   MAXSATDDD_ASSUMPTIONS=config["assumptions"], MAXSATDDD_SPARSE_COSTS=config["sparse_costs"],
                   MAXSATDDD_RESOURCE_ORDERS=config["resource_orders"],
                   MAXSATDDD_ORDER_TRANSITIVITY=config["order_transitivity"],
                   MAXSATDDD_OBJECTIVE_BOUND=config["objective_bound"],
                   MAXSATDDD_BACKEND=config["backend"],
                   MAXSATDDD_RESIDUAL_HARDENING=config["residual_hardening"],
                   MAXSATDDD_CORE_MINIMIZE_CHECKS=config["core_minimize_checks"],
                   JSON_OUT=str(target / f"{objective}.json"), RUN_LOG_DIR=str(target / f"{objective}.logs"))
        subprocess.run(["bash", "quick_scripts/run_all_txt_instances_limited.sh"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "quick_scripts/analyze/audit_aglr_campaign.py", str(root),
                    "--timeout", str(args.timeout), "--conference-reference", "results",
                    "--conference-profile", "published-csv-120",
                    "--conference-runtime-mode", "assumed-equivalent"], cwd=repo, check=True)
    records = audit.load_json_method(target, config, args.timeout)
    report = comparison(manifest, records, args.timeout)
    (target / "focus_comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def replay(args) -> None:
    manifest = json.loads(args.manifest.read_text())
    selected = validate_manifest(manifest)
    source = load_full(args.full_method, 120)
    config = audit.read_config(args.full_method / "config.txt")
    records = [r for r in audit.load_json_method(args.full_method, config, 120)
               if r["name"] in selected[r["objective"]]]
    report = comparison(manifest, records, 120)
    report.update(result_source="reused audited full run; no solver rerun",
                  source=source,
                  actual_full_coverage={o: len(source["proven"][o]) for o in OBJECTIVES})
    if args.output.exists():
        raise ValueError("replay output already exists; do not overwrite an earlier report")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("tested_by_objective", "proven_by_objective", "actual_full_coverage")}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    builder = actions.add_parser("build")
    builder.add_argument("--full-method", type=Path, action="append", required=True)
    builder.add_argument("--conference-reference", type=Path, default=Path("results"))
    builder.add_argument("--output", type=Path, required=True)
    runner = actions.add_parser("run")
    runner.add_argument("--manifest", type=Path, required=True)
    runner.add_argument("--results", type=Path, required=True)
    runner.add_argument("--variant", required=True)
    runner.add_argument("--binary", type=Path, required=True)
    runner.add_argument("--timeout", type=int, choices=[30, 120], default=120)
    runner.add_argument("--ram-kb", type=int, default=15000000)
    reader = actions.add_parser("replay")
    reader.add_argument("--manifest", type=Path, required=True)
    reader.add_argument("--full-method", type=Path, required=True)
    reader.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "build":
        result = build(args.full_method, args.conference_reference, args.output)
        print(json.dumps(result["instances_by_objective"], indent=2))
    elif args.action == "replay":
        replay(args)
    else:
        run_trial(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: {exc}")
