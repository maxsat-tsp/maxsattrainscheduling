import copy
import json
import unittest
from pathlib import Path

from censor_results import censor_solve


class CensorResultsTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "results/conferences/MaxsatScDefault_finsteps123.json"
        self.source = json.loads(path.read_text())[0]["solves"][0]

    def test_optimum_at_or_before_cutoff_is_preserved_without_changing_source(self):
        for elapsed in (0.1, 119.999, 120.0):
            source = copy.deepcopy(self.source)
            source["total_time"] = elapsed
            before = copy.deepcopy(source)
            result = censor_solve("origA1", "finsteps123", source, 120)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["cost"], 11)
            self.assertEqual(result["timeout_seconds"], 120)
            self.assertEqual(source, before)

    def test_late_optimum_and_timeout_do_not_supply_cutoff_bounds(self):
        for status, elapsed in (("ok", 120.001), ("timeout", 150.0)):
            source = copy.deepcopy(self.source)
            source.update(status=status, total_time=elapsed, process_exit_code=0)
            result = censor_solve("origA1", "finsteps123", source, 120)
            self.assertEqual(result["status"], "timeout")
            self.assertEqual(result["total_time"], 120)
            self.assertIsNone(result["lb"])
            self.assertIsNone(result["ub"])
            self.assertNotIn("solution", result)
            self.assertFalse(result["bounds_at_cutoff_available"])

    def test_crash_is_not_hidden_and_invalid_source_is_rejected(self):
        source = copy.deepcopy(self.source)
        source.update(total_time=0.1, process_exit_code=139)
        result = censor_solve("origA1", "finsteps123", source, 120)
        self.assertEqual(result["status"], "segfault")
        source["lb"] = 0
        with self.assertRaises(ValueError):
            censor_solve("origA1", "finsteps123", source, 120)

    def test_cannot_extend_source_cutoff(self):
        with self.assertRaises(ValueError):
            censor_solve("origA1", "finsteps123", self.source, 180)
