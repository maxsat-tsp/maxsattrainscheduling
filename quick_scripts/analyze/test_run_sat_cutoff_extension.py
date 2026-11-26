from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_sat_cutoff_extension as extension


class CutoffExtensionTests(unittest.TestCase):
    def test_v49_fallback_requires_three_matching_confirmations(self):
        proof=dict(objective='cont',name='trackA8',cost=24441,proven=True)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'COMPLETED').touch()
            for phase in ('hard','followup'):
                (root/phase).mkdir()
            fixed={k:0 for k in ('commit','binary_sha256','build_manifest_sha256','dataset_sha256','ram_kb','cpu_affinity')}
            fixed.update(threshold_session='reuse-pair-budget',timeout_seconds=1200)
            for phase in ('hard','followup'):
                extension.ex.save(root/phase/'manifest.json',fixed)
            screen=dict(audit_passed=True,complete=True,newly_solved=[proof])
            repeats=[dict(proof,repeat=i) for i in (1,2,3)]
            for rows, expected in ((repeats,True),(repeats[:2],False),
                                  (repeats[:2]+[dict(repeats[2],proven=False)],False)):
                replay=dict(audit_passed=True,complete=True,records=rows)
                with patch.object(extension.search,'audit',side_effect=[screen,replay]):
                    self.assertEqual(extension.v49_reproduced(root,None,None),expected)

    def test_longer_extension_reuses_proofs_within_their_original_cutoff(self):
        pair=('cont','trackB12')
        row=dict(objective=pair[0],name=pair[1],cost=15182,proven=True,upper_witness_verified=True,
                 seconds=1000,timeout_seconds=1200)
        self.assertFalse(extension.controls.first_checked_proofs([row],{pair}))
        self.assertIn(pair,extension.controls.first_checked_proofs([row],{pair},2400))
        self.assertFalse(extension.controls.first_checked_proofs([dict(row,timeout_seconds=600)],{pair},2400))

    def test_prior_protocol_checks_relative_source_paths_and_binary_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)/'before'
            root = repo/'results/aglr/original'
            root.mkdir(parents=True)
            rel = 'results/data/ref.tgz'
            expected = dict(timeout_seconds=1200,binaries={'ddd':'fixed'},runner_commit='new',
                            source_sha256={str(extension.ex.REPO/rel):'checksum'})
            previous = dict(expected,runner_commit='old',source_sha256={str(repo/rel):'checksum'})
            extension.ex.save(root/'manifest.json',previous)
            self.assertEqual(extension.load_prior(root,expected),previous)
            for change in (dict(binaries={'ddd':'changed'}),dict(source_sha256={str(repo/rel):'changed'})):
                extension.ex.save(root/'manifest.json',dict(previous,**change))
                with self.assertRaisesRegex(ValueError,'prior extension protocol'):
                    extension.load_prior(root,expected)

    def test_prior_audit_requires_the_same_replayed_observations(self):
        methods = (extension.SAT,*extension.controls.METHODS)
        pair = ('cont','trackA8')
        row = dict(objective=pair[0],name=pair[1],status='timeout',proven=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = dict(runner_commit='previous')
            extension.ex.save(root/'manifest.json',previous)
            saved = {m:[row] if m==extension.SAT else [] for m in methods}
            extension.ex.save(root/'audit.json',dict(audit_passed=True,measurements=saved))
            lock = dict(methods={m:dict(tasks=[pair] if m==extension.SAT else []) for m in methods},
                prior_results=dict(root=tmp,manifest_sha256=extension.ex.focus.sha(root/'manifest.json'),
                                   audit_sha256=extension.ex.focus.sha(root/'audit.json')))
            with patch.object(extension,'measure',return_value=dict(row)) as replay:
                report = extension.replay_prior(None,lock,{}, {}, {}, {})
                self.assertEqual(report[extension.SAT],[dict(row,replayed_from_prior=True)])
                self.assertFalse(replay.call_args.kwargs['run'])
            with patch.object(extension,'measure',return_value=dict(row,name='changed')):
                with self.assertRaisesRegex(ValueError,'prior observations'):
                    extension.replay_prior(None,lock,{}, {}, {}, {})

    def test_gurobi_api_error_gets_a_failure_receipt_and_checks_raw_files(self):
        method = extension.GUROBI_METHOD
        pair = ('infsteps180','stationA11')
        o,n = pair
        lock = dict(timeout_seconds=1200,runner_commit='runner',binaries={'ddd':'fixed'})
        raw = [dict(name=n,solves=[dict(status='gurobi_error',process_exit_code=0,
                    process_wall_time_seconds=1124.718,timeout_seconds=1200,solver_name='BigMLazy')])]

        def native_error(_args,case,_o,_n,_tasks):
            logs = case/'logs'
            (logs/'instances').mkdir(parents=True)
            fields = dict(binary_sha256='fixed',git_commit='runner',solver='bigm_lazy',
                          objective=o,selected_instances=n,selected_instance_count=1,
                          instance_timeout_seconds=1200,ram_limit_kb=extension.cplex.RAM_KB)
            (logs/'manifest.txt').write_text(''.join(f'{k}={v}\n' for k,v in fields.items()))
            for stream in ('stdout','stderr'):
                (logs/f'{n}.{stream}.log').write_text('')
            extension.ex.save(case/(o+'.json'),raw)
            extension.ex.save(logs/'instances'/(n+'.json'),raw)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = (SimpleNamespace(ddd=None,cplex=None),method,pair,root,lock,{},None,{}, {}, {})
            with patch.object(extension.controls,'measured_case',side_effect=native_error):
                row = extension.measure(*args)
            case = root/method/o/n
            self.assertEqual(row['status'],'gurobi_error')
            self.assertNotIn('proven',row)
            self.assertFalse((case/'completion.json').exists())
            self.assertTrue((case/'failure.json').is_file())
            self.assertEqual(extension.measure(*args,run=False),row)
            (case/'logs'/f'{n}.stderr.log').write_text('modified')
            with self.assertRaisesRegex(ValueError,'saved Gurobi failure evidence changed'):
                extension.measure(*args,run=False)

    def test_campaign_continues_with_other_cases_after_a_native_gurobi_error(self):
        g,cp = extension.GUROBI_METHOD,'BigM-CPLEX'
        pair = ['infsteps180','stationA11']
        lock = dict(timeout_seconds=1200,label='V45',cpu_affinity=list(range(8)),methods={
            m:dict(tasks=[pair] if m in (g,cp) else [],reused=[])
            for m in (extension.SAT,*extension.controls.METHODS)})
        attempted = []

        def observation(_args,method,_pair,*_params,run=True,**_named):
            if not run:
                return None
            attempted.append(method)
            return dict(method=method,objective=pair[0],name=pair[1],proven=False,
                        status='gurobi_error' if method==g else 'timeout')

        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(results=Path(tmp),round_seconds=21000,diagnostic_ddd=None)
            with patch.object(extension,'material',return_value=(lock,{}, {}, {})), \
                 patch.object(extension,'prepare_lock',return_value=(None,lock)), \
                 patch.object(extension,'measure',side_effect=observation), \
                 patch.object(extension.os,'sched_setaffinity',create=True):
                self.assertEqual(extension.run(args),76)
            result = extension.read(args.results/'audit.json')
            self.assertEqual(attempted,[g,cp])
            self.assertEqual(result['summary'][g]['measured'],0)
            self.assertEqual(result['summary'][cp]['measured'],1)
            self.assertEqual(result['failed_cases'][0]['method'],g)
            self.assertFalse(result['complete'])
            self.assertFalse((args.results/'COMPLETED').exists())

    def test_v47_replay_allows_rounding_in_derived_sat_time_only(self):
        raw = dict(threshold_sat_seconds=539.607390101, lb=106, ub=146, status='timeout')
        self.assertTrue(extension.ex.reports_match(dict(raw,threshold_sat_seconds=539.6073901010001),raw))
        self.assertFalse(extension.ex.reports_match(dict(raw,lb=106.0000000000001),raw))

    def test_promotion_requires_every_old_proof_and_a_net_gain(self):
        old = [dict(objective='cont',name=f'instance-{i}',proven=True) for i in range(206)]
        extras = [dict(objective='cont',name=f'new-{i}',proven=True) for i in range(3)]
        profile = dict(threshold_session='reuse-offset-tree',timeout_seconds=600)
        v45 = dict(threshold_session='reuse')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'COMPLETED').touch()
            args = SimpleNamespace(v47=path)
            self.assertEqual(extension.pick_sat(args,old,v45)[2:],('V45',1200))
            (path/'full-evaluation.json').touch()
            for rows, expected in (
                (old,('V45',1200)),
                (old[1:]+extras,('V45',1200)),
                (old+extras[:2],('V47',1200)),
                (old+extras,('V47',600)),
            ):
                with patch.object(extension,'full_sat',return_value=(rows,profile)):
                    self.assertEqual(extension.pick_sat(args,old,v45)[2:],expected)

    def test_a_failed_screening_cannot_start_the_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'COMPLETED').touch()
            (path/'FAILED').touch()
            with self.assertRaisesRegex(ValueError,'clean completion'):
                extension.pick_sat(SimpleNamespace(v47=path),[],{})

    def test_coverage_gate_waits_for_all_measured_controls(self):
        proof = dict(objective='cont',name='case',proven=True,status='ok')
        lock = dict(label='V47',timeout_seconds=1200,methods={
            'SAT':dict(reused=[proof],tasks=[]),
            'BigM-CPLEX':dict(reused=[],tasks=[['cont','case']]),
        })
        measured = {'SAT':[], 'BigM-CPLEX':[]}
        self.assertFalse(extension.report(lock,measured)['beats_all_baselines'])
        measured['BigM-CPLEX'].append(dict(proof,proven=False,status='timeout'))
        self.assertTrue(extension.report(lock,measured)['beats_all_baselines'])
        measured['BigM-CPLEX'][0] = proof
        self.assertFalse(extension.report(lock,measured)['beats_all_baselines'])

    def test_disagreeing_independently_checked_proofs_stop_comparison(self):
        proof = dict(objective='cont',name='case',proven=True,cost=4)
        self.assertEqual(extension.register_optima([proof,dict(proof,proven=False,cost=5)]),
                         {('cont','case'):4})
        with self.assertRaisesRegex(ValueError,'proved optima disagree'):
            extension.register_optima([proof,dict(proof,cost=5)])

    def test_a_600_second_timeout_does_not_complete_a_1200_second_case(self):
        solve = dict(lb=3,ub=5)
        row = dict(solve=solve,errors=[],status='timeout',time=600.1,objective='cont',name='case')
        known = dict(lb=3,ub=5,proven=False)
        self.assertEqual(extension.controls.case_record(None,'CSOnet',row,known)['timeout_seconds'],600)
        with self.assertRaisesRegex(ValueError,'stopped before the measured cutoff'):
            extension.controls.case_record(None,'CSOnet',row,known,1200)
