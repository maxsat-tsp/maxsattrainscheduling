import io
from pathlib import Path
import tarfile
import tempfile
import unittest

import rebuild_cplex_recheck as correction


class CplexCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.original=correction.ex.REPO/'results/sat_research/cplex_full_120_20261108/raw_snapshot.tar.gz'
        self.recheck=self.original.parent/'bound_recheck_20261109/raw_snapshot.tar.gz'

    def test_strict_rerun_proves_34_on_the_original_lp_instead_of_35(self):
        report=correction.audit_native(self.recheck,self.original)
        self.assertEqual(report['original_solve']['cost'],35)
        self.assertEqual(report['solve']['cost'],34)
        self.assertEqual(report['solve']['lb'],report['solve']['ub'])
        self.assertTrue(report['audit_passed'])

    def test_changed_lp_is_rejected_before_using_the_result(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'changed.tar.gz'
            with tarfile.open(self.recheck) as source,tarfile.open(target,'w:gz') as out:
                for member in source.getmembers():
                    if member.isfile():
                        data=source.extractfile(member).read()
                        if member.name.startswith('tight_recheck/') and member.name.endswith('.lp'):data+=b'\n'
                        member.size=len(data);out.addfile(member,io.BytesIO(data))
                    else:out.addfile(member)
            with self.assertRaisesRegex(ValueError,'changed native LP'):
                correction.audit_native(target,self.original)


if __name__=='__main__':unittest.main()
