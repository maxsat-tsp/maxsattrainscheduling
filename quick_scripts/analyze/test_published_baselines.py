import csv
import tempfile
import unittest
from pathlib import Path

import published_baselines as published


class PublishedBaselineTests(unittest.TestCase):
    def test_counts_follow_closed_bounds_and_do_not_claim_schedule_verification(self):
        root = Path(__file__).resolve().parents[2] / "results"
        records, metadata = published.load_directory(root)
        self.assertEqual(len(metadata["errors"]), 2)
        self.assertEqual({(r["objective"], r["name"]) for r in metadata["cost_conflicts"]},
                         {("finsteps123", "trackA1"), ("infsteps180", "stationB12")})
        self.assertEqual(len(records), 4 * 3 * 72)
        self.assertTrue(all(not r["schedule_independently_verified"] for r in records))
        expected = {"MaxSAT-Journal": (72, 68, 59), "CSOnet": (72, 68, 60),
                    "BigM-Gurobi": (72, 67, 67), "BigM-CPLEX": (72, 68, 47)}
        for tag, counts in expected.items():
            actual = tuple(sum(r["proven"] for r in records if r["tag"] == tag and r["objective"] == o)
                           for o in published.common.OBJECTIVES)
            self.assertEqual(actual, counts)
        self.assertTrue(any(r["tag"] == "BigM-CPLEX" and r["status"] == "ok" and not r["proven"]
                            for r in records))

    def test_disputed_published_cost_is_not_used_to_reject_a_new_schedule(self):
        references = [dict(objective="cont", name="origA1", proven=True, solve=dict(cost=c))
                      for c in (98, 120)]
        current = [dict(tag="AGLR", objective="cont", name="origA1", proven=True,
                        config=dict(kind="exact"), solve=dict(cost=98))]
        self.assertEqual(published.compare_new_costs(current, references), [])
        references = references[:1]
        current[0]["solve"]["cost"] = 99
        self.assertEqual(len(published.compare_new_costs(current, references)), 1)

    def test_missing_duplicate_and_wrong_cost_are_rejected(self):
        root = Path(__file__).resolve().parents[2] / "results"
        with (root / "MILP_BigM_CPLEX_cont_120s.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        for mutated in (rows[:-1], rows[:-1] + [rows[0]], [dict(rows[0], cost="9999999")] + rows[1:]):
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "reference.csv"
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(mutated)
                _, errors = published.load_file(path, "BigM-CPLEX", "cont")
                self.assertTrue(errors)
