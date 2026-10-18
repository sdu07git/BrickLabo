"""Independent stock pools, faithful ALT copies, timestamps and global undo."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
from atelier.data import Database
from atelier.alternative_catalogue import copy_items
from atelier.stock_clear import clear,statistics
from atelier.stock_filter import StockFilterDialog
from atelier.catalogue import Catalogue
from atelier.build_stock import InventoryReader,find_builds
from atelier.preview import VisualEngine
from atelier import projects,storage_wall as walls
from atelier.task_lifetime import drain_tasks

app=QApplication.instance() or QApplication([])

class StockAndAlternativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.db=Database(self.path/'db.sqlite');self.windows=[];self.engines=[]
        self.photo=self.path/'photo.png';Image.new('RGB',(70,60),'red').save(self.photo)
        self.p=self.item('part','3005');self.s=self.item('set','100-1');self.other=self.item('set','200-1')
        self.db.run("UPDATE items SET category='Bricks',category_id='1',image=?,year='2001',quantity=80,weight='2',dimensions='1x1' WHERE id=?",(str(self.photo),self.p))
        self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)");self.db.run("INSERT INTO colors VALUES(1,'Blue','0000FF',0)")
        for n,ref,qty in ((1,'100-1',5),(2,'200-1',7)):
            self.db.run('INSERT INTO inventories VALUES(?,1,?)',(n,ref));self.db.run("INSERT INTO inventory_parts VALUES(?,'3005',4,?,0,'')",(n,qty))
        self.db.add('stock',self.p,'4',40);self.db.add('stock_sets',self.s,quantity=2);self.db.add('stock_sets',self.other)
    def tearDown(self):
        for w in self.windows:w.close()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents();drain_tasks();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        for e in self.engines:e.close()
        self.db.close();self.temp.cleanup()
    def item(self,kind,ref,source='RB'):return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,'Test '+ref,ref))
    def keep(self,window):self.windows.append(window);return window
    def get(self,identity):return self.db.get_item(identity)
    def copy(self,identity=None,parts=False):return self.get(copy_items(self.db,[self.get(identity or self.s)],parts,'marque Lepin')['target_ids'][0])
    def snapshot(self,tables=('stock','stock_sets','stock_set_components','project_parts','storage_contents')):
        return {table:sorted(self.db.rows('SELECT * FROM '+table),key=lambda r:repr(sorted(r.items()))) for table in tables}
    def exclusions(self):return [self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.p,))[0]['id'],-self.db.rows('SELECT id FROM stock_sets WHERE item_id=?',(self.other,))[0]['id']]
    def available(self,**kw):
        with self.db.read() as c:c.execute('BEGIN');return InventoryReader(c,**kw).stock()
    def test_selected_sets_independent_of_unchecked_loose_rows(self):
        before=self.snapshot();self.assertEqual(sum(self.available(excluded_entries=self.exclusions()).values()),10)
        self.assertEqual([r['ref'] for r in find_builds(self.db,copies=2,excluded_entries=self.exclusions())[0]],['100-1']);self.assertEqual(self.snapshot(),before)
    def test_no_double_count_and_loose_only_reservations(self):
        project=projects.create(self.db,'Reserve',[{'item_id':self.p,'color':'4','quantity':30}]);projects.reserve(self.db,project)
        self.assertEqual(sum(self.available().values()),27);self.assertEqual(sum(self.available(include_set_stock=False).values()),10);self.assertEqual(sum(self.available(excluded_entries=self.exclusions()).values()),10)
    def test_untracked_sets_fallback_and_zero_custom_components(self):
        entry=self.db.rows('SELECT id FROM stock_sets WHERE item_id=?',(self.s,))[0]['id'];self.db.run('UPDATE stock_set_components SET quantity=0 WHERE set_entry_id=?',(entry,));self.assertFalse(self.available(excluded_entries=self.exclusions()))
        self.db.run('DELETE FROM stock_set_components WHERE set_entry_id=?',(entry,));before=self.snapshot();self.assertEqual(sum(self.available(excluded_entries=self.exclusions()).values()),10);self.assertEqual(before,self.snapshot())
    def test_stock_picker_displays_physical_quantities_and_native_ids(self):
        self.db.run("UPDATE items SET quantity=999 WHERE id=?",(self.p,));d=self.keep(StockFilterDialog(self.db));row=next(r for r in d.rows if r['kind']=='part');self.assertEqual(row['quantity'],40);self.assertEqual(row['item_id'],self.p);self.assertEqual(d.table.columnCount(),8)
        self.assertEqual({r['id'] for r in d.visible_items()},{self.p,self.s,self.other})
    def test_sets_only_shortcut_and_cancel(self):
        self.db.set_setting('build_excluded_entries',self.exclusions()[1:]);d=self.keep(StockFilterDialog(self.db));d.select_sets_only();d.reject();self.assertEqual(self.db.setting('build_excluded_entries'),self.exclusions()[1:])
        second=self.keep(StockFilterDialog(self.db));second.select_sets_only();second.save();self.assertTrue(self.db.setting('build_include_set_stock'));self.assertEqual(sum(self.available(excluded_entries=self.db.setting('build_excluded_entries')).values()),10)
    def test_copy_retains_all_metadata_visuals_and_settings(self):
        self.db.save_visual(self.p,color='4',links=['https://example.test/model']);self.db.set_setting('camera_item_'+str(self.p),{'yaw':17});before=self.snapshot();alt=self.copy(self.p)
        for field in ('category','category_id','image','year','quantity','weight','dimensions'):self.assertEqual(alt[field],self.get(self.p)[field])
        self.assertEqual((alt['origin_source'],alt['origin_ref'],alt['comment']),('RB','3005','marque Lepin'));self.assertEqual(self.db.visual(alt['id'])['color'],'4');self.assertEqual(self.db.setting('camera_item_'+str(alt['id'])),{'yaw':17});self.assertEqual(before,self.snapshot())
    def test_renamed_copy_keeps_render_photo_colours_and_comment_search(self):
        alt=self.copy(self.p);self.db.alternative('part','custom','Alternative','Bricks',item_id=alt['id']);alt=self.get(alt['id'])
        model=self.path/'ldraw';(model/'parts').mkdir(parents=True);(model/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n');(model/'parts/3005.dat').write_text('0 Brick\n4 16 0 0 0 20 0 0 20 20 0 0 20 0\n4 16 0 0 0 0 20 0 0 20 20 0 0 20\n');self.db.set_setting('ldraw',str(model));e=VisualEngine(self.db);self.engines.append(e)
        self.assertEqual(e.photo(alt,False).tobytes(),e.photo(self.get(self.p),False).tobytes());self.assertEqual(self.db.available_colors(alt)[0]['id'],4);self.assertEqual(self.db.query(source='ALT',search='Lepin')[1],1)
        for view in ('perspective','top','side','bottom'):
            a,_=e.render_3d(alt,(160,100),'4',view);b,_=e.render_3d(self.get(self.p),(160,100),'4',view);self.assertEqual(a.tobytes(),b.tobytes())
    def test_set_parts_copy_keeps_colours_spares_and_no_possession(self):
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',1,2,0,'')");self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',4,1,1,'')");before=self.snapshot();alt=self.copy(parts=True);rows=self.db.components(alt,strict=True)
        self.assertTrue(all(r['source']=='ALT' for r in rows));self.assertEqual(sorted((str(r['chosen_color']),r['chosen_quantity'],r['is_spare']) for r in rows),[('1',2,0),('4',1,1),('4',5,0)]);self.assertEqual(self.snapshot(),before)
    def test_copy_set_alone_does_not_overwrite_custom_inventory(self):
        alt=self.copy();self.assertEqual(self.db.components(alt)[0]['source'],'RB');self.db.set_setting('alt_components_'+str(alt['id']),[{'item_id':self.p,'color':'4','quantity':9}]);self.copy();self.assertEqual(self.db.components(alt)[0]['chosen_quantity'],9)
    def test_alt_owned_set_usable_and_native_equivalence_opt_in(self):
        alt=self.copy(parts=True);clear(self.db,'stock');clear(self.db,'stock_sets');self.db.add('stock_sets',alt['id']);before=self.snapshot()
        self.assertEqual([r['source'] for r in find_builds(self.db,source='ALT')[0]],['ALT']);self.assertFalse(find_builds(self.db)[0]);self.assertEqual([r['ref'] for r in find_builds(self.db,allow_alternatives=True)[0]],['100-1']);self.assertEqual(self.snapshot(),before)
    def test_unlinked_alt_is_not_guessed(self):
        clear(self.db,'stock');clear(self.db,'stock_sets');part=self.db.alternative('part','3005','Test 3005','Bricks');self.db.add('stock',part,'4',40);self.assertFalse(find_builds(self.db,allow_alternatives=True)[0])
    def test_project_keeps_physical_alt_ids_without_double_reservations(self):
        alt=self.copy(self.p);clear(self.db,'stock');self.db.add('stock',self.p,'4',2);self.db.add('stock',alt['id'],'4',3);before=self.db.rows('SELECT * FROM stock');project=projects.from_set(self.db,self.s,allow_alternatives=True)
        self.assertEqual({r['id']:r['required'] for r in projects.detail(self.db,project)},{self.p:2,alt['id']:3});projects.reserve(self.db,project);self.assertEqual(sum(r['reserved'] for r in projects.detail(self.db,project)),5)
        second=projects.from_set(self.db,self.s,allow_alternatives=True);self.assertEqual(projects.detail(self.db,second)[0]['id'],self.p);self.db.undo_last_action();self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
    def test_incomplete_copy_is_atomic(self):
        missing=self.item('set','999-1');before=self.snapshot(('items','settings','visual'))
        with self.assertRaises(ValueError):copy_items(self.db,[self.get(self.s),self.get(missing)],True)
        self.assertEqual(self.snapshot(('items','settings','visual')),before)
    def test_last_add_date_undo_redo_and_first_date_retained(self):
        self.db.run("UPDATE stock SET added='2000-01-01 01:02:03',last_added='2001-01-01 01:02:03'");before=self.db.rows('SELECT * FROM stock');self.db.add('stock',self.p,'4',5);row=self.db.rows('SELECT * FROM stock WHERE item_id=?',(self.p,))[0]
        self.assertEqual(row['quantity'],45);self.assertEqual(row['added'],'2000-01-01 01:02:03');self.assertNotEqual(row['last_added'],'2001-01-01 01:02:03');self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT * FROM stock'),before);self.db.redo_last_action();self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.p,))[0]['quantity'],45)
    def test_local_date_column_default_position_both_stocks(self):
        for scope in ('stock','stock_sets'):
            row=self.db.query(scope=scope,sort='stock_entered_at')[0][0];self.assertRegex(row['stock_entered_at'],r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d');cat=self.keep(Catalogue(self.db,scope=scope));self.assertEqual(cat.visible_columns.index('stock_entered_at'),cat.visible_columns.index('ref')+1)
    def test_date_migration_backfills_existing_rows(self):
        self.db.run('ALTER TABLE stock DROP COLUMN last_added');self.db.run('ALTER TABLE stock_sets DROP COLUMN last_added');path=self.db.path;self.db.close();self.db=Database(path)
        for scope in ('stock','stock_sets'):
            for row in self.db.rows('SELECT * FROM '+scope):self.assertEqual(row['added'],row['last_added'])
        self.assertEqual(statistics(self.db,'stock')['quantity'],40)
    def test_clear_one_action_restores_reservations_drawers_and_owned_sets(self):
        project=projects.create(self.db,'Project',[{'item_id':self.p,'color':'4','quantity':5}]);projects.reserve(self.db,project);wall=walls.create_wall(self.db,'Cabinet',2,1);drawers=walls.drawers(self.db,wall)
        for drawer in drawers:walls.assign(self.db,drawer['id'],[(self.p,'4')])
        self.db.run('UPDATE storage_contents SET quantity=10 WHERE drawer_id=?',(drawers[0]['id'],));before=self.snapshot();count=len(self.db.rows('SELECT * FROM action_history'));clear(self.db,'stock')
        self.assertEqual(len(self.db.rows('SELECT * FROM action_history')),count+1);self.assertEqual(statistics(self.db,'stock')['quantity'],0);self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),before['stock_sets']);self.db.undo_last_action();self.assertEqual(self.snapshot(),before)
    def test_clear_sets_never_transfers_to_loose_and_survives_restart_undo(self):
        before=self.snapshot();clear(self.db,'stock_sets');self.assertFalse(self.db.rows('SELECT * FROM stock_sets'));self.assertEqual(self.db.rows('SELECT * FROM stock'),before['stock']);path=self.db.path;self.db.close();self.db=Database(path);self.db.undo_last_action();self.assertEqual(self.snapshot(),before)
    def test_clear_revision_conflict_refuses_entire_change(self):
        facts=statistics(self.db,'stock');self.db.add('stock',self.p,'4',1);before=self.snapshot()
        with self.assertRaises(ValueError):clear(self.db,'stock',facts['revision'])
        self.assertEqual(self.snapshot(),before)
    def test_global_clear_across_pages_filtered_rows_cancel_and_undo(self):
        with self.db.connect() as c:
            for n in range(1201):
                iid=c.execute("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part',?,'Bulk','bulk')",('bulk'+str(n),)).lastrowid;c.execute("INSERT INTO stock(item_id,color,quantity) VALUES(?,'4',1)",(iid,))
        cat=self.keep(Catalogue(self.db,scope='stock'));cat.search.setText('3005');cat.timer.stop();cat.reload();before=self.snapshot()
        with patch('atelier.catalogue.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as question:cat.clear_all_stock()
        self.assertEqual(question.call_args.args[-1],QMessageBox.StandardButton.No);self.assertEqual(self.snapshot(),before)
        with patch('atelier.catalogue.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):cat.clear_all_stock()
        self.assertEqual(statistics(self.db,'stock')['lines'],0);self.db.undo_last_action();self.assertEqual(self.snapshot(),before)
