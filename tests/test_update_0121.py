import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile,copy
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import VisualEngine,Preview
from atelier.edge_style import normalize_style
from atelier.edge_controls import EdgeControls
from atelier.labels import default_template,independent_category,render_label
from atelier.boxes import boxes_for_set,BoxDialog
from atelier.cross_source import bricklink_reference
from atelier.brickarchitect import model_ref
app=QApplication.instance() or QApplication([])
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite');self.engine=VisualEngine(self.db)
 def tearDown(self):self.tmp.cleanup()
 def item(self,source,kind,ref):
  id=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',(source,kind,ref,ref,'Brick',ref));return self.db.get_item(id)
 def test_ten_pixel_controls_and_saved_settings(self):
  w=EdgeControls({'black':80,'width':10});self.assertEqual(w.spins['width'].value(),10);w.sliders['width'].setValue(97);self.assertEqual(w.spins['width'].value(),9.7)
  self.db.set_setting('edge_settings',w.settings());self.assertEqual(normalize_style(self.db.setting('edge_settings'))['width'],9.7);self.assertEqual(normalize_style({'width':99})['width'],10)
 def test_legacy_category_fill_stays_when_text_moves(self):
  t=default_template();t.pop('layout_schema');t['layers']=[x for x in t['layers'] if x['type']!='category_band'];old=copy.deepcopy(t);split=independent_category(t)
  self.assertEqual(t,old);band=next(x for x in split['layers'] if x['type']=='category_band');self.assertEqual(band['x'],1)
  text=next(x for x in split['layers'] if x['type']=='category');text.update(x=42,w=20,align='right');self.assertEqual(band['x'],1)
  item=self.item('RB','part','a');im=render_label(item,self.db,{},split);self.assertNotEqual(im.getpixel((25,30)),(255,255,255))
  again=independent_category(split);self.assertEqual(len(again['layers']),len(split['layers']))
 def test_verified_cross_source_photo_and_no_reference_guessing(self):
  rb=self.item('RB','part','113578');native=self.item('BL','part','unknown');self.db.save_visual(rb['id'],color='27')
  calls=[]
  def image(url,download=True):
   calls.append(url)
   return Image.new('RGBA',(40,30),'red') if '/P/113578.gif' in url else None
  with patch.object(self.engine.images,'get',side_effect=image):
   out=self.engine.photo(rb);self.assertIsNotNone(out);self.assertEqual(out.info['bricklabo_photo_source']['source'],'BL');self.assertFalse(any('/PN/27/' in s for s in calls))
  other=self.item('RB','part','unknown');self.assertIsNone(bricklink_reference(self.db,other));self.assertEqual(other['ref'],native['ref'])
  self.db.set_setting('rb_bricklink_refs_part_unknown',['a','b']);self.assertIsNone(bricklink_reference(self.db,other))
 def test_api_mapping_uses_external_identifier_and_caches_it(self):
  item=self.item('RB','part','different');self.db.set_setting('api_rb','key')
  with patch('atelier.cross_source.API.rb',return_value={'external_ids':{'BrickLink':['bl-ref']}}) as call:
   self.assertEqual(bricklink_reference(self.db,item,True),'bl-ref');self.assertEqual(bricklink_reference(self.db,item,True),'bl-ref');call.assert_called_once()
 def test_box_matches_exact_set_and_uses_original_box_url(self):
  set1=self.item('RB','set','8470-1');box=self.item('BL','box','8470-1');self.item('BL','box','8470-2');self.assertEqual([x['id'] for x in boxes_for_set(self.db,set1)],[box['id']]);self.assertFalse(boxes_for_set(self.db,self.item('ALT','set','8470-1')))
  with patch.object(self.engine.images,'get',side_effect=lambda url,download:Image.new('RGB',(80,60)) if '/O/8470-1.gif' in url else None):self.assertIsNotNone(self.engine.photo(box))
  with patch.object(self.engine,'photo',return_value=Image.new('RGB',(80,60))),patch('atelier.boxes.async_task',side_effect=lambda parent,work,done,fail:done(work(None))):
   dialog=BoxDialog(self.db,self.engine,set1);self.assertEqual(dialog.choice.count(),1);self.assertIn('?O=8470-1',dialog.link.text());dialog.reject()
 def test_known_printed_model_preserves_catalogue_reference(self):
  item=self.item('RB','part','98138pr9996');self.assertEqual(model_ref(self.db,item),'98138pa4.dat');self.assertEqual(self.db.get_item(item['id'])['ref'],'98138pr9996');self.assertEqual(model_ref(self.db,self.item('BL','part','98138pr9996')),'98138pr9996')
 def test_individual_buttons_are_below_camera(self):
  w=Preview(self.db,self.engine);layout=w.layout();self.assertEqual(layout.indexOf(w.edit_one),layout.indexOf(w.camera_button)+1);self.assertEqual(layout.indexOf(w.reset_one),layout.indexOf(w.edit_one)+1);self.assertEqual(w.reset_one.text(),'Réinitialiser la disposition');w.close()
