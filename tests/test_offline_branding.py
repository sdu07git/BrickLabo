import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from atelier.data import Database
from atelier.preview import Preview,VisualEngine
from atelier.app import MainWindow
from atelier.version import APP_NAME,VERSION
app=QApplication.instance() or QApplication([])

class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.startup_patch=patch.object(MainWindow,"first_import",lambda self:None);self.startup_patch.start()
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.db=Database(self.path/'db.sqlite');self.windows=[]
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL','part','3001','Brick','Bricks','brick'))
        self.item=self.db.get_item(iid)
    def tearDown(self):
        self.startup_patch.stop()
        time.sleep(.12);app.processEvents()
        for w in self.windows:w.close()
        QThreadPool.globalInstance().waitForDone(6000);app.processEvents();self.temp.cleanup()
    def test_palette_import_does_not_invent_availability(self):
        f=self.path/'Colors.txt';f.write_text('Color ID\tColor Name\tRGB\n5\tRed\tC91A09\n7\tBlue\t0055BF\n')
        self.assertEqual(self.db.import_file(f),2)
        self.assertEqual(self.db.available_colors(self.item),[])
        self.assertEqual(VisualEngine(self.db).color_rgb(self.item,'5'),'#C91A09')
        self.db.run('INSERT INTO colors VALUES(?,?,?,?)',(5,'RB Different','ffffff',0))
        self.assertEqual(VisualEngine(self.db).color_rgb(self.item,'5'),'#C91A09')
        f.write_text('Color ID\tColor Name\n5\tRed\n');self.db.import_file(f)
        self.assertEqual(self.db.setting('bl_colors')['5']['rgb'],'C91A09')
    def test_no_api_required_for_render_palette(self):
        self.db.run('INSERT INTO colors VALUES(?,?,?,?)',(4,'Red','ff0000',0))
        e=VisualEngine(self.db)
        with patch.object(Preview,'refresh'),patch.object(Preview,'fetch_colors') as api:
            p=Preview(self.db,e);self.windows.append(p);p.set_item(self.item)
            api.assert_not_called();self.assertTrue(p.load_colors.isHidden());self.assertFalse(p.available.isEnabled())
            idx=p.color.findData('#ff0000');self.assertGreater(idx,1);p.color.setCurrentIndex(idx)
            self.assertEqual(self.db.visual(self.item['id'])['color'],'#ff0000')
            self.assertEqual(e.color_rgb(self.item,'#ff0000'),'#ff0000')
    def test_brand_and_version(self):
        with patch.object(VisualEngine,'visuals',return_value=({'main':Image.new('RGB',(20,20),'yellow')},'')):
            w=MainWindow(self.db);self.windows.append(w)
            self.assertEqual(w.windowTitle(),APP_NAME+' — v'+VERSION)
        self.assertEqual(APP_NAME,'BrickLabo by SDU7')
    def make_set(self):
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('ALT','set','demo','Demo','Sets','demo'))
        self.db.set_setting('alt_components_'+str(iid),[{'item_id':self.item['id'],'color':'5','quantity':3}])
        return iid
    def test_removing_set_keeps_other_stock_and_uses_added_inventory(self):
        sid=self.make_set();self.db.add('stock',self.item['id'],'5',7);self.db.add('stock',self.item['id'],'7',4)
        self.db.add('stock',sid,quantity=2)
        self.db.set_setting('alt_components_'+str(sid),[{'item_id':self.item['id'],'color':'5','quantity':99}])
        entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(sid,))[0]['id']
        self.db.remove('stock',[entry],remove_set_parts=True)
        rows=self.db.rows('SELECT color,quantity FROM stock WHERE item_id=? ORDER BY color',(self.item['id'],))
        self.assertEqual(rows,[{'color':'5','quantity':7},{'color':'7','quantity':4}])
        self.assertEqual(self.db.rows('SELECT * FROM stock_set_components'),[])
    def test_set_only_removal_and_cancel(self):
        from atelier.catalogue import Catalogue
        from PySide6.QtWidgets import QMessageBox
        sid=self.make_set();self.db.add('stock',sid)
        cat=Catalogue(self.db,kind='set',scope='stock');self.windows.append(cat);cat.table.selectRow(0)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):cat.delete_selected()
        self.assertEqual(len(self.db.rows('SELECT * FROM stock')),2)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):cat.delete_selected()
        self.assertEqual(self.db.rows('SELECT item_id,quantity FROM stock'),[{'item_id':self.item['id'],'quantity':3}])
    def test_yes_never_creates_negative_quantity_and_multiple_sets(self):
        sid=self.make_set();self.db.add('stock',sid,quantity=2)
        self.db.run('UPDATE stock SET quantity=1 WHERE item_id=?',(self.item['id'],))
        from atelier.catalogue import Catalogue
        from PySide6.QtWidgets import QMessageBox
        cat=Catalogue(self.db,kind='set',scope='stock');self.windows.append(cat);cat.table.selectRow(0)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):cat.delete_selected()
        self.assertEqual(self.db.rows('SELECT * FROM stock'),[])
    def test_legacy_set_removal_uses_existing_composition(self):
        sid=self.make_set();self.db.add('stock',sid,quantity=2);self.db.run('DELETE FROM stock_set_components')
        entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(sid,))[0]['id']
        self.db.remove('stock',[entry],remove_set_parts=True)
        self.assertEqual(self.db.rows('SELECT * FROM stock'),[])

    def test_adding_another_copy_of_legacy_set_keeps_removal_quantities(self):
        sid=self.make_set();self.db.add('stock',sid);self.db.run('DELETE FROM stock_set_components')
        self.db.add('stock',sid)
        entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(sid,))[0]['id']
        self.db.remove('stock',[entry],remove_set_parts=True)
        self.assertEqual(self.db.rows('SELECT * FROM stock'),[])
