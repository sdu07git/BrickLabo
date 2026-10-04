import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.build_stock import find_builds,build_details,BuildStockDialog
app=QApplication.instance() or QApplication([])
class BuildTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite');self.next_inv=0
  self.db.run("INSERT INTO colors VALUES(0,'Black','000000',0)");self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)")
 def tearDown(self):self.tmp.cleanup()
 def item(self,kind,ref,source='RB',name='Brick'):
  return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,name,name))
 def inv(self,ref,parts):
  self.next_inv+=1;i=self.next_inv;self.db.run('INSERT INTO inventories VALUES(?,?,?)',(i,1,ref))
  for part,color,qty,spare in parts:self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(i,part,color,qty,spare,''))
  return i
 def seed(self):
  p=self.item('part','3001');s=self.item('set','100-1',name='Castle');self.inv('100-1',[('3001',4,5,0)]);return p,s
 def test_quantities_set_stock_not_doubled_and_copies(self):
  p,s=self.seed();self.db.add('stock',s,quantity=1)
  result,_,_,_=find_builds(self.db);self.assertEqual(len(result),1);self.assertEqual(result[0]['total'],5)
  self.assertEqual(find_builds(self.db,copies=2)[0],[])
  result=find_builds(self.db,copies=2,minimum=0)[0][0];self.assertEqual(result['missing'],5);self.assertEqual(result['percent'],50)
 def test_color_modes_and_detail_missing(self):
  p,s=self.seed();self.db.add('stock',p,'0',5)
  self.assertFalse(find_builds(self.db)[0]);self.assertEqual(len(find_builds(self.db,ignore_colors=True)[0]),1)
  detail,ok=build_details(self.db,self.db.get_item(s));self.assertTrue(ok);self.assertEqual(detail[0][-1],5)
 def test_duplicate_requirements_aggregate_and_spares_not_required(self):
  p,s=self.seed();self.db.run('INSERT INTO inventory_parts VALUES(1,?,?,?,?,?)',('3001',4,3,0,''));self.db.run('INSERT INTO inventory_parts VALUES(1,?,?,?,?,?)',('rare',0,1,1,''))
  self.db.add('stock',p,'4',5);row=find_builds(self.db,minimum=0)[0][0];self.assertEqual(row['total'],8);self.assertEqual(row['missing'],3)
 def test_missing_catalogue_parts_are_still_required(self):
  p,s=self.seed();self.db.add('stock',p,'4',5);self.db.run('INSERT INTO inventory_parts VALUES(1,?,?,?,?,?)',('not_in_items',4,1,0,''))
  self.assertFalse(find_builds(self.db)[0]);self.assertEqual(find_builds(self.db,minimum=0)[0][0]['missing'],1)
 def test_unknown_minifig_inventory_excludes_set(self):
  p,s=self.seed();self.db.add('stock',p,'4',5);self.db.run('INSERT INTO inventory_minifigs VALUES(1,?,1)',('fig-1',))
  rows,_,excluded,_=find_builds(self.db,minimum=0);self.assertFalse(rows);self.assertEqual(excluded,1)
 def test_minifig_and_nested_set_multipliers(self):
  p,s=self.seed();f=self.item('minifig','fig-1');child=self.item('set','child-1');self.inv('fig-1',[('3001',4,2,0)]);self.inv('child-1',[('3001',4,3,0)])
  self.db.run('INSERT INTO inventory_minifigs VALUES(1,?,2)',('fig-1',));self.db.run('INSERT INTO inventory_sets VALUES(1,?,2)',('child-1',))
  self.db.add('stock',p,'4',11);self.db.add('stock',f,'',2)
  row=next(r for r in find_builds(self.db)[0] if r['ref']=='100-1');self.assertEqual(row['total'],15)
 def test_bricklink_requires_color_mapping_and_keeps_ambiguous_refs_distinct(self):
  p,s=self.seed();b=self.item('part','bl-special','BL');self.db.add('stock',b,'4',5);self.db.set_setting('export_rb_bl_parts',{'bl-special':['3001']})
  self.assertFalse(find_builds(self.db)[0]);self.db.run("UPDATE stock SET color='5' WHERE item_id=?",(b,));self.assertTrue(find_builds(self.db)[0])
  self.db.set_setting('export_rb_bl_parts',{'bl-special':['3001','other']});self.assertFalse(find_builds(self.db)[0])
 def test_cyclic_inventory_and_no_inventory_never_match(self):
  p,s=self.seed();self.db.run('INSERT INTO inventory_sets VALUES(1,?,1)',('100-1',));self.item('set','empty');self.db.add('stock',p,'4',50)
  rows,_,excluded,_=find_builds(self.db,minimum=0);self.assertFalse(rows);self.assertEqual(excluded,2)
 def test_cancellation_and_stock_unchanged(self):
  p,s=self.seed();self.db.add('stock',p,'4',5);before=self.db.rows('SELECT * FROM stock');cancel=threading.Event();cancel.set()
  self.assertTrue(find_builds(self.db,cancel=cancel)[3]);find_builds(self.db);self.assertEqual(before,self.db.rows('SELECT * FROM stock'))
 def test_ui_results_and_details(self):
  p,s=self.seed();self.db.add('stock',p,'4',5)
  def task(owner,work,done,fail,*args):
   try:data=work(lambda _:None)
   except Exception as e:fail(str(e));raise
   else:done(data)
  with patch('atelier.build_stock.async_task',side_effect=task):
   d=BuildStockDialog(self.db);d.start();self.assertEqual(d.table.rowCount(),1);self.assertEqual(d.parts.rowCount(),1);self.assertEqual(d.parts.item(0,6).text(),'0');d.reject()
if __name__=='__main__':unittest.main()
