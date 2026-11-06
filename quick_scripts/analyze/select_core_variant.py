#!/usr/bin/env python3
"""Select a single tested variant; never combine per-instance winners."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

OBJECTIVES = {"finsteps123", "infsteps180", "cont"}


def variant_for(row: dict) -> str:
    sparse = row.get("sparse_costs") == "true"
    orders = row.get("resource_orders") == "true"
    transitive = row.get("order_transitivity") == "true"
    bound = row.get("objective_bound") == "true"
    backend = row.get("backend", "minisat")
    if backend == "glucose":
        if not transitive or not orders or sparse or bound or row["assumptions"] != "legacy":
            raise ValueError("Glucose trial requires the explicitly tested transitive-orders configuration")
        return "orders-transitive-glucose"
    if backend != "minisat":
        raise ValueError("unsupported SAT backend")
    if bound and (not orders or sparse or transitive):
        raise ValueError("objective-bound trial requires the explicitly tested orders configuration")
    if transitive and (not orders or sparse):
        raise ValueError("transitivity requires orders and an explicitly tested cost configuration")
    if (sparse or orders or transitive or bound) and row["assumptions"] != "legacy":
        raise ValueError("combined mechanisms require an explicit new variant")
    if bound:
        return "orders-bound"
    if transitive:
        return "orders-transitive"
    if orders:
        return "orders-sparse" if sparse else "orders"
    return "sparse" if sparse else row["assumptions"]


def select(rows: list[dict], audit: dict) -> dict:
    if audit.get("errors") != []:
        raise ValueError("a complete, error-free audit is required")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["tag"], []).append(row)
    ranking = []
    for tag, items in grouped.items():
        if len(items) != 3 or {r["objective"] for r in items} != OBJECTIVES:
            raise ValueError(f"{tag}: expected exactly three objective rows")
        if any(int(r["instances"]) != 24 for r in items):
            raise ValueError(f"{tag}: expected the locked 24-instance development set")
        variants = {variant_for(row) for row in items}
        if len(variants) != 1:
            raise ValueError(f"{tag}: objective rows have different variants")
        variant = variants.pop()
        if variant not in {"legacy", "full", "geometric", "sparse", "orders", "orders-sparse", "orders-transitive", "orders-bound", "orders-transitive-glucose"}:
            raise ValueError(f"unsupported variant {variant}")
        par2 = sum(float(r["par2_seconds"]) for r in items)
        if not math.isfinite(par2) or par2 < 0:
            raise ValueError(f"{tag}: invalid PAR-2")
        coverage = {r["objective"]: int(r["proven_optimal"]) for r in items}
        targets = {r["objective"]: int(r["conference_coverage"]) for r in items}
        ranking.append(dict(tag=tag, variant=variant, coverage=coverage, targets=targets,
                            eligible=all(coverage[o] >= targets[o] for o in OBJECTIVES),
                            total=sum(coverage.values()), par2_sum=par2))
    ranking.sort(key=lambda r: (not r["eligible"], -r["total"], r["par2_sum"], r["variant"]))
    winner = ranking[0] if ranking and ranking[0]["eligible"] else None
    return dict(selected=winner, ranking=ranking,
                reason="one configuration, chosen by coverage then PAR-2" if winner
                else "no tested configuration preserves development-set coverage")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("promote_dir", type=Path)
    args = parser.parse_args()
    root = args.promote_dir
    with (root / "aglr_summary.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for tag in {row["tag"] for row in rows}:
        config = dict(line.split("=", 1) for line in (root / tag / "config.txt").read_text().splitlines())
        if config.get("timeout_seconds") != "120":
            raise ValueError("selection requires the 120-second promotion stage")
    decision = select(rows, json.loads((root / "aglr_audit.json").read_text()))
    (root / "core_selection.json").write_text(json.dumps(decision, indent=2) + "\n")
    if decision["selected"] is None:
        return 1
    print(decision["selected"]["variant"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
