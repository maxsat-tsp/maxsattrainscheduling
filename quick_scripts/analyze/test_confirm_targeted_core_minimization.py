import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import confirm_targeted_core_minimization as confirm
import extended_timeout_experiments as extended


class CoreConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.trials = [self.base/"C100", self.base/"C1000"]
        self.gain = dict(objective="cont", name="origB11", cost=75494, seconds=153.39)
        self.manifest = dict(instances_by_objective=dict(cont=["origB11"]), timeout_seconds=300,
                             dataset_sha256="dataset", binary_sha256="binary", solver_source_commit="source",
                             definition=dict(extended.METHODS["Orders-Transitive"],
                                             core_minimize_checks="4", core_minimize_conflicts="1000"))
        for root in self.trials:
            root.mkdir()
            extended.save(root/"manifest.json", self.manifest)
            extended.save(root/"core_minimization_audit.json", {})
        self.args = SimpleNamespace(trials=self.trials, reference=self.base/"reference", binary=self.base/"ddd",
                                    results=self.base/"confirm", ram_kb=6000000, round_seconds=21600)

    def report(self, gains, par2):
        return dict(complete=True, audit_passed=True, newly_solved=gains,
                    summary=[dict(instances=1, par2_seconds=par2)])

    def test_coverage_precedes_runtime_then_lower_par2_breaks_ties(self):
        slow_gain, fast_timeout = self.report([self.gain], 299), self.report([], 10)
        with patch.object(confirm.checker, "audit_saved", side_effect=[slow_gain, fast_timeout]):
            self.assertEqual(confirm.choose(self.trials, self.args.reference)[0], self.trials[0])
        with patch.object(confirm.checker, "audit_saved", side_effect=[slow_gain, self.report([self.gain], 153)]):
            self.assertEqual(confirm.choose(self.trials, self.args.reference)[0], self.trials[1])

    def test_incomplete_failed_and_different_binary_trials_are_rejected(self):
        for bad in (dict(self.report([], 600), complete=False), dict(self.report([], 600), audit_passed=False)):
            with patch.object(confirm.checker, "audit_saved", return_value=bad):
                with self.assertRaisesRegex(ValueError, "finish and independently audit"):
                    confirm.choose(self.trials, self.args.reference)
        extended.save(self.trials[1]/"manifest.json", dict(self.manifest, binary_sha256="different"))
        with patch.object(confirm.checker, "audit_saved", return_value=self.report([], 600)):
            with self.assertRaisesRegex(ValueError, "binary_sha256"):
                confirm.choose(self.trials, self.args.reference)

    def run_confirmations(self, records):
        def git(command, **kwargs):
            return "runner\n" if "rev-parse" in command else b""
        with patch.object(confirm, "choose", return_value=(self.trials[1], self.report([self.gain], 153))), \
             patch.object(extended.focus, "sha", return_value="binary"), \
             patch.object(confirm.subprocess, "check_output", side_effect=git), \
             patch.object(confirm.os, "sched_getaffinity", return_value={0, 1, 4, 5}, create=True), \
             patch.object(extended, "run_case") as runner, \
             patch.object(extended, "assess_case", side_effect=records):
            confirm.run(self.args)
            return runner.call_args_list

    def record(self, proven=True, cost=75494):
        return dict(proven=proven, status="ok" if proven else "timeout", errors=[],
                    time=154 if proven else 300, solve=dict(cost=cost))

    def test_exactly_three_audited_repeats_confirm_a_gain_without_a_full_claim(self):
        calls = self.run_confirmations([self.record() for _ in range(3)])
        report = json.loads((self.args.results/"confirmation_audit.json").read_text())
        self.assertEqual(len(calls), 3)
        self.assertTrue(report["complete"] and report["confirmed"])
        self.assertFalse(report["submission_passed"])
        self.assertEqual([r["repeat"] for r in report["cases"]], [1, 2, 3])
        # Reference costs stay in the auditor; only the algorithm definition
        # is passed to the solver runner.
        for call in calls:
            self.assertEqual(call.args[3].method_definitions, {"Core-confirm": self.manifest["definition"]})

    def test_a_timeout_cannot_count_as_reproducing_the_optimum(self):
        self.run_confirmations([self.record(), self.record(False), self.record()])
        report = json.loads((self.args.results/"confirmation_audit.json").read_text())
        self.assertTrue(report["complete"])
        self.assertFalse(report["confirmed"])
        self.assertFalse(report["cases"][1]["reproduced"])

    def test_invalid_schedule_or_different_proved_cost_stops_confirmation(self):
        for record in (dict(self.record(), errors=["invalid schedule"]), self.record(cost=75493)):
            with self.assertRaises(ValueError):
                self.run_confirmations([record])


if __name__ == "__main__":
    unittest.main()
