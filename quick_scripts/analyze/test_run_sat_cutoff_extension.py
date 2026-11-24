from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_sat_cutoff_extension as extension


class CutoffExtensionTests(unittest.TestCase):
    def test_promotion_requires_every_old_proof_and_a_net_gain(self):
        old = [dict(objective='cont',name=f'instance-{i}',proven=True) for i in range(206)]
        extras = [dict(objective='cont',name=f'new-{i}',proven=True) for i in range(3)]
        profile = dict(threshold_session='reuse-offset-tree',timeout_seconds=600)
        v45 = dict(threshold_session='reuse')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'COMPLETED').touch()
            args = SimpleNamespace(v47=path)
            self.assertEqual(extension.pick_sat(args,old,v45)[2:],('V45',1200))
            (path/'full-evaluation.json').touch()
            for rows, expected in (
                (old,('V45',1200)),
                (old[1:]+extras,('V45',1200)),
                (old+extras[:2],('V47',1200)),
                (old+extras,('V47',600)),
            ):
                with patch.object(extension,'full_sat',return_value=(rows,profile)):
                    self.assertEqual(extension.pick_sat(args,old,v45)[2:],expected)

    def test_a_failed_screening_cannot_start_the_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'COMPLETED').touch()
            (path/'FAILED').touch()
            with self.assertRaisesRegex(ValueError,'clean completion'):
                extension.pick_sat(SimpleNamespace(v47=path),[],{})

    def test_coverage_gate_waits_for_all_measured_controls(self):
        proof = dict(objective='cont',name='case',proven=True,status='ok')
        lock = dict(label='V47',timeout_seconds=1200,methods={
            'SAT':dict(reused=[proof],tasks=[]),
            'BigM-CPLEX':dict(reused=[],tasks=[['cont','case']]),
        })
        measured = {'SAT':[], 'BigM-CPLEX':[]}
        self.assertFalse(extension.report(lock,measured)['beats_all_baselines'])
        measured['BigM-CPLEX'].append(dict(proof,proven=False,status='timeout'))
        self.assertTrue(extension.report(lock,measured)['beats_all_baselines'])
        measured['BigM-CPLEX'][0] = proof
        self.assertFalse(extension.report(lock,measured)['beats_all_baselines'])

    def test_disagreeing_independently_checked_proofs_stop_comparison(self):
        proof = dict(objective='cont',name='case',proven=True,cost=4)
        self.assertEqual(extension.register_optima([proof,dict(proof,proven=False,cost=5)]),
                         {('cont','case'):4})
        with self.assertRaisesRegex(ValueError,'proved optima disagree'):
            extension.register_optima([proof,dict(proof,cost=5)])

    def test_a_600_second_timeout_does_not_complete_a_1200_second_case(self):
        solve = dict(lb=3,ub=5)
        row = dict(solve=solve,errors=[],status='timeout',time=600.1,objective='cont',name='case')
        known = dict(lb=3,ub=5,proven=False)
        self.assertEqual(extension.controls.case_record(None,'CSOnet',row,known)['timeout_seconds'],600)
        with self.assertRaisesRegex(ValueError,'stopped before the measured cutoff'):
            extension.controls.case_record(None,'CSOnet',row,known,1200)
