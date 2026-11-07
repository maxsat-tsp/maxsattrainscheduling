import copy
import unittest

from compare_targeted_backends import compare_pair


class BackendComparisonTests(unittest.TestCase):
    def pair(self):
        mini = dict(definition=dict(backend='minisat', core_minimize_conflicts='0'), backend_override='minisat',
                    measurement_context='paired-screen', paired_run_id='v28', cpu_affinity=[0, 1, 4, 5],
                    binary_sha256='frozen', timeout_seconds=300)
        cadi = dict(mini, definition=dict(mini['definition'], backend='cadical'),
                    backend_override='cadical', cpu_affinity=[2, 3, 6, 7])
        report = dict(audit_passed=True, errors=[], expected_runs=4, completed_runs=4, complete=True,
                      newly_solved=[], summary=[dict(par2_seconds=600, instances=4)])
        return mini, cadi, copy.deepcopy(report), copy.deepcopy(report)

    def test_equal_timeout_screens_tie_without_a_speedup_or_submission_claim(self):
        result = compare_pair(*self.pair())
        self.assertEqual(result['winner_on_this_screen'], 'tie')
        self.assertIsNone(result['cadical_paired_geomean_speedup'])
        self.assertFalse(result['submission_passed'])

    def test_coverage_precedes_runtime_and_shared_solved_times_are_paired(self):
        mini, cadi, a, b = self.pair()
        gain = dict(objective='infsteps180', name='trackA11', cost=98, seconds=10)
        a['newly_solved'] = [gain]; b['newly_solved'] = [dict(gain, seconds=20), dict(gain, name='trackA12', cost=104)]
        a['summary'][0]['par2_seconds'] = 1
        result = compare_pair(mini, cadi, a, b)
        self.assertEqual(result['winner_on_this_screen'], 'cadical')
        self.assertEqual(result['cadical_paired_geomean_speedup'], .5)
        self.assertEqual(result['only_cadical'], [dict(objective='infsteps180', name='trackA12')])

    def test_partial_screens_cannot_declare_a_winner_or_missing_cases_as_losses(self):
        mini, cadi, a, b = self.pair(); a.update(complete=False, completed_runs=1)
        b['newly_solved'] = [dict(objective='infsteps180', name='trackA11', cost=98, seconds=2)]
        result = compare_pair(mini, cadi, a, b)
        self.assertFalse(result['complete']); self.assertIsNone(result['winner_on_this_screen'])
        self.assertEqual(result['only_minisat'], []); self.assertEqual(result['only_cadical'], [])

    def test_mismatched_config_binary_or_cpu_groups_are_rejected(self):
        for change in [dict(binary_sha256='other'), dict(timeout_seconds=600), dict(cpu_affinity=[0, 1]),
                       dict(paired_run_id='other'), dict(definition=dict(backend='cadical', core_minimize_conflicts='100'))]:
            mini, cadi, a, b = self.pair(); cadi.update(change)
            with self.assertRaises(ValueError): compare_pair(mini, cadi, a, b)

    def test_disagreeing_optimal_costs_or_unchecked_reports_fail(self):
        mini, cadi, a, b = self.pair()
        gain = dict(objective='infsteps180', name='trackA11', cost=98, seconds=10)
        a['newly_solved'] = [gain]; b['newly_solved'] = [dict(gain, cost=99)]
        with self.assertRaisesRegex(ValueError, 'optima'): compare_pair(mini, cadi, a, b)
        mini, cadi, a, b = self.pair(); a['audit_passed'] = False
        with self.assertRaisesRegex(ValueError, 'audited'): compare_pair(mini, cadi, a, b)


if __name__ == '__main__':
    unittest.main()
