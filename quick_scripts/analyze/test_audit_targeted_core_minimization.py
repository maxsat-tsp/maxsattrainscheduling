import copy
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import audit_targeted_core_minimization as checker
import extended_timeout_experiments as extended


class SavedCoreAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, self.reference = self.base/"trial", self.base/"reference"
        self.root.mkdir()
        self.reference.mkdir()
        extended.save(self.reference/"manifest.json", dict(plan=dict(timeout_seconds=300)))
        extended.save(self.reference/"backend_comparison.json", dict(complete=True))
        self.selection = dict(finsteps123=[], infsteps180=[], cont=["origA1", "origA2"])
        self.config = dict(extended.METHODS["Orders-Transitive"],
                           core_minimize_checks="4", core_minimize_conflicts="100")
        self.manifest = dict(schema="targeted-core-minimization-v1", timeout_seconds=300,
                             instances_by_objective=self.selection, definition=self.config,
                             dataset_sha256=extended.focus.dataset_hash(), binary_sha256="test-binary",
                             runner_commit="test-source", ram_kb=6000000,
                             reference_manifest_sha256=extended.focus.sha(self.reference/"manifest.json"),
                             reference_report_sha256=extended.focus.sha(self.reference/"backend_comparison.json"))
        extended.save(self.root/"manifest.json", self.manifest)
        case = self.root/"cases/cont/origA1"
        (case/"logs").mkdir(parents=True)
        self.case = case
        solve = dict(status="timeout", total_time=300, timeout_seconds=300, process_exit_code=0)
        solve.update({"maxsat_"+key: value for key, value in self.config.items() if key not in {"solver", "kind"}})
        extended.save(case/"cont.json", [dict(name="origA1", solves=[solve])])
        provenance = dict(binary_sha256="test-binary", git_commit="test-source", git_dirty="0",
                          solver=self.config["solver"], objective="cont", selected_instances="origA1",
                          selected_instance_count="1", instance_timeout_seconds="300", ram_limit_kb="6000000")
        provenance.update({"maxsatddd_"+key: value for key, value in self.config.items() if key not in {"solver", "kind"}})
        (case/"logs/manifest.txt").write_text("".join(f"{k}={v}\n" for k, v in provenance.items()))
        record = extended.assess_case(case, "Orders-Transitive-Mincore-C100", "cont", "origA1", 300, self.config)
        self.assertFalse(record["errors"])
        self.report = dict(schema=self.manifest["schema"], expected_runs=2, completed_runs=1,
                           complete=False, errors=[], submission_passed=False,
                           scope="unresolved cases only; losses on previously solved cases have not been tested",
                           newly_solved=[], summary=extended.audit.summarize([record], 300))
        extended.save(self.root/"core_minimization_audit.json", self.report)
        for name, value in (("definition", extended.METHODS["Orders-Transitive"]),
                            ("tasks", [])):
            manager = patch.object(checker.dual, name, return_value=value)
            manager.start()
            self.addCleanup(manager.stop)
        manager = patch.object(checker.targeted, "select", return_value=self.selection)
        manager.start()
        self.addCleanup(manager.stop)

    def test_partial_audit_rebuilds_the_report_without_changing_raw_files(self):
        before = (self.case/"cont.json").read_bytes()
        result = checker.audit_saved(self.root, self.reference)
        self.assertTrue(result["audit_passed"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["completed_runs"], 1)
        self.assertFalse(result["submission_passed"])
        self.assertEqual((self.case/"cont.json").read_bytes(), before)

    def test_later_failure_cannot_be_hidden_by_an_earlier_clean_report(self):
        extended.save(self.root/"failure.json", dict(error="process exit=124"))
        result = checker.audit_saved(self.root, self.reference)
        self.assertFalse(result["audit_passed"])
        self.assertEqual(result["errors"][0]["status"], "campaign-failure")
        self.assertEqual(result["completed_runs"], 1)

    def test_reference_or_selection_change_is_rejected(self):
        with patch.object(checker.targeted, "select", return_value=dict(self.selection, cont=["origA2"])):
            with self.assertRaisesRegex(ValueError, "selection differs"):
                checker.audit_saved(self.root, self.reference)
        extended.save(self.reference/"backend_comparison.json", dict(complete=False))
        with self.assertRaisesRegex(ValueError, "reference differs"):
            checker.audit_saved(self.root, self.reference)

    def test_missing_case_and_changed_binary_provenance_are_rejected(self):
        path = self.case/"logs/manifest.txt"
        path.write_text(path.read_text().replace("test-binary", "wrong-binary"))
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            checker.audit_saved(self.root, self.reference)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            checker.audit_saved(self.root, self.reference)

    def test_changed_runtime_budget_or_report_is_rejected(self):
        path = self.case/"cont.json"
        content = json.loads(path.read_text())
        content[0]["solves"][0]["maxsat_core_minimize_conflicts"] = 1000
        extended.save(path, content)
        with self.assertRaisesRegex(ValueError, "saved report differs"):
            checker.audit_saved(self.root, self.reference)
        content[0]["solves"][0]["maxsat_core_minimize_conflicts"] = 100
        extended.save(path, content)
        self.report["summary"][0]["par2_seconds"] = 1
        extended.save(self.root/"core_minimization_audit.json", self.report)
        with self.assertRaisesRegex(ValueError, "saved report differs"):
            checker.audit_saved(self.root, self.reference)

    def test_snapshot_excludes_unreported_running_case_and_protects_all_bytes(self):
        running = self.root/"cases/cont/origA2"
        running.mkdir()
        (running/"cont.json").write_text("incomplete and invalid")
        archive = self.base/"partial.tar.gz"
        result = checker.snapshot(self.root, archive)
        self.assertEqual(result["completed_runs"], 1)
        self.assertEqual(result["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "preserve"):
            checker.snapshot(self.root, archive)
        extracted = self.base/"extracted"
        extracted.mkdir()
        with tarfile.open(archive) as stream:
            # Entries come from our freezer with fixed, validated relative names.
            stream.extractall(extracted)
        self.assertFalse((extracted/"cases/cont/origA2").exists())
        self.assertTrue(checker.audit_saved(extracted, self.reference)["audit_passed"])
        (extracted/"cases/cont/origA1/cont.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "changed snapshot artifact"):
            checker.audit_saved(extracted, self.reference)

    def test_duplicate_rows_and_a_fabricated_optimum_are_rejected(self):
        path = self.case/"cont.json"
        original = json.loads(path.read_text())
        extended.save(path, original+original)
        with self.assertRaisesRegex(ValueError, "exactly its planned"):
            checker.audit_saved(self.root, self.reference)
        fake = copy.deepcopy(original)
        fake[0]["solves"][0].update(status="ok", cost=0, lb=0, ub=0, solution=[])
        extended.save(path, fake)
        with self.assertRaisesRegex(ValueError, "saved report differs"):
            checker.audit_saved(self.root, self.reference)

    def test_exhaustion_selection_and_predecessor_hashes_are_checked_independently(self):
        prior_config=dict(self.config)
        evidence=dict(trials=[dict(manifest_sha256="prior",report_sha256="report")],selected_manifest_sha256="prior")
        self.config["core_exhaust_checks"]="4"
        self.manifest["previous_trials"]=evidence
        extended.save(self.root/"manifest.json",self.manifest)
        path=self.case/"cont.json"
        rows=json.loads(path.read_text());rows[0]["solves"][0]["maxsat_core_exhaust_checks"]=4
        extended.save(path,rows)
        path=self.case/"logs/manifest.txt"
        path.write_text(path.read_text()+"maxsatddd_core_exhaust_checks=4\n")
        self.report["summary"][0]["tag"]+="-E4"
        extended.save(self.root/"core_minimization_audit.json",self.report)
        with self.assertRaisesRegex(ValueError,"provide the prior"):
            checker.audit_saved(self.root,self.reference)
        previous=[self.base/"prior"]
        with patch.object(checker.targeted,"unresolved_after_trials",return_value=(self.selection,prior_config,evidence)):
            self.assertTrue(checker.audit_saved(self.root,self.reference,previous)["audit_passed"])
        with patch.object(checker.targeted,"unresolved_after_trials",return_value=(self.selection,prior_config,{})):
            with self.assertRaisesRegex(ValueError,"prior trial hashes"):
                checker.audit_saved(self.root,self.reference,previous)

    def test_selection_and_completeness_are_strict(self):
        for names in (["origA1", "origA1"], ["../outside"], "origA1"):
            manifest = dict(self.manifest, instances_by_objective=dict(self.selection, cont=names))
            with self.assertRaises(ValueError):
                checker.planned_cases(manifest)
        for count in (-1, 3, True):
            with self.assertRaises(ValueError):
                checker.completed_cases(self.manifest, dict(self.report, completed_runs=count))
        with self.assertRaises(ValueError):
            checker.completed_cases(self.manifest, dict(self.report, complete=True))


if __name__ == "__main__":
    unittest.main()
