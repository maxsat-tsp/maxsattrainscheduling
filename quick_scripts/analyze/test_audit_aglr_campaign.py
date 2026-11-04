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

    def test_conference_reference_compares_costs_but_not_runtime(self):
        reference_dir = Path(__file__).resolve().parents[2] / "results" / "conferences"
        _, _, reference_records = audit.conference_audit.audit_directory(reference_dir)
        reference = next(
            record
            for record in reference_records
            if record["objective"] == "finsteps123" and record["verified"]
        )
        campaign_record = {
            "tag": "AGLR",
            "objective": reference["objective"],
            "name": reference["name"],
            "status": "ok",
            "proven": True,
            "time": 999.0,
            "errors": [],
            "solve": {"cost": reference["cost"]},
            "config": {"kind": "exact"},
        }

        comparisons, errors, metadata = audit.compare_conference_reference(
            [campaign_record], reference_dir
        )
        self.assertEqual(errors, [])
        self.assertEqual(comparisons[0]["comparison"], "match")
        self.assertNotIn("reference_time", comparisons[0])
        self.assertFalse(metadata["runtime_used_for_gate_or_ranking"])

        campaign_record["solve"]["cost"] = float(reference["cost"]) + 1
        comparisons, errors, _ = audit.compare_conference_reference(
            [campaign_record], reference_dir
        )
        self.assertEqual(comparisons[0]["comparison"], "cost-mismatch")
        self.assertEqual(len(errors), 1)

    def test_gate_requires_per_objective_non_regression_and_total_gain(self):
        conference = [
            {"objective": "finsteps123", "verified_ok": 72, "par2_seconds": 1.0},
            {"objective": "infsteps180", "verified_ok": 68, "par2_seconds": 2.0},
            {"objective": "cont", "verified_ok": 58, "par2_seconds": 3.0},
        ]

        def row(tag, objective, proven):
            return {
                "tag": tag,
                "objective": objective,
                "instances": 72,
                "proven_optimal": proven,
                "par2_seconds": 1.0,
            }

        summary = []
        for tag in ("AGLR", "MaxSAT-Journal", "CSOnet", "BigM-Gurobi", "BigM-CPLEX"):
            summary.extend(
                row(tag, objective, proven)
                for objective, proven in (
                    ("finsteps123", 72),
                    ("infsteps180", 68),
                    ("cont", 59 if tag == "AGLR" else 58),
                )
            )
        gate = audit.evaluate_gate(summary, conference)
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["total_coverage"], 199)

        summary[2]["proven_optimal"] = 57
        gate = audit.evaluate_gate(summary, conference)
        self.assertFalse(gate["passed"])
        self.assertTrue(any("cont" in reason for reason in gate["reasons"]))


if __name__ == "__main__":
    unittest.main()
