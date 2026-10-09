import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile,threading,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication,QDialog,QMainWindow,QListWidget
from atelier.data import Database
from atelier import storage_wall as walls,inventory_batches as batches
from atelier.build_stock import find_builds,build_details
from atelier.storage_panel import StoragePanel
from atelier.inventory_batch_dialog import InventoryBatchDialog
from atelier.windows import show_window

app=QApplication.instance() or QApplication([])


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.windows=[]
        self.part=self.item('part','3005','Brique 1 x 1');self.other=self.item('part','3001','Brique 2x4')
        self.db.run("INSERT INTO colors VALUES(4,'Rouge','FF0000',0)")
        self.db.add('stock',self.part,'4',40);self.db.add('stock',self.other,'4',12)
    def tearDown(self):
        for window in self.windows:window.close()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents();self.db.close();self.temp.cleanup()
    def item(self,kind,ref,name='Set',source='RB'):
        return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,name,name))
    def keep(self,window):self.windows.append(window);return window


class StorageTests(Fixture):
    def seed(self):
        wall=walls.create_wall(self.db,'Atelier',4,6)
        drawer=next(d for d in walls.drawers(self.db,wall) if d['col']==3 and d['row']==5)
        return wall,drawer
    def test_mixed_drawer_and_search_exact_address_do_not_change_stock(self):
        wall,drawer=self.seed();before=self.db.rows('SELECT * FROM stock')
        walls.assign(self.db,drawer['id'],[(self.part,'4'),(self.other,'4')]);walls.assign(self.db,drawer['id'],[(self.part,'4')])
        self.assertEqual(len(walls.contents(self.db,drawer['id'])),2)
        hit=walls.search(self.db,'1 × 1 rouge')[0];self.assertEqual((hit['col'],hit['row']),(3,5));self.assertIn('3',walls.address(hit))
        self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
    def test_multiple_locations_and_zero_stock_remain_visible(self):
        wall,drawer=self.seed();first=walls.drawers(self.db,wall)[0]
        for d in (first,drawer):walls.assign(self.db,d['id'],[(self.part,'4')])
        self.assertEqual(len(walls.search(self.db,'3005')),2)
        self.db.run('UPDATE stock SET quantity=0 WHERE item_id=?',(self.part,))
        self.assertEqual(walls.contents(self.db,drawer['id'])[0]['chosen_quantity'],0)
    def test_wide_drawer_merges_empty_neighbours_and_preserves_contents(self):
        wall,drawer=self.seed();first=walls.drawers(self.db,wall)[0];walls.assign(self.db,first['id'],[(self.part,'4')])
        walls.save_drawer(self.db,wall,1,1,2,1,'Chapeaux',first['id'])
        self.assertEqual(len(walls.drawers(self.db,wall)),23);self.assertEqual(walls.contents(self.db,first['id'])[0]['id'],self.part)
        hit=walls.search(self.db,'chapeaux')[0];self.assertEqual(hit['width'],2)
    def test_overlap_with_populated_drawer_rolls_back(self):
        wall,_=self.seed();drawers=walls.drawers(self.db,wall);walls.assign(self.db,drawers[1]['id'],[(self.part,'4')]);before=walls.drawers(self.db,wall)
        with self.assertRaises(ValueError):walls.save_drawer(self.db,wall,1,1,2,1,'Armes',drawers[0]['id'])
        self.assertEqual(walls.drawers(self.db,wall),before)
    def test_layout_can_grow_and_survives_reopen(self):
        wall,_=self.seed();walls.save_drawer(self.db,wall,5,7,3,2,'Escaliers')
        reopened=Database(self.db.path)
        self.assertEqual((walls.walls(reopened)[0]['columns'],walls.walls(reopened)[0]['rows']),(7,8));reopened.close()
    def test_mixed_wall_ui_search_selects_drawer_and_rotation_writes_no_files(self):
        wall,drawer=self.seed();walls.assign(self.db,drawer['id'],[(self.part,'4'),(self.other,'4')])
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1000,800);panel.show();app.processEvents()
        panel.query.setText('1x1');panel.search();self.assertEqual(panel.results.rowCount(),1);self.assertEqual(panel.drawer_id,drawer['id']);self.assertEqual(panel.table.rowCount(),2)
        panel.search();self.assertIn(walls.address(drawer),panel.status.text())
        before={p.relative_to(self.temp.name) for p in Path(self.temp.name).rglob('*')}
        for angle in (-30,0,30):panel.angle.setValue(angle)
        panel.front.setChecked(True);panel.front.setChecked(False);panel.grab()
        self.assertEqual(before,{p.relative_to(self.temp.name) for p in Path(self.temp.name).rglob('*')})
    def test_storage_backup_uses_references_and_preserves_stock_quantities(self):
        from atelier.preferences_backup import export_family,restore_families
        wall,drawer=self.seed();walls.assign(self.db,drawer['id'],[(self.part,'4'),(self.other,'4')])
        path=Path(self.temp.name)/'storage.json';export_family(self.db,'storage',path)
        second=Database(Path(self.temp.name)/'other.sqlite');second.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','other','Other','other')")
        restore_families(second,[path]);found=walls.search(second,'3005');self.assertEqual(len(found),1);self.assertEqual(found[0]['stock_quantity'],0);self.assertEqual((found[0]['col'],found[0]['row']),(3,5));second.close()


