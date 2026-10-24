"""A Windows-compatible fixture cleanup closes only its owned disposable handles."""
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from test_resources import FixtureResources
from atelier.data import Database


class FixtureResourceTests(unittest.TestCase):
    def test_cleanup_releases_local_database_and_archive_but_keeps_other_collection_open(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            with FixtureResources():
                target = tempfile.TemporaryDirectory(dir=root)
                local = Database(Path(target.name)/'collection.sqlite')
                outside = Database(root/'other.sqlite')
                local.rows('SELECT 1'); outside.rows('SELECT 1')
                archive_path = Path(target.name)/'models.zip'
                with ZipFile(archive_path,'w') as writer:
                    writer.writestr('model.dat','0 Test')
                reader = ZipFile(archive_path)
                target.cleanup()
                self.assertIsNone(local._reader)
                self.assertIsNone(reader.fp)
                self.assertIsNotNone(outside._reader)
                self.assertEqual(outside.rows('SELECT 1 AS value')[0]['value'],1)
                outside.close()


if __name__ == '__main__':
    unittest.main()
