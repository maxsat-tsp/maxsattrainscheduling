"""Audit a solved-case regression before reusing its lost pairs in the next trial."""
import json
import math
from pathlib import Path

import compare_sat_backends as dual
import extended_timeout_experiments as extended


def audit(root: Path, reference: Path, selected: dict, selected_manifest_sha: str):
    manifest=json.loads((root/"manifest.json").read_text())
    report=json.loads((root/"regression_audit.json").read_text())
    if manifest.get("schema")!="v16-solved-case-regression-v1" or report.get("schema")!=manifest["schema"]:
        raise ValueError("unsupported solved-case regression")
    if not report.get("complete"):
        raise ValueError("finish the regression before selecting its lost cases")
    source=json.loads((reference/"manifest.json").read_text())
    locked=dict(definition=selected["definition"],binary_sha256=selected["binary_sha256"],
        solver_source_commit=selected["solver_source_commit"],dataset_sha256=selected["dataset_sha256"],
        selected_trial_manifest_sha256=selected_manifest_sha,
        reference_manifest_sha256=extended.focus.sha(reference/"manifest.json"),
        reference_report_sha256=extended.focus.sha(reference/"backend_comparison.json"),
        timeout_seconds=source["plan"]["timeout_seconds"],ram_kb=selected["ram_kb"],
        cpu_affinity=selected["cpu_affinity"])
    if any(manifest.get(key)!=value for key,value in locked.items()):
        raise ValueError("regression differs from its selected configuration or reference")
    if manifest["dataset_sha256"]!=extended.focus.dataset_hash():
        raise ValueError("regression dataset changed")
    expected=[]
    for task in dual.tasks(source["plan"]):
        if task[:2]!=("minisat","Orders-Transitive"):continue
        prior=dual.assess(reference,task,source)
        if prior["proven"]:
            expected.append(dict(objective=task[2],name=task[3],cost=prior["solve"]["cost"]))
    if manifest.get("selection")!=expected or report.get("expected_runs")!=len(expected) or report.get("completed_runs")!=len(expected):
        raise ValueError("regression is missing or changing previously solved cases")
    if len(report.get("cases",[]))!=len(expected):
        raise ValueError("regression case ledger has the wrong length")
    losses=[]
    for original,saved in zip(expected,report["cases"]):
        objective,name=original["objective"],original["name"]
        if (saved.get("objective"),saved.get("name"))!=(objective,name):
            raise ValueError("duplicate or unexpected regression case")
        case=root/"cases"/objective/name
        digest=extended.focus.sha(case/f"{objective}.json")
        if digest!=saved.get("sha256"):
            raise ValueError("regression raw result bytes changed")
        provenance=dict(line.split("=",1) for line in (case/"logs/manifest.txt").read_text().splitlines() if "=" in line)
        expected_provenance=dict(git_commit=manifest["runner_commit"],git_dirty="0",binary_sha256=manifest["binary_sha256"],
            solver=manifest["definition"]["solver"],selected_instances=name,selected_instance_count="1",
            objective=objective,instance_timeout_seconds=str(manifest["timeout_seconds"]),
            ram_limit_kb=str(manifest["ram_kb"]))
        expected_provenance.update({"maxsatddd_"+k:v for k,v in manifest["definition"].items() if k not in {"solver","kind"}})
        if any(provenance.get(k)!=v for k,v in expected_provenance.items()):
            raise ValueError("regression case provenance changed")
        result=extended.assess_case(case,"V16-regression",objective,name,manifest["timeout_seconds"],manifest["definition"])
        if result["errors"] or result["status"] in extended.audit.FATAL_STATUSES:
            raise ValueError("regression contains an invalid schedule, status or configuration")
        retained=result["proven"] and extended.common.same_number(result["solve"]["cost"],original["cost"])
        if result["proven"] and not retained:
            raise ValueError("regression proved an inconsistent optimum")
        rebuilt=dict(objective=objective,name=name,expected_cost=original["cost"],cost=result["solve"].get("cost"),
            status=result["status"],proven=result["proven"],retained=retained,errors=result["errors"],sha256=digest)
        if any(saved.get(k)!=v for k,v in rebuilt.items()) or not math.isclose(result["time"],saved.get("seconds",-1),abs_tol=1e-9,rel_tol=1e-12):
            raise ValueError("regression ledger differs from independently audited results")
        if not retained:losses.append(dict(objective=objective,name=name))
    if report.get("lost")!=losses or report.get("passed")!=(not losses):
        raise ValueError("regression concealed or changed its losses")
    return losses,dict(manifest_sha256=extended.focus.sha(root/"manifest.json"),
                       report_sha256=extended.focus.sha(root/"regression_audit.json"))
