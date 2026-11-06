import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare_sat_backends as dual
import targeted_core_minimization as targeted


class TargetedCoreTests(unittest.TestCase):
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
