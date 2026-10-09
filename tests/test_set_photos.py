import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import VisualEngine,Preview
from atelier.services import API,rebrickable_set_photo
from atelier.cross_source import bricklink_reference
app=QApplication.instance() or QApplication([])

class SetPhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.engine=VisualEngine(self.db)
        self.image=Image.new('RGB',(32,32),'red')
    def tearDown(self):self.temp.cleanup()
    def item(self,ref):
        url='https://cdn.rebrickable.com/media/sets/'+ref.lower()+'.jpg'
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,image,search) VALUES(?,?,?,?,?,?)',('RB','set',ref,ref,url,ref))
        return self.db.get_item(iid)
    def missing(self,url,download=True):raise urllib.error.HTTPError(url,404,'Missing',{},None)
    def test_030_2_uses_verified_bricklink_photo_and_reuses_shared_cache(self):
        item=self.item('030-2');url='https://img.bricklink.com/ItemImage/SL/030-2.png'
        def download(candidate,headers=None,destination=None,timeout=45):
            if candidate!=url:return self.missing(candidate)
            self.image.save(destination,format='PNG')
        with patch('atelier.services.request',side_effect=download) as images,patch('atelier.preview.request',side_effect=ValueError('Page unavailable')) as page:
            result,note=self.engine.visuals(item,download=True,_composition=False)
            self.assertEqual(result['main'].size,self.image.size)
            self.assertEqual(result['main'].info['bricklabo_photo_source'],{'source':'BL','ref':'030-2'})
            self.assertIn('Photo BrickLink : 030-2',note)
            calls=images.call_count;stamps={p.name:p.stat().st_mtime_ns for p in self.engine.images.folder.iterdir()}
            for cached in (False,True):
                result,_=self.engine.visuals(item,download=cached,_composition=False)
                self.assertEqual(result['main'].size,self.image.size)
            self.assertEqual(images.call_count,calls);page.assert_called_once()
            self.assertEqual(stamps,{p.name:p.stat().st_mtime_ns for p in self.engine.images.folder.iterdir()})
            links=[call.args[0] for call in images.call_args_list if 'bricklink.com' in call.args[0]]
            self.assertEqual(links[-1],url);self.assertTrue(all('/030-2.' in link for link in links))
        stored=self.db.get_item(item['id'])
        self.assertEqual((stored['source'],stored['ref'],stored['image']),('RB','030-2',item['image']))
    def test_bricklink_normalized_small_set_image_is_available_when_large_is_missing(self):
        item=self.item('030-2');url='https://img.bricklink.com/ItemImage/SN/0/030-2.png'
        def get(candidate,download):return self.image if candidate==url else self.missing(candidate)
        with patch.object(self.engine.images,'get',side_effect=get),patch('atelier.preview.request',side_effect=ValueError('Page unavailable')):
            self.assertIs(self.engine.photo(item),self.image)
            self.assertEqual(self.image.info['bricklabo_photo_source'],{'source':'BL','ref':'030-2'})
    def test_available_rebrickable_photo_keeps_priority_over_bricklink(self):
        item=self.item('030-2')
        with patch.object(self.engine.images,'get',return_value=self.image) as images,patch('atelier.preview.request') as page:
            self.assertIs(self.engine.photo(item),self.image)
            images.assert_called_once_with(item['image'],True);page.assert_not_called()
            self.assertNotIn('bricklabo_photo_source',self.image.info)
    def test_set_photo_mapping_requires_one_explicit_same_kind_reference(self):
        item=self.item('unverified-1')
        self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('BL','set',item['ref'],'Different set',item['ref']))
        self.db.set_setting('api_rb','fake-test-key')
        with patch.object(API,'rb') as api,patch('atelier.cross_source.request',side_effect=ValueError('Unavailable test page')):
            self.assertIsNone(bricklink_reference(self.db,item,True))
            self.db.set_setting('rb_bricklink_refs_part_'+item['ref'],['part-photo'])
            self.assertIsNone(bricklink_reference(self.db,item,True))
            self.db.set_setting('rb_bricklink_refs_set_'+item['ref'],['030-2','513-1'])
            self.assertIsNone(bricklink_reference(self.db,item,True))
            self.db.set_setting('rb_bricklink_refs_set_'+item['ref'],['030-2'])
            self.assertEqual(bricklink_reference(self.db,item,True),'030-2');api.assert_not_called()
        self.assertIsNone(bricklink_reference(self.db,self.item('30-2')))
        self.assertIsNone(bricklink_reference(self.db,self.item('030-1')))
        part={**item,'kind':'part','ref':'030-2'}
        self.assertIsNone(bricklink_reference(self.db,part))
    def test_plush_alternative_format_uses_native_lowercase_and_updates_database(self):
        item=self.item('PLUSH-2');url=item['image'].replace('.jpg','.png')
        def get(candidate,download):return self.image if candidate==url else self.missing(candidate)
        with patch.object(self.engine.images,'get',side_effect=get),patch('atelier.preview.request') as request:
            self.assertIs(self.engine.photo(item),self.image);request.assert_not_called()
            self.assertIs(self.engine.photo(item),self.image)
        self.assertEqual(self.db.get_item(item['id'])['image'],url)
    def test_404_existing_address_refreshes_api_metadata(self):
        item=self.item('2160-2');self.db.set_setting('api_rb','fake-test-key');url='https://cdn.rebrickable.com/media/sets/current-photo.jpg'
        def get(candidate,download):return self.image if candidate==url else self.missing(candidate)
        with patch.object(self.engine.images,'get',side_effect=get),patch.object(API,'enrich',return_value=url) as api,patch('atelier.preview.request') as request:
            self.assertIs(self.engine.photo(item),self.image);api.assert_called_once();request.assert_not_called()
    def test_published_page_image_recovers_both_references_and_is_cached(self):
        for ref in ('2160-2','PLUSH-2'):
            item=self.item(ref);url='https://cdn.rebrickable.com/media/sets/'+ref.lower()+'-published.png'
            html=f'<title>LEGO {ref} Set</title><meta property="og:image" content="{url}">'.encode()
            def get(candidate,download):return self.image if candidate==url else self.missing(candidate)
            with patch.object(self.engine.images,'get',side_effect=get),patch('atelier.preview.request',return_value=html) as request:
                self.assertIs(self.engine.photo(item),self.image);self.assertIs(self.engine.photo(item),self.image);request.assert_called_once()
            self.assertEqual(self.db.get_item(item['id'])['image'],url)
    def test_unavailable_page_attempted_once_and_never_in_cache_only_mode(self):
        item=self.item('PLUSH-2')
        with patch.object(self.engine.images,'get',side_effect=self.missing),patch('atelier.preview.request',side_effect=ValueError('HTTP 403')) as request,patch.object(API,'enrich') as api,patch('atelier.cross_source.request',side_effect=ValueError('Unavailable test page')) as external:
            with self.assertRaises(ValueError):self.engine.photo(item,False)
            request.assert_not_called();api.assert_not_called()
            for _ in range(2):
                with self.assertRaises(ValueError):self.engine.photo(item,True)
            request.assert_called_once()
            external.assert_called_once()
    def test_metadata_rejects_other_sets_recommendations_and_external_images(self):
        page='https://rebrickable.com/sets/PLUSH-2/'
        self.assertEqual(rebrickable_set_photo('<title>PLUSH-20</title><meta property="og:image" content="https://cdn.rebrickable.com/other.jpg">','PLUSH-2',page),'')
        self.assertEqual(rebrickable_set_photo('<title>PLUSH-2</title><img src="https://cdn.rebrickable.com/other.jpg">','PLUSH-2',page),'')
        self.assertEqual(rebrickable_set_photo('<title>PLUSH-2</title><meta property="og:image" content="https://example.com/logo.jpg">','PLUSH-2',page),'')
    def test_switch_clears_previous_image_and_ignores_outdated_async_failure(self):
        first=self.item('2160-2');second=self.item('PLUSH-2');callbacks=[]
        with patch('atelier.preview.async_task',side_effect=lambda owner,work,done,failed:callbacks.append((done,failed))):
            preview=Preview(self.db,self.engine);preview.set_item(first);callbacks[-1][0](({'main':self.image},None,''));self.assertIs(preview.image,self.image)
            previous_failure=callbacks[-1][1];preview.set_item(second);self.assertIsNone(preview.image)
            callbacks[-1][0](({'main':self.image},None,''));previous_failure('old error');self.assertIs(preview.image,self.image)
            callbacks[-1][1]('HTTP 404');self.assertIsNone(preview.image);self.assertEqual(preview.photo.text(),'Visuel indisponible');preview.close();preview.deleteLater();app.processEvents()
