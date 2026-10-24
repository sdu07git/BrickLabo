"""Partial platform results must never be reported as a successful full suite."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from test_shards import census,combine


class TestCoverageTests(unittest.TestCase):
    def test_missing_duplicate_changed_census_or_failed_shard_is_rejected(self):
        ids=['first','second','third']
        base=dict(version='0.1.73',system='Windows',shard_count=2,discovered_tests=3,
            discovered_digest=census(ids),success=True,qt_shutdown=True,failures=0,errors=0,skipped=0,seconds=1)
        reports=[dict(base,shard_index=0,tests=2,cases=[{'id':v} for v in ids[:2]]),
                 dict(base,shard_index=1,tests=1,cases=[{'id':ids[2]}])]
        self.assertEqual(combine(reports)[0]['tests'],3)
        for bad in ([reports[0]],[reports[0],reports[0]]):
            with self.assertRaises(ValueError):combine(bad)
        for key,value in [('success',False),('qt_shutdown',False),('discovered_digest','changed'),('cases',[{'id':'duplicate'}])]:
            bad=copy.deepcopy(reports);bad[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):combine(bad)
