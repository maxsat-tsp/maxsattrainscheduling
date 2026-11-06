import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import compare_sat_backends as dual
import targeted_core_minimization as targeted
import extended_timeout_experiments as extended


class TargetedCoreTests(unittest.TestCase):
    def test_exhaustion_requires_matching_runtime_telemetry_and_forwards_the_flag(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            cfg=dict(extended.METHODS["Orders-Transitive"],core_minimize_checks="4",
                     core_minimize_conflicts="100",core_exhaust_checks="4")
            solve=dict(status="timeout",total_time=300,timeout_seconds=300,process_exit_code=0)
            solve.update({"maxsat_"+k:v for k,v in cfg.items() if k not in {"solver","kind"}})
            for value in (None,0,4):
                solve["maxsat_core_exhaust_checks"]=value
                extended.save(root/"cont.json",[dict(name="origA1",solves=[solve])])
                errors=extended.assess_case(root,"Exhaust","cont","origA1",300,cfg)["errors"]
                self.assertEqual(bool(errors),value!=4)
            args=SimpleNamespace(timeout=300,binary=root/"ddd",ram_kb=6000000,method_definitions={"Exhaust":cfg})
            with patch.object(extended,"execute") as execute:
                extended.run_case("Exhaust","cont","origA1",args,root/"run")
            env=execute.call_args.args[4]
            self.assertEqual(env["MAXSATDDD_CORE_EXHAUST_CHECKS"],"4")
            self.assertEqual(env["MAXSATDDD_CORE_MINIMIZE_CONFLICTS"],"100")

    def test_next_trial_reuses_the_winner_and_only_keeps_its_unresolved_cases(self):
        selection=dict(finsteps123=[],infsteps180=[],cont=["origA1","origA2"])
        config=dict(extended.METHODS["Orders-Transitive"],core_minimize_checks="4",core_minimize_conflicts="100")
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            extended.save(root/"manifest.json",dict(definition=config))
            extended.save(root/"core_minimization_audit.json",{})
            with patch("confirm_targeted_core_minimization.choose",return_value=(root,dict(newly_solved=[dict(objective="cont",name="origA1")]))), \
                 patch.object(targeted,"select",return_value=selection):
                chosen,cfg,evidence=targeted.unresolved_after_trials(root,[root])
            self.assertEqual(chosen["cont"],["origA2"])
            self.assertEqual(cfg,config)
            self.assertEqual(evidence["selected_manifest_sha256"],extended.focus.sha(root/"manifest.json"))
            with patch("confirm_targeted_core_minimization.choose",return_value=(root,dict(newly_solved=[dict(objective="cont",name="origA1")]))), \
                 patch.object(targeted,"select",return_value=selection), \
                 patch("core_regression_reference.audit",return_value=([dict(objective="cont",name="origA3")],dict(manifest_sha256="reg",report_sha256="report"))):
                chosen,_,evidence=targeted.unresolved_after_trials(root,[root],root/'regression')
            self.assertEqual(chosen['cont'],['origA3','origA2'])
            self.assertEqual(evidence['regression']['manifest_sha256'],'reg')
            extended.save(root/"manifest.json",dict(definition=dict(config,core_exhaust_checks="4")))
            with self.assertRaisesRegex(ValueError,"original V16"):
                targeted.unresolved_after_trials(root,[root])

    def test_conflict_limited_trial_requires_matching_solver_telemetry(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            cfg=dict(extended.METHODS["Orders-Transitive"],core_minimize_checks="4",core_minimize_conflicts="1000")
            solve=dict(status="timeout",total_time=300,timeout_seconds=300,process_exit_code=0)
            solve.update({"maxsat_"+field:value for field,value in cfg.items() if field not in {"solver","kind"}})
            solve.pop("maxsat_core_minimize_conflicts")
            extended.save(root/"cont.json",[dict(name="origA1",solves=[solve])])
            result=extended.assess_case(root,"LimitedCore","cont","origA1",300,cfg)
            self.assertIn("maxsat_core_minimize_conflicts differs from the locked configuration",result["errors"])
            solve["maxsat_core_minimize_conflicts"]=1000
            extended.save(root/"cont.json",[dict(name="origA1",solves=[solve])])
            self.assertFalse(extended.assess_case(root,"LimitedCore","cont","origA1",300,cfg)["errors"])

    def test_only_unproved_minisat_candidate_cases_are_selected(self):
        tasks=[("minisat","Orders-Transitive","cont","origA1"),
               ("minisat","Orders-Transitive","cont","origA2"),
               ("minisat","CSOnet","cont","origA3"),
               ("cadical","Orders-Transitive","cont","origA4")]
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            (root/"manifest.json").write_text(json.dumps(dict(plan={})))
            for task in tasks:
                case=dual.case_root(root,task)
                case.mkdir(parents=True)
                (case/"measurement.json").write_text("{}")
            with patch.object(dual,"audit_saved"),patch.object(dual,"tasks",return_value=tasks), \
                 patch.object(dual,"assess",side_effect=lambda _root,task,_source:dict(proven=task[3]=="origA1")):
                result=targeted.select(root)
            self.assertEqual(result,dict(finsteps123=[],infsteps180=[],cont=["origA2"]))
            (dual.case_root(root,tasks[0])/"measurement.json").unlink()
            with patch.object(dual,"audit_saved"),patch.object(dual,"tasks",return_value=tasks):
                with self.assertRaises(ValueError): targeted.select(root)


if __name__=="__main__": unittest.main()
