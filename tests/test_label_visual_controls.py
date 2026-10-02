import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.edge_style import style_for_item,general_style,normalize_style
from atelier.edge_controls import EdgeControls
from atelier.edges import EdgeDialog
from atelier.editor import LabelEditor
from atelier.labels import default_template,individual_template_key,render_label
from atelier.preview import VisualEngine
from atelier.render import LDraw
from atelier.thumbnails import PartThumbnails
from types import SimpleNamespace
app=QApplication.instance() or QApplication([])
class LabelControlsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=Database(self.root/'db.sqlite')
  iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part','a','Long brick','Bricks','a'));self.item=self.db.get_item(iid);self.engine=VisualEngine(self.db)
  model=self.root/'ldraw';(model/'parts').mkdir(parents=True);(model/'ldconfig.ldr').write_text('0 Palette\n');(model/'parts/a.dat').write_text('4 16 -20 0 -20 20 0 -20 20 0 20 -20 0 20\n2 24 -15 0 0 15 0 0\n');self.db.set_setting('ldraw',str(model));self.db.set_setting('camera_default',{})
 def tearDown(self):self.temp.cleanup()
 def test_legacy_styles_migrate_without_modifying_saved_settings(self):
  self.db.set_setting('edge_strength',2);self.assertEqual(general_style(self.db),{'black':100.,'width':2.,'legacy':2});self.assertIsNone(self.db.setting('edge_settings'))
 def test_global_changes_affect_inherited_labels_and_keep_individual_values(self):
  a=dict(self.item,_scope='queue',entry_id=1);b=dict(self.item,_scope='queue',entry_id=2);template=default_template();template['edge_settings']={'black':64.2,'width':2.1};self.db.set_setting(individual_template_key(a),template)
  self.db.set_setting('edge_settings',{'black':90,'width':1.2});before=PartThumbnails.state(SimpleNamespace(db=self.db),a)
  self.assertEqual(style_for_item(self.db,b),{'black':90.,'width':1.2});self.db.set_setting('edge_settings',{'black':70,'width':.8})
  self.assertEqual(style_for_item(self.db,a),{'black':64.2,'width':2.1});self.assertEqual(style_for_item(self.db,b)['width'],.8)
  self.assertEqual(before,PartThumbnails.state(SimpleNamespace(db=self.db),a));self.assertNotEqual(before,PartThumbnails.state(SimpleNamespace(db=self.db),b))
 def test_slider_and_numeric_values_are_synchronized(self):
  controls=EdgeControls({'black':90,'width':1});controls.sliders['width'].setValue(23);self.assertEqual(controls.settings()['width'],2.3);controls.spins['black'].setValue(62.4);self.assertEqual(controls.sliders['black'].value(),624);controls.deleteLater();app.processEvents()
 def test_continuous_renderer_accepts_fractions_and_zero_intensity_hides_edges(self):
  renderer=self.engine.renderer();plain,_=renderer.render('a',(180,150),view='top',outlines=False);zero,_=renderer.render('a',(180,150),view='top',edge_settings={'black':0,'width':3});self.assertEqual(plain.tobytes(),zero.tobytes())
  one,_=renderer.render('a',(180,150),view='top',edge_settings={'black':55.5,'width':1.1});two,_=renderer.render('a',(180,150),view='top',edge_settings={'black':55.5,'width':1.2});self.assertNotEqual(one.tobytes(),two.tobytes())
 def test_draft_preview_and_saved_export_use_identical_edge_values(self):
  template=default_template();template['edge_settings']={'black':65,'width':2.2}
  preview,note=self.engine.visuals(self.item,template=template);self.db.set_setting(individual_template_key(self.item),template);saved,note=self.engine.visuals(self.item)
  for key in ('main','top','side'):self.assertEqual(preview[key].tobytes(),saved[key].tobytes())
  self.assertEqual(render_label(self.item,self.db,preview,template).tobytes(),render_label(self.item,self.db,saved).tobytes())
 def test_editor_cancel_does_not_save_and_apply_is_individual(self):
  editor=LabelEditor(self.db,self.engine,self.item,individual=True)
  editor.edge_controls.inherit.setChecked(False);editor.edge_controls.spins['width'].setValue(2.4);editor.reject();self.assertIsNone(self.db.setting(individual_template_key(self.item)));self.assertIsNone(self.db.setting('edge_settings'));editor.deleteLater();app.processEvents()
  editor=LabelEditor(self.db,self.engine,self.item,individual=True);editor.edge_controls.inherit.setChecked(False);editor.edge_controls.spins['black'].setValue(71.3);editor.apply();self.assertEqual(style_for_item(self.db,self.item)['black'],71.3);self.assertIsNone(self.db.setting('edge_settings'));editor.deleteLater();app.processEvents()
 def test_named_presets_reload_rename_delete_without_applying_general_style(self):
  d=EdgeDialog(self.db,self.engine,self.item);d.timer.stop()
  d.controls.spins['width'].setValue(1.7);d.store_preset('Fin');d.controls.spins['width'].setValue(2.8);d.store_preset('Fort');d.presets.setCurrentIndex(d.presets.findData('Fin'));self.assertEqual(d.settings()['width'],1.7)
  with self.assertRaises(ValueError):d.store_preset('Fort')
  d.rename_saved('Fin','Impression');d.delete_saved('Fort');self.assertEqual(list(self.db.setting('edge_presets')),['Impression']);self.assertIsNone(self.db.setting('edge_settings'));self.assertEqual(Database(self.db.path).setting('edge_presets')['Impression']['width'],1.7);d.reject();d.deleteLater();app.processEvents()
 def test_cropping_fills_long_views_and_zoom_remains_inside_its_layer(self):
  image=Image.new('RGBA',(240,180));image.paste('red',(15,80,225,100));side=Image.new('RGBA',(240,160));side.paste('blue',(15,70,225,90));visuals={'top':image,'side':side}
  template=default_template();template['layers']=[{'type':'top','x':2,'y':3,'w':20,'h':5},{'type':'side','x':2,'y':12,'w':20,'h':5}]
  old=copy.deepcopy(template)
  for layer in old['layers']:layer['auto_crop']=False
  before=np.array(render_label(self.item,self.db,visuals,old));after=np.array(render_label(self.item,self.db,visuals,template));red=lambda a:((a[:,:,0]>230)&(a[:,:,1]<20)&(a[:,:,2]<20)).sum();blue=lambda a:((a[:,:,2]>230)&(a[:,:,0]<20)&(a[:,:,1]<20)).sum()
  self.assertGreater(red(after),red(before)*2);template['layers'][0]['image_zoom']=250;zoom=np.array(render_label(self.item,self.db,visuals,template));self.assertGreater(red(zoom),red(after));self.assertEqual(blue(zoom),blue(after));outside=np.ones(after.shape[:2],dtype=bool);scale=300/25.4;outside[round(3*scale):round(3*scale)+round(5*scale),round(2*scale):round(2*scale)+round(20*scale)]=False;np.testing.assert_array_equal(zoom[outside],after[outside])
if __name__=='__main__':unittest.main()
