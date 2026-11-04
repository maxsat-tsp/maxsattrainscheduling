#!/usr/bin/env python3

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize_conference as audit


REPO = Path(__file__).resolve().parents[2]
CONFERENCE_RESULTS = REPO / "results" / "conferences"


class ConferenceAuditTests(unittest.TestCase):
    def test_committed_results_are_independently_verified(self):
        summary, report, records = audit.audit_directory(CONFERENCE_RESULTS)

        self.assertEqual(report["errors"], [])
        self.assertEqual(
            report["verified_optima"],
            {"finsteps123": 72, "infsteps180": 68, "cont": 58},
        )
        self.assertFalse(report["runtime_comparable"])
        self.assertTrue(any("runtime is diagnostic only" in item for item in report["warnings"]))
        self.assertEqual(len(records), 216)

        by_objective = {row["objective"]: row for row in summary}
        self.assertAlmostEqual(by_objective["finsteps123"]["par2_seconds"], 0.12000146175)
        self.assertAlmostEqual(by_objective["infsteps180"]["par2_seconds"], 18.57350442647222)
        self.assertAlmostEqual(by_objective["cont"]["par2_seconds"], 63.595542883125)

    def test_missing_and_duplicate_names_are_rejected(self):
        rows = [
            {
                "name": "origA1",
                "solves": [
                    {
                        "status": "timeout",
                        "solver_name": audit.EXPECTED_SOLVER,
                        "delay_cost_type": "finite-step123",
                        "timeout_seconds": 150,
                        "total_time": 150,
                        "lb": 0,
                        "ub": 1,
                    }
                ],
            },
            {
                "name": "origA1",
                "solves": [
                    {
                        "status": "timeout",
                        "solver_name": audit.EXPECTED_SOLVER,
                        "delay_cost_type": "finite-step123",
                        "timeout_seconds": 150,
                        "total_time": 150,
                        "lb": 0,
                        "ub": 1,
                    }
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "results.json"
            path.write_text(json.dumps(rows))
            _, errors, _ = audit.audit_result_file(path, "finsteps123")

        self.assertTrue(any("canonical 72-instance list" in item for item in errors))
        self.assertTrue(any("duplicate instance name" in item for item in errors))

    def test_invalid_solution_and_mismatched_bounds_are_rejected(self):
        solve = {
            "status": "ok",
            "solver_name": audit.EXPECTED_SOLVER,
            "delay_cost_type": "finite-step123",
            "timeout_seconds": 150,
            "total_time": 0.1,
            "cost": 10,
            "lb": 9,
            "ub": 10,
            "solution": {},
        }
        rows = [{"name": "origA1", "solves": [solve]}]
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "results.json"
            path.write_text(json.dumps(rows))
            _, errors, _ = audit.audit_result_file(path, "finsteps123")

        self.assertTrue(any("matching finite cost" in item for item in errors))
        self.assertTrue(any("independent verification" in item for item in errors))

    def test_source_commit_is_required_but_machine_manifest_is_only_a_warning(self):
        _, report, _ = audit.audit_directory(CONFERENCE_RESULTS, source_commit="")
        self.assertTrue(any("source commit" in item for item in report["errors"]))
        self.assertTrue(report["warnings"])


if __name__ == "__main__":
    unittest.main()
