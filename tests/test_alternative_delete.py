import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox,QPushButton
from atelier.data import Database
from atelier.catalogue import Catalogue
app=QApplication.instance() or QApplication([])
class AlternativeDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.windows=[]
    def tearDown(self):
        for w in self.windows:w.close();w.deleteLater()
        app.processEvents();self.temp.cleanup()
    def item(self,ref,source='ALT',kind='set'):
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,ref,ref));return self.db.get_item(iid)
    def catalogue(self):
        w=Catalogue(self.db,'ALT','set');self.windows.append(w);return w
    def test_single_click_delete_button_and_cancel(self):
        item=self.item('custom');w=self.catalogue();w.table.selectRow(0)
        button=next(b for b in w.findChildren(QPushButton) if b.text()=='Supprimer')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):button.click()
        self.assertEqual(w.total,1)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):button.click()
        self.assertEqual(w.total,0);self.assertIsNone(w.documents.item)
    def test_stock_parts_queue_and_history_survive_catalogue_deletion(self):
        part=self.item('part',kind='part');item=self.item('set');self.db.add_alt_component(item['id'],part['id'],'4',3)
        self.db.add('stock',item['id']);self.db.add('queue',part['id'])
        self.db.run('INSERT INTO history(item_id,quantity,method) VALUES(?,?,?)',(item['id'],1,'PDF'))
        self.db.delete_alternatives([item['id']]);self.assertEqual(self.db.query('ALT','set')[1],0)
        self.assertEqual(self.db.query('ALT','set',scope='stock')[1],1);self.assertEqual(self.db.query(scope='history')[1],1);self.assertEqual(self.db.query(scope='queue')[1],1)
        self.assertEqual(self.db.components(item)[0]['chosen_quantity'],3)
        entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(item['id'],))[0]['id'];self.db.remove('stock',[entry],True)
        self.assertEqual(self.db.query(scope='stock')[1],0)
    def test_multiple_deletion_and_native_catalogue_protection_are_atomic(self):
        a=self.item('a');b=self.item('b');native=self.item('native','RB')
        with self.assertRaises(ValueError):self.db.delete_alternatives([a['id'],native['id']])
        self.assertEqual(self.db.query('ALT','set')[1],2)
        self.db.delete_alternatives([a['id'],b['id']]);self.assertEqual(self.db.query('ALT','set')[1],0);self.assertEqual(self.db.query('RB','set')[1],1)
    def test_copying_again_restores_existing_reference(self):
        native=self.item('rb','RB');self.db.copy_alternative(native);alternative=self.db.query('ALT','set')[0][0]
        self.db.delete_alternatives([alternative['id']]);self.db.copy_alternative(native)
        self.assertEqual(self.db.query('ALT','set')[0][0]['id'],alternative['id'])
    def test_existing_database_migration_preserves_items(self):
        path=Path(self.temp.name)/'old.sqlite'
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE items(id INTEGER PRIMARY KEY,source TEXT,kind TEXT,ref TEXT,name TEXT,category TEXT,search TEXT,UNIQUE(source,kind,ref))')
            c.execute("INSERT INTO items VALUES(1,'ALT','set','old','Old','','old')")
        migrated=Database(path);self.assertEqual(migrated.get_item(1)['catalogue_hidden'],0)
        migrated.delete_alternatives([1]);self.assertEqual(migrated.get_item(1)['catalogue_hidden'],1)
    def test_readding_deleted_manual_set_preserves_identity_and_inventory(self):
        item=self.item('manual');part=self.item('part',kind='part');self.db.add_alt_component(item['id'],part['id'],'',2)
        self.db.delete_alternatives([item['id']]);self.db.alternative('set','manual','New name','City')
        restored=self.db.query('ALT','set')[0][0];self.assertEqual(restored['id'],item['id']);self.assertEqual(restored['name'],'New name');self.assertEqual(len(self.db.components(restored)),1)
