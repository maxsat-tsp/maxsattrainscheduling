import unittest

from run_long_baseline_cases import first_checked_proofs
from compare_search_bounds import full_comparison


class LongBaselineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.pair = ('cont', 'stationA1')
        self.row = dict(objective=self.pair[0], name=self.pair[1], cost=12884,
            seconds=90, timeout_seconds=120, proven=True, upper_witness_verified=True,
            source='original proof')

    def test_reuse_only_on_time_checked_proofs(self):
        unusable = [dict(self.row,proven=False),dict(self.row,upper_witness_verified=False),
                    dict(self.row,seconds=121)]
        self.assertFalse(first_checked_proofs(unusable,{self.pair}))
        proof = first_checked_proofs([*unusable,self.row],{self.pair})[self.pair]
        self.assertEqual((proof['lb'],proof['ub']), (12884,12884))
        self.assertTrue(proof['reused'])

    def test_conflicting_proofs_cannot_be_merged(self):
        with self.assertRaisesRegex(ValueError,'proof costs disagree'):
            first_checked_proofs([self.row,dict(self.row,cost=12885)],{self.pair})

    def test_a_300_second_reference_does_not_report_600_second_runtime_or_coverage(self):
        rows = [dict(objective=o,name='origA1',cost=11,lb=11,ub=11,proven=True,seconds=12)
                for o in ('finsteps123','infsteps180','cont')]
        report = full_comparison(rows,rows,600,[],baseline_cutoff=300)
        self.assertFalse(report['runtime_comparable'])
        self.assertIsNone(report['summary'][0]['baseline_par2_seconds'])
        self.assertIsNone(report['proof_cutoffs_seconds']['600']['reference'])
        self.assertEqual(report['proof_cutoffs_seconds']['150']['reference']['cont'],1)
