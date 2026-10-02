import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem
from atelier.thumbnail_cache import ThumbnailCache
from atelier.data import Database
from atelier.preview import VisualEngine
from atelier.thumbnails import PartThumbnails
from atelier.render import LDraw
app=QApplication.instance() or QApplication([])
class CacheTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_ram_lru_is_bounded_and_evicted_images_reload_from_disk(self):
  cache=ThumbnailCache(self.root/'cache',ram_limit=52000);image=Image.new('RGB',(1600,1000),'red')
  for i in range(20):cache.put((i,'color'),image)
  self.assertEqual(len(cache.memory),2);self.assertLessEqual(cache.memory_bytes,52000);self.assertEqual(cache.get((0,'color')).size,(100,65));self.assertEqual(len(cache.memory),2)
  fresh=ThumbnailCache(cache.folder);self.assertEqual(fresh.get((0,'color')).size,(100,65))
 def test_disk_quota_evicts_oldest_files(self):
  image=Image.fromarray(np.random.default_rng(1).integers(0,256,(65,100,3),dtype=np.uint8));cache=ThumbnailCache(self.root/'cache',disk_limit=50000)
  for i in range(10):cache.put((i,),image)
  self.assertLessEqual(cache.usage()[1],50000);self.assertFalse(cache.path((0,)).exists());self.assertTrue(cache.path((9,)).exists())
 def test_corrupt_image_is_discarded_and_key_tracks_visual_settings(self):
  cache=ThumbnailCache(self.root/'cache');cache.path((1,'red')).write_bytes(b'bad');self.assertIsNone(cache.get((1,'red')))
  cache.put((1,'red'),Image.new('RGB',(100,65),'red'));self.assertIsNone(cache.get((1,'blue')))
 def test_clear_preserves_originals_and_rejects_inflight_write(self):
  original=self.root/'image.png';original.write_bytes(b'original');cache=ThumbnailCache(self.root/'cache');generation=cache.generation;cache.put((1,),Image.new('RGB',(100,65)))
  cache.invalidate();cache.put((2,),Image.new('RGB',(100,65)),generation)
  self.assertEqual(cache.usage(),(0,0));self.assertEqual(original.read_bytes(),b'original')
 def test_item_invalidation_keeps_other_piece_cache(self):
  cache=ThumbnailCache(self.root/'cache');image=Image.new('RGB',(100,65));cache.put((1,'a'),image);cache.put((2,'a'),image);cache.invalidate(1)
  self.assertIsNone(cache.get((1,'a')));self.assertIsNotNone(cache.get((2,'a')))
 def test_mesh_budget_evicts_geometry_and_rebuilds_identically(self):
  model=self.root/'ldraw';(model/'parts').mkdir(parents=True);(model/'ldconfig.ldr').write_text('0 Palette\n')
  face='4 16 -10 0 -10 10 0 -10 10 0 10 -10 0 10\n'
  for ref in ('a','b','c'):(model/'parts'/(ref+'.dat')).write_text(face)
  renderer=LDraw(model);renderer.mesh_limit=700;first=renderer.mesh('a')
  renderer.mesh('b');renderer.mesh('c');self.assertLessEqual(renderer.mesh_bytes,700);self.assertNotIn('a',renderer.mesh_cache)
  rebuilt=renderer.mesh('a');np.testing.assert_array_equal(first[3],rebuilt[3]);renderer.clear_mesh_cache();self.assertEqual(renderer.mesh_bytes,0)
 def test_visible_rows_only_small_icons_and_disk_reuse_after_restart(self):
  db=Database(self.root/'db.sqlite');engine=VisualEngine(db);rows=[]
  for i in range(100):
   iid=db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('RB','part',str(i),'Brick','brick'));rows.append(db.get_item(iid))
  table=QTableWidget(100,1);table.resize(230,250)
  for i in range(100):table.setItem(i,0,QTableWidgetItem(''));table.setRowHeight(i,72)
  table.show();app.processEvents();calls=[]
  def task(owner,work,done,failed,progress=None):done(work(progress or (lambda *_:None)))
  def photo(item,*a,**kw):calls.append(item['id']);return Image.new('RGB',(1600,900),'red')
  thumbs=PartThumbnails(table,db,engine,lambda:rows,0,table)
  with patch('atelier.thumbnails.async_task',side_effect=task),patch.object(engine,'renderer',return_value=None),patch.object(engine,'photo',side_effect=photo):
   thumbs.load();self.assertLess(len(calls),10);self.assertTrue(table.item(50,0).icon().isNull());self.assertEqual(next(iter(engine.thumbnail_cache.memory.values()))[0].size,(100,65))
   first_calls=len(calls);engine.thumbnail_cache.memory.clear();engine.thumbnail_cache.memory_bytes=0;thumbs.reset();thumbs.load();self.assertEqual(len(calls),first_calls)
   table.verticalScrollBar().setValue(table.verticalScrollBar().maximum());thumbs.load();self.assertTrue(table.item(0,0).icon().isNull());self.assertFalse(table.item(99,0).icon().isNull())
   thumbs.suspend();self.assertTrue(table.item(99,0).icon().isNull());self.assertLessEqual(engine.thumbnail_cache.memory_bytes,8*1024*1024)
  thumbs.stop();table.close();table.deleteLater();app.processEvents()
 def test_replaced_ldraw_archive_reopens_renderer_instead_of_using_old_geometry(self):
  import zipfile
  archive=self.root/'complete.zip'
  def write(width):
   with zipfile.ZipFile(archive,'w') as z:
    z.writestr('LDConfig.ldr','0 Palette\n');z.writestr('parts/a.dat',f'4 16 -{width} 0 -10 {width} 0 -10 {width} 0 10 -{width} 0 10\n')
  write(10);db=Database(self.root/'db.sqlite');db.set_setting('ldraw',str(archive));engine=VisualEngine(db);old=engine.renderer();first=old.mesh('a')[3].copy()
  write(30);new=engine.renderer();self.assertIsNot(old,new);self.assertGreater(new.mesh('a')[3][0],first[0])
if __name__=='__main__':unittest.main()
