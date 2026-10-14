"""Draft cabinet overlays, reference modes and persistent atomic undo."""
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QThreadPool,QItemSelectionModel,QCoreApplication,QEvent
from PySide6.QtWidgets import QMessageBox,QInputDialog,QDialogButtonBox
from PySide6.QtGui import QColor

from atelier import storage_assignment as assignment,storage_wall as walls
from atelier.action_undo import set_default_color,set_visual_color
from atelier.data import Database
from atelier.preview import VisualEngine
from atelier.storage_panel import StoragePanel
from atelier.storage_tools import StoragePlanDialog
from atelier.storage_preview import proposal_snapshot
from atelier.task_lifetime import drain_tasks
from atelier.app import MainWindow,NAV
from test_storage_and_inventory_batches import Fixture,app


def wait(predicate):
    end=time.monotonic()+8
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Preview did not complete')


class ProposalPreviewTests(Fixture):
    def setUp(self):
        super().setUp();self.db.run("UPDATE items SET category='Bricks'")
        self.wall=walls.create_wall(self.db,'Inventaire',4,3)
        self.engines=[]

    def tearDown(self):
        for window in self.windows:window.close()
        QThreadPool.globalInstance().waitForDone(5000);drain_tasks();app.processEvents()
        for engine in self.engines:engine.close()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        super().tearDown()

    def snapshot(self):
        return {name:self.db.rows('SELECT * FROM '+name) for name in ('stock','stock_sets','stock_set_components','stock_undo','storage_drawers','storage_contents','settings','action_undo')}

    def dialog(self):
        window=self.keep(StoragePlanDialog(self.db,self.wall));window.show();app.processEvents();return window

    def test_preview_and_changing_targets_never_write_stock_or_storage(self):
        before=self.snapshot();window=self.dialog();preview=window.proposal_preview
        first=window.targets[0].currentData();second=window.targets[1].currentData()
        self.assertEqual(preview.snapshot['contents'][first][0]['ref'],'3005')
        self.assertTrue(preview.items[first].drop_active)
        window.targets[0].setCurrentIndex(0)
        self.assertFalse(preview.items[first].drop_active);self.assertEqual(preview.snapshot['contents'][first],[])
        self.assertTrue(preview.items[second].drop_active);self.assertEqual(self.snapshot(),before)
        window.reject();self.assertEqual(self.snapshot(),before)

    def test_preview_contains_category_colours_quantities_and_click_selects_the_group(self):
        self.db.add('stock',self.part,'1',7);window=self.dialog();preview=window.proposal_preview
        identity=window.targets[0].currentData();preview.choose_drawer(identity)
        self.assertEqual({(p['chosen_color'],p['chosen_quantity']) for p in preview.rows},{('4',40),('1',7)})
        self.assertTrue(all(p['category']=='Bricks' for p in preview.rows))
        self.assertEqual(len(window.table.selectionModel().selectedRows()),1)
        preview.open_drawer(identity);self.assertEqual(preview.tabs.currentIndex(),1)
        headers=[preview.table.horizontalHeaderItem(i).text() for i in range(preview.table.columnCount())]
        self.assertIn('Catégorie',headers);self.assertIn('Stock global en vrac',headers)

    def test_missing_drawers_and_conflicts_remain_visible_without_overwriting(self):
        small=walls.create_wall(self.db,'Petit',1,1);plan=assignment.propose(self.db,small)
        self.assertIsNone(plan['groups'][1]['drawer_id'])
        snap=proposal_snapshot(plan,[g['drawer_id'] for g in plan['groups']]);self.assertEqual(len(snap['assignments']),1)
        window=self.dialog();target=window.targets[0].currentData();window.targets[1].setCurrentIndex(window.targets[1].findData(target))
        self.assertFalse(window.apply_button.isEnabled());self.assertIn(target,window.proposal_preview.snapshot['conflicts'])
        self.assertEqual(walls.wall_contents(self.db,self.wall),[])

    def test_reference_mode_separates_variants_and_keeps_colours_of_one_reference_together(self):
        iid=self.item('part','3005pb01','Brick 1 x 1 with Pattern');self.db.run("UPDATE items SET category='Bricks' WHERE id=?",(iid,));self.db.add('stock',iid,'4',3);self.db.add('stock',self.part,'1',7)
        plan=assignment.propose(self.db,self.wall,grouping='reference')
        self.assertEqual(len(plan['groups']),3)
        self.assertTrue(all(len({identity for identity,color in g['entries']})==1 for g in plan['groups']))
        group=next(g for g in plan['groups'] if g['entries'][0][0]==self.part)
        self.assertEqual(set(group['entries']),{(self.part,'4'),(self.part,'1')})

    def test_reference_and_manual_modes_include_parts_without_dimensions(self):
        figure=self.item('minifig','fig-test','Chewbacca');self.db.run("UPDATE items SET category='Minifigs' WHERE id=?",(figure,));self.db.add('stock',figure,'',1)
        size=assignment.propose(self.db,self.wall);self.assertEqual([p['id'] for p in size['unknown']],[figure])
        for mode in ('reference','manual'):
            plan=assignment.propose(self.db,self.wall,grouping=mode)
            self.assertIn((figure,''),{tuple(e) for g in plan['groups'] for e in g['entries']});self.assertEqual(plan['unknown'],[])

    def test_manual_multi_selection_shares_a_drawer_and_matches_applied_contents(self):
        before=self.snapshot();window=self.dialog();window.grouping.setCurrentIndex(window.grouping.findData('manual'))
        self.assertTrue(all(w.currentData() is None for w in window.targets))
        for row in range(2):window.table.selectionModel().select(window.table.model().index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        target=window.plan['available'][0]
        with patch.object(QInputDialog,'getItem',return_value=(walls.address(target),True)):window.combine.click()
        self.assertEqual([w.currentData() for w in window.targets],[target['id']]*2);self.assertTrue(window.apply_button.isEnabled())
        self.assertEqual({p['id'] for p in window.proposal_preview.snapshot['contents'][target['id']]},{self.part,self.other})
        self.assertEqual(self.snapshot(),before)
        expected=window.proposal_preview.snapshot['contents'][target['id']];name=window.proposal_preview.items[target['id']].drawer['name']
        with patch.object(QMessageBox,'information'):window.apply()
        actual=walls.contents(self.db,target['id'])
        self.assertEqual({(p['id'],p['chosen_color'],p['chosen_quantity']) for p in actual},{(p['id'],p['chosen_color'],p['chosen_quantity']) for p in expected})
        self.assertEqual(walls.drawers(self.db,self.wall)[0]['name'],name)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(walls.wall_contents(self.db,self.wall),[])

    def test_catalogue_only_proposal_has_zero_quantity_and_no_stock_mutation(self):
        part=self.item('part','unowned','Tile 1 x 2');self.db.run("UPDATE items SET category='Tiles' WHERE id=?",(part,));before=self.snapshot()
        plan=assignment.propose(self.db,self.wall,entries=[(part,'')],from_catalogue=True)
        snap=proposal_snapshot(plan,[g['drawer_id'] for g in plan['groups']]);entry=next(p for rows in snap['contents'].values() for p in rows)
        self.assertEqual(entry['chosen_quantity'],0);self.assertEqual(entry['ref'],'unowned');self.assertEqual(self.snapshot(),before)

    def test_main_drawer_contents_has_category_and_keeps_drag_reference_identity(self):
        drawer=walls.drawers(self.db,self.wall)[0];walls.assign(self.db,drawer['id'],[(self.part,'4')])
        panel=self.keep(StoragePanel(self.db,None));panel.show();panel.choose_drawer(drawer['id']);app.processEvents()
        self.assertEqual(panel.table.horizontalHeaderItem(3).text(),'Catégorie');self.assertEqual(panel.table.item(0,3).text(),'Bricks')
        self.assertEqual(panel.table.item(0,4).text(),'4');self.assertEqual(panel.rows[0]['id'],self.part)

    def test_preview_resizes_and_controls_remain_accessible_at_800_by_540(self):
        window=self.dialog();window.resize(800,540)
        for _ in range(6):app.processEvents()
        self.assertLessEqual(window.width(),800);self.assertLessEqual(window.height(),540)
        self.assertTrue(window.rect().contains(window.apply_button.mapTo(window,window.apply_button.rect().center())))
        preview=window.proposal_preview;self.assertGreater(preview.view.viewport().width(),100);self.assertGreater(preview.view.viewport().height(),60)
        bounds=preview.view.mapToScene(preview.view.viewport().rect()).boundingRect()
        self.assertTrue(bounds.contains(preview.scene.sceneRect().center()))

    def test_board_and_detail_table_reuse_the_same_real_ldraw_thumbnail_cache(self):
        root=Path(self.temp.name)/'ldraw';(root/'parts').mkdir(parents=True)
        (root/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
        for ref in ('3005','3001'):(root/'parts'/f'{ref}.dat').write_text('0 Brick test\n4 16 -10 0 -10 10 0 -10 10 0 10 -10 0 10\n4 16 -10 20 -10 10 20 -10 10 20 10 -10 20 10\n')
        self.db.set_setting('ldraw',str(root));engine=VisualEngine(self.db);self.engines.append(engine)
        parent=self.keep(StoragePanel(self.db,engine));window=self.keep(StoragePlanDialog(self.db,self.wall,parent));window.show();preview=window.proposal_preview
        with patch.object(engine,'render_3d',wraps=engine.render_3d) as render:
            wait(lambda:len(preview.icons)==2 and not preview.running);self.assertEqual(render.call_count,2)
            preview.open_drawer(window.targets[0].currentData());wait(lambda:bool(preview.thumbs.applied) and not preview.thumbs.running)
            self.assertEqual(render.call_count,2)
        window.reject();self.assertTrue(preview.closed)


class ExtendedUndoTests(Fixture):
    def setUp(self):
        super().setUp();self.wall=walls.create_wall(self.db,'Meuble',2,2);self.drawers=walls.drawers(self.db,self.wall)

    def stock_state(self):
        return {name:self.db.rows('SELECT * FROM '+name) for name in ('stock','stock_sets','stock_set_components','stock_revision','stock_undo')}

    def test_main_button_and_ctrl_z_action_restore_colour_and_refresh_drawers(self):
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.thumbnails.PartThumbnails.schedule'),patch('atelier.storage_panel.StoragePanel.schedule_icons'),patch('atelier.preview.Preview.refresh') as refresh:
            window=self.keep(MainWindow(self.db));window.startup_timer.stop();window.show();window.nav.setCurrentRow(next(index for index,entry in enumerate(NAV) if entry[3]=='storage'));app.processEvents()
            window.default_color();dialog=window._consultation_windows[-1];dialog.setCurrentColor(QColor('#112233'));dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            self.assertTrue(window.undo_button.isEnabled());window.undo_button.click();self.assertIsNone(self.db.setting('default_color'));self.assertTrue(refresh.called)
            drawer=self.drawers[0];assignment.place_entries(self.db,drawer['id'],[(self.part,'4')]);window.storage.refresh();window.storage.choose_drawer(drawer['id'])
            self.assertEqual(window.storage.table.rowCount(),1);self.assertTrue(window.undo_shortcut.isEnabled());window.undo_shortcut.trigger()
            self.assertEqual(window.storage.table.rowCount(),0);self.assertEqual(window.storage.items[drawer['id']].parts,[]);self.assertTrue(window.redo_button.isEnabled());self.assertTrue(window.undo_button.isEnabled())
            window.engine.close()

    def test_colour_undo_restores_an_absent_setting_and_persists_after_restart(self):
        before=self.stock_state();self.assertTrue(set_default_color(self.db,'#112233'))
        reopened=Database(self.db.path)
        try:
            self.assertIn('couleur 3D',reopened.undo_description());self.assertTrue(reopened.undo_last_action());self.assertIsNone(reopened.setting('default_color'))
            self.assertTrue(reopened.redo_description());self.assertTrue(reopened.undo_description())
        finally:reopened.close()
        self.assertEqual(self.stock_state(),before)

    def test_colour_reset_and_no_op_leave_the_correct_last_action(self):
        self.db.set_setting('default_color','#112233');set_default_color(self.db,'#f3d55b')
        self.assertFalse(set_default_color(self.db,'#f3d55b'));self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.setting('default_color'),'#112233')

    def test_colour_conflict_is_atomic_and_does_not_overwrite_later_changes(self):
        set_default_color(self.db,'#112233');self.db.set_setting('default_color','#abcdef')
        with self.assertRaises(ValueError):self.db.undo_last_action()
        self.assertEqual(self.db.setting('default_color'),'#abcdef');self.assertTrue(self.db.undo_description())

    def test_individual_colour_undo_preserves_image_and_other_references(self):
        self.db.save_visual(self.part,mode='local',image='own-photo.png',color='#112233')
        before=self.db.visual(self.part);other=self.db.visual(self.other);set_visual_color(self.db,self.part,'#abcdef')
        self.assertEqual(self.db.visual(self.part)['image'],'own-photo.png');self.assertTrue(self.db.undo_last_action())
        self.assertEqual(self.db.visual(self.part),before);self.assertEqual(self.db.visual(self.other),other)

    def test_individual_colour_from_the_preview_is_undoable_without_mutating_stock(self):
        from atelier.preview import Preview
        engine=VisualEngine(self.db);preview=self.keep(Preview(self.db,engine));stock=self.stock_state()
        try:
            with patch.object(preview,'refresh'):
                preview.set_item(self.db.get_item(self.part));preview.save_color('#abcdef')
                self.assertEqual(self.db.visual(self.part)['color'],'#abcdef');self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.visual(self.part)['color'],'')
            self.assertEqual(self.stock_state(),stock)
        finally:engine.close()

    def test_move_between_drawers_restores_both_contents_without_changing_stock(self):
        a,b=self.drawers[:2];walls.assign(self.db,a['id'],[(self.part,'4')]);walls.assign(self.db,b['id'],[(self.other,'4')]);before=self.stock_state()
        assignment.place_entries(self.db,b['id'],[(self.part,'4')],a['id'])
        reopened=Database(self.db.path)
        try:self.assertTrue(reopened.undo_last_action())
        finally:reopened.close()
        self.assertEqual([p['id'] for p in walls.contents(self.db,a['id'])],[self.part]);self.assertEqual([p['id'] for p in walls.contents(self.db,b['id'])],[self.other]);self.assertEqual(self.stock_state(),before)

    def test_proposal_undo_restores_names_and_previous_contents(self):
        self.db.run("UPDATE items SET category='Bricks'");a=self.drawers[0];walls.assign(self.db,a['id'],[(self.other,'4')]);self.db.run("UPDATE storage_drawers SET name='Grandes briques' WHERE id=?",(a['id'],))
        before=walls.print_snapshot(self.db);stock=self.stock_state();plan=assignment.propose(self.db,self.wall,'Bricks',reorganize=True);assignment.apply_proposal(self.db,plan)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(walls.print_snapshot(self.db),before);self.assertEqual(self.stock_state(),stock)

    def test_remove_reference_is_undoable_and_duplicate_placement_is_a_no_op(self):
        a=self.drawers[0];walls.assign(self.db,a['id'],[(self.part,'4')]);walls.unassign(self.db,a['id'],[(self.part,'4')]);self.assertTrue(self.db.undo_last_action());self.assertEqual([p['id'] for p in walls.contents(self.db,a['id'])],[self.part])
        set_default_color(self.db,'#112233');description=self.db.undo_description();self.assertEqual(assignment.place_entries(self.db,a['id'],[(self.part,'4')]),0);self.assertEqual(self.db.undo_description(),description)

    def test_new_stock_action_precedes_storage_and_colour_in_history(self):
        assignment.place_entries(self.db,self.drawers[0]['id'],[(self.part,'4')]);set_default_color(self.db,'#112233')
        self.db.add('stock',self.part,'4',3);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        self.assertEqual(self.db.setting('default_color'),'#112233');self.assertEqual(len(walls.contents(self.db,self.drawers[0]['id'])),1);self.assertIn('couleur',self.db.undo_description())
        self.assertTrue(self.db.undo_last_action());self.assertIsNone(self.db.setting('default_color'))

    def test_unrelated_drawer_changes_survive_undo_and_invalid_operations_keep_the_journal(self):
        a=self.drawers[0];assignment.place_entries(self.db,a['id'],[(self.part,'4')]);before=self.db.undo_description()
        with self.assertRaises(ValueError):assignment.place_entries(self.db,99999,[(self.other,'4')])
        self.assertEqual(self.db.undo_description(),before)
        self.db.run('INSERT INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',(a['id'],self.other,'4'))
        self.assertTrue(self.db.undo_last_action())
        self.assertEqual([part['id'] for part in walls.contents(self.db,a['id'])],[self.other])
