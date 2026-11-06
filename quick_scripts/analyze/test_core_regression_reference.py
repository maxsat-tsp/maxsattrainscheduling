import copy,json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core_regression_reference as regression
import extended_timeout_experiments as extended


class CoreRegressionReferenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"regression";self.reference=Path(temp.name)/"reference"
        self.root.mkdir();self.reference.mkdir()
        extended.save(self.reference/"manifest.json",dict(plan=dict(timeout_seconds=300)))
        extended.save(self.reference/"backend_comparison.json",{})
        cfg=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100')
        self.selected=dict(definition=cfg,binary_sha256='binary',solver_source_commit='source',
            dataset_sha256=extended.focus.dataset_hash(),ram_kb=6000000,cpu_affinity=[0,1,4,5])
        selection=[dict(objective='cont',name='origA1',cost=5526)]
        self.manifest=dict(self.selected,schema='v16-solved-case-regression-v1',runner_commit='runner',
            selected_trial_manifest_sha256='chosen',reference_manifest_sha256=extended.focus.sha(self.reference/'manifest.json'),
            reference_report_sha256=extended.focus.sha(self.reference/'backend_comparison.json'),
            timeout_seconds=300,selection=selection)
        extended.save(self.root/'manifest.json',self.manifest)
        case=self.root/'cases/cont/origA1';(case/'logs').mkdir(parents=True);self.case=case
        solve=dict(status='timeout',total_time=300,timeout_seconds=300,process_exit_code=0)
        solve.update({'maxsat_'+k:v for k,v in cfg.items() if k not in ('solver','kind')})
        extended.save(case/'cont.json',[dict(name='origA1',solves=[solve])])
        provenance=dict(git_commit='runner',git_dirty='0',binary_sha256='binary',solver=cfg['solver'],
            selected_instances='origA1',selected_instance_count='1',objective='cont',instance_timeout_seconds='300',ram_limit_kb='6000000')
        provenance.update({'maxsatddd_'+k:v for k,v in cfg.items() if k not in ('solver','kind')})
        (case/'logs/manifest.txt').write_text(''.join(f'{k}={v}\n' for k,v in provenance.items()))
        row=dict(objective='cont',name='origA1',expected_cost=5526,cost=None,status='timeout',proven=False,
                 retained=False,seconds=300,errors=[],sha256=extended.focus.sha(case/'cont.json'))
        self.report=dict(schema=self.manifest['schema'],complete=True,expected_runs=1,completed_runs=1,
                         passed=False,lost=[dict(objective='cont',name='origA1')],cases=[row])
        extended.save(self.root/'regression_audit.json',self.report)
        manager=patch.object(regression.dual,'tasks',return_value=[('minisat','Orders-Transitive','cont','origA1')]);manager.start();self.addCleanup(manager.stop)
        manager=patch.object(regression.dual,'assess',return_value=dict(proven=True,solve=dict(cost=5526)));manager.start();self.addCleanup(manager.stop)

    def audit(self):return regression.audit(self.root,self.reference,self.selected,'chosen')

    def test_valid_timeout_is_returned_as_a_loss_with_frozen_hashes(self):
        lost,evidence=self.audit()
        self.assertEqual(lost,[dict(objective='cont',name='origA1')])
        self.assertEqual(evidence['report_sha256'],extended.focus.sha(self.root/'regression_audit.json'))

    def test_incomplete_or_missing_regression_cannot_select_a_next_round(self):
        extended.save(self.root/'regression_audit.json',dict(self.report,complete=False))
        with self.assertRaisesRegex(ValueError,'finish the regression'):self.audit()
        extended.save(self.root/'regression_audit.json',dict(self.report,completed_runs=0))
        with self.assertRaisesRegex(ValueError,'missing or changing'):self.audit()

    def test_concealed_loss_is_rejected_by_the_raw_result(self):
        report=copy.deepcopy(self.report);report['cases'][0]['retained']=True;report.update(lost=[],passed=True)
        extended.save(self.root/'regression_audit.json',report)
        with self.assertRaisesRegex(ValueError,'ledger differs'):self.audit()

    def test_changed_binary_or_conflict_budget_is_rejected(self):
        for selected in (dict(self.selected,binary_sha256='other'),
                         dict(self.selected,definition=dict(self.selected['definition'],core_minimize_conflicts='1000'))):
            with self.assertRaisesRegex(ValueError,'selected configuration'):
                regression.audit(self.root,self.reference,selected,'chosen')

    def test_changed_raw_bytes_or_case_provenance_is_rejected(self):
        path=self.case/'logs/manifest.txt';original=path.read_text()
        path.write_text(original.replace('binary_sha256=binary','binary_sha256=wrong'))
        with self.assertRaisesRegex(ValueError,'provenance changed'):self.audit()
        path.write_text(original)
        (self.case/'cont.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.audit()
