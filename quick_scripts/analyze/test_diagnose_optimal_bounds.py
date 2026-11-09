import copy
import json
from pathlib import Path
import tempfile
import unittest

import diagnose_optimal_bounds as diag


class BoundDiagnosticAuditTests(unittest.TestCase):
    def fixture(self):
        rows=json.loads((diag.ex.REPO/'results/conferences/MaxsatScDefault_cont.json').read_text())
        row=next(r for r in rows if r['name']=='origA1')
        solve=copy.deepcopy(row['solves'][0])
        solve.update(solver_name='BigMLazy',status='ok',process_exit_code=0)
        return dict(name='origA1',solves=[solve])

    def oracle(self):
        row=self.fixture();solve=row['solves'][0]
        return dict(objective='cont',name='origA1',optimum=solve['cost'],solution=solve['solution'])

    def record(self, mode):
        oracle=self.oracle();cost=oracle['optimum']
        decision=mode in ('at-opt','below-opt')
        return dict(schema='bound-diagnostic-v1',mode=mode,objective='cont',oracle_optimum=cost,
            submission_eligible=False,diagnostic_only=True,timeout_seconds=300,
            maxsat_backend='minisat',maxsat_backend_signature='MiniSAT v2.1.0',
            maxsat_assumptions='legacy',maxsat_sparse_costs=False,maxsat_objective_bound=decision,
            maxsat_resource_orders=True,maxsat_order_transitivity=True,
            maxsat_core_minimize_checks=4,maxsat_core_minimize_conflicts=100,
            maxsat_core_exhaust_checks=4,maxsat_core_trim_checks=0,maxsat_am1_checks=0,
            diagnostic_target=cost-(mode=='below-opt') if decision else None,
            diagnostic_supplied_ub=cost if mode=='oracle-ub' else None,
            status='unsat' if mode=='below-opt' else 'sat' if decision else 'optimal',
            diagnostic_outcome='unsat' if mode=='below-opt' else 'sat',seconds=1.0,
            cost=cost,solution=oracle['solution'],lb=cost,ub=cost,maxsat_core_literals=0)

    def test_oracle_requires_an_independently_valid_schedule_and_matching_bounds(self):
        row=self.fixture()
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'cont.json'
            path.write_text(json.dumps([row]))
            result=diag.mip_oracles({'cont':['origA1']},[('cont',path)])
            self.assertEqual(result[0]['optimum'],row['solves'][0]['cost'])
            row['solves'][0]['lb']-=1
            path.write_text(json.dumps([row]))
            with self.assertRaisesRegex(ValueError,'proved optimum'):
                diag.mip_oracles({'cont':['origA1']},[('cont',path)])
            row=self.fixture();row['solves'][0]['solution'][0][0]=-1000000
            path.write_text(json.dumps([row]))
            with self.assertRaises(ValueError):diag.mip_oracles({'cont':['origA1']},[('cont',path)])

    def test_duplicate_names_and_unknown_solver_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'cont.json';row=self.fixture()
            path.write_text(json.dumps([row,row]))
            with self.assertRaisesRegex(ValueError,'duplicate'):
                diag.mip_oracles({'cont':['origA1']},[('cont',path)])
            row['solves'][0]['solver_name']='MaxSatDddLadderSc'
            path.write_text(json.dumps([row]))
            with self.assertRaisesRegex(ValueError,'Big-M'):
                diag.mip_oracles({'cont':['origA1']},[('cont',path)])

    def test_only_maxsat_unresolved_cases_are_selected(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'cont.json';path.write_text(json.dumps([self.fixture()]))
            with self.assertRaisesRegex(ValueError,'no unresolved'):
                diag.mip_oracles({'cont':['stationA2']},[('cont',path)])

    def test_all_four_results_have_distinct_semantics(self):
        for mode in diag.MODES:
            report=diag.check_result(self.record(mode),self.oracle(),mode,300)
            self.assertEqual(report['mode'],mode)
        record=self.record('at-opt');record['status']='unsat'
        with self.assertRaisesRegex(ValueError,'unexpected'):
            diag.check_result(record,self.oracle(),'at-opt',300)
        record=self.record('below-opt');record['status']='sat'
        with self.assertRaisesRegex(ValueError,'unexpected'):
            diag.check_result(record,self.oracle(),'below-opt',300)

    def test_oracle_results_cannot_enter_coverage_or_change_configuration(self):
        for field,value in [('submission_eligible',True),('diagnostic_only',False),
            ('diagnostic_target',0),('maxsat_backend','cadical'),('maxsat_core_exhaust_checks',0)]:
            record=self.record('at-opt');record[field]=value
            with self.assertRaises(ValueError):diag.check_result(record,self.oracle(),'at-opt',300)

    def test_closed_bounds_and_schedule_are_rechecked(self):
        for field,value in [('lb',0),('ub',0),('cost',0),('solution',[])]:
            record=self.record('oracle-ub');record[field]=value
            with self.assertRaises(ValueError):diag.check_result(record,self.oracle(),'oracle-ub',300)

    def test_timeout_requires_actual_deadline(self):
        record=self.record('at-opt');record.update(status='timeout',seconds=300.01)
        self.assertEqual(diag.check_result(record,self.oracle(),'at-opt',300)['status'],'timeout')
        record['seconds']=2
        with self.assertRaisesRegex(ValueError,'before'):
            diag.check_result(record,self.oracle(),'at-opt',300)


if __name__=='__main__':unittest.main()
