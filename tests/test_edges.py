import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import VisualEngine
from atelier.render import LDraw
from atelier.edges import EdgeDialog
from atelier.thumbnails import PartThumbnails
app=QApplication.instance() or QApplication([])
class EdgeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=Database(self.root/'db.sqlite');model=self.root/'ldraw';(model/'parts').mkdir(parents=True)
  (model/'ldconfig.ldr').write_text('0 Test palette\n')
  face='4 16 -20 0 -20 20 0 -20 20 0 20 -20 0 20\n';edge='2 24 -15 0 0 15 0 0\n';hidden='2 24 0 10 -15 0 10 15\n'
  (model/'parts/a.dat').write_text(face+edge);(model/'parts/b.dat').write_text(face+edge+hidden);self.db.set_setting('ldraw',str(model));self.db.set_setting('camera_default',{})
  iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part','a','Test','Bricks','a'));self.item=self.db.get_item(iid);self.engine=VisualEngine(self.db)
 def tearDown(self):self.temp.cleanup()
 def test_strength_makes_visible_edges_darker_and_wider_without_showing_hidden_edges(self):
  renderer=self.engine.renderer();counts=[];bounds=[]
  for level in range(3):
   im,b=renderer.render('a',(180,150),view='top',edge_strength=level);pixels=np.array(im);counts.append(int(((pixels[:,:,:3].mean(axis=2)<70)&(pixels[:,:,3]>200)).sum()));bounds.append(b)
   hidden,_=renderer.render('b',(180,150),view='top',edge_strength=level);self.assertEqual(im.tobytes(),hidden.tobytes())
  self.assertLess(counts[0],counts[1]);self.assertLess(counts[1],counts[2]);np.testing.assert_array_equal(bounds[0],bounds[2])
  default,_=renderer.render('a',(180,150),view='top');normal,_=renderer.render('a',(180,150),view='top',edge_strength=0);self.assertEqual(default.tobytes(),normal.tobytes())
 def test_setting_is_persistent_shared_by_views_and_invalidates_thumbnails(self):
  before=PartThumbnails.state(SimpleNamespace(db=self.db),self.item);self.db.set_setting('edge_strength',2)
  self.assertNotEqual(before,PartThumbnails.state(SimpleNamespace(db=self.db),self.item));self.assertEqual(Database(self.db.path).setting('edge_strength'),2)
  renderer=self.engine.renderer()
  with patch.object(renderer,'render',wraps=renderer.render) as render:
   self.engine.visuals(self.item,download=False)
   self.assertEqual(render.call_count,3);self.assertTrue(all(c.kwargs['edge_strength']==2 for c in render.call_args_list))
 def test_dialog_preview_does_not_save_before_apply(self):
  def task(owner,work,done,failed):done(work(lambda *_:None))
  with patch('atelier.edges.async_task',side_effect=task):
   d=EdgeDialog(self.db,self.engine,self.item)
   try:
    d.controls.spins['width'].setValue(2.5);d.timer.stop();d.render_preview();self.assertEqual(d.settings()['width'],2.5);self.assertIsNone(self.db.setting('edge_settings'));self.assertIsNotNone(d.preview.pixmap());d.reject();self.assertIsNone(self.db.setting('edge_settings'))
   finally:d.deleteLater();app.processEvents()
if __name__=='__main__':unittest.main()
