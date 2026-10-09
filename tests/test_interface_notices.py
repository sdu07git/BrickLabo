import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt,QThreadPool,QPoint,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from atelier.data import Database
from atelier.preview import VisualEngine,Preview
from atelier.dialogs import RelationsDialog
from atelier.contours import ContourDialog
from atelier.documents import DocumentsPanel,discover_notices,notice_targets
from atelier.labels import default_template
app=QApplication.instance() or QApplication([])

def wait(fn):
    limit=time.monotonic()+5
    while time.monotonic()<limit:
        app.processEvents()
        if fn():return
        time.sleep(.01)
    raise AssertionError('No asynchronous result')

class InterfaceNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.db=Database(self.folder/'db.sqlite');self.windows=[]
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part','3005','Brick 1 x 1','Bricks','3005'))
        self.part=self.db.get_item(iid)
        sid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','set','60004-1','Fire station','City','60004'))
        self.set=self.db.get_item(sid);self.db.run('INSERT INTO inventories VALUES(?,?,?)',(1,1,'60004-1'));self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(1,'3005',4,3,0,''))
        self.engine=VisualEngine(self.db)
        self.engine.visuals=lambda *args,**kwargs:({'main':Image.new('RGB',(100,60),'yellow'),'bounds':[20,24,20]},'')
        self.engine.photo=lambda *args,**kwargs:Image.new('RGB',(100,65),'yellow')
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
        for w in self.windows:w.close();w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents();self.temp.cleanup()
    def keep(self,w):self.windows.append(w);return w
    def test_table_separator_drag_and_saved_sizes(self):
        d=self.keep(RelationsDialog(self.db,self.engine,self.part,None));d.resize(1200,800);d.show();app.processEvents()
        self.assertEqual(d.tables_splitter.orientation(),Qt.Orientation.Vertical)
        before=d.tables_splitter.sizes();handle=d.tables_splitter.handle(1);center=handle.rect().center()
        QTest.mousePress(handle,Qt.MouseButton.LeftButton,pos=center)
        QTest.mouseMove(handle,center+QPoint(0,100),delay=20)
        QTest.mouseRelease(handle,Qt.MouseButton.LeftButton,pos=center+QPoint(0,100));app.processEvents()
        after=d.tables_splitter.sizes();self.assertGreater(after[0],before[0]);self.assertLess(after[1],before[1])
        d.close();self.assertEqual(self.db.setting('relations_table_sizes'),after)
    def test_contour_live_preview_and_cancel_do_not_save(self):
        old=self.db.setting('template',default_template());d=self.keep(ContourDialog(self.db,self.engine,self.part));d.show()
        wait(lambda:bool(d.visual));d.picker.setCurrentColor(QColor('#ff0000'));d.render_preview()
        self.assertEqual(d.label_image.convert('RGB').getpixel((200,10)),(255,0,0))
        red=d.label_image.tobytes();d.picker.setCurrentColor(QColor('#0000ff'));d.render_preview()
        self.assertNotEqual(d.label_image.tobytes(),red);self.assertEqual(d.template['category_colors']['Bricks'],'#0000ff')
        d.reject();self.assertEqual(self.db.setting('template',default_template()),old)
    def test_bricklink_label_and_visible_add_link(self):
        p=self.keep(Preview(self.db,self.engine));p.set_item(self.part)
        texts=[p.links_layout.itemAt(i).widget().text() for i in range(p.links_layout.count())]
        self.assertEqual(texts,['Rebrickable','BrickLink'])
        self.assertTrue(any(b.text()=='Ajouter un lien de site' for b in p.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton)))
    def test_only_manual_notice_links_are_removed(self):
        panel=self.keep(DocumentsPanel(self.db));panel.set_item(self.set)
        panel.url.setText('https://manuall.fr/lego-set-60004-city/');panel.add_url()
        key='notice_links_60004-1';entries=self.db.setting(key);entries.append({'name':'Book','source':'Rebrickable','url':'https://cdn.rebrickable.com/book.pdf','state':'À télécharger'});self.db.set_setting(key,entries)
        local=panel.folder()/'existing.pdf';local.write_bytes(b'%PDF-1.4 local');panel.reload()
        row=next(i for i,e in enumerate(panel.entries) if e.get('manual'));panel.table.selectRow(row);self.assertTrue(panel.remove_button.isEnabled());panel.remove_manual()
        self.assertTrue(local.exists());self.assertEqual(len(self.db.setting(key)),1);self.assertEqual(self.db.setting(key)[0]['source'],'Rebrickable')
    def test_search_follows_matching_manuall_page_and_published_download(self):
        base='https://manuall.fr/?s=LEGO+60004';page='https://manuall.fr/lego-set-60004-city-fire-station/'
        html='<a href="'+page+'">60004</a><a href="/lego-set-60005-city/">60005</a>'
        with patch('atelier.documents.request',return_value=b'<a href="?download=1">Download PDF</a>') as fetch:
            links,errors=discover_notices(html,base,'60004-1')
        self.assertEqual(links,[page+'?download=1']);self.assertEqual(errors,[]);fetch.assert_called_once()
    def test_rebrickable_instruction_source_lists_all_books(self):
        panel=self.keep(DocumentsPanel(self.db));self.assertIn(('Rebrickable','https://rebrickable.com/instructions/60004-1/'),panel.sources(self.set))
        links,_=notice_targets('<a href="https://cdn.rebrickable.com/one.pdf">Book 1</a><iframe src="/two.pdf"></iframe>','https://rebrickable.com/instructions/60004-1/')
        self.assertEqual(len(links),2)
    def test_download_manual_page_streams_published_pdf(self):
        panel=self.keep(DocumentsPanel(self.db));panel.set_item(self.set);url='https://manuall.fr/lego-set-60004-city/'
        panel.url.setText(url);panel.add_url();panel.table.selectRow(0);calls=[]
        def download(link,headers=None,destination=None,timeout=None):
            calls.append(link)
            data=b'<a href="?download=1">Download PDF</a>' if link==url else b'%PDF-1.4 test'
            Path(destination).write_bytes(data);return Path(destination)
        with patch('atelier.documents.request',side_effect=download):
            panel.download_selected();wait(lambda:'Notice téléchargée' in panel.progress_label.text())
        self.assertEqual(calls,[url,url+'?download=1']);self.assertEqual(len(list(panel.folder().glob('*.pdf'))),1)
        self.assertEqual(list(panel.folder().glob('*.tmp')),[])
    def test_invalid_download_keeps_existing_pdf(self):
        panel=self.keep(DocumentsPanel(self.db));panel.set_item(self.set);url='https://example.test/book.pdf';file=panel.folder()/'book.pdf';file.write_bytes(b'%PDF-1.4 original')
        panel.url.setText(url);panel.add_url();row=next(i for i,e in enumerate(panel.entries) if e['url']==url);panel.table.selectRow(row)
        def download(link,headers=None,destination=None,timeout=None):Path(destination).write_text('<html>No PDF</html>');return Path(destination)
        with patch('atelier.documents.request',side_effect=download):
            panel.download_selected();wait(lambda:'Aucun lien PDF' in panel.progress_label.text())
        self.assertEqual(file.read_bytes(),b'%PDF-1.4 original');self.assertEqual(list(panel.folder().glob('*.tmp')),[])

    def test_previous_link_buttons_are_hidden_before_deferred_deletion(self):
        from PySide6.QtGui import QDesktopServices
        p=self.keep(Preview(self.db,self.engine));p.set_item(self.part);p.show();app.processEvents()
        old=[p.links_layout.itemAt(i).widget() for i in range(p.links_layout.count())]
        p.set_item(self.part)
        for button in old:
            self.assertTrue(button.isHidden());self.assertFalse(button.isEnabled())
        with patch.object(QDesktopServices,'openUrl') as open_url:
            for button in old:button.click()
            open_url.assert_not_called()
        self.assertEqual(p.links_layout.count(),2)
    def test_minifig_lists_containing_sets_without_replacing_its_parts(self):
        fid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','minifig','fig-test','Test figure','City','fig-test'))
        fig=self.db.get_item(fid);self.db.run('INSERT INTO inventories VALUES(?,?,?)',(2,1,'fig-test'));self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(2,'3005',0,2,0,''))
        self.db.run('INSERT INTO inventory_minifigs VALUES(?,?,?)',(1,'fig-test',1))
        for inventory,ref in ((3,'60005-1'),(5,'60006-1')):
            self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','set',ref,ref,'City',ref))
            self.db.run('INSERT INTO inventories VALUES(?,?,?)',(inventory,1,ref));self.db.run('INSERT INTO inventory_minifigs VALUES(?,?,?)',(inventory,'fig-test',1))
        self.db.run('INSERT INTO inventories VALUES(?,?,?)',(4,2,'60005-1'))
        d=self.keep(RelationsDialog(self.db,self.engine,fig,None));d.show();app.processEvents()
        self.assertFalse(d.set_table.isHidden());self.assertEqual([s['ref'] for s in d.sets],['60004-1','60006-1']);self.assertEqual(d.parts[0]['ref'],'3005')
        d.set_table.selectRow(1);app.processEvents();self.assertEqual(d.active_set['id'],fid);self.assertEqual(d.parts[0]['chosen_quantity'],2)
        self.assertIn('60006-1',d.set_image_title.text())
        with patch('atelier.dialogs.RelationsDialog') as window:
            d.open_containing_set(None);self.assertEqual(window.call_args[0][2]['ref'],'60006-1');window.return_value.show.assert_called_once()
    def test_bricklink_minifig_membership_absence_is_explained(self):
        fid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL','minifig','sw-test','Test figure','Star Wars','sw-test'))
        d=self.keep(RelationsDialog(self.db,self.engine,self.db.get_item(fid),None))
        self.assertFalse(d.set_table.isHidden());self.assertEqual(d.sets,[]);self.assertIn('fichiers BrickLink',d.sets_heading.text())
