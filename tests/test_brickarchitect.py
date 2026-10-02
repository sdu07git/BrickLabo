import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.brickarchitect import parse_page,parse_detail,replace_catalogue,record_for,model_ref,native_item,update_from_site
from atelier.preview import VisualEngine,Preview
app=QApplication.instance() or QApplication([])
class BrickArchitectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=Database(self.root/'db.sqlite')
 def tearDown(self):self.temp.cleanup()
 def record(self,ref='79717',**kw):return {'ref':ref,'name':'Amortisseur','rank':3,'category':'Technic','models':['79717-f1.dat','79717-f2.dat'],'BL':['79717c01'],'RB':['79717c01'],**kw}
 def put(self,*records):return replace_catalogue(self.db,{'date':'2026-10-01','records':list(records)})
 def test_listing_extracts_only_part_rows_and_preserves_pagination_rank(self):
  html='<a href="https://brickarchitect.com/parts/3001"><div class="tr"><span class="partname">2×4 Brick</span></div></a><a href="https://brickarchitect.com/parts/search">Search</a>'
  self.assertEqual(parse_page(html,22)[0]['rank'],5251)
  with self.assertRaises(ValueError):parse_page('No results',1)
 def test_detail_maps_explicit_external_ids_and_all_variants(self):
  html='<h1>Amortisseur (Part 79717)</h1><a href="https://library.ldraw.org/parts/list?tableSearch=79717-f1.dat">3D</a><a href="https://library.ldraw.org/parts/list?tableSearch=79717-f2.dat">3D</a><a href="https://www.bricklink.com/v2/catalog/catalogitem.page?P=79717c01">BL</a><a href="https://rebrickable.com/parts/79717c04">RB</a><a href="https://evil.test/parts/fake">Ignore</a>'
  r=parse_detail(html,'79717');self.assertEqual(r['models'],['79717-f1.dat','79717-f2.dat']);self.assertEqual(r['RB'],['79717c04']);self.assertEqual(r['BL'],['79717c01'])
 def test_reimport_keeps_item_ids_stock_visual_settings_and_hides_removed_refs(self):
  self.put(self.record(),self.record('2663',models=[]));item=self.db.rows("SELECT * FROM items WHERE source='BA' AND ref='79717'")[0];old=self.db.rows("SELECT * FROM items WHERE source='BA' AND ref='2663'")[0]
  self.db.add('stock',item['id']);self.db.add('stock',old['id']);self.db.save_visual(item['id'],color='#ff0000');self.db.set_setting('architect_model_'+str(item['id']),'79717-f2.dat')
  self.put(self.record(name='Nouveau nom'));self.assertEqual(self.db.query('BA','part')[1],1);self.assertEqual(self.db.query(scope='stock')[1],2);self.assertEqual(self.db.get_item(item['id'])['name'],'Nouveau nom');self.assertEqual(model_ref(self.db,item),'79717-f2.dat');self.assertEqual(self.db.visual(item['id'])['color'],'#ff0000')
  with self.assertRaises(ValueError):self.put(self.record(),self.record())
  self.assertEqual(self.db.query('BA','part')[1],1)
 def test_rank_sort_and_search_are_global(self):
  self.put(*(self.record(str(i),rank=10-i) for i in range(10)))
  rows,total,pages,page=self.db.query('BA','part',size=3,page=2,sort='architect_rank');self.assertEqual(total,10);self.assertEqual([x['architect_rank'] for x in rows],[4,5,6]);self.assertEqual(self.db.query('BA','part',search='Technic')[1],10)
 def test_2663_falls_back_to_declared_bricklink_photo_when_rebrickable_fails(self):
  self.put(self.record('2663',name='Turkey Body',models=[],BL=['2663'],RB=['2663']))
  item=self.db.query('BA','part')[0][0];engine=VisualEngine(self.db);image=Image.new('RGB',(30,20),'red')
  def get(url,download):
   if 'bricklink.com' in url:return image
   return None
  with patch.object(engine.images,'get',side_effect=get):
   visuals,note=engine.visuals(item,download=True);self.assertIs(visuals['main'],image)
  self.assertEqual(self.db.get_item(item['id'])['ref'],'2663');self.assertEqual(self.db.visual(item['id'])['image'],'')
 def test_variants_require_explicit_model_choice_for_ambiguous_native_ids(self):
  self.put(self.record('3245',models=['3245a.dat','3245b.dat'],BL=['3245b','3245c'],RB=['3245a','3245b']))
  item=self.db.query('BA','part')[0][0];self.assertIsNone(native_item(self.db,item,'BL'));self.assertEqual(native_item(self.db,item,'RB')['ref'],'3245a')
  self.db.set_setting('architect_model_'+str(item['id']),'3245b.dat');self.assertEqual(native_item(self.db,item,'BL')['ref'],'3245b');self.assertEqual(item['ref'],'3245')
 def test_render_uses_selected_model_and_keeps_original_label_reference(self):
  self.put(self.record());item=self.db.query('BA','part')[0][0];engine=VisualEngine(self.db)
  self.db.set_setting('architect_model_'+str(item['id']),'79717-f2.dat')
  from unittest.mock import Mock
  renderer=Mock();renderer.render.return_value=(Image.new('RGB',(20,20)),[1,2,3])
  with patch.object(engine,'renderer',return_value=renderer):engine.render_3d(item,(20,20))
  self.assertEqual(renderer.render.call_args.args[0],'79717-f2.dat');self.assertEqual(item['ref'],'79717')
 def test_not_found_external_link_does_not_invent_a_model(self):
  html='<h1>Turkey (Part 2663)</h1><div class="part_detail_externalpart"><a href="https://library.ldraw.org/parts/list?tableSearch=2663.dat">2663</a> Part not found on LDraw.</div>'
  self.assertEqual(parse_detail(html,'2663')['models'],[])
 def test_failed_site_update_leaves_previous_snapshot_intact(self):
  self.put(self.record());html='<a href="https://brickarchitect.com/parts/2663"><div class="tr"><span class="partname">Duplo</span></div></a>'
  with patch('atelier.brickarchitect.request',side_effect=[html.encode(),RuntimeError('HTTP error')]):
   with self.assertRaises(RuntimeError):update_from_site(self.db,pages=1)
  self.assertEqual(record_for(self.db,'79717')['ref'],'79717')
 def test_model_choice_changes_only_selected_piece_and_survives_reload(self):
  self.put(self.record(),self.record('other'));item=self.db.rows("SELECT * FROM items WHERE source='BA' AND ref='79717'")[0]
  engine=VisualEngine(self.db)
  def task(owner,work,done,failed,*args,**kwargs):done(({},None,''))
  with patch('atelier.preview.async_task',side_effect=task):
   preview=Preview(self.db,engine)
   try:
    preview.set_item(item);preview.model_choice.setCurrentIndex(1);self.assertEqual(model_ref(self.db,item),'79717-f2.dat');self.assertEqual(model_ref(self.db,self.db.query('BA','part',search='other')[0][0]),'79717-f1.dat')
    preview.set_item(item);self.assertEqual(preview.model_choice.currentData(),'79717-f2.dat')
   finally:preview.close();preview.deleteLater();app.processEvents()
 def test_m3007_preview_can_show_named_variant_without_resolving_inventory(self):
  self.put(self.record('m3007',models=[],BL=['3007mia','3007mib'],RB=[]))
  item=self.db.query('BA','part')[0][0];engine=VisualEngine(self.db);image=Image.new('RGB',(30,20),'red')
  self.assertIsNone(native_item(self.db,item,'BL'))
  with patch.object(engine.images,'get',return_value=image) as get:
   visuals,note=engine.visuals(item,download=True)
   self.assertIn('/3007mia.',get.call_args.args[0]);self.assertIn('BrickLink : 3007mia',note)
  self.assertIsNone(native_item(self.db,item,'BL'));self.assertEqual(item['ref'],'m3007')
 def test_m3007_explicit_variant_is_persisted_and_used_by_photo(self):
  self.put(self.record('m3007',models=[],BL=['3007mia','3007mib'],RB=[]),self.record('other'))
  item=self.db.query('BA','part',search='m3007')[0][0];engine=VisualEngine(self.db)
  self.db.save_visual(item['id'],color='#123456',image='old.png')
  def task(owner,work,done,failed,*args,**kwargs):done(({},None,''))
  with patch('atelier.preview.async_task',side_effect=task):
   preview=Preview(self.db,engine)
   try:
    preview.set_item(item);preview.photo_variant.setCurrentIndex(preview.photo_variant.findData('BL:3007mib'))
    self.assertEqual(self.db.visual(item['id'])['mode'],'photo_bl');self.assertEqual(self.db.visual(item['id'])['image'],'');self.assertEqual(self.db.visual(item['id'])['color'],'#123456')
    preview.set_item(item);self.assertEqual(preview.photo_variant.currentData(),'BL:3007mib')
    other=self.db.query('BA','part',search='other')[0][0];self.assertEqual(self.db.setting('architect_photo_choice_'+str(other['id']),''),'')
   finally:preview.close();preview.deleteLater();app.processEvents()
  with patch.object(engine.images,'get',return_value=Image.new('RGB',(30,20))) as get:
   visuals,note=engine.visuals(item,download=True);self.assertIn('/3007mib.',get.call_args.args[0]);self.assertIn('BrickLink : 3007mib',note)
  self.assertEqual(self.db.get_item(item['id'])['ref'],'m3007')
  from types import SimpleNamespace
  from atelier.thumbnails import PartThumbnails
  holder=SimpleNamespace(db=self.db);old=PartThumbnails.state(holder,item)
  self.db.set_setting('architect_photo_choice_'+str(item['id']),'BL:3007mia')
  self.assertNotEqual(old,PartThumbnails.state(holder,item))
 def test_invalid_photo_reference_cannot_redirect_to_unlisted_part(self):
  self.put(self.record('m3007',models=[],BL=['3007mia','3007mib']))
  item=self.db.query('BA','part')[0][0];self.db.set_setting('architect_photo_choice_'+str(item['id']),'BL:3007')
  self.assertIsNone(native_item(self.db,item,'BL'));self.assertEqual(native_item(self.db,item,'BL',preview=True)['ref'],'3007mia')
if __name__=='__main__':unittest.main()