class BatchTests(Fixture):
    def sets(self,n=12):return [self.db.get_item(self.item('set',str(100+k)+'-1')) for k in range(n)]
    def api(self,pages=False,fail_ref=None,cancel=None):
        class FakeAPI:
            calls=[]
            def __init__(self,db):pass
            def rb(inner,path):
                inner.calls.append(path)
                if fail_ref and ('sets/'+fail_ref+'/') in path:raise ValueError('inventory unavailable')
                if cancel:cancel.set()
                ref='3001' if path.startswith('https://') else '3005'
                return {'results':[{'part':{'part_num':ref,'name':'Brick','part_cat_id':1},'color':{'id':4,'name':'Rouge','rgb':'FF0000'},'quantity':2,'is_spare':False}],
                  'next':'https://rebrickable.com/api/v3/lego/sets/100-1/parts/?page=2' if pages and not path.startswith('https://') else None}
        return FakeAPI
    def test_ten_then_remainder_resume_and_ownership_unchanged(self):
        items=self.sets();before=self.db.rows('SELECT * FROM stock');job=batches.create_job(self.db,items,10)
        result=batches.run_batch(self.db,job,api_factory=self.api());self.assertEqual((result['loaded'],result['pending']),(10,2))
        reopened=Database(self.db.path);result=batches.run_batch(reopened,job,api_factory=self.api());reopened.close()
        self.assertEqual((result['loaded'],result['pending']),(12,0));self.assertEqual(self.db.rows('SELECT * FROM stock'),before);self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
    def test_cached_inventory_is_used_by_components_and_build_search(self):
        item=self.sets(1)[0];job=batches.create_job(self.db,[item]);batches.run_batch(self.db,job,api_factory=self.api(True))
        self.assertEqual({p['ref'] for p in self.db.components(item,strict=True)},{'3001','3005'})
        builds=find_builds(self.db)[0];self.assertEqual(len(builds),1);self.assertEqual(builds[0]['missing'],0)
        details,complete=build_details(self.db,item);self.assertTrue(complete);self.assertEqual(sum(p[4] for p in details),4)
    def test_available_inventory_is_skipped_without_network(self):
        item=self.sets(1)[0];job=batches.create_job(self.db,[item]);api=self.api();batches.run_batch(self.db,job,api_factory=api)
        again=batches.create_job(self.db,[item]);api=self.api();result=batches.run_batch(self.db,again,api_factory=api)
        self.assertEqual(result['skipped'],1);self.assertEqual(api.calls,[])
    def test_failure_retained_and_retry_keeps_successes(self):
        items=self.sets(2);job=batches.create_job(self.db,items);result=batches.run_batch(self.db,job,api_factory=self.api(fail_ref=items[0]['ref']))
        self.assertEqual((result['errors'],result['loaded']),(1,1));batches.retry_errors(self.db,job)
        api=self.api();result=batches.run_batch(self.db,job,api_factory=api);self.assertEqual(result['loaded'],2);self.assertEqual(len(api.calls),1)
    def test_cancel_mid_inventory_does_not_publish_partial_parts(self):
        item=self.sets(1)[0];job=batches.create_job(self.db,[item]);cancel=threading.Event();result=batches.run_batch(self.db,job,cancel,api_factory=self.api(True,cancel=cancel))
        self.assertEqual(result['pending'],1);self.assertEqual(self.db.rows('SELECT * FROM catalogue_inventory'),[])
    def test_bad_pagination_does_not_commit_inventory(self):
        item=self.sets(1)[0];job=batches.create_job(self.db,[item]);api=self.api()
        def response(self,path):return {'results':[],'next':'https://example.com/parts/'}
        api.rb=response;result=batches.run_batch(self.db,job,api_factory=api)
        self.assertEqual(result['errors'],1);self.assertEqual(self.db.rows('SELECT * FROM catalogue_inventory'),[])
    def test_batch_dialog_selection_and_saved_queue(self):
        self.sets(2);dialog=self.keep(InventoryBatchDialog(self.db));dialog.list_sets();self.assertEqual(dialog.table.rowCount(),2)
        dialog.table.selectRow(0);dialog.prepare_selection();self.assertIsNotNone(dialog.job);self.assertEqual(batches.summary(self.db,dialog.job)['total'],1)
    def test_authentication_failure_keeps_queue_pending(self):
        from urllib.error import HTTPError
        items=self.sets(2);job=batches.create_job(self.db,items);api=self.api()
        def fail(self,path):raise HTTPError('https://rebrickable.com/',401,'Unauthorized',{},None)
        api.rb=fail
        with self.assertRaises(HTTPError):batches.run_batch(self.db,job,api_factory=api)
        self.assertEqual(batches.summary(self.db,job)['pending'],2)
    def test_manual_bricklink_inventory_takes_priority_over_api_cache(self):
        # API cache must never override a manual reference/color decision.
        set_id=self.item('set','123-1',source='BL');part_id=self.item('part','3005',source='BL')
        self.db.run('INSERT INTO bl_manual_inventory VALUES(?,?,?,?,?,?,?,?,?)',(set_id,1,part_id,'5',7,0,0,0,0))
        self.db.set_setting('bl_manual_inventory_'+str(set_id),{'date':'today'})
        batches.store_inventory(self.db,'BL','123-1',[{'source':'BL','kind':'part','ref':'3001','name':'Brick','color':'5','quantity':2}])
        self.assertEqual(self.db.components(self.db.get_item(set_id))[0]['chosen_quantity'],7)


class WindowTests(unittest.TestCase):
    def test_nested_windows_leave_main_and_parent_usable(self):
        root=QMainWindow();root.nav=QListWidget();root.refresh_counts=lambda:None;root.show()
        first=show_window(QDialog(root),root);second=show_window(QDialog(first),first);app.processEvents()
        self.assertIsNone(app.activeModalWidget());self.assertTrue(root.isEnabled());self.assertTrue(first.isEnabled());self.assertIs(second.parent(),root)
        first.reject();app.processEvents();self.assertTrue(second.isVisible());second.reject();root.close()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    def test_close_during_worker_defers_destruction_and_suppresses_callback(self):
        import shiboken6
        from atelier.ui_common import async_task
        root=QMainWindow();root.nav=QListWidget();root.refresh_counts=lambda:None
        window=QDialog(root);release=threading.Event();called=[]
        async_task(window,lambda _:release.wait(3),lambda result:called.append(result))
        show_window(window,root);window.reject();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertTrue(shiboken6.isValid(window));release.set();QThreadPool.globalInstance().waitForDone(5000);app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertFalse(shiboken6.isValid(window));self.assertEqual(called,[]);root.close()
