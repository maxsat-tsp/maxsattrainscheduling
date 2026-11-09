import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_sat_bound_search as search


class SearchAuditTests(unittest.TestCase):
    def fixture(self):
        rows=json.loads((search.ex.REPO/'results/conferences/MaxsatScDefault_cont.json').read_text())
        s=next(r['solves'][0] for r in rows if r['name']=='origA1')
        solution=s['solution'];initial=[[t+1000 for t in train] for train in solution]
        trains=search.ex.common.parse_txt_instance('origA1')
        upper=sum(search.ex.common.delay_cost('cont',time-v['aimed']) for train,times in zip(trains,initial)
            for v,time in zip(train,times) if v['aimed'] is not None)
        search.validate_schedule('origA1','cont',initial,upper)
        lower=search.initial_lower('origA1','cont');initial_lower=lower;initial_upper=upper;queries=[]
        optimum=s['cost']
        while lower<upper:
            target=lower+(upper-lower-1)//2;answer='sat' if target>=optimum else 'unsat'
            q=dict(lower_before=lower,upper_before=upper,target=target,remaining_seconds=299.99-len(queries),
                seconds=1.0,outcome=answer,cost=optimum if answer=='sat' else None,
                solution=solution if answer=='sat' else None,native_sat_calls=1,native_sat_seconds=0.9,
                native_budgeted_calls=0,variables=100,clauses=200,
                threshold_evidence=dict(threshold_target=target,threshold_outcome=answer,
                    maxsat_objective_bound=True,maxsat_resource_orders=True,maxsat_order_transitivity=True,
                    maxsat_sparse_costs=False,maxsat_core_literals=0))
            queries.append(q)
            if answer=='sat':upper=optimum
            else:lower=target+1
        return dict(schema='sat-bound-search-v1',solver_name='SAT-Bisect-Restart',status='ok',
            objective='cont',uses_optimum_oracle=False,maxsat_backend='minisat',
            maxsat_backend_signature='MiniSAT v2.1.0',timeout_seconds=300,total_time=len(queries)+0.2,
            lb=lower,ub=upper,cost=upper,solution=solution,initial_lb=initial_lower,
            initial_ub=initial_upper,initial_solution=initial,queries=queries)

    def test_replays_all_proofs_and_independently_checks_incumbents(self):
        result=self.fixture();row,trace=search.check_result(result,'origA1','cont',300,5526)
        self.assertTrue(row['proven']);self.assertEqual(row['cost'],5526)
        self.assertEqual(trace[-1]['lb'],trace[-1]['ub'])

    def test_lower_bound_must_be_computed_from_input(self):
        result=self.fixture();result['initial_lb']=5526
        with self.assertRaisesRegex(ValueError,'input-only'):search.check_result(result,'origA1','cont',300)

    def test_wrong_threshold_or_witness_is_rejected(self):
        for field,value in [('target',0),('cost',0),('solution',[])]:
            result=self.fixture();result['queries'][0][field]=value
            with self.assertRaises(ValueError):search.check_result(result,'origA1','cont',300)

    def test_budget_cannot_be_reset_for_each_query(self):
        result=self.fixture();result['queries'][1]['remaining_seconds']=300
        with self.assertRaisesRegex(ValueError,'budget'):search.check_result(result,'origA1','cont',300)

    def test_unknown_does_not_change_either_bound(self):
        result=self.fixture();q=result['queries'][0]
        q.update(outcome='unknown',cost=None,solution=None,seconds=300)
        q['threshold_evidence'].pop('threshold_outcome');result.update(queries=[q],status='timeout',total_time=300.01,
            lb=result['initial_lb'],ub=result['initial_ub'],cost=result['initial_ub'],solution=result['initial_solution'])
        self.assertFalse(search.check_result(result,'origA1','cont',300)[0]['proven'])
        bad=copy.deepcopy(result);bad['lb']+=1
        with self.assertRaisesRegex(ValueError,'replay'):search.check_result(bad,'origA1','cont',300)
        bad=copy.deepcopy(result);bad['queries'].append(q)
        with self.assertRaisesRegex(ValueError,'UNKNOWN'):search.check_result(bad,'origA1','cont',300)

    def test_oracle_flags_wrong_backend_and_false_optimality_are_rejected(self):
        for field,value in [('uses_optimum_oracle',True),('maxsat_backend','cadical'),
            ('lb',5525),('total_time',301)]:
            result=self.fixture();result[field]=value
            with self.assertRaises(ValueError):search.check_result(result,'origA1','cont',300)

    def test_unsat_above_a_known_optimum_is_rejected(self):
        result=self.fixture();q=result['queries'][0]
        q.update(outcome='unsat',cost=None,solution=None);q['threshold_evidence']['threshold_outcome']='unsat'
        with self.assertRaisesRegex(ValueError,'contradicts'):search.check_result(result,'origA1','cont',300,5526)

    def test_runner_passes_no_optimum_or_reference_schedule(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);binary=root/'solver';binary.write_bytes(b'fake binary')
            case=root/'case'
            def execute(command,**kwargs):
                (case/'result.json').write_text('{}');(case/'result.trace.jsonl').write_text('')
                self.assertNotIn('--optimum',command);self.assertNotIn('--oracle-schedule',command)
                self.assertEqual(command.count('--timeout'),1)
                return SimpleNamespace(returncode=0)
            with patch.object(search.subprocess,'run',side_effect=execute):
                search.run_case(binary,300,6000000,'commit',case,'cont','origA1',0)

    def test_audit_rejects_wrong_build_and_duplicate_tasks_before_results(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);reference=root/'reference';reference.mkdir()
            (reference/'manifest.json').write_text('{}')
            build=dict(git_commit='source',binary_sha256='binary')
            (root/'build_manifest.json').write_text(json.dumps(build))
            task=dict(objective='cont',name='origA8',repeat=0)
            manifest=dict(schema='sat-bound-search-campaign-v1',uses_optimum_oracle=False,
                dataset_sha256='dataset',reference_manifest_sha256=search.ex.focus.sha(reference/'manifest.json'),
                build_manifest_sha256=search.ex.focus.sha(root/'build_manifest.json'),commit='source',
                binary_sha256='wrong',tasks=[task])
            (root/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(search.ex.focus,'dataset_hash',return_value='dataset'):
                with self.assertRaisesRegex(ValueError,'build evidence'):search.audit(root,reference)
                manifest.update(binary_sha256='binary',tasks=[task,task])
                (root/'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'duplicate'):search.audit(root,reference)


if __name__=='__main__':unittest.main()
