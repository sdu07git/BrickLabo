import csv,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication,QDialog
from PIL import Image
from atelier.data import Database
from atelier.build_stock import BuildStockDialog,export_build_parts
from atelier.contours import ContourDialog
app=QApplication.instance() or QApplication([])
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite')
  self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','3001','Brick','Bricks','brick')")
  self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('BL','set','75192-1','Falcon','Star Wars','falcon')")
 def tearDown(self):self.tmp.cleanup()
 def test_csv_partial_stock_and_ignored_colors(self):
  rows=[('RB','3001','Brick','RB:0',5,9,0),('RB','3002','Brick','RB:4',7,2,5),('BL','x','Other','*',3,0,3)]
  for mode,amounts in [('missing',['5','3']),('owned',['5','2'])]:
   p=Path(self.tmp.name)/(mode+'.csv');export_build_parts(p,{'source':'RB','ref':'set'},rows,mode,2,True)
   with p.open(encoding='utf-8-sig') as stream:r=list(csv.DictReader(stream,delimiter=';'))
   self.assertEqual([x['quantite_exportee'] for x in r],amounts);self.assertEqual(r[0]['exemplaires'],'2')
  self.assertEqual(r[0]['quantite_stock_totale'],'9')
 def test_double_click_passes_reference_and_black_color(self):
  engine=Mock();engine.visuals.return_value=({'main':Image.new('RGB',(50,50))},'')
  d=BuildStockDialog(self.db,engine);d.detail_rows=[('RB','3001','Brick','RB:0',5,9,0)]
  from PySide6.QtWidgets import QTableWidgetItem
  d.parts.setRowCount(1);d.parts.setItem(0,0,QTableWidgetItem('RB'))
  def task(owner,work,done,*args):done(work(lambda *_:None))
  with patch('atelier.build_stock.async_task',side_effect=task),patch.object(QDialog,'exec',return_value=0):d.parts.itemDoubleClicked.emit(d.parts.item(0,0))
  self.assertEqual(engine.visuals.call_args.args[0]['ref'],'3001');self.assertEqual(engine.visuals.call_args.args[1],'0')
  d.clear_details();self.assertFalse(d.export_owned.isEnabled());d.reject()
 def test_contours_only_parts_even_when_set_selected(self):
  item=self.db.rows("SELECT * FROM items WHERE kind='set'")[0]
  with patch('atelier.contours.async_task'):
   d=ContourDialog(self.db,Mock(),item)
   self.assertEqual([d.category.itemText(i) for i in range(d.category.count())],['Bricks']);self.assertEqual(d.preview_item['kind'],'part');d.reject()
if __name__=='__main__':unittest.main()
