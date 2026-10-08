import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import VisualEngine
from atelier.build_stock import BuildStockDialog
from atelier.catalogue import Catalogue
from atelier.moc_search import MocSearchDialog

application=QApplication.instance() or QApplication([])

def synchronous(owner,work,done,failed,*args):done(work(lambda _:None))

def wait_for(predicate):
    until=time.monotonic()+5
    while time.monotonic()<until:
        application.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('UI callback did not finish')

class Update38Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'Donnees'/'db.sqlite');self.windows=[]
    def tearDown(self):
        for window in reversed(self.windows):window.close();window.deleteLater()
        QThreadPool.globalInstance().waitForDone(5000);application.processEvents();self.temp.cleanup()
    def keep(self,window):self.windows.append(window);return window

    def test_set_photos_follow_references_after_sorting_and_reuse_cache(self):
        self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)")
        part=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','3001','Brick','brick')")
        for index,(ref,name) in enumerate((('100-1','Alpha Falcon'),('200-1','Beta Falcon')),1):
            self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','set',?,?,?)",(ref,name,name));self.db.run('INSERT INTO inventories VALUES(?,1,?)',(index,ref));self.db.run("INSERT INTO inventory_parts VALUES(?,'3001',4,2,0,'')",(index,))
        self.db.add('stock',part,'4',2);self.db.set_setting('thumbnail_disk_mb',0);engine=VisualEngine(self.db);requests=[]
        def photo(item,*args,**kwargs):
            if item['kind']=='set':requests.append(item['ref'])
            return Image.new('RGBA',(100,65),'#ff3300' if item['ref']=='100-1' else '#0066ff')
        with patch.object(engine,'photo',side_effect=photo),patch('atelier.build_stock.async_task',side_effect=synchronous):
            window=self.keep(BuildStockDialog(self.db,engine));window.show();window.start()
            wait_for(lambda:window.table.rowCount()==2 and all(not window.table.item(r,7).icon().isNull() for r in range(2)))
            window.table.sortItems(2,Qt.SortOrder.DescendingOrder)
            wait_for(lambda:not window.table.item(0,7).icon().isNull() and window.visible_sets()[0]['ref']=='200-1')
            self.assertEqual(window.table.item(0,7).icon().pixmap(100,65).toImage().pixelColor(50,32).name(),'#0066ff')
            self.assertEqual(window.table.item(1,7).icon().pixmap(100,65).toImage().pixelColor(50,32).name(),'#ff3300')
            QThreadPool.globalInstance().waitForDone(5000);self.assertCountEqual(requests,['100-1','200-1']);self.assertEqual(list(engine.thumbnail_cache.folder.iterdir()),[])

    def test_set_column_can_be_dragged_to_a_new_width(self):
        window=self.keep(BuildStockDialog(self.db));window.show();application.processEvents();header=window.table.horizontalHeader();width=header.sectionSize(2);edge=header.sectionViewportPosition(2)+width-1;point=QPoint(edge,header.height()//2)
        QTest.mousePress(header.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point);QTest.mouseMove(header.viewport(),point+QPoint(80,0),20);QTest.mouseRelease(header.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point+QPoint(80,0));application.processEvents();self.assertGreater(header.sectionSize(2),width+50)

    def test_all_set_catalogues_open_global_search_with_the_keyword(self):
        for source in ('RB','BL','ALT'):
            catalogue=self.keep(Catalogue(self.db,source,'set'));catalogue.search.setText('falcon');catalogue.timer.stop()
            with patch('atelier.moc_search.MocSearchDialog') as search:
                catalogue.moc_search_button.click();self.assertEqual(search.call_args.kwargs['keyword'],'falcon');search.return_value.exec.assert_called_once()
        window=self.keep(BuildStockDialog(self.db));window.search.setText('falcon')
        with patch('atelier.moc_search.MocSearchDialog') as search:
            window.global_search();self.assertEqual(search.call_args.kwargs['keyword'],'falcon')
        self.assertEqual(self.db.query(scope='stock')[1],0);self.assertEqual(self.db.query(scope='stock_sets')[1],0)

    def test_global_moc_search_includes_unowned_sets_and_original_mocs(self):
        window=self.keep(MocSearchDialog(self.db,None,keyword='falcon'));self.assertFalse(window.alternates.isChecked())
        alternate={'set_num':'MOC-900','name':'Midi Falcon','designer_name':'Creator','bases':['75440-1'],'bases_loaded':True}
        original={'set_num':'MOC-901','name':'Original Falcon','designer_name':'Creator','bases':[],'bases_loaded':True}
        next_page='https://rebrickable.com/mocs/?q=falcon&page=2'
        with patch('atelier.moc_search.fetch_search',side_effect=[([alternate],next_page),([alternate,original],None)]) as fetch,patch('atelier.moc_search.async_task',side_effect=synchronous),patch('atelier.build_stock.InventoryReader.stock',side_effect=AssertionError('Stock was consulted')):
            window.load(True);query=parse_qs(urlsplit(fetch.call_args.args[0]).query);self.assertEqual(query['q'],['falcon']);self.assertNotIn('show_alts_only',query);self.assertTrue(window.more.isEnabled());self.assertIn('75440-1',window.origins.text());window.load(False)
        self.assertEqual([r['set_num'] for r in window.rows],['MOC-900','MOC-901']);self.assertFalse(window.more.isEnabled());self.assertEqual(self.db.query(scope='stock')[1],0);self.assertEqual(self.db.query(scope='stock_sets')[1],0)
