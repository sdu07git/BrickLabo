import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import csv,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.stock_export import stock_rows,stock_sets,validate_rows,validate_sets,write_csv,write_sets_csv,resolve_bricklink,StockExportDialog
app=QApplication.instance() or QApplication([])
class ExportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=Database(self.root/'db.sqlite')
  self.db.run("INSERT INTO colors VALUES(0,'Black','000000',0)");self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)")
 def tearDown(self):self.tmp.cleanup()
 def item(self,source,kind,ref,name='Brick'):
  return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,name,name))
 def seed(self):
  p=self.item('RB','part','3001');s=self.item('RB','set','123-1','Set')
  self.db.run("INSERT INTO inventories(id,version,set_num) VALUES(1,1,'123-1')")
  self.db.run('INSERT INTO inventory_parts VALUES(1,?,?,?,0,?)',('3001',4,5,''))
  self.db.add('stock',s,'',2);self.db.add('stock',p,'4',3)
  return p,s
 def test_sets_are_not_counted_twice_and_csv_headers(self):
  p,s=self.seed();rows,notes,count=stock_rows(self.db)
  self.assertFalse(notes);self.assertEqual(count,1);self.assertEqual(rows[0]['quantity'],3)
  valid,issues=validate_rows(rows,{'3001'},{'4'});self.assertEqual(valid,[('3001','4',3)]);self.assertFalse(issues)
  sets,known=stock_sets(self.db);validsets,issues=validate_sets(sets,known);self.assertEqual(validsets,[('123-1',2)])
  write_csv(self.root/'parts.csv',valid);write_sets_csv(self.root/'sets.csv',validsets)
  with (self.root/'parts.csv').open() as f:self.assertEqual(list(csv.reader(f)),[['Part','Color','Quantity'],['3001','4','3']])
  with (self.root/'sets.csv').open() as f:self.assertEqual(list(csv.reader(f)),[['Set','Quantity'],['123-1','2']])
 def test_bricklink_color_id_is_never_assumed_rb_id(self):
  self.item('RB','part','3001');b=self.item('BL','part','3001');self.db.add('stock',b,'4',2)
  rows,_,_=stock_rows(self.db);self.assertEqual(rows[0]['part'],'3001');self.assertEqual(rows[0]['rb_color'],'25')
  self.db.set_setting('export_rb_bl_colors',{'4':['0']});rows,_,_=stock_rows(self.db);self.assertEqual(rows[0]['rb_color'],'25')
 def test_api_mapping_multiple_results_never_selects_first(self):
  b=self.item('BL','part','x');self.db.add('stock',b,'11',2)
  event=threading.Event()
  def response(path):
   if path.startswith('colors'):return {'results':[{'id':0,'external_ids':{'BrickLink':{'ext_ids':[11]}}}],'next':None}
   return {'results':[{'part_num':'a'},{'part_num':'b'}],'next':None}
  with patch('atelier.stock_export.API.rb',side_effect=response),patch.object(event,'wait',return_value=False):parts,colors=resolve_bricklink(self.db,{'x'},event,lambda _:None)
  self.assertEqual(parts['x'],['a','b']);self.assertEqual(colors['11'],['0'])
  rows,_,_=stock_rows(self.db);self.assertEqual(rows[0]['part'],'');self.assertEqual(rows[0]['rb_color'],'0')
 def test_minifig_breakdown_and_missing_composition_report(self):
  p=self.item('RB','part','head');f=self.item('RB','minifig','fig-1');g=self.item('RB','minifig','fig-2')
  self.db.set_setting('rb_minifig_components_fig-1',[dict(self.db.get_item(p),chosen_color='4',chosen_quantity=2)])
  self.db.add('stock',f,'',3);self.db.add('stock',g,'',1)
  rows,_,_=stock_rows(self.db);valid,issues=validate_rows(rows,{'head'},{'4'})
  self.assertEqual(valid,[('head','4',6)]);self.assertEqual(len(issues),1);self.assertFalse(issues[0]['convertible'])
 def test_edited_stock_and_legacy_sets_raise_review_notes(self):
  p,s=self.seed();self.db.run('UPDATE stock SET quantity=1 WHERE item_id=?',(p,));rows,notes,_=stock_rows(self.db);self.assertFalse(notes);self.assertEqual(rows[0]['quantity'],1)
  self.db.run('DELETE FROM stock_set_components');rows,notes,_=stock_rows(self.db);self.assertIn('sans suivi',notes[0]);self.assertEqual(rows[0]['quantity'],1)
 def test_dialog_two_tabs_and_save_two_lists(self):
  self.seed()
  def task(owner,work,done,fail,*args):done(work(lambda _:None))
  with patch('atelier.stock_export.async_task',side_effect=task):
   d=StockExportDialog(self.db);self.assertEqual(d.tabs.count(),2);self.assertEqual(d.table.rowCount(),1);self.assertEqual(d.set_table.rowCount(),1)
   with patch('atelier.stock_export.QFileDialog.getExistingDirectory',return_value=str(self.root)),patch('atelier.stock_export.QMessageBox.information') as info:
    d.save();self.assertTrue(info.called)
   self.assertTrue((self.root/'stock_pieces.csv').exists());self.assertTrue((self.root/'stock_sets.csv').exists());self.assertTrue((self.root/'stock_rapport.txt').exists());d.reject()
if __name__=='__main__':unittest.main()
