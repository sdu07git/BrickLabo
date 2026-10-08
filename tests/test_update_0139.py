"""Regression checks for disk reads, transaction rollback and worker races."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import VisualEngine,Preview
from atelier.memory_cache import MemoryCache
from atelier.thumbnail_cache import ThumbnailCache
from atelier.services import Images
from atelier.render import LDraw

application=QApplication.instance() or QApplication([])


class Update39Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.db=Database(self.root/'Donnees/db.sqlite');self.engine=VisualEngine(self.db);self.widgets=[]
        self.iid=self.db.run("INSERT INTO items(source,kind,ref,name,category,category_id,search) VALUES('RB','part','3001','Brick','Bricks','1','brick')")
        self.db.run("INSERT INTO categories VALUES(1,'Bricks')")
        self.item=self.db.get_item(self.iid)
    def tearDown(self):
        for widget in self.widgets:
            if hasattr(widget,'stop'):widget.stop()
            widget.close();widget.deleteLater()
        QThreadPool.globalInstance().waitForDone();application.processEvents()
        self.engine.close();self.db.close();self.temp.cleanup()
    def csv(self,name,text):
        file=self.root/(name+'.csv');file.write_text(text,encoding='utf-8');return file
    def model(self,name='base.zip',ref='3001',x=10):
        path=self.root/name
        with ZipFile(path,'w') as z:
            z.writestr('ldraw/LDConfig.ldr','0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
            z.writestr('ldraw/parts/'+ref+'.dat',f'0 Brick\n3 16 0 0 0 {x} 0 0 0 10 0\n')
        return path
    def trace(self):
        self.db.run('CREATE TABLE updates(value TEXT)')
        self.db.run('CREATE TRIGGER observe AFTER UPDATE ON items BEGIN INSERT INTO updates VALUES(new.ref); END')
    def photo(self):
        images=Images(self.root/'photos');url='https://example.test/photo.png'
        def download(url,destination,**kw):Image.new('RGBA',(20,20),'red').save(destination,format='PNG')
        with patch('atelier.services.request',side_effect=download):images.get(url)
        return images,url

    def test_shared_reader_reuses_one_connection_and_ends_snapshots(self):
        from atelier import sqlite_file
        self.db.close()
        with patch.object(sqlite_file,'connect',wraps=sqlite_file.connect) as connect:
            for _ in range(200):self.assertEqual(self.db.get_item(self.iid)['ref'],'3001')
            self.assertEqual(connect.call_count,1)
        with self.db.read() as reader:
            self.assertFalse(reader.in_transaction)
            with self.assertRaises(sqlite3.OperationalError):reader.execute('DELETE FROM items')
        with self.db.connect() as writer:writer.execute('UPDATE items SET name=? WHERE id=?',('Changed',self.iid))
        self.assertEqual(self.db.get_item(self.iid)['name'],'Changed')
        self.db.close();self.assertIsNone(self.db._reader)

    def test_parallel_readers_and_stock_writer_preserve_quantities(self):
        def read():
            for _ in range(70):self.assertEqual(self.db.query('RB','part')[1],1)
        def write():
            for _ in range(20):self.db.add('stock',self.iid,'4',1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(read) for _ in range(3)]+[pool.submit(write)]
            for future in futures:future.result(timeout=15)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],20)
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],19)

    def test_unchanged_part_import_avoids_rewriting_items_and_fts(self):
        file=self.csv('parts','part_num,name,part_cat_id\n3001,Brick,1\n');self.db.import_file(file);self.trace()
        self.db.import_file(file);self.assertEqual(self.db.rows('SELECT * FROM updates'),[])
        file.write_text('part_num,name,part_cat_id\n3001,New Falcon,1\n');self.db.import_file(file)
        self.assertEqual(len(self.db.rows('SELECT * FROM updates')),1);self.assertEqual(self.db.query('RB','part',search='falcon')[1],1)

    def test_unrelated_colour_import_does_not_rewrite_part_categories(self):
        self.trace();self.db.import_file(self.csv('colors','id,name,rgb,is_trans\n4,Red,FF0000,False\n'))
        self.assertEqual(self.db.rows('SELECT * FROM updates'),[])
        self.db.import_file(self.csv('part_categories','id,name\n1,Changed category\n'))
        self.assertEqual(self.db.get_item(self.iid)['category'],'Changed category');self.assertEqual(len(self.db.rows('SELECT * FROM updates')),1)

    def test_minifigure_reimport_keeps_computed_category(self):
        file=self.csv('minifigs','fig_num,name,num_parts\nfig-001,Pilot,3\n');self.db.import_file(file)
        self.db.run("UPDATE items SET category='Star Wars' WHERE kind='minifig'");self.trace();self.db.import_file(file)
        self.assertEqual(self.db.rows("SELECT category FROM items WHERE kind='minifig'")[0]['category'],'Star Wars')
        self.assertEqual(self.db.rows('SELECT * FROM updates'),[])

    def test_fts_trigger_does_not_run_for_identical_values(self):
        with self.db.connect() as c:
            before=c.total_changes;c.execute('UPDATE items SET name=name,search=search WHERE id=?',(self.iid,))
            self.assertEqual(c.total_changes-before,1)
        self.db.run("DROP TRIGGER items_search_update")
        self.db.run("CREATE TRIGGER items_search_update AFTER UPDATE ON items BEGIN DELETE FROM items_search WHERE rowid=old.id; END")
        self.db.close();self.db=Database(self.db.path)
        self.db.run("UPDATE items SET name='Falcon' WHERE id=?",(self.iid,))
        self.assertEqual(self.db.query('RB','part',search='falcon')[1],1)

    def test_visual_changes_write_only_when_different(self):
        self.db.save_visual(self.iid,color='4');self.db.run('CREATE TABLE visual_updates(value INTEGER)')
        self.db.run('CREATE TRIGGER visual_observe AFTER UPDATE ON visual BEGIN INSERT INTO visual_updates VALUES(1); END')
        self.db.save_visual(self.iid,color='4');self.assertEqual(self.db.rows('SELECT * FROM visual_updates'),[])
        self.db.save_visual(self.iid,color='14');self.assertEqual(len(self.db.rows('SELECT * FROM visual_updates')),1)

    def test_multi_part_add_uses_one_transaction_and_one_undo(self):
        self.db.add_many([('stock',self.iid,'4',3),('stock',self.iid,'14',5)])
        self.assertEqual(len(self.db.rows('SELECT * FROM stock')),2)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT * FROM stock'),[])

    def test_failed_personal_inventory_import_rolls_back_everything(self):
        from atelier.stock_import import import_rows
        row={'source':'RB','kind':'part','ref':'3001','color':'4','quantity':3}
        with patch('atelier.stock._apply',side_effect=RuntimeError('Interrupted')):
            with self.assertRaises(RuntimeError):import_rows(self.db,[row],'stock_sets',name='My parts')
        self.assertEqual(self.db.rows("SELECT * FROM items WHERE source='ALT'"),[])
        self.assertEqual(self.db.rows("SELECT * FROM settings WHERE key LIKE 'alt_components_%'"),[])
        self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
        import_rows(self.db,[row],'stock_sets',name='My parts');self.assertTrue(self.db.undo_last_action())
        self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])

    def test_stock_colour_merge_remains_undoable(self):
        self.db.add('stock',self.iid,'4',3);self.db.add('stock',self.iid,'14',5)
        entry=self.db.rows("SELECT id FROM stock WHERE color='4'")[0]['id']
        preview=Preview(self.db,self.engine);self.widgets.append(preview)
        preview.item=dict(self.item,_scope='stock',entry_id=entry,chosen_color='4',chosen_quantity=3)
        preview.save_color('14')
        self.assertEqual(preview.item['chosen_quantity'],8)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE quantity>0')[0]['quantity'],8)
        self.db.undo_last_action();self.assertEqual(sorted(r['quantity'] for r in self.db.rows('SELECT quantity FROM stock WHERE quantity>0')),[3,5])

    def test_warm_photos_do_not_decode_or_read_ledger_again(self):
        images,url=self.photo()
        with patch('PIL.Image.open',side_effect=AssertionError('Repeated decode')),patch.object(Path,'read_text',side_effect=AssertionError('Repeated ledger read')),patch('atelier.services.atomic_output',side_effect=AssertionError('Repeated write')):
            for _ in range(100):self.assertEqual(images.get(url).size,(20,20))

    def test_photo_metadata_is_isolated_and_ram_is_bounded(self):
        images=Images(self.root/'photos');images.decoded.limit=8000
        for i in range(8):
            file=self.root/f'{i}.png';Image.new('RGBA',(20,20),(i,0,0,255)).save(file)
            result=images.get(str(file));result.info['private']='changed'
            self.assertNotIn('private',images.get(str(file)).info)
        self.assertLessEqual(images.decoded.bytes,8000);self.assertEqual(len(list(self.root.glob('*.png'))),8)

    def test_parallel_photo_reads_share_one_decode(self):
        file=self.root/'photo.png';Image.new('RGBA',(20,20),'red').save(file);images=Images(self.root/'photos')
        with patch('PIL.Image.open',wraps=Image.open) as decode,ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:images.get(str(file)),range(16)))
        self.assertEqual(decode.call_count,1);self.assertEqual(len(results),16)

    def test_changed_photo_or_missing_ledger_is_refreshed(self):
        images,url=self.photo();file=next(images.folder.glob('*.img'))
        Image.new('RGBA',(21,20),'blue').save(file,format='PNG');self.assertEqual(images.get(url).size,(21,20))
        ledger=images.folder/'SOURCES_IMAGES.json';ledger.unlink();images.get(url);self.assertTrue(ledger.is_file())

    def test_ldraw_text_reads_are_bounded_and_archive_is_closed(self):
        renderer=LDraw(self.model())
        try:
            with patch.object(renderer.archive,'read',wraps=renderer.archive.read) as read:
                for _ in range(30):renderer.read('3001.dat')
                self.assertEqual(read.call_count,1)
            renderer.text_limit=256;renderer.text_cache.clear();renderer.text_bytes=0
            for _ in range(4):renderer.read('LDConfig.ldr');renderer.read('3001.dat')
            self.assertLessEqual(renderer.text_bytes,256)
        finally:renderer.close()
        self.assertTrue(renderer.archive.stream.closed)

    def test_renderer_initialises_once_for_concurrent_requests(self):
        self.db.set_setting('ldraw',str(self.model()))
        with patch('atelier.preview.LDraw',wraps=LDraw) as constructor,ThreadPoolExecutor(max_workers=4) as pool:
            renderers=list(pool.map(lambda _:self.engine.renderer(),range(12)))
        self.assertEqual(constructor.call_count,1);self.assertTrue(all(r is renderers[0] for r in renderers))

    def test_replacing_model_archive_does_not_change_inflight_reader(self):
        original=self.model();self.db.set_setting('ldraw',str(original));old=self.engine.renderer()
        replacement=self.model('new.zip',x=17);os.replace(replacement,original);new=self.engine.renderer()
        try:
            self.assertIsNot(old,new);self.assertIn('17 0 0',new.read('3001.dat'));self.assertIn('10 0 0',old.read('3001.dat'))
        finally:old.close()

    def test_identical_3d_render_is_reused_without_disk_writes(self):
        self.db.set_setting('ldraw',str(self.model(ref='72841')))
        first=self.engine.render_3d(self.item,(100,65),'4')
        with patch('PIL.Image.Image.save',side_effect=AssertionError('Render write')),patch.object(self.db,'connect',side_effect=AssertionError('Write connection')):
            second=self.engine.render_3d(self.item,(100,65),'4')
        self.assertIs(first,second);self.assertTrue(first[0].getbbox())

    def test_memory_cache_clear_during_old_work_keeps_new_result(self):
        cache=MemoryCache();started=threading.Event();release=threading.Event()
        def old():started.set();self.assertTrue(release.wait(5));return Image.new('RGBA',(10,10),'red')
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(cache.get_or_create,'key',old)
            try:
                self.assertTrue(started.wait(5));cache.clear();blue=cache.get_or_create('key',lambda:Image.new('RGBA',(10,10),'blue'))
            finally:release.set()
            future.result(timeout=5)
        self.assertIs(cache.get_or_create('key',lambda:None),blue)

    def test_thumbnail_invalidation_during_old_work_keeps_new_result(self):
        cache=ThumbnailCache(self.root/'thumbs');started=threading.Event();release=threading.Event();key=(1,'same')
        def old():started.set();self.assertTrue(release.wait(5));return Image.new('RGBA',(100,65),'red')
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(cache.get_or_create,key,old)
            try:
                self.assertTrue(started.wait(5));cache.invalidate();cache.get_or_create(key,lambda:Image.new('RGBA',(100,65),'blue'))
            finally:release.set()
            future.result(timeout=5)
        self.assertEqual(cache.get(key).getpixel((0,0)),(0,0,255,255))
        with Image.open(cache.path(key)) as image:self.assertEqual(image.getpixel((0,0)),(0,0,255,255))

    def test_preview_runs_only_the_latest_pending_selection(self):
        preview=Preview(self.db,self.engine);self.widgets.append(preview);jobs=[]
        def schedule(owner,work,done,failed,*args):jobs.append((work,done))
        with patch('atelier.preview.async_task',side_effect=schedule),patch.object(self.engine,'visuals',return_value=({'main':Image.new('RGBA',(20,20),'blue')},'Latest')) as visuals,patch('atelier.preview.render_label',return_value=Image.new('RGBA',(20,20))):
            preview.item=dict(self.item);preview.refresh()
            for i in range(20):preview.item=dict(self.item,name=str(i));preview.refresh()
            self.assertEqual(len(jobs),1);jobs[0][1](jobs[0][0](lambda _:None))
            self.assertEqual(len(jobs),2);jobs[1][1](jobs[1][0](lambda _:None))
            self.assertEqual(visuals.call_count,1);self.assertEqual(preview.note.text(),'Latest')
        self.assertFalse(preview.render_running)

    def test_browsing_notices_does_not_create_folders(self):
        from atelier.documents import DocumentsPanel
        panel=DocumentsPanel(self.db);self.widgets.append(panel)
        panel.set_item(dict(self.item,kind='set',ref='100-1'));panel.reload()
        self.assertFalse((self.db.path.parent/'Notices').exists())

    def test_active_temporary_workspace_survives_purge_and_then_cleans_up(self):
        from atelier.temp_area import workspace,purge
        with workspace(self.db.path.parent) as folder:
            file=folder/'download.zip';file.write_bytes(b'active');os.utime(file,(1,1))
            purge(self.db.path.parent/'temp');self.assertTrue(file.exists())
        self.assertFalse(folder.exists())

    def test_failed_model_download_cleans_partial_files(self):
        from atelier.architect_models import ensure_models
        def fail(url,destination,**kw):Path(destination).write_bytes(b'partial');raise OSError('Interrupted')
        with patch('atelier.services.request',side_effect=fail):result=ensure_models(self.db,{'models':['missing.dat']})
        self.assertEqual(result['model_status']['missing.dat'],'unavailable')
        self.assertEqual(list((self.db.path.parent/'temp').iterdir()),[])
        self.assertFalse((self.db.path.parent/'temporaires').exists())

    def test_model_pack_reads_only_selected_geometry_and_dependencies(self):
        from atelier.architect_models import build_pack
        path=self.root/'all.zip'
        with ZipFile(path,'w') as z:
            z.writestr('parts/a.dat','0 A\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 b.dat\n')
            z.writestr('parts/b.dat','0 B\n3 16 0 0 0 10 0 0 0 10 0\n');z.writestr('parts/unrelated.dat','unused')
        original=ZipFile.read;reads=[]
        def read(archive,name,*args,**kwargs):reads.append(name);return original(archive,name,*args,**kwargs)
        with patch.object(ZipFile,'read',read):build_pack([{'models':['a.dat']}],[('official',path)],self.root/'pack.zip')
        self.assertCountEqual(reads,['parts/a.dat','parts/b.dat'])

    def test_catalogue_publication_rolls_back_file_and_database_on_commit_failure(self):
        from atelier.brickarchitect import publish_catalogue,replace_catalogue
        target=self.db.path.parent/'brickarchitect_ldraw.zip';target.write_bytes(b'old')
        staged=self.root/'pending.zip';staged.write_bytes(b'new')
        old={'records':[{'ref':'A','name':'Old','models':[]}]};new={'records':[{'ref':'B','name':'New','models':[]}]}
        replace_catalogue(self.db,old);connect=self.db.connect
        @contextmanager
        def fail_commit():
            with connect() as c:
                yield c
                raise sqlite3.OperationalError('Commit failed')
        with patch.object(self.db,'connect',side_effect=fail_commit):
            with self.assertRaises(sqlite3.OperationalError):publish_catalogue(self.db,new,staged)
        self.assertEqual(target.read_bytes(),b'old');self.assertEqual(self.db.rows('SELECT ref FROM brickarchitect')[0]['ref'],'A')
        self.assertEqual(list((self.db.path.parent/'temp').iterdir()),[])

    def test_legacy_temporary_purge_preserves_referenced_and_recent_files(self):
        from atelier.disk_space import clean_temp,usage
        from atelier.backups import create_backup
        folder=self.db.path.parent/'temporaires';folder.mkdir()
        old=folder/'old.tmp';keep=folder/'user.png';recent=folder/'recent.tmp'
        for path in (old,keep,recent):path.write_bytes(b'content')
        for path in (old,keep):os.utime(path,(time.time()-10*86400,)*2)
        self.db.save_visual(self.iid,mode='local',image=str(keep));self.assertIn('Anciens temporaires',[r[0] for r in usage(self.db)])
        backup=self.root/'backup.zip';create_backup(self.db,backup)
        with ZipFile(backup) as z:self.assertFalse(any('/temporaires/' in n or n.startswith('temporaires/') for n in z.namelist()))
        count,_,errors=clean_temp(self.db);self.assertEqual(count,1);self.assertFalse(errors)
        self.assertFalse(old.exists());self.assertTrue(keep.exists());self.assertTrue(recent.exists())
