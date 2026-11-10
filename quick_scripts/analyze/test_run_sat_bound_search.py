import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_sat_bound_search as search


class SearchAuditTests(unittest.TestCase):
    def polished_fixture(self):
        r=self.fixture('upper');r['incumbent_polish_checks']=4096
        for q in r['queries']:
            if q['outcome']=='sat':q['polish']=dict(source_cost=q['cost'],source_solution=q['solution'],
                retimed_cost=q['cost'],checks=10,accepted_moves=0,seconds=0.1)
        return r

    def test_polished_witness_is_independently_checked_and_budgeted(self):
        r=self.polished_fixture();row,_=search.check_result(r,'origA1','cont',300,5526)
        self.assertTrue(row['proven']);self.assertEqual(row['incumbent_polish_checks'],4096)

    def test_polishing_cannot_fabricate_an_original_sat_witness(self):
        r=self.polished_fixture();q=next(q for q in r['queries'] if q['outcome']=='sat')
        q['polish']['source_cost']+=1
        with self.assertRaises(ValueError):search.check_result(r,'origA1','cont',300,5526)

    def test_polishing_must_be_requested_and_evidenced(self):
        for mutate in [lambda r:r.update(incumbent_polish_checks=0),
                       lambda r:r.update(incumbent_polish_checks=True),
                       lambda r:r.update(incumbent_polish_checks=-1),
                       lambda r:[q.pop('polish',None) for q in r['queries']]]:
            r=self.polished_fixture();mutate(r)
            with self.assertRaises(ValueError):search.check_result(r,'origA1','cont',300,5526)

    def test_polishing_cannot_change_a_lower_bound_or_an_unknown_answer(self):
        r=self.polished_fixture();q=r['queries'][-1];self.assertEqual(q['outcome'],'unsat')
        q['polish']=r['queries'][0]['polish']
        with self.assertRaisesRegex(ValueError,'without a SAT witness'):search.check_result(r,'origA1','cont',300,5526)
        q['outcome']='unknown'
        with self.assertRaisesRegex(ValueError,'without a SAT witness'):search.check_result(r,'origA1','cont',300,5526)

    def test_polishing_limits_cost_and_shared_time_are_enforced(self):
        for update in [dict(checks=4097),dict(checks=True),dict(accepted_moves=11),
                       dict(seconds=1.01),dict(seconds=float('nan')),dict(retimed_cost=0)]:
            r=self.polished_fixture();next(q for q in r['queries'] if q['outcome']=='sat')['polish'].update(update)
            with self.assertRaises(ValueError):search.check_result(r,'origA1','cont',300,5526)

    def test_full_search_cannot_mix_polished_and_unpolished_configurations(self):
        a={k:0 for k in ('commit','binary_sha256','build_manifest_sha256','dataset_sha256','timeout_seconds','ram_kb','cpu_affinity')}
        with self.assertRaisesRegex(ValueError,'mixes methods'):search.same_method(dict(a,incumbent_polish_checks=4096),a)

    def warm_fixture(self,optimal=True):
        r=self.fixture();schedule=r['solution'];cost=r['cost']
        evidence=dict(aglr_policy='legacy',maxsat_assumptions='legacy',maxsat_resource_orders=True,
            maxsat_order_transitivity=True,maxsat_sparse_costs=False,maxsat_objective_bound=False,
            maxsat_extract_initial_cost=False,maxsat_residual_hardening=False,maxsat_order_master=False,
            maxsat_core_minimize_checks=4,maxsat_core_minimize_conflicts=100,maxsat_core_exhaust_checks=4,
            maxsat_core_trim_checks=0,maxsat_am1_checks=0,maxsat_order_cycle_cuts=False,maxsat_order_path_cuts=False)
        checkpoints=[dict(seconds=0.1,lb=0,ub=r['initial_ub'],cost=r['initial_ub'],solution=r['initial_solution'])]
        if optimal:checkpoints.append(dict(seconds=0.5,lb=cost,ub=cost,cost=cost,solution=schedule))
        warm=dict(status='optimal' if optimal else 'timeout',budget_seconds=30,seconds=1 if optimal else 30,
            lower_before=r['initial_lb'],upper_before=r['initial_ub'],
            lb=cost if optimal else r['initial_lb'],ub=cost if optimal else r['initial_ub'],
            solution=schedule if optimal else r['initial_solution'],checkpoints=checkpoints,native_sat_calls=3,evidence=evidence)
        if optimal:
            evidence.update(lb=cost,ub=cost);r.update(queries=[],total_time=1.2)
        else:r['total_time']+=30
        r.update(solver_name='RC2-Warm-'+r['solver_name'],rc2_warmup_seconds=30,warmup=warm)
        return r

    def test_warmup_can_prove_optimality_without_any_threshold_query(self):
        r=self.warm_fixture();row,trace=search.check_result(r,'origA1','cont',300,5526)
        self.assertTrue(row['proven']);self.assertEqual(row['sat_calls'],3);self.assertEqual(trace,[])

    def test_warmup_witness_checkpoint_and_proof_cannot_be_fabricated(self):
        for mutate in (lambda r:r['warmup']['checkpoints'][-1].update(cost=0),
                       lambda r:r['warmup']['checkpoints'][-1].update(lb=5527),
                       lambda r:r['warmup']['evidence'].update(lb=5525),
                       lambda r:r.update(warmup=None)):
            r=self.warm_fixture();mutate(r)
            with self.assertRaises(ValueError):search.check_result(r,'origA1','cont',300,5526)

    def test_threshold_phase_cannot_get_a_fresh_budget_after_warmup(self):
        r=self.warm_fixture(optimal=False)
        with self.assertRaisesRegex(ValueError,'budget'):search.check_result(r,'origA1','cont',300,5526)
        for q in r['queries']:q['remaining_seconds']-=30
        self.assertTrue(search.check_result(r,'origA1','cont',300,5526)[0]['proven'])

    def test_missing_selection_archive_and_mixed_warmup_methods_are_rejected(self):
        from pathlib import Path
        with self.assertRaisesRegex(ValueError,'selection archive'):
            search.baseline_for_manifest(dict(selection_archive='missing.tar.gz',selection_archive_sha256='bad'),Path('.'),None)
        a={k:0 for k in ('commit','binary_sha256','build_manifest_sha256','dataset_sha256','timeout_seconds','ram_kb','cpu_affinity')}
        with self.assertRaisesRegex(ValueError,'mixes methods'):search.same_method(dict(a,rc2_warmup_seconds=30),a)

    def test_previous_full_search_selects_only_its_twelve_unresolved_pairs(self):
        archive=search.ex.REPO/'results/sat_research/v41_sat_bound_search_20261109/complete_snapshot.tar.gz'
        # Membership is checked here; baseline_for_manifest replays the
        # complete raw campaign before using it for an actual selection.
        import tarfile
        with tarfile.open(archive) as t:
            saved=json.load(t.extractfile('evaluation/full_evaluation.json'))
        rows=saved['cases'];selected=search.hard_tasks(None,baseline=rows)
        self.assertEqual(len(selected),12);self.assertEqual(sum(r['proven'] for r in rows),204)
        self.assertIn(('infsteps180','stationA8'),selected)
        self.assertNotIn(('cont','origA8'),selected);self.assertNotIn(('cont','stationA2'),selected)

    def fixture(self,policy='bisect'):
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
            target=search.query_target(lower,upper,policy);answer='sat' if target>=optimum else 'unsat'
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
        return dict(schema='sat-bound-search-v1',solver_name={'bisect':'SAT-Bisect-Restart','close-upper':'SAT-CloseUpper-Restart','upper':'SAT-Upper-Restart'}[policy],status='ok',threshold_policy=policy,
            objective='cont',uses_optimum_oracle=False,maxsat_backend='minisat',
            maxsat_backend_signature='MiniSAT v2.1.0',timeout_seconds=300,total_time=len(queries)+0.2,
            lb=lower,ub=upper,cost=upper,solution=solution,initial_lb=initial_lower,
            initial_ub=initial_upper,initial_solution=initial,queries=queries)

    def test_replays_all_proofs_and_independently_checks_incumbents(self):
        result=self.fixture();row,trace=search.check_result(result,'origA1','cont',300,5526)
        self.assertTrue(row['proven']);self.assertEqual(row['cost'],5526)
        self.assertEqual(trace[-1]['lb'],trace[-1]['ub'])

    def test_upper_policy_proves_the_incumbent_without_bisection(self):
        result=self.fixture('upper');row,trace=search.check_result(result,'origA1','cont',300,5526)
        self.assertTrue(row['proven'])
        self.assertTrue(all(q['target']==q['upper_before']-1 for q in result['queries']))
        self.assertEqual(result['queries'][-1]['outcome'],'unsat')
        self.assertEqual(trace[-1]['lb'],5526)
        result['threshold_policy']='bisect';result['solver_name']='SAT-Bisect-Restart'
        with self.assertRaisesRegex(ValueError,'threshold'):search.check_result(result,'origA1','cont',300,5526)

    def test_close_upper_thresholds_are_replayed_and_changed_policy_is_rejected(self):
        self.assertEqual(search.query_target(8949,9245,'close-upper'),9244)
        self.assertEqual(search.query_target(12,118,'close-upper'),64)
        result=self.fixture('close-upper')
        row,_=search.check_result(result,'origA1','cont',300,5526)
        self.assertTrue(row['proven']);self.assertEqual(row['threshold_policy'],'close-upper')
        result['threshold_policy']='bisect';result['solver_name']='SAT-Bisect-Restart'
        with self.assertRaisesRegex(ValueError,'threshold'):search.check_result(result,'origA1','cont',300,5526)

    def test_extra_regression_cases_do_not_duplicate_the_original_hard_set(self):
        old=[('cont','origA8')]
        with patch.object(search,'tasks_for',return_value=old):
            self.assertEqual(search.hard_tasks(None,[('infsteps180','stationA8')]),[('infsteps180','stationA8')]+old)
            for extra in ([('cont','origA8')],[('cont','bad')],[('infsteps180','stationA8')]*2):
                with self.assertRaises(ValueError):search.hard_tasks(None,extra)

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
