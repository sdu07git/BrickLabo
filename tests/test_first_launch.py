import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtCore import QThreadPool
from atelier.data import Database
from atelier.dialogs import ImportDialog
app=QApplication.instance() or QApplication([])

class FirstLaunchTests(unittest.TestCase):
    def run_import(self,failure=False):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            with patch.object(db,'import_file',side_effect=ValueError('Import impossible') if failure else None,return_value=3) as importer:
                d=ImportDialog(db,None,['parts.csv'],auto_start=True);d.show()
                deadline=time.monotonic()+5
                while not importer.called or d.running:
                    app.processEvents();time.sleep(.01)
                    self.assertLess(time.monotonic(),deadline)
                app.processEvents();QThreadPool.globalInstance().waitForDone(5000)
                importer.assert_called_once()
                if failure:
                    self.assertTrue(d.isVisible());self.assertIn('ERREUR',d.progress_label.text())
                else:
                    self.assertFalse(d.isVisible());self.assertEqual(d.result(),QDialog.DialogCode.Accepted)
                d.close();d.deleteLater();app.processEvents()
    def test_first_launch_imports_and_closes_automatically(self):self.run_import()
    def test_import_failure_stays_visible_for_retry(self):self.run_import(True)
