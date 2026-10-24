from contextlib import closing
"""Real SQLite/UI checks for resumable work and conservation of physical stock."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QMainWindow,QPushButton
from test_storage_and_inventory_batches import Fixture,app
from atelier import collection_workflows as work,projects,storage_wall as walls
from atelier.storage_quantities import put_entry,available
from atelier.storage_tools import StoragePlanDialog
from atelier import storage_sessions
from atelier.collection_dialogs import CountDialog,InventoryHub,LotsDialog,PickListDialog,BuildComparisonDialog,StartAssistant
from atelier.stock_import_jobs import create_job,import_ready
from atelier.result_tables import row_index


class CollectionTests(Fixture):
    def cabinet(self):
        wall=walls.create_wall(self.db,'Atelier',2,3);drawer=walls.drawers(self.db,wall)[0]['id']
        put_entry(self.db,drawer,self.part,'4',40);return wall,drawer
    def build(self,ref,parts):
        identity=self.item('set',ref,ref)
        inv=self.db.run('INSERT INTO inventories(version,set_num) VALUES(1,?)',(ref,))
        for iid,qty in parts:
            item=self.db.get_item(iid);self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(inv,item['ref'],4,qty,0,''))
        return identity
    def test_counts_resume_missing_surplus_zero_and_unknown_without_mutating_stock(self):
        wall,drawer=self.cabinet();put_entry(self.db,drawer,self.other,'4',None)
        identity=work.start_count(self.db,'cabinet',wall);record=work.session(self.db,identity,'count')
        values=[0 if r['item_id']==self.part else 3 for r in record['data']['rows']]
        work.save_count(self.db,identity,values,record['body'])
        current=work.session(self.db,identity,'count');total=work.count_totals(current['data'])
        self.assertEqual((total['remaining'],total['missing'],total['surplus']),(0,40,0))
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        with self.assertRaises(ValueError):work.save_count(self.db,identity,[1,2],record['body'])
        self.db.close();from atelier.data import Database
        self.db=Database(self.db.path);self.assertEqual(work.session(self.db,identity,'count')['body'],current['body'])
    def test_set_count_is_inventory_not_owned_stock_and_omits_spares(self):
        sid=self.build('A-1',[(self.part,4)])
        inv=self.db.rows('SELECT id FROM inventories WHERE set_num=?',('A-1',))[0]['id']
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(inv,'3001',4,1,1,''))
        identity=work.start_count(self.db,'set',sid);rows=work.session(self.db,identity,'count')['data']['rows']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['expected'],4);self.assertIsNone(rows[0]['counted'])
    def test_count_ui_keeps_row_identity_when_sorted_and_saves_zero(self):
        wall,drawer=self.cabinet();put_entry(self.db,drawer,self.other,'4',12)
        identity=work.start_count(self.db,'cabinet',wall);d=self.keep(CountDialog(self.db,identity))
        d.table.sortItems(1,Qt.SortOrder.DescendingOrder)
        for index,spin in d.spins:spin.setValue(0 if d.rows[index]['item_id']==self.part else 15)
        self.assertTrue(d.save());body=work.session(self.db,identity,'count')['data'];totals=work.count_totals(body)
        self.assertEqual((totals['missing'],totals['surplus']),(40,3))
        d.filter.setCurrentIndex(d.filter.findData('missing'))
        shown=[d.rows[row_index(d.table,n)]['item_id'] for n in range(d.table.rowCount()) if not d.table.isRowHidden(n)]
        self.assertEqual(shown,[self.part])
    def test_lot_add_correct_cancel_and_undo_leave_other_stock(self):
        identity=work.create_lot(self.db,'Vide grenier','Mayenne',1500,'Lot en vrac')
        work.add_to_lot(self.db,identity,self.part,'4',7)
        work.correct_lot_quantity(self.db,identity,'stock',self.part,'4',4)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],44)
        work.cancel_lot(self.db,identity)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],44)
        self.assertTrue(self.db.redo_last_action());self.assertEqual(self.db.rows('SELECT cancelled FROM purchase_lots WHERE id=?',(identity,))[0]['cancelled'],1)
    def test_cancel_allocated_lot_rolls_back_every_row(self):
        wall,drawer=self.cabinet();identity=work.create_lot(self.db,'Vrac')
        work.add_to_lot(self.db,identity,self.other,'4',5);work.add_to_lot(self.db,identity,self.part,'4',7)
        # One fully counted drawer follows the addition: cancelling must be reviewed, not silently change it.
        with self.assertRaises(ValueError):work.cancel_lot(self.db,identity)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.other,))[0]['quantity'],17)
        self.assertEqual(self.db.rows('SELECT cancelled FROM purchase_lots WHERE id=?',(identity,))[0]['cancelled'],0)
    def test_manual_lot_cannot_silently_recreate_deleted_identity(self):
        with self.assertRaises(ValueError):work.add_to_lot(self.db,'missing',self.part,'4',1)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
    def test_set_lot_correction_and_cancellation_adjust_exact_components(self):
        sid=self.build('A-1',[(self.part,3)]);lot=work.create_lot(self.db,'Sets')
        work.add_to_lot(self.db,lot,sid,'',2)
        work.correct_lot_quantity(self.db,lot,'stock_sets',sid,'',1)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock_set_components')[0]['quantity'],3)
        work.cancel_lot(self.db,lot);self.assertFalse(self.db.rows('SELECT * FROM stock_set_components'))
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT quantity FROM stock_set_components')[0]['quantity'],3)
    def test_import_auto_lot_is_atomic_idempotent_and_undoable(self):
        path=Path(self.temp.name)/'vrac.csv';path.write_text('part_num,color_id,quantity\n3005,4,6\n')
        job=create_job(self.db,path);self.assertEqual(import_ready(self.db,job)['imported'],1)
        self.assertEqual(import_ready(self.db,job)['imported'],0)
        lot=self.db.rows('SELECT * FROM purchase_lots')[0];self.assertEqual(lot['name'],'vrac.csv')
        self.assertEqual(self.db.rows('SELECT quantity FROM purchase_lot_entries')[0]['quantity'],6)
        self.db.undo_last_action();self.assertFalse(self.db.rows('SELECT * FROM purchase_lots'));self.assertFalse(self.db.rows('SELECT * FROM stock_import_applied'))
        self.db.redo_last_action();work.cancel_lot(self.db,lot['id'])
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
    def test_pick_take_partial_return_reservations_and_undo(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=6)])
        row=work.pick_list(self.db,pid)[0];self.assertEqual(row['suggested'],6)
        work.pick(self.db,pid,self.part,'4',drawer,4,40)
        self.assertEqual(self.db.rows('SELECT quantity FROM storage_contents')[0]['quantity'],36)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        self.assertEqual(self.db.rows('SELECT reserved FROM project_parts')[0]['reserved'],4)
        self.assertEqual(work.pick_list(self.db,pid)[0]['suggested'],2)
        with self.db.read() as c:self.assertEqual(available(c,self.part,'4'),0)
        with self.assertRaises(ValueError):projects.release(self.db,pid)
        projects.delete(self.db,pid);self.assertFalse(projects.list_projects(self.db));self.db.undo_last_action()
        work.return_picks(self.db,pid);self.assertFalse(self.db.rows('SELECT * FROM project_pick_rows'))
        self.assertEqual(self.db.rows('SELECT quantity FROM storage_contents')[0]['quantity'],40)
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT quantity FROM project_pick_rows')[0]['quantity'],4)
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT quantity FROM storage_contents')[0]['quantity'],40)
    def test_stale_pick_and_other_project_reservations_are_rejected(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=10)])
        other=projects.create(self.db,'Autre',[dict(item_id=self.part,color='4',quantity=39)]);projects.reserve(self.db,other)
        with self.assertRaises(ValueError):work.pick(self.db,pid,self.part,'4',drawer,2,40)
        with self.assertRaises(ValueError):work.pick(self.db,pid,self.part,'4',drawer,1,39)
        self.assertFalse(self.db.rows('SELECT * FROM project_pick_rows'))
    def test_stock_addition_follows_drawer_without_duplicating_picked_parts(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=4)])
        work.pick(self.db,pid,self.part,'4',drawer,4);self.db.add('stock',self.part,'4',10)
        self.assertEqual(self.db.rows('SELECT quantity FROM storage_contents')[0]['quantity'],46)
        from atelier.storage_assignment import propose
        plan=propose(self.db,wall,allocate_quantities=True)
        self.assertFalse(any((self.part,'4') in g['entries'] for g in plan['groups']))
    def test_completed_pick_list_still_displays_taken_reference(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=4)])
        work.pick(self.db,pid,self.part,'4',drawer,4)
        d=self.keep(PickListDialog(self.db,pid));self.assertEqual(d.table.rowCount(),0);self.assertEqual(d.taken_table.item(0,3).text(),'3005')
        walls.delete_wall(self.db,wall);d.refresh()
        self.assertFalse(self.db.rows('SELECT * FROM storage_walls'))
        self.assertEqual(d.taken_table.item(0,0).text(),'Aucun tiroir défini')
        self.assertEqual(d.taken_table.item(0,5).text(),'4')
    def test_pick_dialog_records_partial_then_completed_picks_in_already_picked(self):
        from PySide6.QtWidgets import QInputDialog
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=6)])
        d=self.keep(PickListDialog(self.db,pid));d.table.selectRow(0)
        self.assertTrue(d.take_button.isEnabled())
        with patch.object(QInputDialog,'getInt',return_value=(4,True)):d.take_button.click()
        d.tabs.setCurrentIndex(1)
        self.assertEqual(d.taken_table.item(0,5).text(),'4');self.assertFalse(d.take_button.isEnabled())
        self.assertTrue(d.empty_note.isHidden())
        d.tabs.setCurrentIndex(0);d.table.selectRow(0)
        with patch.object(QInputDialog,'getInt',return_value=(2,True)):d.take_button.click()
        self.assertEqual(d.table.rowCount(),0)
        d.tabs.setCurrentIndex(1);self.assertEqual(d.taken_table.item(0,5).text(),'6')
        self.assertEqual(self.db.rows('SELECT quantity FROM storage_contents')[0]['quantity'],34)
    def test_open_pick_dialog_refreshes_after_undo_redo_and_return(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=4)])
        d=self.keep(PickListDialog(self.db,pid));d.tabs.setCurrentIndex(1)
        self.assertEqual(d.taken_table.rowCount(),0);self.assertIn('Aucun prélèvement',d.empty_note.text())
        work.pick(self.db,pid,self.part,'4',drawer,4);d.stock_changed()
        self.assertEqual(d.taken_table.item(0,5).text(),'4')
        self.db.undo_last_action();d.stock_changed();self.assertEqual(d.taken_table.rowCount(),0)
        self.db.redo_last_action();d.stock_changed();self.assertEqual(d.taken_table.rowCount(),1)
        work.return_picks(self.db,pid);d.stock_changed();self.assertEqual(d.taken_table.rowCount(),0)
        self.assertFalse(d.return_button.isEnabled())
    def test_already_picked_groups_actual_colour_across_requested_colours(self):
        wall,drawer=self.cabinet()
        pid=projects.create(self.db,'Couleurs ignorées',[dict(item_id=self.part,color=color,quantity=3) for color in ('1','4')],ignore_colors=True)
        work.pick(self.db,pid,self.part,'4',drawer,3,need_color='1')
        work.pick(self.db,pid,self.part,'4',drawer,3,need_color='4')
        d=self.keep(PickListDialog(self.db,pid));d.tabs.setCurrentIndex(1)
        self.assertEqual(d.table.rowCount(),0);self.assertEqual(d.taken_table.rowCount(),1)
        self.assertEqual(d.taken_table.item(0,5).text(),'6');self.assertEqual(d.taken_rows[0]['color'],'4')
        self.assertEqual(d.visible_taken_parts()[0]['chosen_color'],'4')
    def test_pick_export_counts_taken_units_once_with_multiple_remaining_drawers(self):
        wall,drawer=self.cabinet();other=walls.drawers(self.db,wall)[1]['id']
        from atelier.storage_quantities import set_quantity
        set_quantity(self.db,drawer,self.part,'4',20);put_entry(self.db,other,self.part,'4',20)
        pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=30)])
        work.pick(self.db,pid,self.part,'4',drawer,4)
        d=self.keep(PickListDialog(self.db,pid))
        with patch('atelier.collection_dialogs.export_rows') as export:d.export()
        rows=export.call_args.args[2]
        self.assertEqual(sum(r[5] for r in rows),26);self.assertEqual(sum(r[6] for r in rows),4)
    def test_reserving_without_taking_keeps_already_picked_empty(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=4)])
        projects.reserve(self.db,pid);d=self.keep(PickListDialog(self.db,pid));d.tabs.setCurrentIndex(1)
        self.assertEqual(d.taken_table.rowCount(),0);self.assertIn('Prélever la ligne',d.empty_note.text())
        self.assertFalse(d.return_button.isEnabled());self.assertFalse(d.take_button.isEnabled())
    def test_main_window_undo_updates_an_open_already_picked_tab(self):
        from atelier.app import MainWindow
        from atelier.windows import show_window
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=4)])
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.thumbnails.PartThumbnails.schedule'),patch('atelier.storage_panel.StoragePanel.schedule_icons'),patch('atelier.preview.Preview.refresh'):
            owner=self.keep(MainWindow(self.db));owner.startup_timer.stop();owner.cleanup_timer.stop()
            d=show_window(PickListDialog(self.db,pid,parent=owner),owner);d.tabs.setCurrentIndex(1)
            work.pick(self.db,pid,self.part,'4',drawer,4);owner.refresh_counts()
            self.assertEqual(d.taken_table.item(0,5).text(),'4')
            owner.undo_shortcut.trigger();self.assertEqual(d.taken_table.rowCount(),0)
            owner.redo_shortcut.trigger();self.assertEqual(d.taken_table.item(0,5).text(),'4')
    def test_comparison_finds_two_small_builds_instead_of_one_big(self):
        a=self.build('A-1',[(self.part,40)]);b=self.build('B-1',[(self.part,20)]);c=self.build('C-1',[(self.part,20)])
        result=work.compare_builds(self.db,[(a,1),(b,1),(c,1)],include_set_stock=False)
        self.assertEqual(result['selected'],[1,2]);self.assertEqual(sum(result['remaining'].values()),12)
        ids=work.create_comparison_projects(self.db,result);self.assertEqual(len(ids),2)
        self.db.undo_last_action();self.assertFalse(projects.list_projects(self.db));self.db.redo_last_action();self.assertEqual(len(projects.list_projects(self.db)),2)
    def test_comparison_honors_selected_owned_sets_and_exclusion(self):
        sid=self.build('A-1',[(self.part,50)]);self.db.add('stock_sets',sid,'',1)
        loose_ids=[r['id'] for r in self.db.rows('SELECT id FROM stock')]
        result=work.compare_builds(self.db,[(sid,1)],excluded_entries=loose_ids)
        self.assertEqual(result['selected'],[0])
        result=work.compare_builds(self.db,[(sid,1)],include_set_stock=False)
        self.assertEqual(result['selected'],[])
    def test_comparison_rejects_missing_inventory_and_does_not_change_stock(self):
        sid=self.item('set','UNKNOWN')
        with self.assertRaises(ValueError):work.compare_builds(self.db,[(sid,1)])
        self.assertEqual(self.db.rows('SELECT SUM(quantity) AS n FROM stock')[0]['n'],52)
    def test_draft_round_trip_preserves_split_counts_destinations_and_tuple_keys(self):
        wall=walls.create_wall(self.db,'Atelier',4,3)
        d=self.keep(StoragePlanDialog(self.db,wall));d.drawer_counts={self.part:2};d.criteria['reference'].setChecked(True);d.rebuild()
        d.targets[0].setCurrentIndex(d.targets[0].count()-1);body=storage_sessions.capture(d)
        identity=work.save_session(self.db,'storage_draft','Essai',body)
        loaded=work.session(self.db,identity,'storage_draft')['data'];fresh=self.keep(StoragePlanDialog(self.db,wall))
        storage_sessions.restore(fresh,loaded)
        self.assertEqual(fresh.plan['fingerprint'],d.plan['fingerprint']);self.assertEqual(fresh.plan['quantities'],d.plan['quantities'])
        self.assertEqual([g['entries'] for g in fresh.plan['groups']],[g['entries'] for g in d.plan['groups']]);self.assertEqual([t.currentData() for t in fresh.targets],body['targets'])
        self.assertEqual(fresh.drawer_counts,{self.part:2})
    def test_stale_draft_rejects_without_mutating_controls_or_recalculates_explicitly(self):
        wall=walls.create_wall(self.db,'Atelier',4,3);d=self.keep(StoragePlanDialog(self.db,wall));body=storage_sessions.capture(d)
        self.db.add('stock',self.part,'4',1);fresh=self.keep(StoragePlanDialog(self.db,wall));old_plan=fresh.plan
        with self.assertRaises(ValueError):storage_sessions.restore(fresh,body)
        self.assertIs(fresh.plan,old_plan)
        self.assertTrue(storage_sessions.restore(fresh,body,True));self.assertNotEqual(fresh.plan['fingerprint'],d.plan['fingerprint'])
    def test_alignment_handles_mixed_sizes_and_can_be_undone(self):
        a=walls.create_wall(self.db,'A',2,3);b=walls.create_wall(self.db,'B',5,2)
        before=walls.walls(self.db);walls.align_walls(self.db,'vertical',.5)
        after=walls.walls(self.db);self.assertEqual(after[1]['x'],after[0]['x']);self.assertEqual(after[1]['y'],after[0]['y']+4)
        self.db.undo_last_action();self.assertEqual(walls.walls(self.db),before)
        walls.align_walls(self.db,'horizontal',.7);after=walls.walls(self.db);self.assertAlmostEqual(after[1]['x'],after[0]['x']+3)
        with self.assertRaises(ValueError):walls.align_walls(self.db,'vertical',.2,before)
    def test_new_windows_initialize_and_furniture_view_is_flat(self):
        wall,_=self.cabinet()
        for cls in (InventoryHub,LotsDialog,BuildComparisonDialog):self.keep(cls(self.db))
        from atelier.storage_panel import StoragePanel
        panel=self.keep(StoragePanel(self.db,None));self.assertTrue(panel.front.isChecked());self.assertTrue(panel.angle.isHidden())
        panel.front.setChecked(False);panel.angle.setValue(24)
        cabinet=next(iter(panel.cabinets.values()));self.assertEqual(cabinet.face.m11(),1);self.assertEqual(cabinet.face.m12(),0)
        from atelier.app import MainWindow
        owner=self.keep(MainWindow(self.db));owner.startup_timer.stop();assistant=self.keep(StartAssistant(owner))
        assistant.move(1);assistant.move(1);assistant.move(1);assistant.move(1)
        self.assertTrue(self.db.setting('start_assistant_completed',False))

    def test_compare_copy_counts_are_bundles_and_weight_the_objective(self):
        a=self.build('A-1',[(self.part,20)]);b=self.build('B-1',[(self.part,40)])
        result=work.compare_builds(self.db,[(b,1),(a,2)])
        self.assertEqual(result['selected'],[1]);self.assertEqual(result['choices'][1]['copies'],2)
    def test_cancel_then_resume_import_creates_a_new_lot_for_pending_rows(self):
        path=Path(self.temp.name)/'vrac.csv';path.write_text('part_num,color_id,quantity\n3005,4,6\nUNKNOWN,4,2\n')
        job=create_job(self.db,path);self.assertEqual(import_ready(self.db,job)['pending'],1)
        old=self.db.rows('SELECT id FROM purchase_lots')[0]['id'];work.cancel_lot(self.db,old)
        from atelier.stock_import_jobs import update_row,job_rows
        pending=next(r for r in job_rows(self.db,job) if not r['imported']);update_row(self.db,job,pending['ordinal'],dict(ref='3001'))
        self.assertEqual(import_ready(self.db,job)['imported'],1)
        lots=self.db.rows('SELECT * FROM purchase_lots');self.assertEqual(len(lots),2);self.assertEqual(sum(r['cancelled'] for r in lots),1)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.other,))[0]['quantity'],14)
    def test_picked_parts_prevent_clear_and_new_drawer_overallocation(self):
        wall,drawer=self.cabinet();pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=4)])
        work.pick(self.db,pid,self.part,'4',drawer,4)
        from atelier.stock_clear import clear
        with self.assertRaises(ValueError):clear(self.db,'stock')
        another=walls.drawers(self.db,wall)[1]['id']
        with self.assertRaises(ValueError):put_entry(self.db,another,self.part,'4',1)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
    def test_guided_count_export_includes_zero_and_surplus(self):
        wall,drawer=self.cabinet();identity=work.start_count(self.db,'cabinet',wall);d=self.keep(CountDialog(self.db,identity))
        d.spins[0][1].setValue(0);path=Path(self.temp.name)/'count.csv'
        with patch('atelier.collection_dialogs.QFileDialog.getSaveFileName',return_value=(str(path),'')):d.export()
        self.assertIn('Attendu,Compté,Manquante,Surplus',path.read_text(encoding='utf-8-sig'))
        self.assertIn(',40,0,40,0',path.read_text(encoding='utf-8-sig'))
    def test_parent_close_rejects_transient_picker_without_a_late_callback(self):
        dialog=self.keep(InventoryHub(self.db));dialog.new_set()
        child=dialog._workflow_children[0];self.assertTrue(child.isVisible());dialog.reject()
        self.assertFalse(dialog._workflow_children);self.assertEqual(child.result(),QDialog.DialogCode.Rejected)
    def test_comparison_defaults_and_stock_choice_follow_saved_vrac_filter(self):
        self.db.set_setting('build_include_set_stock',False);self.db.set_setting('build_excluded_entries',[1])
        d=self.keep(BuildComparisonDialog(self.db));self.assertFalse(d.sets.isChecked());self.assertEqual(d.options['excluded_entries'],[1])
        d.choose_stock();child=d._workflow_children[0];self.assertFalse(child.include_sets.isChecked());child.reject()
    def test_comparison_flags_a_stock_change_before_creating_projects(self):
        sid=self.build('A-1',[(self.part,5)]);d=self.keep(BuildComparisonDialog(self.db));item=self.db.get_item(sid)
        d.candidates=[dict(item,copies=1)];d.result=work.compare_builds(self.db,[(sid,1)]);d.refresh()
        self.db.add('stock',self.part,'4',1);d.stock_changed();self.assertIsNone(d.result);self.assertFalse(d.buttons[3].isEnabled())
    def test_lot_ui_correction_uses_stable_sorted_entry_and_captured_lot(self):
        lot=work.create_lot(self.db,'Lot');work.add_to_lot(self.db,lot,self.part,'4',3);work.add_to_lot(self.db,lot,self.other,'4',2)
        d=self.keep(LotsDialog(self.db));d.detail.sortItems(1,Qt.SortOrder.DescendingOrder);d.detail.selectRow(0)
        selected=d.parts[row_index(d.detail)]['item_id'];self.assertEqual(selected,self.part)
        with patch('atelier.collection_dialogs.QInputDialog.getInt',return_value=(1,True)):d.correct()
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],41)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.other,))[0]['quantity'],14)

    def test_assistant_resumes_last_step_without_marking_completed(self):
        owner=self.keep(QMainWindow());owner.db=self.db
        assistant=self.keep(StartAssistant(owner));assistant.move(1);assistant.move(1);assistant.reject()
        self.assertFalse(self.db.setting('start_assistant_completed',False))
        reopened=self.keep(StartAssistant(owner));self.assertEqual(reopened.page,2)
    def test_count_quantities_sort_numerically_and_keep_their_reference(self):
        wall,drawer=self.cabinet();put_entry(self.db,drawer,self.other,'4',12)
        identity=work.start_count(self.db,'cabinet',wall);d=self.keep(CountDialog(self.db,identity))
        for index,spin in d.spins:spin.setValue(2 if d.rows[index]['item_id']==self.part else 10)
        d.table.sortItems(6,Qt.SortOrder.AscendingOrder)
        self.assertEqual(d.rows[row_index(d.table,0)]['item_id'],self.part)
        self.assertEqual(d.table.cellWidget(0,6).value(),2)
    def test_guided_count_and_purchase_lot_are_in_the_full_backup(self):
        from atelier.backups import create_backup
        import zipfile,sqlite3
        wall,drawer=self.cabinet();identity=work.start_count(self.db,'cabinet',wall);lot=work.create_lot(self.db,'Vrac');work.add_to_lot(self.db,lot,self.other,'4',1)
        backup=tempfile.TemporaryDirectory();self.addCleanup(backup.cleanup)
        destination=Path(backup.name)/'backup.zip';create_backup(self.db,destination)
        with zipfile.ZipFile(destination) as archive:
            name=next(name for name in archive.namelist() if name.endswith('/atelier.sqlite'))
            path=Path(self.temp.name)/'restored.sqlite';path.write_bytes(archive.read(name))
        with closing(sqlite3.connect(path)) as c, c:
            self.assertEqual(c.execute('SELECT id FROM collection_sessions').fetchone()[0],identity)
            self.assertEqual(c.execute('SELECT id FROM purchase_lots').fetchone()[0],lot)
