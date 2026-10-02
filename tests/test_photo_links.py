import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication,QPushButton,QInputDialog
from atelier.data import Database
from atelier.preview import Preview,VisualEngine
app=QApplication.instance() or QApplication([])
URL='https://cdn.rebrickable.com/media/thumbs/sets/2160-2/176631.jpg/1000x800p.jpg?1788981699.512492'
class PhotoLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.engine=VisualEngine(self.db)
        self.tasks=patch('atelier.preview.async_task');self.tasks.start();self.preview=Preview(self.db,self.engine)
    def tearDown(self):
        self.tasks.stop();self.preview.close();self.preview.deleteLater();app.processEvents();self.temp.cleanup()
    def item(self,ref='2160-2',source='RB'):
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,'set',ref,ref,ref));return self.db.get_item(iid)
    def test_legacy_image_link_moves_to_photo_and_preserves_site_links(self):
        item=self.item();site='https://example.com/set'
        self.db.save_visual(item['id'],links=[URL,site]);self.preview.set_item(item)
        v=self.db.visual(item['id']);self.assertEqual(v['image'],URL);self.assertEqual(v['mode'],'photo_rb');self.assertEqual(v['links'],[site]);self.assertEqual(self.preview.gallery.currentData(),URL)
        self.assertIn(URL,self.db.setting('photo_choices_'+str(item['id'])))
    def test_add_site_button_routes_direct_image_to_photo_only_selected_item(self):
        item=self.item();other=self.item('other');self.preview.set_item(item);updates=[];self.preview.visual_changed.connect(updates.append)
        with patch.object(QInputDialog,'getText',return_value=(URL,True)):self.preview.add_link()
        self.assertEqual(self.db.visual(item['id'])['image'],URL);self.assertEqual(self.db.visual(item['id'])['links'],[]);self.assertEqual(self.db.visual(other['id'])['image'],'');self.assertEqual(updates[-1]['id'],item['id'])
    def test_manual_site_link_can_be_removed_without_removing_native_links(self):
        item=self.item();site='https://example.com/my-site';self.db.save_visual(item['id'],links=[site]);self.preview.set_item(item)
        buttons=self.preview.links.findChildren(QPushButton);next(b for b in buttons if b.text()=='Supprimer').click()
        self.assertEqual(self.db.visual(item['id'])['links'],[])
        self.assertIn('Rebrickable',[b.text() for b in self.preview.links.findChildren(QPushButton) if not b.isHidden()])
    def test_remove_photo_returns_to_automatic_without_deleting_other_gallery_entries(self):
        item=self.item();self.preview.set_item(item);other=URL.replace('176631','another');self.preview.store_photos(item,[other]);self.preview.use_link_photo(URL)
        self.assertTrue(self.preview.remove_photo_button.isEnabled());self.preview.remove_photo_button.click()
        self.assertEqual(self.db.visual(item['id'])['image'],'');self.assertEqual(self.db.setting('photo_choices_'+str(item['id'])),[other]);self.assertFalse(self.preview.remove_photo_button.isEnabled())
    def test_photo_selection_uses_each_native_source(self):
        for source in ('RB','BL','ALT'):
            item=self.item('set-'+source,source);self.preview.set_item(item);self.preview.use_link_photo(URL)
            self.assertEqual(self.db.visual(item['id'])['mode'],{'RB':'photo_rb','BL':'photo_bl','ALT':'local'}[source]);self.assertEqual(self.preview.gallery.currentData(),URL)
    def test_verified_2160_address_is_used_and_saved_for_table_and_preview(self):
        item=self.item();image=Image.new('RGB',(1000,800),'white')
        with patch.object(self.engine.images,'get',side_effect=lambda url,download:image if url==URL else None) as get:
            self.assertIs(self.engine.photo(item),image)
        self.assertEqual(get.call_args.args[0],URL);self.assertEqual(self.db.get_item(item['id'])['image'],URL)
