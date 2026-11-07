import unittest
from unittest.mock import patch
from pathlib import Path
import confirm_component_gains as follow

class FollowupTests(unittest.TestCase):
    def test_objective_filtered_gain_regresses_only_the_declared_scope(self):
        source=dict(objective_filter=['infsteps180'],instances_by_objective=dict(finsteps123=[],infsteps180=['trackA11'],cont=[]))
        gain=dict(objective='infsteps180',name='trackA11',cost=7,seconds=10)
        report=dict(complete=True,audit_passed=True,errors=[],newly_solved=[gain])
        solved=[dict(objective='cont',name='origA1',cost=5),dict(objective='infsteps180',name='origA1',cost=3)]
        with patch.object(follow,'reference_costs',return_value=({},solved)):
            _,confirmations,regressions=follow.plan_for(source,report,Path('unused'))
        self.assertEqual(len(confirmations),3)
        self.assertEqual(regressions,[dict(stage='regression',repeat=0,**solved[1])])
        manifest=dict(schema='test',selected_gains=[gain],confirmation_plan=confirmations,regression_plan=regressions,
            objective_filter=['infsteps180'])
        completed=[dict(task,retained=True) for task in confirmations+regressions]
        result=follow.report_for(manifest,completed)
        self.assertTrue(result['confirmed']);self.assertTrue(result['regression_passed'])
        self.assertFalse(result['full_reference_regression']);self.assertFalse(result['submission_passed'])

    def test_plan_contains_three_repeats_and_only_previously_solved_regressions(self):
        source=dict(instances_by_objective=dict(cont=['origA1'],infsteps180=[],finsteps123=[]))
        gain=dict(objective='cont',name='origA1',cost=7,seconds=10)
        report=dict(complete=True,audit_passed=True,errors=[],newly_solved=[gain])
        solved=[dict(objective='cont',name='origA2',cost=5)]
        with patch.object(follow,'reference_costs',return_value=({},solved)):
            gains,confirmation,regression=follow.plan_for(source,report,Path('unused'))
        self.assertEqual(gains,[gain]);self.assertEqual([t['repeat'] for t in confirmation],[1,2,3])
        self.assertTrue(all(t['cost']==7 for t in confirmation));self.assertEqual(regression,[dict(stage='regression',repeat=0,**solved[0])])
        with self.assertRaises(ValueError):follow.plan_for(source,dict(report,complete=False),Path('unused'))
        with self.assertRaises(ValueError):follow.plan_for(source,dict(report,newly_solved=[gain,gain]),Path('unused'))

    def test_empty_trial_does_not_claim_confirmation_or_submission(self):
        manifest=dict(schema='test',selected_gains=[],confirmation_plan=[],regression_plan=[dict(name='old')])
        report=follow.report_for(manifest,[])
        self.assertTrue(report['complete']);self.assertFalse(report['confirmed']);self.assertFalse(report['regression_passed']);self.assertFalse(report['submission_passed'])

    def test_partial_or_failed_confirmations_cannot_pass_the_regression_gate(self):
        manifest=dict(schema='test',selected_gains=[dict(name='new')],confirmation_plan=[{}]*3,regression_plan=[{}])
        record=dict(stage='confirmation',repeat=1,objective='cont',name='new',retained=True)
        report=follow.report_for(manifest,[record]);self.assertFalse(report['confirmed']);self.assertFalse(report['complete'])
        records=[dict(record,repeat=i,retained=i!=2) for i in [1,2,3]]
        report=follow.report_for(manifest,records);self.assertFalse(report['confirmed']);self.assertFalse(report['regression_passed'])
        self.assertEqual(report['confirmation_failures'],[dict(repeat=2,objective='cont',name='new')])

    def test_loss_is_reported_even_after_all_gains_reproduce(self):
        manifest=dict(schema='test',selected_gains=[dict(name='new')],confirmation_plan=[{}]*3,regression_plan=[{}])
        records=[dict(stage='confirmation',repeat=i,objective='cont',name='new',retained=True) for i in [1,2,3]]
        records.append(dict(stage='regression',repeat=0,objective='cont',name='old',retained=False))
        report=follow.report_for(manifest,records);self.assertTrue(report['confirmed']);self.assertTrue(report['complete'])
        self.assertFalse(report['regression_passed']);self.assertEqual(report['lost'],[dict(objective='cont',name='old')])
        self.assertFalse(report['submission_passed'])

if __name__=='__main__':unittest.main()
