import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import compare_sat_backends as dual
import extended_timeout_experiments as extended


def plan():
    return dict(schema="extended-timeout-v1", timeout_seconds=300, selection_cutoff_seconds=120,
                dataset_sha256=extended.focus.dataset_hash(), scope="focused only",sat_backend="cadical",
                instances_by_objective=dict(finsteps123=[], infsteps180=[], cont=["origA1","origA2"]))


def record(backend, role, name, solved=False, seconds=300, mode="parallel-development", cost=5):
    return dict(backend=backend, method=role, objective="cont", name=name, proven=solved,
                time=seconds,errors=[],solve=dict(cost=cost),measurement=dict(execution_mode=mode,binary_sha256="same"))


class BackendComparisonTests(unittest.TestCase):
    def test_cpu_sets_cannot_overlap_through_hyperthread_siblings(self):
        topology={cpu:(0,cpu%4) for cpu in range(8)}
        dual.validate_groups(dict(minisat=[0,1,4,5],cadical=[2,3,6,7]),topology,set(range(8)))
        for groups in (dict(minisat=[0],cadical=[4]),dict(minisat=[0],cadical=[1,2]),
                       dict(minisat=[0,0],cadical=[1,2])):
            with self.assertRaises(ValueError): dual.validate_groups(groups,topology,set(range(8)))

    def test_partial_comparison_uses_only_the_same_completed_cases(self):
        records=[record("minisat","CSOnet","origA1",True,2),
                 record("cadical","CSOnet","origA1",False),
                 record("cadical","CSOnet","origA2",True,1)]
        result=dual.summarize(plan(),records)
        row=result["comparison"][0]
        self.assertEqual(row["paired_completed"],1)
        self.assertEqual(row["minisat_optimal"],1)
        self.assertEqual(row["cadical_optimal"],0)
        self.assertEqual(row["cadical_par2_seconds"],600)
        self.assertEqual(row["preferred_backend"],"minisat")
        self.assertFalse(row["complete_for_objective"])
        self.assertFalse(result["complete"])
        self.assertFalse(result["submission_passed"])
        self.assertEqual(len(dual.tasks(plan())),12)

    def test_coverage_precedes_par2_and_historical_times_are_separated(self):
        records=[record("minisat","CSOnet","origA1",True,290,"historical-sequential"),
                 record("cadical","CSOnet","origA1",False)]
        result=dual.summarize(plan(),records)
        self.assertEqual(result["comparison"][0]["preferred_backend"],"minisat")
        self.assertFalse(result["matching_binary_parallel_comparison"])
        records[0]["measurement"]["execution_mode"]="parallel-development"
        records[0]["measurement"]["binary_sha256"]="different"
        self.assertFalse(dual.summarize(plan(),records)["matching_binary_parallel_comparison"])

    def test_duplicate_unknown_or_inconsistent_optima_are_rejected(self):
        original=record("minisat","CSOnet","origA1",True,1)
        with self.assertRaises(ValueError): dual.summarize(plan(),[original,original])
        with self.assertRaises(ValueError): dual.summarize(plan(),[dict(original,name="not-an-instance")])
        with self.assertRaises(ValueError):
            dual.summarize(plan(),[original,record("cadical","CSOnet","origA1",True,1,cost=6)])

    def make_reference(self,root,backend):
        frozen=dict(plan(),sat_backend=backend)
        definitions=extended.methods_for(frozen)
        extended.save(root/"plan.json",frozen)
        extended.save(root/"manifest.json",dict(methods=definitions,git_commit="source",binary_sha256="binary",
                      ram_kb=15000000,plan_sha256=extended.focus.sha(root/"plan.json")))
        records=[]
        # A partial reference is sufficient; import only reported completed SAT cases.
        for role in ("CSOnet","MaxSAT-Journal","BigM-Gurobi"):
            directory=root/"cases"/role/"cont"/"origA1"
            directory.mkdir(parents=True)
            solve=dict(status="timeout",timeout_seconds=300,total_time=300,process_exit_code=0)
            for field,value in definitions[role].items():
                if field not in {"solver","kind"}: solve["maxsat_"+field]=value
            if backend=="cadical" and role in dual.ROLES: solve["maxsat_backend_signature"]="cadical-test"
            extended.save(directory/"cont.json",[dict(name="origA1",solves=[solve])])
            records.append(extended.assess_case(directory,role,"cont","origA1",300,definitions[role]))
        extended.save(root/"extended_audit.json",extended.summarize(frozen,records))

    def test_import_preserves_case_bytes_and_rejects_wrong_backend_or_cutoff(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            self.make_reference(root,"minisat")
            reference,imports=dual.load_reference(root,"minisat",plan())
            self.assertEqual(len(imports),2)
            self.assertTrue(all(item["method"] in dual.ROLES for item in imports))
            item=next(r for r in imports if r["method"]=="MaxSAT-Journal")
            target=root/"trial"
            directory=dual.case_root(target,dual.key(item))
            directory.mkdir(parents=True)
            (directory/"cont.json").write_bytes(Path(item["source"]).read_bytes())
            extended.save(directory/"measurement.json",item)
            manifest=dict(plan=plan(),imports=imports)
            self.assertFalse(dual.assess(target,dual.key(item),manifest)["errors"])
            (directory/"cont.json").write_text("[]")
            with self.assertRaises(ValueError): dual.assess(target,dual.key(item),manifest)
            with self.assertRaises(ValueError): dual.load_reference(root,"cadical",plan())
            with self.assertRaises(ValueError): dual.load_reference(root,"minisat",dict(plan(),timeout_seconds=600))

    def test_failed_worker_stops_its_peer_and_records_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            failed,active=MagicMock(),MagicMock()
            failed.poll.return_value=1
            active.poll.return_value=None
            active.pid=12345
            manifest=dict(cpu_groups=dict(minisat=[0],cadical=[1]))
            report=dict(completed_runs=0,expected_runs=12,complete=False,progress=[])
            with patch.object(dual,"initialize",return_value=(root,manifest)), \
                 patch.object(dual,"audit_saved",return_value=report), \
                 patch.object(dual.subprocess,"Popen",side_effect=[failed,active]), \
                 patch.object(dual.os,"killpg") as kill:
                with self.assertRaises(RuntimeError): dual.run(SimpleNamespace(round_seconds=30))
            kill.assert_called_once_with(12345,dual.signal.SIGTERM)
            self.assertTrue((root/"failure.json").exists())


if __name__=="__main__": unittest.main()
