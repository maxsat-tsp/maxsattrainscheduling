#!/usr/bin/env python3

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_aglr_campaign as audit


class AuditAglrCampaignTests(unittest.TestCase):
    def test_cplex_names_are_normalized(self):
        self.assertEqual(audit.canonical_name("addtrackA3"), "trackA3")
        self.assertEqual(audit.canonical_name("addstationB12"), "stationB12")
        self.assertEqual(audit.canonical_name("originalA1"), "origA1")
        self.assertEqual(audit.canonical_name("origB4"), "origB4")

    def test_matching_bounds_are_required_for_optimality(self):
        self.assertTrue(audit.bounds_prove_optimal({"lb": 10, "ub": 10.000001}))
        self.assertFalse(audit.bounds_prove_optimal({"lb": 9, "ub": 10}))
        self.assertFalse(audit.bounds_prove_optimal({"lb": None, "ub": 10}))

    def test_cplex_requires_explicit_validation_evidence(self):
        self.assertTrue(audit.recorded_validation_passed({"valid": "true"}))
        self.assertTrue(audit.recorded_validation_passed({"validation_status": "passed"}))
        self.assertFalse(audit.recorded_validation_passed({"status": "ok"}))

        with tempfile.TemporaryDirectory() as raw:
            cplex = Path(raw) / "CPLEX"
            cplex.mkdir()
            path = cplex / "results_bigm_finsteps123_120s.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["name", "status", "lb", "ub", "valid", "total_time"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "name": "originalA1",
                        "status": "ok",
                        "lb": "10",
                        "ub": "10",
                        "valid": "",
                        "total_time": "1",
                    }
                )
            records = audit.load_cplex(Path(raw), 120)

        record = next(item for item in records if item["name"] == "origA1")
        self.assertFalse(record["proven"])
        self.assertTrue(any("valid=true" in error for error in record["errors"]))

    def test_loader_reports_missing_and_duplicate_subset_rows(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            rows = [
                {"name": "origA3", "solves": [{"status": "timeout", "total_time": 30}]},
                {"name": "origA3", "solves": [{"status": "timeout", "total_time": 30}]},
            ]
            for objective in audit.OBJECTIVES:
                (root / f"{objective}.json").write_text(json.dumps(rows))
            config = {
                "tag": "AGLR-test",
                "kind": "exact",
                "policy": "adaptive",
                "instances": "origA3,trackA3",
            }
            records = audit.load_json_method(root, config, 30)

        self.assertEqual(len(records), 9)
        missing = [record for record in records if record["status"] == "missing"]
        duplicates = [
            record
            for record in records
            if any("duplicate instance" in error for error in record["errors"])
        ]
        self.assertEqual(len(missing), 3)
        self.assertEqual(len(duplicates), 6)


if __name__ == "__main__":
    unittest.main()
