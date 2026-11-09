import unittest
import bound_quality as b


class BoundQualityTests(unittest.TestCase):
    def candidate(self,solved=1,new=0,gap=0.2,time=10,verified=True):
        return dict(proven_total=solved,new_best_bound_cases=new,
            mean_unsolved_relative_gap=gap,par2_sum=time,bounds_verified=verified)

    def test_coverage_precedes_bounds_and_runtime(self):
        a=self.candidate(solved=2,gap=0.9,time=1000)
        z=self.candidate(solved=1,new=20,gap=0.0,time=1)
        self.assertEqual(b.preference(a,z),(True,'optimal_coverage'))
        self.assertLess(b.rank_key(a),b.rank_key(z))

    def test_new_known_bounds_and_gap_precede_time(self):
        a=self.candidate(new=1,gap=0.3,time=1000)
        z=self.candidate(gap=0.1,time=1)
        self.assertEqual(b.preference(a,z),(True,'new_best_bounds'))
        self.assertLess(b.rank_key(a),b.rank_key(z))
        a=self.candidate(gap=0.1,time=1000)
        z=self.candidate(gap=0.2,time=1)
        self.assertEqual(b.preference(a,z),(True,'remaining_bound_gap'))
        self.assertLess(b.rank_key(a),b.rank_key(z))

    def test_time_is_only_a_tiebreak_with_verified_equal_bounds(self):
        a=self.candidate(time=1);z=self.candidate(time=2)
        self.assertEqual(b.preference(a,z),(True,'runtime_after_equal_bounds'))
        a['bounds_verified']=False
        self.assertEqual(b.preference(a,z),(None,'bound_evidence_incomplete'))

    def test_minimization_directions_and_tradeoffs_are_explicit(self):
        r=b.compare(11,19,10,20)
        self.assertTrue(r['lb_improved']);self.assertTrue(r['ub_improved']);self.assertTrue(r['interval_dominates'])
        self.assertEqual((r['lb_gain'],r['ub_gain']),(1,1))
        r=b.compare(11,22,10,20)
        self.assertTrue(r['new_bound']);self.assertTrue(r['tradeoff']);self.assertFalse(r['interval_dominates'])

    def test_known_optimum_is_not_a_new_bound(self):
        r=b.compare(9171,9193,9193,9193)
        self.assertFalse(r['new_bound']);self.assertTrue(r['lb_worse'])
        self.assertAlmostEqual(r['relative_gap'],22/9193)

    def test_integer_rounding_alone_is_not_an_improvement(self):
        r=b.compare(13,20,12.2,20)
        self.assertEqual(r['reference_lb'],13);self.assertFalse(r['lb_improved'])
        self.assertEqual(b.lower(12.000000001),12)

    def test_missing_bounds_are_not_zero_gap(self):
        r=b.summarize([dict(proven=False,lb=None,ub=100,bounds_verified=False)])
        self.assertIsNone(r['mean_unsolved_relative_gap']);self.assertFalse(r['bounds_verified'])
        self.assertEqual(r['unsolved_bounds_missing'],1)
        self.assertFalse(b.compare(10,20,None,None)['new_bound'])

    def test_nonfinite_sentinels_and_crossed_bounds(self):
        self.assertIsNone(b.relative_gap(float('nan'),20))
        self.assertIsNone(b.relative_gap(0,2**31-1))
        with self.assertRaises(ValueError):b.relative_gap(21,20)
        with self.assertRaises(ValueError):b.compare(21,30,10,20)

    def test_reference_pool_never_replaces_candidate_bounds(self):
        e=b.envelope([dict(lb=10,ub=30,source='A'),dict(lb=11,ub=20,source='B')])
        self.assertEqual((e['lb'],e['ub']),(11,20))
        r=b.compare(12,25,e['lb'],e['ub'])
        self.assertEqual((r['lb'],r['ub']),(12,25));self.assertTrue(r['tradeoff'])

    def test_all_solved_needs_no_timeout_gap(self):
        r=b.summarize([dict(proven=True,lb=5,ub=5)])
        self.assertEqual(r['mean_unsolved_relative_gap'],0);self.assertTrue(r['bounds_verified'])


if __name__=='__main__':unittest.main()
