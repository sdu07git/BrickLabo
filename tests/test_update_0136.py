import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QTableWidget,QInputDialog
from atelier.data import Database
from atelier.catalogue import Catalogue
from atelier.search_filters import FilterDialog
from atelier.result_tables import fill_table,row_index
from atelier.build_stock import BuildStockDialog
from atelier.alternates import AlternatesDialog
app=QApplication.instance() or QApplication([])
class Update36Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite');self.widgets=[]
  for ref,category in [('1','Bricks'),('2','Plates'),('3','Tiles')]:self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part',?,'Piece',?,'piece')",(ref,category))
 def tearDown(self):
  for w in self.widgets:
   if hasattr(w,'timer'):w.timer.stop()
   w.close()
  self.tmp.cleanup()
 def test_categories_or_with_other_filters_and_pagination(self):
  for indexed in (True,False):
   self.db.search_index_available=indexed
   rows,total,_,_=self.db.query(search='piece',size=1,advanced={'categories':['Bricks','Plates']});self.assertEqual(total,2);self.assertEqual(len(rows),1)
   self.assertEqual(self.db.query(advanced={'categories':['Bricks','Plates'],'stock':'yes'})[1],0)
   self.assertEqual(self.db.query(advanced={'categories':["Bricks' OR 1=1 --"]})[1],0)
 def test_tags_legacy_preset_reset_and_simple_category_switch(self):
  cat=Catalogue(self.db,'RB','part');self.widgets.append(cat)
  cat.category.setCurrentIndex(cat.category.findData('Bricks'))
  d=FilterDialog(cat);self.widgets.append(d);self.assertEqual(d.categories.values(),['Bricks'])
  d.categories.set_values(['Bricks','Plates']);cat.apply_filter_state(d.state());self.assertEqual(cat.total,2)
  with patch.object(QInputDialog,'getText',return_value=('Two categories',True)):d.save_preset()
  saved=Database(self.db.path).setting(d.preset_key)['Two categories'];d.set_state({});d.set_state(saved)
  self.assertEqual(set(d.categories.values()),{'Bricks','Plates'})
  cat.remove_category_tag('Bricks');self.assertEqual(cat.total,1);self.assertEqual(cat.rows[0]['ref'],'2')
  cat.category.setCurrentIndex(cat.category.findData('Tiles'));self.assertFalse(cat.advanced.get('categories'));self.assertEqual(cat.rows[0]['ref'],'3')
  d.set_state({});cat.apply_filter_state(d.state());self.assertEqual(cat.total,3)
 def test_numeric_sort_keeps_row_identity(self):
  t=QTableWidget(0,2);self.widgets.append(t);fill_table(t,[('A',100),('B',2),('C',10)])
  t.sortItems(1,Qt.SortOrder.AscendingOrder)
  self.assertEqual([t.item(i,0).text() for i in range(3)],['B','C','A']);self.assertEqual(row_index(t,0),1)
 def test_preview_rows_follow_sort_and_keep_color(self):
  with patch('atelier.build_stock.async_task'):
   d=BuildStockDialog(self.db,Mock());self.widgets.append(d)
   rows=[('RB','1','Brick','RB:4',100,0,100),('RB','2','Plate','RB:0',2,0,2)]
   d.detail_rows=rows;d.part_visuals=[d.part_visual(row) for row in rows]
   fill_table(d.parts,[tuple(row)+('Preview',) for row in rows]);d.parts.sortItems(4,Qt.SortOrder.AscendingOrder)
   self.assertEqual(d.parts.columnCount(),8);self.assertEqual(d.visible_parts()[0]['ref'],'2');self.assertEqual(d.visible_parts()[0]['chosen_color'],'0');self.assertTrue(d.thumbnails.force_3d)
 def test_alternates_sorted_selection_uses_correct_moc(self):
  with patch('atelier.alternates.async_task'):
   d=AlternatesDialog(self.db,None,{'source':'RB','ref':'123-1'});self.widgets.append(d)
   d.rows=[{'set_num':'MOC-A','name':'A','designer_name':'D','num_parts':100},{'set_num':'MOC-B','name':'B','designer_name':'D','num_parts':2}]
   fill_table(d.table,[(r['set_num'],r['name'],r['designer_name'],r['num_parts']) for r in d.rows]);d.table.sortItems(3,Qt.SortOrder.AscendingOrder);d.table.selectRow(0)
   self.assertEqual(d.selected()['set_num'],'MOC-B')
