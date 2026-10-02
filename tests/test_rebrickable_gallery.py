import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import Preview,VisualEngine
from atelier.services import rebrickable_photo_links,rebrickable_photos
app=QApplication.instance() or QApplication([])
PHOTO='https://cdn.rebrickable.com/media/parts/photos/0/100097.jpg'
SECOND='https://cdn.rebrickable.com/media/parts/photos/0/100097_2.jpg'
class RebrickableGalleryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite')
  iid=self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('RB','part','100097','Hipwear','100097'))
  self.item=self.db.get_item(iid)
 def tearDown(self):self.temp.cleanup()
 def test_page_keeps_only_exact_part_images_and_accepts_large_thumbs(self):
  large='https://cdn.rebrickable.com/media/thumbs/parts/photos/0/100097.jpg/1000x800p.jpg?123'
  html='<img src="'+PHOTO+'"><a href="'+large+'"><img src="'+SECOND+'"></a><img src="https://cdn.rebrickable.com/media/parts/photos/0/26697.jpg"><img src="https://evil.example/media/parts/100097.jpg"><img src="https://cdn.rebrickable.com/media/parts/100097pr1.jpg">'
  self.assertEqual(rebrickable_photo_links(html,self.item),[PHOTO,large,SECOND])
 def test_escaped_and_relative_urls_are_read_once(self):
  content='"'+PHOTO.replace('/','\\/')+'" <img data-src="//cdn.rebrickable.com/media/parts/photos/0/100097.jpg"><img src="/media/parts/photos/0/100097_2.jpg">'
  self.assertEqual(rebrickable_photo_links(content,self.item),[PHOTO,'https://rebrickable.com/media/parts/photos/0/100097_2.jpg'])
 def test_api_colors_follow_pagination_and_merge_without_duplicates(self):
  self.db.set_setting('api_rb','test-key');next_url='https://rebrickable.com/api/v3/lego/parts/100097/colors/?page=2'
  with patch('atelier.services.API.rb',side_effect=[{'part_img_url':PHOTO},{'results':[{'part_img_url':PHOTO}],'next':next_url},{'results':[{'part_img_url':SECOND}],'next':None}]) as rb,patch('atelier.services.request',return_value=b''):
   urls,errors=rebrickable_photos(self.db,self.item)
  self.assertEqual(urls,[PHOTO,SECOND]);self.assertEqual(errors,[]);self.assertEqual(rb.call_args.args[0],next_url)
 def test_blocked_site_keeps_known_photo_and_reports_error(self):
  self.item['image']=PHOTO
  with patch('atelier.services.request',side_effect=ValueError('HTTP 403')):urls,errors=rebrickable_photos(self.db,self.item)
  self.assertEqual(urls,[PHOTO]);self.assertIn('HTTP 403',errors[0])
 def test_api_pagination_cannot_send_key_to_another_domain(self):
  self.db.set_setting('api_rb','test-key')
  with patch('atelier.services.API.rb',side_effect=[{'part_img_url':PHOTO},{'results':[],'next':'https://evil.example/'}]) as rb,patch('atelier.services.request',return_value=b''):
   urls,errors=rebrickable_photos(self.db,self.item)
  self.assertEqual(rb.call_count,2);self.assertEqual(urls,[PHOTO]);self.assertIn('Pagination',errors[0])
 def test_gallery_selection_is_saved_for_selected_part_only(self):
  engine=VisualEngine(self.db)
  with patch('atelier.preview.async_task'):
   preview=Preview(self.db,engine);preview.set_item(self.item);self.assertFalse(preview.find_rb_photos_button.isHidden());preview.store_photos(self.item,[PHOTO,SECOND]);preview.gallery.setCurrentIndex(preview.gallery.findData(SECOND))
   self.assertEqual(self.db.visual(self.item['id'])['image'],SECOND);self.assertEqual(self.db.visual(self.item['id'])['mode'],'photo_rb')
   preview.close();preview.deleteLater();app.processEvents()
 def test_search_result_after_selection_change_does_not_change_new_part(self):
  engine=VisualEngine(self.db);pending=[]
  def task(parent,work,done,fail):pending.append(done)
  with patch('atelier.preview.async_task',side_effect=task):
   preview=Preview(self.db,engine);preview.set_item(self.item);preview.find_rb_photos();callback=pending[-1]
   iid=self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('RB','part','3001','Brick','3001'));other=self.db.get_item(iid);preview.set_item(other);callback(([PHOTO,SECOND],[]))
   self.assertEqual(self.db.setting('photo_choices_'+str(self.item['id'])),[PHOTO,SECOND]);self.assertEqual(preview.gallery.count(),1);self.assertEqual(self.db.visual(other['id'])['image'],'')
   preview.close();preview.deleteLater();app.processEvents()
