"""Real Qt drops, atomic location moves and A4/PDF output using shared images."""
from contextlib import contextmanager
from io import BytesIO
import re
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QPointF,QThreadPool,QCoreApplication,QEvent
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
import shiboken6

from atelier import storage_wall as walls
from atelier.storage_panel import StoragePanel
from atelier.storage_printing import StoragePrintPreview
from atelier.thumbnail_cache import ThumbnailCache
from atelier.thumbnails import ThumbnailContext,load_thumbnail
from atelier.windows import show_window
from test_storage_and_inventory_batches import Fixture,app


class DrawerMoveTests(Fixture):
    def seed(self):
        a=walls.create_wall(self.db,'Briques',4,3);b=walls.create_wall(self.db,'Accessoires',4,3)
        da,db=walls.drawers(self.db,a)[0],walls.drawers(self.db,b)[0]
        walls.save_drawer(self.db,a,1,1,1,1,'Briques rouges',da['id'])
        walls.save_drawer(self.db,b,1,1,1,1,'Armes',db['id'])
        walls.assign(self.db,da['id'],[(self.part,'4'),(self.other,'4')]);walls.assign(self.db,db['id'],[(self.other,'4')])
        return a,b,da,db
    def quantities(self):
        return {t:self.db.rows('SELECT * FROM '+t) for t in ('stock','stock_sets','stock_set_components','stock_undo','stock_revision','history')}
    def location(self,identity):return self.db.rows('SELECT * FROM storage_drawers WHERE id=?',(identity,))[0]
    def test_swap_filled_drawers_between_cabinets_keeps_ids_names_links_and_stock(self):
        a,b,da,db=self.seed();before=self.quantities();links=self.db.rows('SELECT * FROM storage_contents ORDER BY drawer_id,item_id')
        self.assertTrue(walls.move_drawer(self.db,da['id'],b,1,1))
        self.assertEqual((self.location(da['id'])['wall_id'],self.location(db['id'])['wall_id']),(b,a))
        self.assertEqual(self.location(da['id'])['name'],'Briques rouges');self.assertEqual(self.location(db['id'])['name'],'Armes')
        self.assertEqual(self.db.rows('SELECT * FROM storage_contents ORDER BY drawer_id,item_id'),links);self.assertEqual(self.quantities(),before)
        self.assertEqual({r['wall_name'] for r in walls.search(self.db,'3005')},{'Accessoires'})
    def test_large_drawer_moves_over_blank_cells_and_refills_old_footprint(self):
        a,b,da,db=self.seed();walls.save_drawer(self.db,a,1,1,2,1,'Briques rouges',da['id']);before=self.quantities()
        walls.move_drawer(self.db,da['id'],a,2,2)
        self.assertEqual((self.location(da['id'])['col'],self.location(da['id'])['row'],self.location(da['id'])['width']),(2,2,2))
        self.assertEqual(len(walls.contents(self.db,da['id'])),2);self.assertEqual(self.quantities(),before)
        drawers=walls.drawers(self.db,a);covered=[(x,y) for d in drawers for y in range(d['row'],d['row']+d['height']) for x in range(d['col'],d['col']+d['width'])]
        self.assertEqual(len(covered),12);self.assertEqual(len(set(covered)),12)
    def test_large_partial_move_keeps_overlapping_source_cells_covered_once(self):
        a,_,da,_=self.seed();walls.save_drawer(self.db,a,1,1,2,1,'Briques rouges',da['id'])
        walls.move_drawer(self.db,da['id'],a,2,1)
        cells=[(x,y) for d in walls.drawers(self.db,a) for y in range(d['row'],d['row']+d['height']) for x in range(d['col'],d['col']+d['width'])]
        self.assertEqual(len(cells),12);self.assertEqual(len(set(cells)),12);self.assertEqual(len(walls.contents(self.db,da['id'])),2)
    def test_different_filled_sizes_or_named_neighbours_reject_without_mutation(self):
        a,b,da,db=self.seed();walls.save_drawer(self.db,a,1,1,2,1,'Briques rouges',da['id'])
        before=walls.print_snapshot(self.db);quantities=self.quantities()
        with self.assertRaises(ValueError):walls.move_drawer(self.db,da['id'],b,1,1)
        self.assertEqual(walls.print_snapshot(self.db),before);self.assertEqual(self.quantities(),quantities)
        other=next(d for d in walls.drawers(self.db,a) if d['col']==2 and d['row']==2)
        walls.save_drawer(self.db,a,2,2,1,1,'Réservé',other['id']);before=walls.print_snapshot(self.db)
        with self.assertRaises(ValueError):walls.move_drawer(self.db,da['id'],a,2,2)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_outside_invalid_missing_target_and_unchanged_drop_do_not_write(self):
        a,b,da,db=self.seed();before=walls.print_snapshot(self.db);statements=[];original=self.db.connect
        @contextmanager
        def traced():
            with original() as c:c.set_trace_callback(statements.append);yield c
        with patch.object(self.db,'connect',traced):self.assertFalse(walls.move_drawer(self.db,da['id'],a,1,1))
        self.assertFalse(any(s.lstrip().upper().startswith(('UPDATE','INSERT','DELETE')) for s in statements))
        for wall,col,row in [(a,5,1),(a,0,1),(a,1,4),(a,True,1),(a,1.5,1),(999,1,1)]:
            with self.subTest(wall=wall,col=col,row=row),self.assertRaises(ValueError):walls.move_drawer(self.db,da['id'],wall,col,row)
            self.assertEqual(walls.print_snapshot(self.db),before)
    def test_failed_swap_rolls_back_every_update(self):
        a,b,da,db=self.seed();before=walls.print_snapshot(self.db)
        self.db.run("CREATE TRIGGER reject_drawer_move BEFORE UPDATE ON storage_drawers WHEN NEW.wall_id<>OLD.wall_id BEGIN SELECT RAISE(ABORT,'write refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):walls.move_drawer(self.db,da['id'],b,1,1)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_moved_locations_round_trip_in_separate_storage_backup(self):
        from atelier.preferences_backup import export_family,restore_families
        from atelier.data import Database
        a,b,da,db=self.seed();walls.move_drawer(self.db,da['id'],b,2,2)
        path=Path(self.temp.name)/'rangement.json';export_family(self.db,'storage',path)
        restored=Database(Path(self.temp.name)/'restored.sqlite')
        try:
            restore_families(restored,[path]);hit=walls.search(restored,'3005')[0]
            self.assertEqual((hit['wall_name'],hit['col'],hit['row']),('Accessoires',2,2))
            self.assertEqual(len(walls.contents(restored,hit['id'])),2)
        finally:restored.close()


class DrawerDragTests(Fixture):
    def seed(self):
        a=walls.create_wall(self.db,'Briques',3,2);b=walls.create_wall(self.db,'Casques',3,2)
        walls.position_wall(self.db,b,*walls.relative_position(self.db,b,a,'above'))
        da,db=walls.drawers(self.db,a)[0],walls.drawers(self.db,b)[0]
        walls.assign(self.db,da['id'],[(self.part,'4')]);walls.assign(self.db,db['id'],[(self.other,'4')])
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1100,850);panel.show();panel.front.setChecked(True)
        panel.drag_drawers.setChecked(True);panel.fit();app.processEvents();return panel,a,b,da,db
    def drag(self,panel,item,end):
        start=panel.view.mapFromScene(item.mapToScene(item.transform_face.map(QPointF(40,30))))
        QTest.mousePress(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
        QTest.mouseMove(panel.view.viewport(),end,20)
    def test_real_drop_between_cabinets_writes_only_on_release(self):
        panel,a,b,da,db=self.seed();before=walls.print_snapshot(self.db);stock=self.db.rows('SELECT * FROM stock')
        item=panel.items[da['id']];target=panel.items[db['id']]
        end=panel.view.mapFromScene(target.mapToScene(target.transform_face.map(QPointF(40,30))))
        self.drag(panel,item,end);app.processEvents();self.assertTrue(shiboken6.isValid(item));self.assertEqual(walls.print_snapshot(self.db),before)
        QTest.mouseRelease(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
        moved=self.db.rows('SELECT wall_id FROM storage_drawers WHERE id=?',(da['id'],))[0]['wall_id']
        self.assertEqual(moved,b);self.assertEqual(panel.wall_id,b);self.assertEqual(panel.drawer_id,da['id'])
        self.assertEqual(panel.table.rowCount(),1);self.assertEqual(self.db.rows('SELECT * FROM stock'),stock)
        self.assertEqual(walls.search(self.db,'3005')[0]['wall_name'],'Casques')
    def test_angled_drop_snaps_to_cell_without_generating_files(self):
        panel,a,b,da,db=self.seed();panel.front.setChecked(False);panel.angle.setValue(30);panel.fit();app.processEvents()
        item=panel.items[da['id']];target=next(i for i in panel.items.values() if i.drawer['wall_id']==a and i.drawer['col']==2 and i.drawer['row']==2)
        end=panel.view.mapFromScene(target.mapToScene(target.transform_face.map(QPointF(40,30))))
        before={p.relative_to(self.temp.name) for p in Path(self.temp.name).rglob('*')}
        self.drag(panel,item,end);QTest.mouseRelease(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
        moved=next(d for d in walls.drawers(self.db,a) if d['id']==da['id']);self.assertEqual((moved['col'],moved['row']),(2,2))
        self.assertEqual(before,{p.relative_to(self.temp.name) for p in Path(self.temp.name).rglob('*')})
    def test_invalid_drop_and_disk_error_restore_visible_item(self):
        panel,a,b,da,db=self.seed();item=panel.items[da['id']];before=walls.print_snapshot(self.db)
        old=QPointF(item.pos());item.start_position=old;item.setPos(-1000,-1000)
        panel.move_drawer(da['id'],item.mapToScene(QPointF()))
        self.assertEqual(item.pos(),old);self.assertEqual(walls.print_snapshot(self.db),before)
        target=panel.items[db['id']]
        with patch.object(walls,'move_drawer',side_effect=sqlite3.OperationalError('Disque inaccessible')):panel.move_drawer(da['id'],target.mapToScene(QPointF()))
        self.assertEqual(item.pos(),old);self.assertEqual(walls.print_snapshot(self.db),before);self.assertIn('Disque inaccessible',panel.placement_hint.text())
    def test_modes_are_exclusive_and_remain_usable_after_last_cabinet_deleted(self):
        panel,a,b,da,db=self.seed();panel.arrange.setChecked(True)
        self.assertFalse(panel.drag_drawers.isChecked());panel.drag_drawers.setChecked(True);self.assertFalse(panel.arrange.isChecked())
        walls.delete_wall(self.db,a);walls.delete_wall(self.db,b);panel.reload_walls()
        self.assertFalse(panel.drag_drawers.isChecked());self.assertFalse(panel.drag_drawers.isEnabled());self.assertFalse(panel.print_action.isEnabled())


class PrintTests(Fixture):
    def seed(self):
        a=walls.create_wall(self.db,'Briques',3,3);b=walls.create_wall(self.db,'Casques',2,2)
        walls.position_wall(self.db,b,*walls.relative_position(self.db,b,a,'above'))
        drawer=walls.drawers(self.db,a)[0];walls.save_drawer(self.db,a,1,1,2,1,'Briques rouges',drawer['id'])
        walls.assign(self.db,drawer['id'],[(self.part,'4'),(self.other,'4')]);walls.assign(self.db,walls.drawers(self.db,b)[0]['id'],[(self.part,'4')])
        return a,b
    def engine(self):
        class FakeEngine:
            def __init__(inner):inner.thumbnail_cache=ThumbnailCache(Path(self.temp.name)/'cache');inner.calls=[]
            def renderer(inner):return True
            def render_3d(inner,part,size,color):
                inner.calls.append((part['id'],color));image=Image.new('RGBA',size,'white')
                ImageDraw.Draw(image).rectangle((15,10,85,55),fill='#ee3333',outline='black');return image,''
            def photo(inner,*args,**kwargs):return None
        return FakeEngine()
    def wait(self,window):
        deadline=time.monotonic()+5
        while window.running and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        app.processEvents();self.assertFalse(window.running)
    def pdf(self,window,name):
        path=Path(self.temp.name)/name;window.export_pdf(path);content=path.read_bytes()
        self.assertTrue(content.startswith(b'%PDF-'));return path,content
    def test_a4_pages_orientation_scope_and_images_use_shared_cache(self):
        a,b=self.seed();engine=self.engine();part=walls.wall_contents(self.db,a)[0]
        load_thumbnail(engine,part,ThumbnailContext(self.db).state(part),engine.thumbnail_cache.generation)
        window=self.keep(StoragePrintPreview(self.db,engine,a));self.wait(window)
        self.assertEqual(len(engine.calls),2);self.assertEqual(len(window.images),2)
        path,content=self.pdf(window,'portrait.pdf');self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',content)),2)
        self.assertIn(b'/Subtype /Image',content);self.assertRegex(content,rb'/MediaBox\s*\[0 0 595(?:\.\d+)? 842(?:\.\d+)?\]')
        before={p:p.stat().st_mtime_ns for p in (Path(self.temp.name)/'cache').glob('*.png')}
        window.orientation.setCurrentIndex(1);window.scope.setCurrentIndex(2);self.wait(window)
        _,content=self.pdf(window,'overview.pdf');self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',content)),1)
        self.assertRegex(content,rb'/MediaBox\s*\[0 0 842(?:\.\d+)? 595(?:\.\d+)?\]')
        window.scope.setCurrentIndex(0);self.wait(window);self.assertEqual(len(window.pages()),1);self.assertEqual(len(engine.calls),2)
        self.assertEqual({p:p.stat().st_mtime_ns for p in (Path(self.temp.name)/'cache').glob('*.png')},before)
    def test_snapshot_and_repaints_do_not_reread_database_or_touch_stocks(self):
        a,b=self.seed();stock=self.db.rows('SELECT * FROM stock');window=self.keep(StoragePrintPreview(self.db,None,a))
        snapshot=window.snapshot;walls.delete_wall(self.db,b)
        with patch.object(self.db,'rows',side_effect=AssertionError('paint queried SQL')),patch.object(self.db,'read',side_effect=AssertionError('paint queried SQL')),patch.object(self.db,'connect',side_effect=AssertionError('paint wrote SQL')):
            window.orientation.setCurrentIndex(1);window.update_preview();_,content=self.pdf(window,'snapshot.pdf')
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',content)),2);self.assertEqual(window.snapshot,snapshot);self.assertEqual(self.db.rows('SELECT * FROM stock'),stock)
    def test_printer_page_range_renders_only_requested_cabinet(self):
        a,b=self.seed();window=self.keep(StoragePrintPreview(self.db,None,a));printer=window.make_printer()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat);path=Path(self.temp.name)/'range.pdf';printer.setOutputFileName(str(path))
        printer.setPrintRange(QPrinter.PrintRange.PageRange);printer.setFromTo(2,2)
        self.assertTrue(window.paint_pages(printer));self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',path.read_bytes())),1)
    def test_failed_pdf_does_not_replace_existing_file(self):
        a,b=self.seed();window=self.keep(StoragePrintPreview(self.db,None,a));path=Path(self.temp.name)/'keep.pdf';path.write_bytes(b'original')
        with patch.object(window,'paint_pages',return_value=False),self.assertRaises(OSError):window.export_pdf(path)
        self.assertEqual(path.read_bytes(),b'original')
    def test_close_cancels_loading_suppresses_callbacks_and_defers_delete(self):
        a,b=self.seed();engine=self.engine();release=threading.Event();started=threading.Event()
        original=engine.render_3d
        def blocked(*args):started.set();release.wait(3);return original(*args)
        engine.render_3d=blocked;root=self.keep(QWidget());window=StoragePrintPreview(self.db,engine,a,root);show_window(window,root)
        self.assertTrue(started.wait(2));window.reject();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertTrue(shiboken6.isValid(window));release.set();QThreadPool.globalInstance().waitForDone(4000);app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertFalse(shiboken6.isValid(window));self.assertEqual(len(engine.calls),1)
    def test_scope_change_during_loading_uses_latest_selection_and_cached_result(self):
        a,b=self.seed();engine=self.engine();release=threading.Event();started=threading.Event();original=engine.render_3d
        def blocked(*args):started.set();release.wait(3);return original(*args)
        engine.render_3d=blocked;window=self.keep(StoragePrintPreview(self.db,engine,a))
        self.assertTrue(started.wait(2));window.scope.setCurrentIndex(0)
        self.assertFalse(window.print_button.isEnabled());self.assertTrue(window.pending)
        release.set();self.wait(window)
        self.assertFalse(window.pending);self.assertTrue(window.print_button.isEnabled());self.assertEqual(len(window.images),2)
        self.assertEqual(len(engine.calls),2);self.assertEqual(len(window.pages()),1)
    def test_image_memory_budget_stops_worker_and_keeps_references_printable(self):
        a,b=self.seed();engine=self.engine()
        with patch('atelier.storage_printing.IMAGE_BUDGET',1):
            window=self.keep(StoragePrintPreview(self.db,engine,a));self.wait(window)
        self.assertTrue(window.limited);self.assertEqual(window.image_bytes,0);self.assertEqual(len(engine.calls),1)
        self.assertTrue(window.print_button.isEnabled());_,content=self.pdf(window,'without-images.pdf')
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',content)),2)
    def test_same_part_in_two_colours_has_two_separate_print_images(self):
        a,b=self.seed();self.db.run("INSERT INTO colors VALUES(1,'Bleu','0000FF',0)");self.db.add('stock',self.part,'1',5)
        drawer=walls.drawers(self.db,a)[0];walls.assign(self.db,drawer['id'],[(self.part,'1')]);engine=self.engine()
        window=self.keep(StoragePrintPreview(self.db,engine,a));self.wait(window)
        self.assertIn((self.part,'1'),window.images);self.assertIn((self.part,'4'),window.images)
        self.assertEqual({color for item,color in engine.calls if item==self.part},{'1','4'})
