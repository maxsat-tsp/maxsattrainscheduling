import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_aglr_campaign as audit
import focused_experiments as focus


def fixture():
    anchors = []
    for label, failures in (("best", {"cont": ["origA1"], "infsteps180": ["origA2"]}),
                            ("conference", {"cont": ["origA3"], "infsteps180": ["origA2"]})):
        anchors.append(dict(label=label, proven={
            o: [n for n in focus.common.EXPECTED_NAMES if n not in failures.get(o, [])]
            for o in focus.OBJECTIVES}))
    return dict(schema="focused-sat-v1", timeout_seconds=120,
                dataset_sha256=focus.dataset_hash(), primary_anchor="best", anchors=anchors,
                instances_by_objective=focus.choose(anchors))


def records(manifest, solved):
    return [dict(objective=o, name=n, proven=(o, n) in solved, status="ok" if (o,n) in solved else "timeout",
                 errors=[], solve={"total_time": 1 if (o,n) in solved else 120})
            for o, names in manifest["instances_by_objective"].items() for n in names]


class FocusTests(unittest.TestCase):
    def test_glucose_variant_is_explicit_and_does_not_mix_other_trials(self):
        from select_core_variant import variant_for
        config = dict(backend="glucose", assumptions="legacy", resource_orders="true",
                      order_transitivity="true", sparse_costs="false", objective_bound="false")
        self.assertEqual(variant_for(config), "orders-transitive-glucose")
        for key in ("sparse_costs", "objective_bound"):
            malformed = dict(config, **{key: "true"})
            with self.assertRaises(ValueError):
                variant_for(malformed)

    def test_union_preserves_losses_and_keeps_objectives_separate(self):
        manifest = fixture()
        self.assertEqual(manifest["instances_by_objective"], dict(
            finsteps123=[], infsteps180=["origA2"], cont=["origA1", "origA3"]))
        self.assertEqual(focus.validate_manifest(manifest), manifest["instances_by_objective"])

    def test_explicit_empty_objective_is_skipped_instead_of_assuming_72_missing(self):
        manifest = fixture()
        config = dict(tag="Focus-test", kind="exact", instances_by_objective=json.dumps(manifest["instances_by_objective"]))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for o in ("infsteps180", "cont"):
                (root/f"{o}.json").write_text(json.dumps([
                    dict(name=n, solves=[dict(status="timeout", total_time=120, timeout_seconds=120)])
                    for n in manifest["instances_by_objective"][o]]))
            loaded = audit.load_json_method(root, config, 120)
            (root/"finsteps123.json").write_text("[]")
            with self.assertRaises(ValueError):
                audit.load_json_method(root, config, 120)
        self.assertEqual(len(loaded), 3)
        self.assertTrue(all(not r["errors"] for r in loaded))
        self.assertFalse(any(r["objective"] == "finsteps123" for r in loaded))

    def test_rejects_unknown_duplicate_or_altered_selection(self):
        original = fixture()
        for names in (["origA1", "origA1"], ["missing"], ["origA1"]):
            manifest = copy.deepcopy(original)
            manifest["instances_by_objective"]["cont"] = names
            with self.assertRaises(ValueError):
                focus.validate_manifest(manifest)

    def test_gain_and_loss_are_both_reported_without_claiming_full_coverage(self):
        manifest = fixture()
        result = focus.comparison(manifest, records(manifest, {("cont", "origA1")}), 120)
        best = result["comparisons"][0]
        self.assertEqual(best["gained"]["cont"], ["origA1"])
        self.assertEqual(best["lost"]["cont"], ["origA3"])
        self.assertFalse(result["promising_for_full"])
        self.assertFalse(result["submission_passed"])
        self.assertTrue(result["full_validation_required"])

    def test_gain_at_120_can_request_full_but_30_seconds_cannot(self):
        manifest = fixture()
        solved = {(o, n) for o, names in manifest["instances_by_objective"].items() for n in names}
        result = focus.comparison(manifest, records(manifest, solved), 120)
        self.assertTrue(result["promising_for_full"])
        self.assertFalse(focus.comparison(manifest, records(manifest, solved), 30)["promising_for_full"])

    def test_late_proof_is_not_counted_and_missing_rows_or_changed_data_fail(self):
        manifest = fixture()
        solved = {(o, n) for o, names in manifest["instances_by_objective"].items() for n in names}
        source = records(manifest, solved)
        source[0]["solve"]["total_time"] = 120.01
        result = focus.comparison(manifest, source, 120)
        self.assertEqual(sum(result["proven_by_objective"].values()), len(source)-1)
        for malformed in (source[:-1], source+[source[0]]):
            with self.assertRaises(ValueError):
                focus.comparison(manifest, malformed, 120)
        with patch.object(focus, "dataset_hash", return_value="changed"):
            with self.assertRaises(ValueError):
                focus.comparison(manifest, source, 120)

    def test_auditor_keeps_late_proof_raw_but_penalizes_it_as_unsolved(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            row=dict(name="origA1", solves=[dict(status="ok", total_time=120.01,
                                               timeout_seconds=120, cost=1, lb=1, ub=1)])
            for objective in audit.OBJECTIVES:
                (root/f"{objective}.json").write_text(json.dumps([row]))
            with patch.object(audit.journal_audit, "independently_verify_solution", return_value=[]):
                loaded=audit.load_json_method(root, dict(tag="test", kind="exact", instances="origA1"), 120)
            self.assertTrue(all(not r["proven"] and not r["errors"] for r in loaded))
            self.assertTrue(all(r["solve"]["status"] == "ok" for r in loaded))
            self.assertTrue(all(r["par2_seconds"] == 240 for r in audit.summarize(loaded,120)))
