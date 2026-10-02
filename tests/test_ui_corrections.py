import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import QTimer,QPoint,Qt,QThreadPool
from PySide6.QtWidgets import QApplication,QMenu
from atelier.data import Database
from atelier.preview import VisualEngine,Preview
from atelier.catalogue import Catalogue
from atelier.dialogs import RelationsDialog
from atelier.editor import LabelEditor
from atelier.labels import default_template,template_for_item,render_label
from atelier.documents import pdf_links

app=QApplication.instance() or QApplication([])

def wait_for(predicate):
    until=time.monotonic()+5
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('UI callback did not complete')

class Renderer:
    def render(self,ref,size,color,view='perspective',camera=None,edge_strength=0):
        return Image.new('RGB',size,color),[20,24,20]

class CorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'data.sqlite');self.engine=VisualEngine(self.db)
        self.windows=[]
        for kind,ref,name in [('part','3005','Brick 1 x 1'),('minifig','fig-test','Figure test'),('set','1234-1','Set test')]:
            self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB',kind,ref,name,'Une très longue catégorie de mini-figures avec de nombreux thèmes et licences',ref+' '+name))
        self.part=self.db.rows("SELECT * FROM items WHERE kind='part'")[0];self.fig=self.db.rows("SELECT * FROM items WHERE kind='minifig'")[0];self.set=self.db.rows("SELECT * FROM items WHERE kind='set'")[0]
        self.db.run('INSERT INTO inventories VALUES(?,?,?)',(1,1,'fig-test'))
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(1,'3005',4,2,0,''))
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
        for window in self.windows:window.close();window.deleteLater()
        app.processEvents();self.tmp.cleanup()
    def keep(self,w):self.windows.append(w);return w
    def test_minifig_opens_its_own_parts(self):
        d=self.keep(RelationsDialog(self.db,self.engine,self.fig,None))
        self.assertTrue(d.is_set);self.assertEqual(d.parts[0]['ref'],'3005');self.assertEqual(d.parts[0]['chosen_quantity'],2);self.assertFalse(d.set_table.isHidden())
    def test_header_context_menu_and_search_width(self):
        cat=self.keep(Catalogue(self.db,kind='minifig'));cat.resize(800,550);cat.show();app.processEvents()
        self.assertGreaterEqual(cat.search.width(),260);self.assertLessEqual(cat.category.width(),260)
        def select_action():
            menu=app.activePopupWidget();self.assertIsInstance(menu,QMenu)
            action=next(a for a in menu.actions() if a.text()=='Année');action.trigger();menu.close()
        QTimer.singleShot(30,select_action)
        cat.table.horizontalHeader().customContextMenuRequested.emit(QPoint(25,10))
        self.assertIn('year',cat.visible_columns);self.assertIn('year',self.db.setting(cat.key))
    def test_set_documents_below_catalogue(self):
        cat=self.keep(Catalogue(self.db,'RB','set'));cat.show();cat.table.selectRow(0);app.processEvents()
        self.assertIsNotNone(cat.documents);self.assertEqual(cat.documents.item['ref'],'1234-1')
        pdf=cat.documents.folder()/'notice.pdf';pdf.write_bytes(b'%PDF-1.4 test');cat.documents.reload()
        self.assertEqual(cat.documents.table.rowCount(),1)
    def test_photo_fallback_downloads_even_after_ldraw_failure(self):
        class BrokenRenderer:
            def render(self,*a,**kwargs):raise ValueError('No model')
        cat=self.keep(Catalogue(self.db,'RB','part'));cat.engine=self.engine
        self.db.run('UPDATE items SET image=? WHERE id=?',('https://example.test/photo.png',self.part['id']))
        cat.reload();calls=[]
        with patch.object(self.engine,'renderer',return_value=BrokenRenderer()),patch.object(self.engine.images,'get',side_effect=lambda url,download:(calls.append((url,download)) or Image.new('RGB',(100,65),'red'))):
            cat.show();cat.load_thumbnails();wait_for(lambda:not cat.table.item(0,cat.visible_columns.index('image')).icon().isNull())
        self.assertTrue(any(download for _,download in calls))
    def test_color_updates_both_duplicate_queue_rows(self):
        self.db.add('queue',self.part['id'],'#ff0000');self.db.add('queue',self.part['id'],'#00ff00')
        cat=self.keep(Catalogue(self.db,scope='queue'));cat.engine=self.engine;preview=self.keep(Preview(self.db,self.engine));preview.visual_changed.connect(lambda item:cat.reload())
        with patch.object(self.engine,'renderer',return_value=Renderer()):
            cat.show();cat.table.selectRow(0);preview.set_item(cat.rows[0]);wait_for(lambda:not cat.table.item(0,cat.visible_columns.index('image')).icon().isNull())
            preview.save_color('#0000ff');preview.refresh();wait_for(lambda:not cat.table.item(0,cat.visible_columns.index('image')).icon().isNull() and cat.table.item(0,cat.visible_columns.index('image')).icon().pixmap(100,65).toImage().pixelColor(50,32).name()=='#0000ff')
            wait_for(lambda:not cat.table.item(1,cat.visible_columns.index('image')).icon().isNull())
            self.assertEqual(cat.table.item(1,cat.visible_columns.index('image')).icon().pixmap(100,65).toImage().pixelColor(50,32).name(),'#00ff00')
    def test_individual_editor_does_not_change_global_and_doubleclick_enlarges(self):
        self.db.add('queue',self.part['id']);entry=dict(self.part,entry_id=1,_scope='queue')
        editor=self.keep(LabelEditor(self.db,self.engine,entry,individual=True));editor.template['layers'][1]['x']=8;editor.apply()
        self.assertEqual(template_for_item(entry,self.db)['layers'][1]['x'],8);self.assertEqual(template_for_item(self.fig,self.db)['layers'][1]['x'],2)
        self.assertEqual(self.db.setting('template',default_template())['layers'][1]['x'],2)
        visual={'main':Image.new('RGB',(100,65),'red')};self.assertNotEqual(render_label(entry,self.db,visual).tobytes(),render_label(self.part,self.db,visual).tobytes())
        preview=self.keep(Preview(self.db,self.engine));preview.item=entry;preview.label_image=render_label(entry,self.db,visual)
        with patch('atelier.preview.image_dialog') as enlarged:
            preview.label_preview.double_clicked.emit();enlarged.assert_called_once()
        preview.reset_individual();self.assertEqual(template_for_item(entry,self.db)['layers'][1]['x'],2)
    def test_bricklink_gif_fallback_and_multiple_photo_choice(self):
        import urllib.error
        from atelier.services import bricklink_photo_links
        self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('BL','part','Zbb018','Znap connector','zbb018'))
        item=self.db.rows("SELECT * FROM items WHERE source='BL'")[0];attempts=[]
        def download(url,headers=None,destination=None,timeout=45):
            attempts.append(url)
            if url.endswith('.png'):raise urllib.error.HTTPError(url,404,'Absent',None,None)
            Image.new('RGB',(64,48),'yellow').save(destination,format='GIF');return destination
        with patch('atelier.services.request',side_effect=download):
            image=self.engine.photo(item,True)
            self.assertEqual(image.getpixel((0,0)),(255,255,0,255));self.assertTrue(attempts[-1].endswith('.gif'))
        markup='https://img.bricklink.com/ItemImage/PN/3/Zbb018.gif https://img.bricklink.com/ItemImage/PL/Zbb018.png https://img.bricklink.com/ItemImage/P/3005.gif'
        urls=bricklink_photo_links(markup,item);self.assertEqual(len(urls),2)
        preview=self.keep(Preview(self.db,self.engine));preview.item=item;preview.store_photos(item,urls)
        with patch.object(preview,'refresh'):
            preview.gallery.setCurrentIndex(2)
        self.assertEqual(self.db.visual(item['id'])['image'],urls[1]);self.assertEqual(self.db.visual(item['id'])['mode'],'photo_bl')

    def test_bricklink_decoration_button_filters_and_restores(self):
        for ref,name in [('plain','Brick plain'),('printedpb01','Brick with Pattern'),('stickerstk01','Brick with Sticker')]:
            self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('BL','part',ref,name,name))
        cat=self.keep(Catalogue(self.db,'BL','part'))
        self.assertIn('has_print',cat.visible_columns);self.assertIn('has_sticker',cat.visible_columns)
        cat.decorated_button.setChecked(True);self.assertEqual(cat.total,1);self.assertEqual(cat.rows[0]['ref'],'plain')
        self.assertEqual(cat.page,1);self.assertFalse(cat.ids)
        reopened=self.keep(Catalogue(self.db,'BL','part'));self.assertTrue(reopened.hide_decorated);self.assertEqual(reopened.total,1)
        cat.decorated_button.setChecked(False);self.assertEqual(cat.total,3)

    def test_pdf_discovery_deduplicates_direct_links(self):
        content='<a href="/files/book.pdf">Book</a> "https:\\/\\/site.test/files/book.pdf"'
        self.assertEqual(pdf_links(content,'https://site.test/set'),['https://site.test/files/book.pdf'])

if __name__=='__main__':unittest.main()
