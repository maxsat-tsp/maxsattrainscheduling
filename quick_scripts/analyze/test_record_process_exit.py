import json
import tempfile
import unittest
from pathlib import Path

from record_process_exit import record_exit


class ProcessExitTests(unittest.TestCase):
    def test_crash_after_ok_json_cannot_count_as_success(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "origA1.json"
            source = [{"name": "origA1", "solves": [{"status": "ok", "cost": 11}]}]
            path.write_text(json.dumps(source))
            record_exit(path, 139, 0.2, "origA1", "test")
            solve = json.loads(path.read_text())[0]["solves"][0]
            self.assertEqual(solve["status"], "segfault")
            self.assertEqual(solve["solver_reported_status"], "ok")
            self.assertEqual(json.loads(path.with_suffix(".raw.json").read_text()), source)

    def test_success_and_missing_json(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "origA1.json"
            record_exit(path, 124, 50.0, "origA1", "test")
            self.assertEqual(json.loads(path.read_text())[0]["solves"][0]["status"], "external_timeout")
            path.write_text(json.dumps([{"name": "origA1", "solves": [{"status": "ok"}]}]))
            record_exit(path, 0, 0.1, "origA1", "test")
            solve = json.loads(path.read_text())[0]["solves"][0]
            self.assertEqual(solve["status"], "ok")
            self.assertEqual(solve["process_exit_code"], 0)
