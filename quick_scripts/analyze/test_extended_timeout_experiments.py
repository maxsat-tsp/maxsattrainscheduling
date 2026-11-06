import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import extended_timeout_experiments as extended


def plan():
    return dict(schema="extended-timeout-v1", timeout_seconds=300, selection_cutoff_seconds=120,
                dataset_sha256=extended.focus.dataset_hash(), scope="focused only",
                instances_by_objective=dict(finsteps123=[], infsteps180=["origA1"], cont=["origA2"]))


class ExtendedTests(unittest.TestCase):
    def test_selection_includes_every_baseline_failure_and_does_not_import_old_timings(self):
        result = extended.build_plan(Path("results/sat_research/focus_20261106/selection.json"), Path("results"), 300)
        self.assertEqual({o:len(n) for o,n in result["instances_by_objective"].items()},
                         dict(finsteps123=0, infsteps180=5, cont=26))
        self.assertIn("stationA8", result["instances_by_objective"]["infsteps180"])
        self.assertEqual(len(result["published_cost_conflicts"]), 2)
        self.assertNotIn("summary", result)
        self.assertEqual(result["selection_cutoff_seconds"], 120)

    def test_all_five_methods_run_exactly_the_same_pairs_in_deterministic_order(self):
        tasks = extended.tasks_for(plan())
        self.assertEqual(tasks, extended.tasks_for(plan()))
        self.assertEqual(len(tasks), 10)
        self.assertEqual(len(set(tasks)), 10)
        for method in extended.METHODS:
            self.assertEqual({(o,n) for m,o,n in tasks if m==method},
                             {("infsteps180","origA1"),("cont","origA2")})

    def test_invalid_plan_duplicate_selection_and_changed_dataset_fail(self):
        original = plan()
        for key,value in (("timeout_seconds",120),("schema","other"),("dataset_sha256","changed")):
            malformed = copy.deepcopy(original)
            malformed[key] = value
            with self.assertRaises(ValueError):
                extended.validate_plan(malformed)
        malformed = copy.deepcopy(original)
        malformed["instances_by_objective"]["cont"] *= 2
        with self.assertRaises(ValueError):
            extended.validate_plan(malformed)

    def test_partial_campaign_never_reports_full_coverage_and_cost_conflicts_block(self):
        source = plan()
        records = [dict(tag=m,objective=o,name=n,status="ok",proven=True,time=1,errors=[],
                        solve=dict(cost=1,ub=1,lb=1,total_time=1),config=extended.METHODS[m])
                   for m,o,n in extended.tasks_for(source)]
        report = extended.summarize(source,records)
        self.assertTrue(report["complete"])
        self.assertFalse(report["submission_passed"])
        self.assertFalse(report["errors"])
        self.assertFalse(extended.summarize(source,records[:-1])["complete"])
        records[0]["solve"]["cost"] = 2
        self.assertTrue(extended.summarize(source,records)["errors"])
        with self.assertRaises(ValueError):
            extended.summarize(source,records+[records[0]])

    def test_cutoff_and_missing_schedule_cannot_be_silently_reused(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            solve=dict(status="ok",cost=1,ub=1,lb=1,total_time=1,timeout_seconds=120,process_exit_code=0)
            (root/"cont.json").write_text(json.dumps([dict(name="origA1",solves=[solve])]))
            record=extended.assess_case(root,"MaxSAT-Journal","cont","origA1",300)
            self.assertTrue(any("cutoff" in e for e in record["errors"]))
            self.assertTrue(any("missing solution" in e for e in record["errors"]))

    def test_cplex_requires_verified_schedule_and_bounds_instead_of_tolerance_status(self):
        visits = [[dict(travel=0,aimed=0)]]
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            sol=root/"schedule.sol"
            log=root/"cplex.log"
            log.write_text("Time limit exceeded")
            for status in ("101","102","107"):
                sol.write_text(f'<CPLEXSolution><header solutionStatusValue="{status}" objectiveValue="1"/>'
                               '<variables><variable name="t_0_0" value="1"/></variables></CPLEXSolution>')
                with patch.object(extended.common,"parse_txt_instance",return_value=visits), \
                     patch.object(extended.common,"independently_verify_solution",return_value=[]):
                    result=extended.cplex_result(sol,log,"origA1","cont",300,2)
                self.assertEqual(result["status"],"ok" if status=="101" else "timeout")
            with patch.object(extended.common,"parse_txt_instance",return_value=visits), \
                 patch.object(extended.common,"independently_verify_solution",return_value=["overlap"]):
                with self.assertRaises(ValueError):
                    extended.cplex_result(sol,log,"origA1","cont",300,2)


if __name__ == "__main__":
    unittest.main()
