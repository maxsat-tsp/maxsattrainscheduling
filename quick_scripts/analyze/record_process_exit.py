#!/usr/bin/env python3
"""Record the real process exit, even if the solver wrote JSON before crashing."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def record_exit(path: Path, exit_code: int, elapsed: float, name: str, solver: str, timeout: float = 0) -> None:
    status = {
        124: "external_timeout", 137: "killed", 134: "aborted",
        139: "segfault", 101: "panic",
    }.get(exit_code, "failed")
    if path.is_file() and path.stat().st_size:
        raw = path.read_bytes()
        try:
            rows = json.loads(raw)
            if not isinstance(rows, list) or len(rows) != 1:
                raise ValueError("expected one result")
            item = rows[0]
            solve = item["solves"][0]
            if item["name"] != name or len(item["solves"]) != 1:
                raise ValueError("wrong instance or solve count")
        except (ValueError, KeyError, TypeError, IndexError):
            path.with_suffix(".raw.json").write_bytes(raw)
        else:
            solve["process_exit_code"] = exit_code
            solve["process_wall_time_seconds"] = elapsed
            if exit_code:
                path.with_suffix(".raw.json").write_bytes(raw)
                solve["solver_reported_status"] = solve.get("status")
                solve["status"] = status
                solve["external_status"] = status
            path.write_text(json.dumps(rows, indent=2) + "\n")
            return
    path.write_text(json.dumps([{
        "name": name,
        "solves": [{
            "solver_name": solver, "status": status, "external_status": status,
            "process_exit_code": exit_code, "total_time": elapsed,
            "timeout_seconds": timeout,
            "process_wall_time_seconds": elapsed,
        }],
    }], indent=2) + "\n")


if __name__ == "__main__":
    record_exit(Path(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), *sys.argv[4:6], float(sys.argv[6]))
