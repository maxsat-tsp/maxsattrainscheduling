import unittest
from compare_search_bounds import Pool,comparison_report,logged_bounds,combine_full


class SearchBoundComparisonTests(unittest.TestCase):
    def pool(self):
        p=Pool([('cont','origA8'),('cont','stationA2')])
        p.add('cont','stationA2',8398,9974,'V17',300,'old-SAT','reported progress')
        p.add('cont','stationA2',9193,9193,'BigM-Gurobi',120,'MIP','verified optimum')
        p.add('cont','origA8',22736,23648,'V17',300,'old-SAT-A8','reported progress')
        p.add('cont','origA8',23143,23143,'BigM-Gurobi',120,'MIP-A8','verified optimum')
        return p

    def test_sat_progress_is_not_mislabeled_as_new_global_bound(self):
        row=dict(objective='cont',name='stationA2',repeat=0,proven=False,lb=9171,ub=9193)
        r=comparison_report([row],self.pool(),2)
        self.assertEqual(r['summary']['sat_bound_improvement_cases'],1)
        self.assertEqual(r['summary']['new_best_bound_cases'],0)
        self.assertFalse(r['complete']);self.assertFalse(r['ranking_eligible'])
        self.assertEqual(r['cases'][0]['ub'],9193)

    def test_optimum_is_counted_before_and_outside_bound_only_progress(self):
        row=dict(objective='cont',name='origA8',repeat=0,proven=True,lb=23143,ub=23143)
        r=comparison_report([row],self.pool(),1)
        self.assertEqual(r['summary']['proven_optimal'],1)
        self.assertEqual(r['summary']['sat_bound_improvement_cases'],0)

    def test_only_explicit_progress_lines_are_imported(self):
        text='Opt { fake_LB=999999 }\n    LB=10\n    EXHAUST LB=11 STEPS=2\nHEUR.FEAS. 23\nHEUR.FEAS. 22\n'
        self.assertEqual(logged_bounds(text),(11,22))

    def test_confirmations_are_not_independent_instances(self):
        row=dict(objective='cont',name='origA8',repeat=1,proven=True,lb=23143,ub=23143)
        r=comparison_report([row],self.pool(),1)
        self.assertEqual(r['summary']['completed_instances'],0)

    def test_conflicting_reference_lb_is_flagged_and_never_used_as_known_bound(self):
        p=Pool([('finsteps123','trackA8')])
        p.add('finsteps123','trackA8',34,34,'V17',300,'SAT34','verified schedule')
        p.records[-1]['upper_witness_verified']=True
        p.add('finsteps123','trackA8',35,35,'BigM-CPLEX',120,'CPLEX35','verified schedule')
        p.records[-1]['upper_witness_verified']=True
        p.check_reference_consistency()
        self.assertEqual(len(p.conflicts),1);self.assertEqual(p.conflicts[0]['reported_lb'],35)
        self.assertIsNone(p.records[1]['lb']);self.assertEqual(p.records[1]['ub'],35)
        self.assertEqual(p.records[1]['excluded_lower_bound'],35)

    def full_fixture(self):
        gain=dict(objective='cont',name='origA8',repeat=0,proven=True,cost=23143)
        baseline=[dict(objective='cont',name='origA8',proven=False),
            dict(objective='infsteps180',name='stationA8',proven=True)]
        hard=dict(complete=True,records=[gain],newly_solved=[gain])
        confirms=[dict(gain,repeat=i) for i in (1,2,3)]
        loss=dict(objective='infsteps180',name='stationA8',repeat=0,proven=False,cost=163)
        return hard,dict(complete=True,records=confirms+[loss]),baseline

    def test_full_coverage_uses_actual_regression_including_losses(self):
        hard,followup,baseline=self.full_fixture()
        records,confirms=combine_full(hard,followup,baseline)
        self.assertEqual(len(records),2);self.assertEqual(sum(r['proven'] for r in records),1)
        self.assertEqual(len(confirms),3)

    def test_full_coverage_rejects_missing_duplicate_or_failed_confirmation(self):
        hard,followup,baseline=self.full_fixture()
        for records in (followup['records'][:-1],followup['records']+[followup['records'][-1]],
                [dict(r,proven=False) if r['repeat']==2 else r for r in followup['records']]):
            with self.assertRaises(ValueError):combine_full(hard,dict(complete=True,records=records),baseline)


if __name__=='__main__':unittest.main()
