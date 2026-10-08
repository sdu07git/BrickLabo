import tempfile,unittest
from pathlib import Path
from atelier.data import Database
from atelier.set_inventory import import_inventory,read_inventory
HEADER='Type\tItem No\tItem Name\tQty\tColor ID\tExtra?\tAlternate?\tMatch ID\tCounterpart?\n'
class InventoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=Database(self.root/'Donnees'/'atelier.sqlite')
  self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('BL','set','75192-1','Falcon','falcon')");self.item=self.db.rows("SELECT * FROM items")[0]
  self.path=self.root/'S-75192-1.txt';self.path.write_text(HEADER+'\nP\t3001\tBrick\t3\t86\tN\tN\t0\tN\t\nP\t3001\tBrick\t1\t11\tY\tN\t0\tN\nM\tsw001\tFigure\t2\t0\tN\tN\t0\tN\nP\t3002\tAlternative\t3\t86\tN\tY\t1\tN\nP\t3003\tSticker equivalent\t3\t86\tN\tN\t1\tY\n')
 def tearDown(self):self.tmp.cleanup()
 def load(self):return import_inventory(self.db,self.item,self.path)
 def test_persistent_without_source_and_flags(self):
  self.load();self.path.unlink();db=Database(self.db.path);parts=db.components(self.item)
  self.assertEqual([(p['ref'],str(p['chosen_color']),p['chosen_quantity']) for p in parts],[('3001','86',3),('3001','11',1),('sw001','0',2)])
  self.assertEqual(db.rows('SELECT COUNT(*) n FROM bl_manual_inventory')[0]['n'],5)
  self.assertEqual(db.containing_sets(parts[0])[0]['id'],self.item['id'])
 def test_stock_exact_quantities_and_removal_after_reimport(self):
  self.load();self.db.add('stock',self.item['id'],quantity=2)
  self.assertEqual(sum(r['quantity'] for r in self.db.rows('SELECT * FROM stock_available')),14)
  self.path.write_text(HEADER+'P\t3001\tBrick\t99\t86\tN\tN\t0\tN\n');self.load()
  entry=self.db.rows('SELECT * FROM stock_sets WHERE item_id=?',(self.item['id'],))[0]
  self.db.remove('stock_sets',[entry['id']],remove_set_parts=True);self.assertEqual(self.db.rows('SELECT * FROM stock WHERE quantity>0'),[]);self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
 def test_reimport_replaces_without_duplicate_or_reset_stock(self):
  self.load();part=self.db.components(self.item)[0];self.db.add('stock',part['id'],'86',5);self.load()
  self.assertEqual(self.db.rows('SELECT COUNT(*) n FROM bl_manual_inventory')[0]['n'],5);self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],5)
 def test_wrong_filename_rejected(self):
  wrong=self.root/'S-1234-1.txt';wrong.write_bytes(self.path.read_bytes())
  with self.assertRaises(ValueError):import_inventory(self.db,self.item,wrong)
  self.assertEqual(self.db.rows('SELECT * FROM bl_manual_inventory'),[])
 def test_invalid_line_atomic(self):
  self.load();self.path.write_text(HEADER+'P\t999\tInvalid\t-1\t0\tN\tN\t0\tN\n')
  with self.assertRaises(ValueError):self.load()
  self.assertEqual(len(self.db.rows('SELECT * FROM bl_manual_inventory')),5)
 def test_general_import_routes_inventory(self):self.assertEqual(self.db.import_file(self.path),5)
 def test_manual_has_priority_over_api_and_rb(self):
  self.db.set_setting('bl_components_75192-1',[{'ref':'other'}]);self.load();self.assertEqual(self.db.components(self.item)[0]['ref'],'3001')
 def test_cp1252(self):
  self.path.write_bytes((HEADER+'P\t3001\tPièce\t1\t86\tN\tN\t0\tN\n').encode('cp1252'));self.load();self.assertEqual(self.db.components(self.item)[0]['name'],'Pièce')
 def test_plain_set_txt(self):
  generic=self.root/'set.txt';generic.write_bytes(self.path.read_bytes());self.assertEqual(len(read_inventory(generic,'75192-1')),5)

 def test_imported_colors_available(self):
  self.load();self.db.set_setting('bl_colors',{'86':{'name':'Light Bluish Gray','rgb':'aabbcc'},'11':{'name':'Black','rgb':'000000'}})
  colors=self.db.available_colors(self.db.components(self.item)[0]);self.assertEqual({c['id'] for c in colors},{'86','11'})

 def test_catalogue_queue_uses_manual_before_api(self):
  from PySide6.QtWidgets import QApplication
  from atelier.catalogue import Catalogue
  app=QApplication.instance() or QApplication([])
  self.load();self.db.set_setting('bl_components_75192-1',[{'id':999999,'chosen_quantity':88}])
  catalogue=Catalogue(self.db,'BL','set','catalogue');catalogue.selection=lambda:[self.item]
  catalogue.add_selected('queue')
  self.assertEqual(sum(row['quantity'] for row in self.db.rows('SELECT * FROM queue')),6);catalogue.close()
