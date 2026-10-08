import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QThreadPool
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import VisualEngine
from atelier.app import MainWindow,NAV
from atelier.owned_sets import OwnedSetsPanel
from atelier.stock_import_dialog import StockImportDialog
from atelier.backup_dialog import BackupDialog
from atelier.moc_search import MocSearchDialog

application=QApplication.instance() or QApplication([])

class Update37UiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'Donnees'/'db.sqlite');self.windows=[]
        self.part=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','3001','Brick','brick')")
        self.second=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','3005','Small brick','small brick')")
        self.set=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','set','100-1','Set','set')")
        self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)");self.db.run("INSERT INTO inventories VALUES(1,1,'100-1')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3001',4,2,0,'')");self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',4,5,0,'')")
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000)
        for window in self.windows:window.close();window.deleteLater()
        application.processEvents();self.temp.cleanup()
    def keep(self,window):self.windows.append(window);return window
    def main_window(self):
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.preview.Preview.refresh'):
            window=self.keep(MainWindow(self.db));window.startup_timer.stop();return window

    def test_navigation_and_undo_controls_follow_stock_journal(self):
        window=self.main_window();self.assertEqual(window.nav.count(),12);self.assertEqual(NAV[8][3],'stock');self.assertEqual(NAV[9][3],'stock_sets');self.assertFalse(window.undo_button.isEnabled())
        self.db.add('stock',self.set,quantity=2)
        with patch('atelier.catalogue.Catalogue.load_thumbnails'):window.refresh_counts()
        self.assertTrue(window.undo_button.isEnabled());self.assertTrue(window.undo_shortcut.isEnabled());self.assertEqual(window.undo_shortcut.shortcut().toString(),'Ctrl+Z');self.assertEqual(self.db.query(scope='stock')[1],0)
        window.undo_shortcut.trigger();self.assertEqual(self.db.query(scope='stock_sets')[1],0);self.assertFalse(window.undo_button.isEnabled())

    def test_owned_components_sort_and_double_click_open_matching_reference(self):
        self.db.add('stock',self.set,quantity=2);panel=self.keep(OwnedSetsPanel(self.db,VisualEngine(self.db)));panel.select(self.db.query(scope='stock_sets')[0][0]);self.assertEqual(panel.table.columnCount(),6)
        panel.table.sortItems(4,Qt.SortOrder.DescendingOrder);self.assertEqual(panel.ordered_parts()[0]['ref'],'3005');self.assertEqual(panel.table.item(0,4).data(Qt.ItemDataRole.DisplayRole),10)
        with patch('atelier.dialogs.RelationsDialog') as dialog:
            panel.table.cellDoubleClicked.emit(0,5);self.assertEqual(dialog.call_args.args[2]['ref'],'3005');dialog.return_value.exec.assert_called_once()

    def test_import_preview_choice_and_missing_reference_gate(self):
        window=self.keep(StockImportDialog(self.db,destination='stock_sets'));self.assertEqual(window.destination.currentData(),'stock_sets');self.assertTrue(window.target.isEnabled());self.assertTrue(window.name.isEnabled())
        path=Path(self.temp.name)/'parts.csv';path.write_text('Part,Color,Quantity\n3001,4,2\n');window.path=path;window.load();self.assertEqual(window.table.rowCount(),1);self.assertTrue(window.commit.isEnabled());window.destination.setCurrentIndex(0);self.assertFalse(window.target.isEnabled())
        path.write_text('Part,Color,Quantity\nmissing,4,2\n');window.load();self.assertFalse(window.commit.isEnabled());self.assertEqual(self.db.query(scope='stock')[1],0)

    def test_backup_defaults_seven_separate_families_without_api(self):
        parent=self.main_window();window=self.keep(BackupDialog(parent));self.assertEqual(len(window.families),8);self.assertFalse(window.families['api'].isChecked());self.assertEqual(sum(c.isChecked() for c in window.families.values()),7)

    def test_moc_origin_loading_preserves_sorted_selection(self):
        window=self.keep(MocSearchDialog(self.db,None));window.rows=[{'set_num':'MOC-123','name':'Falcon','bases_loaded':False,'bases':[]},{'set_num':'MOC-456','name':'Other','bases_loaded':True,'bases':['100-1']}];window.fill();window.table.sortItems(4,Qt.SortOrder.AscendingOrder)
        def synchronous(parent,work,done,failed,*args):done(work(lambda _:None))
        with patch('atelier.moc_search.fetch_bases',return_value=['75192-1']),patch('atelier.moc_search.async_task',side_effect=synchronous):
            row=next(r for r in range(window.table.rowCount()) if window.table.item(r,0).text()=='MOC-123');window.table.selectRow(row)
        self.assertEqual(window.selected()['set_num'],'MOC-123');self.assertTrue(window.open.isEnabled());self.assertIn('75192-1',window.origins.text());self.assertEqual(window.table.item(window.table.currentRow(),4).text(),'75192-1')
