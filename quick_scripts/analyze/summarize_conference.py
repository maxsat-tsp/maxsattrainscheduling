#!/usr/bin/env python3
"""Tổng hợp kết quả CSV từ experiments bản hội nghị v1 thành file summary.

Usage:
    python3 summarize_conference.py <thu_muc_luu_ket_qua> [file output]

Ví dụ (nếu dùng run_conference_experiments.sh):
    python3 summarize_conference.py results/2026-10-20_conference summary.csv

Ví dụ (nếu dùng maxsat_default.sh):
    python3 summarize_conference.py 2026-05-16-Verified-Result-For-Graduation-Thesis/maxsatddd_sc_verify summary.csv
"""

import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

OBJECTIVES = ("finsteps123", "infsteps180", "cont")
DEFAULT_TIMEOUT_SECS = 150


def parse_config_objective(csv_path: Path):
    """Lấy config và objective từ tên file: <config>_<objective>.csv"""
    stem = csv_path.stem  # ví dụ: MaxsatScDefault_finsteps123
    for obj in OBJECTIVES:
        suffix = "_" + obj
        if stem.endswith(suffix):
            config = stem[: -len(suffix)]
            return config, obj
    return None, None


def summarize_csv(csv_path: Path, timeout_secs: float):
    config, objective = parse_config_objective(csv_path)
    if config is None:
        return None

    rows = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    statuses = Counter(r.get("status", "") for r in rows)
    n = len(rows)

    ok_times = []
    par2_terms = []
    for r in rows:
        status = r.get("status", "")
        sol_time_raw = r.get("sol_time", "")
        try:
            sol_time_s = float(sol_time_raw) / 1000.0 if sol_time_raw not in ("", None) else None
        except (TypeError, ValueError):
            sol_time_s = None

        if status == "ok" and sol_time_s is not None:
            ok_times.append(sol_time_s)
            if sol_time_s <= timeout_secs:
                par2_terms.append(sol_time_s)
            else:
                par2_terms.append(2.0 * timeout_secs)
        else:
            par2_terms.append(2.0 * timeout_secs)

    median_ok_ms = (
        statistics.median(ok_times) * 1000.0 if ok_times else ""
    )
    par2_seconds = statistics.mean(par2_terms) if par2_terms else ""

    return {
        "config": config,
        "objective": objective,
        "n": n,
        "ok": statuses.get("ok", 0),
        "timeout": statuses.get("timeout", 0) + statuses.get("external_timeout", 0),
        "panic": statuses.get("panic", 0),
        "invalid_solution": statuses.get("invalid_solution", 0),
        "oom": statuses.get("oom", 0) + statuses.get("killed", 0),
        "other_failure": n
            - statuses.get("ok", 0)
            - statuses.get("timeout", 0)
            - statuses.get("external_timeout", 0)
            - statuses.get("panic", 0)
            - statuses.get("invalid_solution", 0)
            - statuses.get("oom", 0)
            - statuses.get("killed", 0),
        "median_ok_ms": median_ok_ms,
        "par2_seconds": par2_seconds,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 summarize_conference.py <thu_muc_luu_ket_qua> [file output]")
        sys.exit(1)

    result_dir = Path(sys.argv[1])
    out_file = Path(sys.argv[2]) if len(sys.argv) > 2 else result_dir / "summary.csv"

    csv_files = sorted(result_dir.glob("*.csv"))
    if not csv_files:
        print(f"Không tìm thấy file CSV nào trong {result_dir}")
        sys.exit(1)

    summary_rows = []
    for csv_path in csv_files:
        row = summarize_csv(csv_path, DEFAULT_TIMEOUT_SECS)
        if row is not None:
            summary_rows.append(row)

    obj_order = {o: i for i, o in enumerate(OBJECTIVES)}
    summary_rows.sort(key=lambda r: (r["config"], obj_order.get(r["objective"], 99)))

    fieldnames = [
        "config", "objective", "n", "ok", "timeout", "panic",
        "invalid_solution", "oom", "other_failure", "median_ok_ms", "par2_seconds",
    ]

    with out_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Đã ghi {len(summary_rows)} dòng vào {out_file}")


if __name__ == "__main__":
    main()
