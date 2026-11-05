import unittest
from pathlib import Path

import published_conference_reference as reference


class PublishedReferenceTests(unittest.TestCase):
    def test_camera_ready_reference_is_120_seconds_and_200_optima(self):
        root = Path(__file__).resolve().parents[2] / "results"
        summary, metadata, records = reference.audit_directory(root)
        self.assertEqual(metadata["errors"], [])
        self.assertEqual(metadata["verified_optima"], {"finsteps123": 72, "infsteps180": 68, "cont": 60})
        self.assertEqual(metadata["timeout_seconds"], 120)
        self.assertEqual(len(records), 216)
        self.assertTrue(all(not r["schedule_independently_verified"] for r in records))
        self.assertEqual([r["timeout_seconds"] for r in summary], [120, 120, 120])
