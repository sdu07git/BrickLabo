"""Cabinet deletion, persistent layouts and actual Qt arrangement interactions."""
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox,QMessageBox,QPushButton,QDoubleSpinBox
import shiboken6

from atelier.data import Database
from atelier import storage_wall as walls
from atelier.storage_panel import StoragePanel
from atelier.preferences_backup import export_family,restore_families,collect_family
from atelier.preview import VisualEngine
from atelier.paths import resources_directory
from test_storage_and_inventory_batches import Fixture,app


class LayoutTests(Fixture):
    def stock_state(self):
        return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','stock_undo','history','stock_revision')}
    def pair(self):
        return walls.create_wall(self.db,'Briques',2,3),walls.create_wall(self.db,'Accessoires',3,2)
    def test_delete_cascades_only_locations_of_chosen_cabinet(self):
        a,b=self.pair();da,db=walls.drawers(self.db,a)[0],walls.drawers(self.db,b)[0]
        for drawer in (da,db):walls.assign(self.db,drawer['id'],[(self.part,'4'),(self.other,'4')])
        set_id=self.item('set','75192-1');self.db.run('INSERT INTO stock_sets(item_id,color,quantity) VALUES(?,?,?)',(set_id,'',1))
        # Include independent set components, undo history and stock revision.
        entry=self.db.rows('SELECT id FROM stock_sets WHERE item_id=?',(set_id,))[0]['id']
        self.db.run('INSERT INTO stock_set_components VALUES(?,?,?,?)',(entry,self.part,'4',8))
        before=self.stock_state();survivors=walls.drawers(self.db,b)
        walls.delete_wall(self.db,a)
        self.assertEqual(walls.drawers(self.db,a),[]);self.assertEqual(walls.contents(self.db,da['id']),[])
        self.assertEqual(walls.drawers(self.db,b),survivors);self.assertEqual(len(walls.contents(self.db,db['id'])),2)
        self.assertEqual(self.stock_state(),before)
        with self.assertRaises(ValueError):walls.delete_wall(self.db,a)
    def test_legacy_migration_preserves_ids_links_and_runs_once(self):
        a,b=self.pair();drawer=walls.drawers(self.db,a)[0];walls.assign(self.db,drawer['id'],[(self.part,'4')])
        before=self.stock_state();drawers=self.db.rows('SELECT * FROM storage_drawers ORDER BY id');links=self.db.rows('SELECT * FROM storage_contents')
        path=self.db.path;self.db.close()
        with sqlite3.connect(path) as connection:
            connection.execute('ALTER TABLE storage_walls DROP COLUMN x');connection.execute('ALTER TABLE storage_walls DROP COLUMN y')
        self.db=Database(path)
        self.assertEqual([(w['id'],w['x'],w['y']) for w in walls.walls(self.db)],[(a,0.,0.),(b,2.5,0.)])
        self.assertEqual(self.db.rows('SELECT * FROM storage_drawers ORDER BY id'),drawers);self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),links)
        self.assertEqual(self.stock_state(),before)
        walls.position_wall(self.db,a,-2,-4);layout=walls.walls(self.db);self.db.close();self.db=Database(path)
        self.assertEqual(walls.walls(self.db),layout)
    def test_relative_placements_work_with_different_sizes_and_negative_positions(self):
        a,b=self.pair();walls.position_wall(self.db,a,10,10)
        expected={'left':(6.5,10.),'right':(12.5,10.),'above':(10.,7.3),'below':(10.,13.7)}
        before=self.stock_state()
        for direction,coordinates in expected.items():
            with self.subTest(direction=direction):
                self.assertEqual(walls.relative_position(self.db,b,a,direction),coordinates)
                walls.position_wall(self.db,b,*coordinates)
        walls.position_wall(self.db,a,-10,-10)
        coordinates=walls.relative_position(self.db,b,a,'above',0);walls.position_wall(self.db,b,*coordinates)
        self.assertEqual(coordinates,(-10.,-12.5));self.assertEqual(self.stock_state(),before)
    def test_overlap_and_invalid_positions_leave_database_unchanged(self):
        a,b=self.pair();before=walls.walls(self.db)
        for x,y in [(0,0),(2.2,0),(float('nan'),0),(0,float('inf')),(walls.MAX_POSITION+1,0),(True,0)]:
            with self.subTest(x=x,y=y),self.assertRaises(ValueError):walls.position_wall(self.db,b,x,y)
            self.assertEqual(walls.walls(self.db),before)
        walls.position_wall(self.db,b,2.3,0)  # Exact touching edges are allowed.
        with self.assertRaises(ValueError):walls.relative_position(self.db,b,a,'left',-.1)
        with self.assertRaises(ValueError):walls.relative_position(self.db,b,b,'above')
        with self.assertRaises(ValueError):walls.relative_position(self.db,b,a,'diagonal')
    def test_unchanged_position_does_not_issue_an_update(self):
        a,_=self.pair();statements=[];original=self.db.connect
        from contextlib import contextmanager
        @contextmanager
        def traced():
            with original() as connection:
                connection.set_trace_callback(statements.append);yield connection
        with patch.object(self.db,'connect',traced):
            walls.position_wall(self.db,a,0.04,0.01);walls.update_wall(self.db,a,' Briques ',0,0)
        self.assertFalse(any(s.lstrip().upper().startswith('UPDATE ') for s in statements))
    def test_growing_into_another_cabinet_is_atomic(self):
        a,b=self.pair();drawer=walls.drawers(self.db,a)[0];walls.assign(self.db,drawer['id'],[(self.part,'4')])
        before=collect_family(self.db,'storage');stock=self.stock_state()
        with self.assertRaises(ValueError):walls.save_drawer(self.db,a,1,1,3,1,'Large',drawer['id'])
        self.assertEqual(collect_family(self.db,'storage'),before);self.assertEqual(self.stock_state(),stock)
        walls.position_wall(self.db,b,5,0);walls.save_drawer(self.db,a,1,1,3,1,'Large',drawer['id'])
        self.assertEqual(walls.walls(self.db)[0]['columns'],3);self.assertEqual(walls.contents(self.db,drawer['id'])[0]['id'],self.part)
    def test_positions_and_links_round_trip_in_selective_backup(self):
        a,b=self.pair();walls.position_wall(self.db,b,*walls.relative_position(self.db,b,a,'above'))
        walls.assign(self.db,walls.drawers(self.db,b)[0]['id'],[(self.part,'4')])
        before=collect_family(self.db,'storage');stock=self.stock_state();path=Path(self.temp.name)/'storage.json'
        export_family(self.db,'storage',path);walls.delete_wall(self.db,a);walls.position_wall(self.db,b,15,15)
        restore_families(self.db,[path]);self.assertEqual(collect_family(self.db,'storage'),before);self.assertEqual(self.stock_state(),stock)
    def test_legacy_backup_places_cabinets_alongside_each_other(self):
        self.pair();path=Path(self.temp.name)/'storage.json';export_family(self.db,'storage',path)
        payload=json.loads(path.read_text());
        for wall in payload['data']['walls']:wall.pop('x');wall.pop('y')
        path.write_text(json.dumps(payload));stock=self.stock_state();restore_families(self.db,[path])
        self.assertEqual([(w['x'],w['y']) for w in walls.walls(self.db)],[(0.,0.),(2.5,0.)]);self.assertEqual(self.stock_state(),stock)
    def test_invalid_backup_rolls_back_all_cabinets_and_links(self):
        a,b=self.pair();walls.assign(self.db,walls.drawers(self.db,b)[0]['id'],[(self.part,'4')])
        before=collect_family(self.db,'storage');stock=self.stock_state();path=Path(self.temp.name)/'storage.json';export_family(self.db,'storage',path)
        original=json.loads(path.read_text())
        for invalid in [{'x':0,'y':0},{'x':float('nan'),'y':0},{'x':'2.5','y':0},{'x':2.5}]:
            with self.subTest(invalid=invalid):
                payload=json.loads(json.dumps(original));wall=payload['data']['walls'][1];wall.pop('x');wall.pop('y');wall.update(invalid);path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):restore_families(self.db,[path])
                self.assertEqual(collect_family(self.db,'storage'),before);self.assertEqual(self.stock_state(),stock)


