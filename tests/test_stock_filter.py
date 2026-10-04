import os,tempfile,unittest,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication,QTableWidgetItem
from atelier.data import Database
from atelier.build_stock import InventoryReader,find_builds,build_details,BuildStockDialog
from atelier.stock_mocs import StockMocsDialog
app=QApplication.instance() or QApplication([])
class StockFilterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite')
  self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)")
  self.p=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','3001','Brick','Brick')")
  self.s=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','set','100-1','Set','Set')")
  self.db.run("INSERT INTO inventories VALUES(1,1,'100-1')");self.db.run("INSERT INTO inventory_parts VALUES(1,'3001',4,5,0,'')")
 def tearDown(self):self.tmp.cleanup()
 def stock(self,exclude):
  with self.db.connect() as c:return InventoryReader(c,False,exclude).stock()
 def test_excluded_set_reserves_only_tracked_quantities(self):
  self.db.add('stock',self.p,'4',3);self.db.add('stock',self.s,quantity=2)
  entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.s,))[0]['id']
  self.assertEqual(sum(self.stock([]).values()),13)
  self.assertEqual(sum(self.stock([entry]).values()),3)
  self.assertEqual(sum(r['quantity'] for r in self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.p,))),13)
  self.assertEqual(find_builds(self.db,excluded_entries=[entry])[0],[])
  self.assertEqual(build_details(self.db,self.db.get_item(self.s),excluded_entries=[entry])[0][0][-1],2)
 def test_piece_exclusion_and_set_exclusion_do_not_double_subtract(self):
  self.db.add('stock',self.s,quantity=1);self.db.add('stock',self.p,'4',2)
  ids=[r['id'] for r in self.db.rows('SELECT id FROM stock')]
  self.assertFalse(self.stock(ids))
 def test_loose_pieces_find_sets_without_owned_set(self):
  self.db.add('stock',self.p,'4',5)
  self.assertEqual(find_builds(self.db)[0][0]['ref'],'100-1')
 def test_untracked_excluded_set_not_silently_ignored(self):
  entry=self.db.run("INSERT INTO stock(item_id,color,quantity) VALUES(?,'',1)",(self.s,))
  with self.assertRaises(ValueError):self.stock([entry])
 def test_moc_from_loose_stock_and_dedup(self):
  self.db.add('stock',self.p,'4',5);self.db.set_setting('api_rb','fake')
  def task(owner,work,done,*args):done(work(lambda *_:None))
  row={'set_num':'MOC-123','name':'Build','designer_name':'D','num_parts':4,'moc_url':'https://rebrickable.com/mocs/MOC-123/'}
  with patch('atelier.stock_mocs.async_task',side_effect=task),patch('atelier.stock_mocs.fetch_alternates',return_value=([row],None,1)),patch.object(threading.Event,'wait',return_value=False):
   d=StockMocsDialog(self.db,None,[]);d.start();self.assertEqual(len(d.rows),1);self.assertEqual(d.rows[0]['bases'],['100-1']);d.reject()
 def test_context_menu_uses_clicked_result(self):
  d=BuildStockDialog(self.db,Mock());d.results=[{'source':'RB','ref':'100-1'},{'source':'BL','ref':'200-1'}];d.table.setRowCount(2)
  for i in range(2):d.table.setItem(i,0,QTableWidgetItem(str(i)))
  with patch('atelier.build_stock.async_task'),patch('atelier.build_stock.QMenu') as menu,patch('atelier.alternates.AlternatesDialog') as dialog:
   menu.return_value.addAction.side_effect=lambda text,fn:fn()
   d.context_menu(d.table.visualItemRect(d.table.item(1,0)).center())
   self.assertEqual(dialog.call_args.args[2]['ref'],'200-1');dialog.reset_mock()
   d.context_menu(QPoint(-1,-1));dialog.assert_not_called()
  d.reject()
 def test_search_detail_keeps_filter_snapshot(self):
  self.db.add('stock',self.s,quantity=1);self.db.add('stock',self.p,'4',2)
  entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.s,))[0]['id'];self.db.set_setting('build_excluded_entries',[entry])
  def task(owner,work,done,*args):done(work(lambda *_:None))
  with patch('atelier.build_stock.async_task',side_effect=task):
   d=BuildStockDialog(self.db);d.minimum.setValue(0);d.start()
   self.assertEqual(d.last_excluded,[entry]);self.assertEqual(d.detail_rows[0][-1],3);d.reject()
