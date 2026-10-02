import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool,QCoreApplication,QEvent
from atelier.data import Database
from atelier.documents import DocumentsPanel,notice_targets,notice_identity,expired_notice_url
app=QApplication.instance() or QApplication([])
BASE='https://rebrickable.com/instructions/2160-1/'
OLD='https://rebrickable.com/instructions/1648/oldhash/download/?expire=1'
NEW='https://rebrickable.com/instructions/1648/newhash/download/?expire=9999999999'

class RebrickableNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.panel=DocumentsPanel(self.db)
        self.item={'ref':'2160-1','source':'RB','kind':'set'};self.panel.set_item(self.item)
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents();self.panel.close();self.panel.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()
    def wait(self,predicate):
        end=time.monotonic()+5
        while not predicate():
            app.processEvents();time.sleep(.01);self.assertLess(time.monotonic(),end)
    def add(self,url):
        self.panel.url.setText(url);self.panel.add_url();self.panel.table.selectRow(next(i for i,e in enumerate(self.panel.entries) if e['url']==url))
    def test_rebrickable_image_only_and_empty_download_anchors(self):
        page='<a href="'+NEW+'"><img alt="LEGO Building Instructions for 4108974"></a>'
        links,anchors=notice_targets(page,BASE);self.assertEqual(links,[NEW]);self.assertIn('4108974',anchors[0]['text'])
        links,_=notice_targets('<a href="'+NEW+'"></a>',BASE);self.assertEqual(links,[NEW])
    def test_empty_html_attributes_do_not_break_notice_discovery(self):
        page='<a title href="'+NEW+'"><img alt title></a><iframe title src="/book.pdf"></iframe>'
        links,_=notice_targets(page,BASE)
        self.assertEqual(links,sorted([NEW,'https://rebrickable.com/book.pdf']))
        lego='<a title href="https://www.lego.com/cdn/product-assets/product.bi.core.pdf/4108974.pdf"><img alt title></a>'
        links,_=notice_targets(lego,'https://www.lego.com/fr-fr/service/buildinginstructions/2160')
        self.assertEqual(links,['https://www.lego.com/cdn/product-assets/product.bi.core.pdf/4108974.pdf'])
    def test_search_ignores_unrelated_lego_pdfs_and_lists_rebrickable_endpoint(self):
        def fetch(url,**kwargs):
            if 'lego.com/' in url:return b'<a href="/legal/Modern_Slavery_Statement.pdf">PDF</a><a href="/cdn/product-assets/product.bi.core.pdf">PDF</a><a href="/cdn/product-assets/product.bi.core.pdf/4108974.pdf">PDF</a>'
            if url==BASE:return ('<a href="'+NEW+'"><img alt="LEGO Building Instructions for 4108974"></a>').encode()
            return b'<html></html>'
        with patch('atelier.documents.request',side_effect=fetch):
            self.panel.search();self.wait(lambda:'lien(s) PDF trouvé(s)' in self.panel.progress_label.text())
        entries=self.db.setting('notice_links_2160-1');self.assertEqual(len(entries),2);self.assertTrue(any(e['source']=='Rebrickable' and e['url']==NEW for e in entries));self.assertFalse(any('Slavery' in e['url'] for e in entries))
    def test_refresh_updates_same_document_without_duplicates(self):
        self.add(OLD);self.panel.save_discovered(self.item,[{'name':'Notice','url':NEW,'source':'Rebrickable','state':'À télécharger'}])
        entries=self.db.setting('notice_links_2160-1');self.assertEqual(len(entries),1);self.assertEqual(entries[0]['url'],NEW);self.assertTrue(entries[0]['manual']);self.assertEqual(notice_identity(OLD),notice_identity(NEW))
    def test_expiry_detection_preserves_signature_query(self):
        url='https://rebrickable-set-bi-files.eu-central-1.linodeobjects.com/2160-1/4108974.pdf?X-Amz-Date=20260930T224640Z&X-Amz-Expires=3600&X-Amz-Signature=abc'
        self.assertFalse(expired_notice_url(url,now=1790808400));self.assertTrue(expired_notice_url(url,now=1790816000));self.assertTrue(expired_notice_url(OLD));self.assertFalse(expired_notice_url(NEW))
    def test_expired_endpoint_refreshes_before_streaming(self):
        self.add(OLD);calls=[]
        def fetch(url,headers=None,destination=None,timeout=None):
            calls.append(url)
            if url==BASE:return ('<a href="'+NEW+'"></a>').encode()
            self.assertEqual(url,NEW);Path(destination).write_bytes(b'%PDF-1.4 complete notice');return Path(destination)
        with patch('atelier.documents.request',side_effect=fetch):
            self.panel.download_selected();self.wait(lambda:'Notice téléchargée' in self.panel.progress_label.text())
        self.assertEqual(calls,[BASE,NEW]);self.assertEqual(len(list(self.panel.folder().glob('*.pdf'))),1)
    def test_signed_storage_url_refresh_matches_published_filename(self):
        old='https://rebrickable-set-bi-files.eu-central-1.linodeobjects.com/2160-1/4108974.pdf?X-Amz-Date=20000101T000000Z&X-Amz-Expires=3600'
        self.add(old)
        def fetch(url,headers=None,destination=None,timeout=None):
            if url==BASE:return ('<a href="'+NEW+'"><img alt="LEGO Building Instructions for 4108974"></a>').encode()
            self.assertEqual(url,NEW);Path(destination).write_bytes(b'%PDF-1.4 notice');return Path(destination)
        with patch('atelier.documents.request',side_effect=fetch):
            self.panel.download_selected();self.wait(lambda:'Notice téléchargée' in self.panel.progress_label.text())
        self.assertTrue((self.panel.folder()/'4108974.pdf').exists())
    def test_bricklink_catalogue_does_not_open_when_downloading(self):
        self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL','instructions','2160-1','Crystal Scavenger','Aquazone','2160'))
        self.panel.reload();self.panel.table.selectRow(0)
        self.assertFalse(self.panel.download_button.isEnabled());self.assertEqual(self.panel.open_button.text(),'Ouvrir la fiche BrickLink')
        with patch('atelier.documents.QDesktopServices.openUrl') as opener:self.panel.download_selected();opener.assert_not_called()
