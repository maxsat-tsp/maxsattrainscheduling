"""Read existing CSVs without changing conference tables or manuscript.

Run from any directory: python3 manuscript/journal/audit_existing_results.py
The proof criterion matches submission/scripts/summarize_results.py.
This audits recorded bounds, not the correctness of the underlying models.
"""

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def recorded_optimum(row):
    try:
        lb, ub = float(row["lb"]), float(row["ub"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        row.get("status") == "ok"
        and math.isfinite(lb)
        and math.isfinite(ub)
        and abs(lb - ub) <= 1e-6 * max(1.0, abs(ub))
    )


def main():
    report = []
    for objective in ("finsteps123", "infsteps180", "cont"):
        for method in (
            "MILP_BigM_CPLEX", "MaxSAT_Baseline_RC2", "MaxSAT_Default_RC2"
        ):
            path = ROOT / "results" / f"{method}_{objective}_120s.csv"
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            report.append({
                "source": str(path.relative_to(ROOT)),
                "objective": objective,
                "method": method,
                "rows": len(rows),
                "unique_raw_names": len({r["name"] for r in rows}),
                "recorded_optima": sum(recorded_optimum(r) for r in rows),
            })
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
