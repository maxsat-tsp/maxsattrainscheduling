import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import inventory_gurobi_reference as inventory
import run_gurobi_reference_tail as tail


class GurobiInventoryTests(unittest.TestCase):
    def row(self,**values):
        return dict(dict(objective='cont',name='origA1',proven=True,seconds=100,
            timeout_seconds=120,upper_witness_verified=True,source='raw'),**values)

    def test_a_fast_checked_proof_can_be_reused_at_the_longer_cutoff(self):
        r=inventory.summarize([self.row(),self.row()],300)
        self.assertEqual(r['total'],1);self.assertNotIn(['cont','origA1'],r['missing_at_cutoff'])

    def test_unproved_or_unverified_incumbents_are_not_optima(self):
        for row in [self.row(proven=False),self.row(upper_witness_verified=False)]:
            self.assertEqual(inventory.summarize([row],120)['total'],0)

    def test_a_late_proof_does_not_increase_coverage_at_an_earlier_cutoff(self):
        r=inventory.summarize([self.row(seconds=301,timeout_seconds=600)],300)
        self.assertEqual(r['total'],0);self.assertIn(['cont','origA1'],r['observed_no_proof_at_cutoff'])

    def test_a_short_timeout_still_needs_a_longer_run(self):
        row=self.row(proven=False,seconds=120)
        self.assertNotIn(['cont','origA1'],inventory.summarize([row],120)['missing_at_cutoff'])
        self.assertIn(['cont','origA1'],inventory.summarize([row],300)['missing_at_cutoff'])

    def test_missing_time_is_not_a_zero_time_proof(self):
        self.assertEqual(inventory.summarize([self.row(seconds=None)],300)['total'],0)
        with self.assertRaises(ValueError):inventory.summarize([],0)


class GurobiTailAuditTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'inventory.json'
        source.write_text(json.dumps(dict(records=[],at_target=dict(missing_at_cutoff=[['cont','origA1']]))))
        reference=tail.ex.REPO/'results/sat_research/v42_sat_bound_search_20261109/full_evaluation.json'
        tail.ex.save(root/'manifest.json',dict(inventory=str(source),inventory_sha256=tail.ex.focus.sha(source),
            dataset_sha256='dataset',tasks=[['cont','origA1']],timeout_seconds=300,
            checked_reference=str(reference),checked_reference_sha256=tail.ex.focus.sha(reference)))
        return source

    def test_changed_inventory_cannot_silently_change_the_run_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=self.fixture(root);source.write_text('{}')
            with patch.object(tail.ex.focus,'dataset_hash',return_value='dataset'):
                with self.assertRaisesRegex(ValueError,'inventory or dataset changed'):tail.audit(root)

    def test_changed_raw_result_fails_before_being_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            case=root/'cases/BigM-Gurobi/cont/origA1';case.mkdir(parents=True)
            (case/'cont.json').write_text('[]');tail.ex.save(case/'completion.json',dict(raw_sha256='changed'))
            with patch.object(tail.ex.focus,'dataset_hash',return_value='dataset'):
                with self.assertRaisesRegex(ValueError,'changed Gurobi tail result'):tail.audit(root)

    def test_milp_claims_are_checked_against_proved_bounds_and_feasible_incumbents(self):
        ref=dict(proven=True,lb=161,ub=161,cost=161)
        tail.checked_bounds(dict(proven=True,solve=dict(lb=161,ub=161,cost=161)),ref)
        for solve in [dict(lb=162,ub=162,cost=162),dict(lb=162,ub=170),dict(lb=150,ub=160)]:
            with self.assertRaisesRegex(ValueError,'contradict'):tail.checked_bounds(dict(proven=False,solve=solve),ref)


if __name__=='__main__':unittest.main()