class LayoutUITests(Fixture):
    def seed(self):
        a=walls.create_wall(self.db,'Briques',2,3);b=walls.create_wall(self.db,'Accessoires',3,2)
        walls.position_wall(self.db,b,*walls.relative_position(self.db,b,a,'above'))
        da=walls.drawers(self.db,a)[0];db=walls.drawers(self.db,b)[0]
        walls.assign(self.db,da['id'],[(self.other,'4')]);walls.assign(self.db,db['id'],[(self.part,'4')])
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1100,900);panel.show();app.processEvents();panel.front.setChecked(True);panel.fit();app.processEvents()
        return panel,a,b,da,db
    def click_item(self,panel,item,point=QPointF(40,35)):
        position=panel.view.mapFromScene(item.mapToScene(point));QTest.mouseClick(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,position);app.processEvents()
    def test_overview_selection_keeps_emitting_items_alive(self):
        panel,a,b,da,db=self.seed();self.assertEqual(set(panel.cabinets),{a,b});self.assertEqual(len(panel.items),12)
        item=panel.items[db['id']];self.assertIs(item.parentItem(),panel.cabinets[b]);self.click_item(panel,item)
        self.assertTrue(shiboken6.isValid(item));self.assertIs(panel.items[db['id']],item)
        self.assertEqual((panel.wall_id,panel.wall.currentData(),panel.drawer_id),(b,b,db['id']));self.assertEqual(panel.rows[0]['id'],self.part)
        panel.all_walls.setChecked(False);self.assertEqual(set(panel.cabinets),{b});self.assertEqual(len(panel.items),6)
        panel.all_walls.setChecked(True);self.assertEqual(set(panel.cabinets),{a,b})
    def test_global_search_selects_existing_cabinet_and_drawer(self):
        panel,a,b,da,db=self.seed();item=panel.items[db['id']];panel.query.setText('1x1');panel.search()
        self.assertEqual((panel.wall_id,panel.drawer_id),(b,db['id']));self.assertIs(panel.items[db['id']],item);self.assertEqual(panel.results.rowCount(),1)
        panel.wall.setCurrentIndex(panel.wall.findData(a));panel.all_walls.setChecked(False);panel.search();self.assertEqual(panel.results.rowCount(),0)
    def test_actual_drag_saves_on_release_and_does_not_create_render_files(self):
        panel,a,b,da,db=self.seed();panel.arrange.setChecked(True);app.processEvents()
        cabinet=panel.cabinets[b];old=walls.walls(self.db);before={p.relative_to(self.temp.name) for p in Path(self.temp.name).rglob('*')}
        # In arrangement mode a drawer front also moves its whole cabinet.
        start=panel.view.mapFromScene(cabinet.mapToScene(QPointF(40,61)))
        end=panel.view.mapFromScene(cabinet.mapToScene(QPointF(40+112*3,61)))
        QTest.mousePress(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
        QTest.mouseMove(panel.view.viewport(),end,20);app.processEvents();self.assertEqual(walls.walls(self.db),old)
        QTest.mouseRelease(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
        placed=next(w for w in walls.walls(self.db) if w['id']==b);self.assertAlmostEqual(placed['x'],3.,delta=.1);self.assertEqual(placed['y'],-2.7)
        self.assertEqual(cabinet.pos(),QPointF(placed['x']*112,placed['y']*70))
        for angle in (-30,0,30):panel.front.setChecked(False);panel.angle.setValue(angle);panel.grab()
        cabinet=panel.cabinets[b]
        start=panel.view.mapFromScene(cabinet.mapToScene(cabinet.face.map(QPointF(40,12))))
        end=panel.view.mapFromScene(cabinet.mapToScene(cabinet.face.map(QPointF(40,12))+cabinet.back.map(QPointF(112,0))))
        QTest.mousePress(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start);QTest.mouseMove(panel.view.viewport(),end,20)
        QTest.mouseRelease(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
        placed=next(w for w in walls.walls(self.db) if w['id']==b);self.assertAlmostEqual(placed['x'],4.,delta=.1);self.assertEqual(placed['y'],-2.7)
        self.assertEqual(before,{p.relative_to(self.temp.name) for p in Path(self.temp.name).rglob('*')})
    def test_collision_restores_dragged_group_without_rebuilding_scene(self):
        panel,a,b,da,db=self.seed();panel.arrange.setChecked(True);cabinet=panel.cabinets[b];old=QPointF(cabinet.pos());layout=walls.walls(self.db)
        cabinet.setPos(0,0);panel.move_wall(b,0,0)
        self.assertEqual(cabinet.pos(),old);self.assertIs(panel.cabinets[b],cabinet);self.assertEqual(walls.walls(self.db),layout);self.assertIn('chevauche',panel.placement_hint.text())
    def test_failed_position_write_restores_visible_layout(self):
        panel,a,b,da,db=self.seed();panel.arrange.setChecked(True);cabinet=panel.cabinets[b];old=QPointF(cabinet.pos());layout=walls.walls(self.db)
        cabinet.setPos(400,-200)
        with patch.object(walls,'position_wall',side_effect=sqlite3.OperationalError('Disque inaccessible')):panel.move_wall(b,4,-3)
        self.assertEqual(cabinet.pos(),old);self.assertEqual(walls.walls(self.db),layout);self.assertIn('Disque inaccessible',panel.placement_hint.text())
    def test_position_dialog_is_modeless_and_edits_captured_cabinet(self):
        panel,a,b,da,db=self.seed();dialog=self.keep(panel.position_dialog());app.processEvents()
        self.assertIsNone(app.activeModalWidget());self.assertTrue(panel.isEnabled())
        panel.wall.setCurrentIndex(panel.wall.findData(b))
        button=next(button for button in dialog.findChildren(QPushButton) if button.text()=='À gauche');button.click()
        x=dialog.findChild(QDoubleSpinBox,'position_x');y=dialog.findChild(QDoubleSpinBox,'position_y')
        expected=walls.relative_position(self.db,a,b,'left');self.assertEqual((x.value(),y.value()),expected)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click();app.processEvents()
        saved=next(w for w in walls.walls(self.db) if w['id']==a);self.assertEqual((saved['x'],saved['y']),expected);self.assertEqual(panel.wall_id,a)
    def test_stale_position_dialog_reports_deleted_cabinet_without_editing_another(self):
        panel,a,b,da,db=self.seed();dialog=self.keep(panel.position_dialog());walls.delete_wall(self.db,a);before=walls.walls(self.db)
        with patch.object(QMessageBox,'warning') as warning:dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        warning.assert_called_once();self.assertEqual(walls.walls(self.db),before);self.assertTrue(dialog.isVisible())
    def test_delete_cancel_and_delete_last_cabinet_clear_tables_and_scene(self):
        panel,a,b,da,db=self.seed();before=walls.walls(self.db);stock=self.db.rows('SELECT * FROM stock')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):panel.remove_wall()
        self.assertEqual(walls.walls(self.db),before)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):panel.remove_wall();panel.remove_wall()
        self.assertIsNone(panel.wall_id);self.assertIsNone(panel.drawer_id);self.assertEqual(panel.items,{});self.assertEqual(panel.scene.items(),[]);self.assertEqual(panel.table.rowCount(),0);self.assertEqual(panel.results.rowCount(),0)
        self.assertEqual(self.db.rows('SELECT * FROM stock'),stock);self.assertFalse(panel.arrange.isEnabled())
    def test_redraw_batches_drawers_and_contents_across_cabinets(self):
        panel,a,b,da,db=self.seed()
        for index in range(8):walls.create_wall(self.db,'Meuble '+str(index),1,1)
        panel.reload_walls();original=self.db.rows;queries=[]
        def read(sql,*args):queries.append(sql);return original(sql,*args)
        with patch.object(self.db,'rows',read):panel.redraw()
        self.assertEqual(len(queries),3);self.assertEqual(len(panel.cabinets),10)
    def test_delete_closes_only_editors_belonging_to_deleted_cabinet(self):
        panel,a,b,da,db=self.seed();first=panel.position_dialog();panel.wall.setCurrentIndex(panel.wall.findData(b));second=self.keep(panel.position_dialog())
        panel.wall.setCurrentIndex(panel.wall.findData(a))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):panel.remove_wall()
        self.assertFalse(first.isVisible());self.assertTrue(second.isVisible());self.assertEqual(panel.wall_id,b)
        replacement=walls.create_wall(self.db,'Nouveau meuble',1,1);self.assertNotEqual(replacement,b)
    def test_hidden_panel_cancels_delayed_search_without_database_reads(self):
        panel,a,b,da,db=self.seed();panel.query.setText('3005');self.assertTrue(panel.search_timer.isActive());panel.hide()
        self.assertFalse(panel.search_timer.isActive())
        with patch.object(self.db,'rows') as read:QTest.qWait(220)
        read.assert_not_called()
    def test_real_shared_previews_survive_layout_changes_without_cache_writes(self):
        self.db.set_setting('ldraw',str(resources_directory()/'complete.zip'));engine=VisualEngine(self.db)
        a=walls.create_wall(self.db,'Briques',2,2);b=walls.create_wall(self.db,'Accessoires',2,2)
        da,db=walls.drawers(self.db,a)[0],walls.drawers(self.db,b)[0]
        for drawer in (da,db):walls.assign(self.db,drawer['id'],[(self.part,'4'),(self.other,'4')])
        panel=self.keep(StoragePanel(self.db,engine));panel.resize(1100,900);panel.show();app.processEvents();panel.fit();panel.choose_drawer(da['id'])
        def pump_until_ready():
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                app.processEvents();time.sleep(.02)
                if len(panel.icons)==2 and not panel.loading and not panel.thumbnails.running and len(panel.thumbnails.applied)==2:return
            self.fail('Shared drawer/table previews did not complete')
        try:
            with patch.object(engine,'photo',return_value=None),patch.object(engine,'render_3d',wraps=engine.render_3d) as renders:
                pump_until_ready();self.assertTrue(all(not image.isNull() for image in panel.icons.values()));self.assertEqual(renders.call_count,2)
                cache=Path(self.temp.name)/'cache'
                def stamps():return {p.relative_to(cache):(p.stat().st_size,p.stat().st_mtime_ns) for p in cache.rglob('*') if p.is_file()}
                before=stamps();self.assertTrue(before)
                panel.arrange.setChecked(True);panel.move_wall(b,*walls.relative_position(self.db,b,a,'above'));panel.arrange.setChecked(False);panel.choose_drawer(db['id'])
                for angle in (-30,0,30):panel.front.setChecked(False);panel.angle.setValue(angle);panel.grab()
                panel.front.setChecked(True);panel.fit();pump_until_ready()
                self.assertEqual(renders.call_count,2);self.assertEqual(stamps(),before)
        finally:
            panel.close();from PySide6.QtCore import QThreadPool
            QThreadPool.globalInstance().waitForDone(5000);app.processEvents();engine.close()

