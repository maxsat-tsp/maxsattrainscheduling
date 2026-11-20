import unittest
import json
from pathlib import Path
import tempfile

from run_long_baseline_cases import checked_case, first_checked_proofs
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

    def test_watchdog_censoring_requires_boundary_and_clean_process_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            logs = case/'logs'
            (logs/'instances').mkdir(parents=True)
            lock = dict(binary_sha256='test hash',runner_commit='test source')
            (logs/'manifest.txt').write_text('\n'.join(f'{k}={v}' for k,v in dict(
                binary_sha256=lock['binary_sha256'],git_commit=lock['runner_commit'],
                solver='maxsat_ddd',objective='cont',selected_instances='stationA1',
                selected_instance_count=1,instance_timeout_seconds=600,ram_limit_kb=6000000,
                timeout_binary='/usr/bin/timeout',timeout_binary_sha256='timeout hash',
                external_timeout_grace_seconds=20,external_timeout_seconds=620).items()))
            stderr = logs/'stationA1.stderr.log'
            stderr.write_text('')
            (logs/'stationA1.stdout.log').write_text('')
            raw = dict(status='external_timeout',external_status='external_timeout',solver_name='maxsat_ddd',
                      process_exit_code=124,total_time=620.01,timeout_seconds=600,process_wall_time_seconds=620.01)
            def write(data):
                payload = json.dumps([dict(name='stationA1',solves=[data])])
                (case/'cont.json').write_text(payload)
                (logs/'instances/stationA1.json').write_text(payload)
            write(raw)
            row = checked_case(case,'MaxSAT-Journal','cont','stationA1',lock,{})
            self.assertFalse(row['proven'])
            self.assertIsNone(row['ub'])
            for bad in (dict(process_exit_code=137),dict(total_time=619,process_wall_time_seconds=619),
                        dict(cost=12884)):
                write(dict(raw, **bad))
                with self.assertRaisesRegex(ValueError,'external timeout'):
                    checked_case(case,'MaxSAT-Journal','cont','stationA1',lock,{})
            write(raw)
            stderr.write_text('thread panicked at risk')
            with self.assertRaisesRegex(ValueError,'external timeout'):
                checked_case(case,'MaxSAT-Journal','cont','stationA1',lock,{})
