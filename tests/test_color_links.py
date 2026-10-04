import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from atelier.color_links import table,candidates,resolve,save_choice,rb_palette
from atelier.data import Database
from atelier.build_stock import InventoryReader
from atelier.stock_export import stock_rows
from atelier.preview import VisualEngine

class ColorLinksTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite')
 def tearDown(self):self.tmp.cleanup()
 def test_snapshot(self):
  self.assertEqual(len(table()),273);self.assertEqual(len(rb_palette()),273)
  for bl,rb in [('59','320'),('2','19'),('4','25'),('5','4'),('86','71'),('85','72'),('11','0')]:self.assertEqual(resolve(self.db.setting,'3001',bl),rb)
  self.assertEqual(set(candidates(self.db.setting,'72')),{'313','1051'})
  self.assertEqual(set(candidates(self.db.setting,'77')),{'148','1103'})
 def test_ambiguity_scoped_to_piece_and_reversible(self):
  self.assertEqual(resolve(self.db.setting,'3001','72'),'')
  save_choice(self.db,'3001','72','1051')
  self.assertEqual(resolve(self.db.setting,'3001','72'),'1051')
  self.assertEqual(resolve(self.db.setting,'3002','72'),'')
  self.assertEqual(resolve(self.db.setting,'3001','77'),'')
  save_choice(self.db,'3001','72','');self.assertEqual(resolve(self.db.setting,'3001','72'),'')
  with self.assertRaises(ValueError):save_choice(self.db,'3001','72','4')
 def test_snapshot_does_not_collapse_from_old_cache(self):
  self.db.set_setting('export_rb_bl_colors',{'72':['313'],'4':['4']})
  self.assertEqual(resolve(self.db.setting,'x','72'),'');self.assertEqual(resolve(self.db.setting,'x','4'),'25')
  self.assertEqual(resolve(self.db.setting,'x','99999'),'')
 def test_stock_export_and_build_share_choice(self):
  iid=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('BL','part','3001','Brick','Brick')")
  self.db.set_setting('export_rb_bl_parts',{'3001':['3001']});self.db.add('stock',iid,'72',3)
  self.assertEqual(stock_rows(self.db)[0][0]['rb_color'],'')
  save_choice(self.db,'3001','72','313')
  self.assertEqual(stock_rows(self.db)[0][0]['rb_color'],'313')
  import sqlite3
  with sqlite3.connect(self.db.path) as c:
   c.row_factory=sqlite3.Row
   self.assertEqual(InventoryReader(c).canonical('BL','3001','72'),('RB','3001','RB:313'))
   self.assertEqual(InventoryReader(c).canonical('BL','3002','72')[2],'BL:72')
  self.assertEqual(VisualEngine(self.db).color_rgb({'source':'BL','ref':'3001'},'72'),'#'+rb_palette()['313']['rgb'])
 def test_ui_export_ambiguous_choice_persists(self):
  from unittest.mock import patch
  from PySide6.QtWidgets import QApplication
  from atelier.stock_export import StockExportDialog
  app=QApplication.instance() or QApplication([])
  iid=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('BL','part','3001','Brick','Brick')")
  self.db.add('stock',iid,'77',2)
  def task(owner,work,done,*args):done(work(lambda *_:None))
  with patch('atelier.stock_export.async_task',side_effect=task):d=StockExportDialog(self.db)
  combo=d.table.cellWidget(0,6);self.assertEqual(combo.count(),3)
  combo.setCurrentIndex(combo.findData('1103'));d.review()
  self.assertEqual(resolve(self.db.setting,'3001','77'),'1103');d.reject()
 def test_cross_photo_converts_namespace(self):
  from unittest.mock import Mock,patch
  engine=VisualEngine(self.db);engine.photo=Mock(return_value=None)
  with patch('atelier.cross_source.bricklink_reference',return_value='3001'):
   engine.bricklink_fallback({'id':1,'source':'RB','ref':'3001'},False,'4')
  self.assertEqual(engine.photo.call_args.args[2],'5')
