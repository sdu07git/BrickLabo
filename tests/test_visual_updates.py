import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,threading,urllib.error,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from atelier.data import Database
from atelier.preview import VisualEngine,Preview
from atelier.dialogs import RelationsDialog
from atelier.app import MainWindow
from atelier.catalogue import Catalogue
from atelier.services import API

app=QApplication.instance() or QApplication([])
def wait_until(fn,timeout=6):
    limit=time.monotonic()+timeout
    while time.monotonic()<limit:
        app.processEvents()
        if fn():return
        time.sleep(.01)
    raise AssertionError('UI result did not arrive')
def pixel(table,row,col):
    cell=table.item(row,col)
    if not cell or cell.icon().isNull():return None
    return cell.icon().pixmap(100,65).toImage().pixelColor(45,30).name()

class Renderer:
    def render(self,ref,size,color,view='perspective',camera=None,edge_strength=0):
        if ref=='missing':raise ValueError('No LDraw model')
        return Image.new('RGB',size,color),[20,24,20]

class VisualTests(unittest.TestCase):
    def setUp(self):
        self.startup_patch=patch.object(MainWindow,"first_import",lambda self:None);self.startup_patch.start()
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.db=Database(self.path/'data.sqlite');self.windows=[]
        self.photo=self.path/'photo.gif';Image.new('RGB',(100,65),'yellow').save(self.photo)
        self.db.run('INSERT INTO colors VALUES(?,?,?,?)',(1,'Blue','0000ff',0));self.db.run('INSERT INTO colors VALUES(?,?,?,?)',(4,'Red','ff0000',0))
        self.parts=[]
        for ref in ('3005','3001','missing'):
            iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,image,search) VALUES(?,?,?,?,?,?,?)',('RB','part',ref,'Brick '+ref,'Bricks',str(self.photo),ref));self.parts.append(self.db.get_item(iid))
        self.engine=VisualEngine(self.db)
    def tearDown(self):
        self.startup_patch.stop()
        for w in self.windows:w.close()
        QThreadPool.globalInstance().waitForDone(6000);app.processEvents()
        for w in self.windows:w.deleteLater()
        app.processEvents();self.temp.cleanup()
    def keep(self,w):self.windows.append(w);return w
    def set_item(self,ref='42-1'):
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,image,search) VALUES(?,?,?,?,?,?,?)',('RB','set',ref,'Test set','City',str(self.photo),ref))
        self.db.run('INSERT INTO inventories VALUES(?,?,?)',(7,1,ref))
        for part,color in [(self.parts[0],4),(self.parts[0],1),(self.parts[2],4)]:self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(7,part['ref'],color,1,0,str(self.photo)))
        return self.db.get_item(iid)
    def bl_item(self,ref='2412u',kind='part'):
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL',kind,ref,'BrickLink '+ref,'Bricks',ref));return self.db.get_item(iid)
    def test_relation_table_renders_each_inventory_color_and_photo_fallback(self):
        with patch.object(self.engine,'renderer',return_value=Renderer()):
            dialog=self.keep(RelationsDialog(self.db,self.engine,self.set_item(),None));dialog.show()
            self.assertEqual(dialog.part_table.horizontalHeaderItem(5).text(),'Aperçu 3D / photo')
            wait_until(lambda:all(pixel(dialog.part_table,r,5) for r in range(3)))
            self.assertEqual(pixel(dialog.part_table,0,5),'#ff0000');self.assertEqual(pixel(dialog.part_table,1,5),'#0000ff');self.assertEqual(pixel(dialog.part_table,2,5),'#ffff00')
            dialog.change_part_color(0,'1');wait_until(lambda:pixel(dialog.part_table,0,5)=='#0000ff')
    def test_source_change_in_main_window_keeps_other_rows_and_selection(self):
        win=self.keep(MainWindow(self.db));win.show();cat=win.catalogues[0];col=cat.visible_columns.index('image')
        wait_until(lambda:all(pixel(cat.table,r,col) for r in range(len(cat.rows))))
        QThreadPool.globalInstance().waitForDone(6000);app.processEvents()
        cat.table.selectRow(0);selected=cat.rows[0]['id'];cells=[cat.table.item(i,col) for i in range(len(cat.rows))];ids=set(cat.ids);calls=[]
        original=win.engine.photo
        def photo(item,*args,**kwargs):calls.append(item['id']);return original(item,*args,**kwargs)
        with patch.object(cat,'reload',side_effect=AssertionError('Whole table reloaded')),patch.object(win.engine,'photo',side_effect=photo):
            win.preview.mode.setCurrentIndex(win.preview.mode.findData('photo_rb'))
            wait_until(lambda:len(calls)>=2)
            QThreadPool.globalInstance().waitForDone(6000);app.processEvents()
        self.assertEqual(set(calls),{selected});self.assertEqual(cat.ids,ids)
        self.assertTrue(all(cat.table.item(i,col) is cells[i] for i in range(len(cells))))
        self.assertEqual(self.db.visual(selected)['mode'],'photo_rb')
        self.assertTrue(all(self.db.visual(r['id'])['mode']=='3d' for r in cat.rows if r['id']!=selected))
    def test_stale_background_thumbnail_cannot_replace_new_selected_visual(self):
        cat=self.keep(Catalogue(self.db,'RB','part'));cat.show();app.processEvents()
        cat.engine=self.engine;col=cat.visible_columns.index('image');iid=cat.rows[0]['id'];gate=threading.Event();entered=threading.Event();count={'n':0}
        def photo(item,*args,**kwargs):
            if item['id']==iid:
                count['n']+=1
                if count['n']==1:entered.set();gate.wait(4);return Image.new('RGB',(100,65),'red')
                return Image.new('RGB',(100,65),'blue')
            return Image.new('RGB',(100,65),'green')
        with patch.object(self.engine,'renderer',return_value=None),patch.object(self.engine,'photo',side_effect=photo):
            cat.load_thumbnails();wait_until(entered.is_set)
            cat.refresh_visual(cat.rows[0]);wait_until(lambda:pixel(cat.table,0,col)=='#0000ff')
            gate.set();QThreadPool.globalInstance().waitForDone(6000);app.processEvents()
            self.assertEqual(pixel(cat.table,0,col),'#0000ff');self.assertEqual(pixel(cat.table,1,col),'#008000')
    def test_bricklink_known_colors_are_cached_with_native_rgb_and_ids(self):
        item=self.bl_item();calls=[]
        def response(path):
            calls.append(path)
            if path.endswith('/colors'):return [{'color_id':5},{'color_id':11},{'color_id':5}]
            if path=='colors':return [{'color_id':5,'color_name':'Red','color_code':'ff0000'},{'color_id':11,'color_name':'Black','color_code':'000000'}]
            raise AssertionError(path)
        with patch.object(API,'bl',side_effect=response):colors=API(self.db).bl_available_colors(item)
        self.assertEqual({c['id'] for c in colors},{'5','11'});self.assertIn('items/PART/2412u/colors',calls)
        self.assertEqual(self.engine.color_rgb(item,'5'),'#ff0000')
        self.assertEqual(Database(self.db.path).available_colors(item),colors)
        preview=self.keep(Preview(self.db,self.engine))
        with patch.object(preview,'refresh'):preview.set_item(item)
        self.assertEqual(preview.available.count(),3);self.assertEqual(preview.available_title.text(),'Couleurs connues BrickLink')
    def test_minifig_known_color_endpoint_uses_minifig_type(self):
        item=self.bl_item('sw0001','minifig');self.db.set_setting('bl_colors',{'11':{'name':'Black','rgb':'000000'}})
        with patch.object(API,'bl',return_value=[{'color_id':11}]) as endpoint:API(self.db).bl_available_colors(item)
        endpoint.assert_called_once_with('items/MINIFIG/sw0001/colors')
    def test_2412u_fallback_skips_placeholder_and_forbidden_urls(self):
        item=self.bl_item();self.db.run('UPDATE items SET image=? WHERE id=?',('https://img.bricklink.com/Images/dot.gif',item['id']));item=self.db.get_item(item['id']);calls=[]
        def image(url,*args,**kwargs):
            calls.append(url)
            if url.endswith('/Images/dot.gif'):return Image.new('RGB',(1,1))
            if url=='https://img.bricklink.com/ItemImage/PL/2412u.jpg':return Image.new('RGB',(100,65),'yellow')
            raise urllib.error.HTTPError(url,403,'Not available',None,None)
        with patch.object(self.engine.images,'get',side_effect=image):result=self.engine.photo(item)
        self.assertEqual(result.size,(100,65));self.assertIn('https://img.bricklink.com/ItemImage/P/2412u.gif',calls)
    def test_bricklink_minifig_accepts_modern_png_and_old_gif(self):
        item=self.bl_item('sw0001','minifig')
        for suffix in ('M/sw0001.gif','MN/sw0001.png'):
            def image(url,*args,**kwargs):
                if url.endswith(suffix):return Image.new('RGBA',(100,65),'yellow')
                raise urllib.error.HTTPError(url,404,'Not found',None,None)
            with patch.object(self.engine.images,'get',side_effect=image):self.assertEqual(self.engine.photo(item).size,(100,65))
    def test_minifig_gif_is_decoded_and_displayed_in_preview(self):
        item=self.bl_item('sw0002','minifig');self.db.run('UPDATE items SET image=? WHERE id=?',(str(self.photo),item['id']));item=self.db.get_item(item['id']);preview=self.keep(Preview(self.db,self.engine));preview.set_item(item)
        wait_until(lambda:preview.image is not None)
        self.assertEqual(preview.image.getpixel((45,30)),(255,255,0,255));self.assertFalse(preview.photo.pixmap().isNull())

if __name__=='__main__':unittest.main()
