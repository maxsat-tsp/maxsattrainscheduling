import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import targeted_order_cycles as cycles
import extended_timeout_experiments as extended

class CycleTrialTests(unittest.TestCase):
    def test_initial_cost_changes_one_component_without_enabling_cycles(self):
        source=dict(definition=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4'))
        config=cycles.candidate_config(source,'initial-cost')
        self.assertEqual(config,dict(source['definition'],extract_initial_cost='true'))
        self.assertNotIn('order_cycle_cuts',config)
        self.assertEqual(cycles.schema_for('initial-cost'),'targeted-initial-cost-v1')
        self.assertEqual(cycles.report_name('initial-cost'),'initial_cost_audit.json')
        with self.assertRaises(ValueError):cycles.candidate_config(source,'unsupported')

    def test_initial_cost_flag_is_forwarded_and_audited(self):
        config=dict(extended.METHODS['Orders-Transitive'],extract_initial_cost='true')
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);args=SimpleNamespace(binary=root/'ddd',timeout=300,ram_kb=6000000,method_definitions={'test':config})
            with patch.object(extended,'execute') as execute:
                extended.run_case('test','cont','origA1',args,root)
                self.assertEqual(execute.call_args.args[4]['MAXSATDDD_EXTRACT_INITIAL_COST'],'true')
            solve=dict(status='timeout',total_time=300,timeout_seconds=300,process_exit_code=0)
            solve.update({'maxsat_'+k:v for k,v in config.items() if k not in ('solver','kind')})
            extended.save(root/'cont.json',[dict(name='origA1',solves=[solve])])
            self.assertFalse(extended.assess_case(root,'test','cont','origA1',300,config)['errors'])
            solve['maxsat_extract_initial_cost']=False;extended.save(root/'cont.json',[dict(name='origA1',solves=[solve])])
            self.assertIn('maxsat_extract_initial_cost differs from the locked configuration',extended.assess_case(root,'test','cont','origA1',300,config)['errors'])

    def test_only_the_cycle_component_changes(self):
        source=dict(definition=dict(extended.METHODS['Orders-Transitive'],core_minimize_checks='4',core_minimize_conflicts='100',core_exhaust_checks='4'))
        before=copy.deepcopy(source);config=cycles.candidate_config(source)
        self.assertEqual(source,before);self.assertEqual(config,dict(source['definition'],order_cycle_cuts='true'))
        with self.assertRaises(ValueError):cycles.candidate_config(dict(definition=config))
        with self.assertRaises(ValueError):cycles.candidate_config(dict(definition=dict(config,resource_orders='false')))

    def test_cycle_flag_is_forwarded_and_checked_in_returned_data(self):
        config=dict(extended.METHODS['Orders-Transitive'],order_cycle_cuts='true')
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);args=SimpleNamespace(binary=root/'ddd',timeout=300,ram_kb=6000000,method_definitions={'test':config})
            with patch.object(extended,'execute') as execute:
                extended.run_case('test','cont','origA1',args,root)
                self.assertEqual(execute.call_args.args[4]['MAXSATDDD_ORDER_CYCLE_CUTS'],'true')
            solve=dict(status='timeout',total_time=300,timeout_seconds=300,process_exit_code=0)
            solve.update({'maxsat_'+k:v for k,v in config.items() if k not in ('solver','kind')})
            extended.save(root/'cont.json',[dict(name='origA1',solves=[solve])])
            self.assertFalse(extended.assess_case(root,'test','cont','origA1',300,config)['errors'])
            solve['maxsat_order_cycle_cuts']=False;extended.save(root/'cont.json',[dict(name='origA1',solves=[solve])])
            self.assertIn('maxsat_order_cycle_cuts differs from the locked configuration',extended.assess_case(root,'test','cont','origA1',300,config)['errors'])

    def test_reference_selection_uses_actual_status_and_rejects_changed_receipts(self):
        with tempfile.TemporaryDirectory() as raw,patch.object(extended.common,'EXPECTED_NAMES',['origA1','origA2']):
            root=Path(raw);config=extended.METHODS['Orders-Transitive']
            selection={o:['origA1','origA2'] for o in extended.audit.OBJECTIVES};records=[]
            manifest=dict(schema='completed-core-full-v1',instances_by_objective=selection,timeout_seconds=300,
                definition=config,binary_sha256='binary',dataset_sha256=extended.focus.dataset_hash())
            extended.save(root/'manifest.json',manifest)
            for o,names in selection.items():
                for n in names:
                    case=root/'cases'/o/n;case.mkdir(parents=True)
                    extended.save(case/f'{o}.json',[dict(name=n,solves=[dict(status='timeout')])])
                    extended.save(case/'measurement.json',dict(raw_sha256=extended.focus.sha(case/f'{o}.json'),binary_sha256='binary',definition=config))
                    records.append(dict(objective=o,name=n,status='timeout',proven=False,time=300,solve={},tag='Core-E4-full216',errors=[]))
            report=dict(complete=True,errors=[],completed_runs=6,expected_runs=6,case_bounds=[dict(objective=r['objective'],name=r['name'],status=r['status'],proven=False,seconds=300,cost=None,lb=None,ub=None) for r in records],summary=extended.audit.summarize(records,300))
            extended.save(root/'full_audit.json',report)
            with patch.object(extended,'assess_case',side_effect=records):
                self.assertEqual(cycles.load_reference(root)[1],selection)
            case=root/'cases'/'cont'/'origA2';extended.save(case/'measurement.json',dict(raw_sha256='changed',binary_sha256='binary',definition=config))
            with patch.object(extended,'assess_case',side_effect=records):
                with self.assertRaisesRegex(ValueError,'receipt'):cycles.load_reference(root)

    def test_unresolved_scope_never_claims_full_submission_success(self):
        record=dict(objective='cont',name='origA1',proven=True,time=1,solve=dict(cost=3),tag='Order-Cycles')
        result=cycles.report_for([record],[('cont','origA1'),('cont','origA2')],300)
        self.assertFalse(result['complete']);self.assertFalse(result['submission_passed'])
        self.assertEqual(result['newly_solved'][0]['cost'],3)

if __name__=='__main__':unittest.main()
