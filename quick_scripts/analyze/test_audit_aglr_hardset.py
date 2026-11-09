import copy
import tempfile
import unittest
from pathlib import Path

import audit_aglr_hardset as hardset


class ExternalTimeoutAuditTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(solver='maxsat_ddd_ladder_sc', assumptions='legacy', backend='minisat')
        self.record = dict(objective='cont', name='origA8', status='external_timeout',
            proven=False, solve=dict(process_exit_code=124, process_wall_time_seconds=330.1),
            errors=['nonzero process exit 124',
                    'maxsat_assumptions differs from the locked configuration',
                    'maxsat_backend differs from the locked configuration'])

    def manifest(self, root):
        path = root / 'cont.logs' / 'manifest.txt'
        path.parent.mkdir()
        path.write_text('solver=maxsat_ddd_ladder_sc\nobjective=cont\n'
            'instance_timeout_seconds=300\nexternal_timeout_seconds=330\n'
            'selected_instances=origA8\nmaxsatddd_assumptions=legacy\nmaxsatddd_backend=minisat\n')
        return path

    def test_missing_telemetry_requires_matching_launch_and_timeout(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            self.assertTrue(hardset.checked_timeout_record(self.record,root,self.config,300)['errors'])
            self.manifest(root)
            result=hardset.checked_timeout_record(self.record,root,self.config,300)
            self.assertEqual(result['errors'],[])
            self.assertTrue(result['external_timeout_launch_verified'])
            self.assertFalse(result['proven'])

    def test_present_wrong_backend_is_not_suppressed(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); self.manifest(root)
            record=copy.deepcopy(self.record)
            record['solve']['maxsat_backend']='cadical'
            result=hardset.checked_timeout_record(record,root,self.config,300)
            self.assertIn('maxsat_backend differs from the locked configuration',result['errors'])

    def test_mismatched_launch_fails(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); path=self.manifest(root)
            path.write_text(path.read_text().replace('backend=minisat','backend=cadical'))
            self.assertTrue(hardset.checked_timeout_record(self.record,root,self.config,300)['errors'])

    def test_early_exit_is_not_an_external_timeout(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); self.manifest(root)
            record=copy.deepcopy(self.record); record['solve']['process_wall_time_seconds']=1
            self.assertTrue(hardset.checked_timeout_record(record,root,self.config,300)['errors'])

    def test_panic_and_other_errors_are_preserved(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); self.manifest(root)
            record=copy.deepcopy(self.record); record['errors'].append('duplicate instance name')
            result=hardset.checked_timeout_record(record,root,self.config,300)
            self.assertIn('duplicate instance name',result['errors'])
            record['status']='panic'; record['solve']['process_exit_code']=101
            self.assertEqual(hardset.checked_timeout_record(record,root,self.config,300),record)

