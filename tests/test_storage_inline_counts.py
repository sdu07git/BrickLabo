"""Live per-reference counts, stable sorted rows and neighbouring draft targets."""
import threading
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPoint,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QInputDialog
from atelier import storage_assignment as assignment,storage_wall as walls
from atelier.storage_draft import neighbours,connected,group_key,arrange_targets,spaced_references
from atelier.storage_tools import StoragePlanDialog,ReferenceDrawerCountsDialog
from atelier.result_tables import row_index
from atelier.preview import VisualEngine
from atelier.storage_panel import StoragePanel
from atelier.task_lifetime import drain_tasks
from test_storage_and_inventory_batches import Fixture,app
from test_storage_preview_and_undo import wait


class InlineCountsTests(Fixture):
    def setUp(self):
        super().setUp();self.db.run("UPDATE items SET category='Bricks'");self.wall=walls.create_wall(self.db,'Meuble',3,3);self.engines=[]
    def tearDown(self):
        for window in self.windows:window.close()
        QThreadPool.globalInstance().waitForDone(5000);drain_tasks();app.processEvents()
        for engine in self.engines:engine.close()
        super().tearDown()
    def window(self,**kwargs):
        window=self.keep(StoragePlanDialog(self.db,self.wall,**kwargs));window.show();app.processEvents();return window
    def groups(self,window,identity):return [i for i,g in enumerate(window.plan['groups']) if any(item==identity for item,color in g['entries'])]
    def edit(self,window,identity,value):next(spin for item,spin in window.count_spins if item==identity).setValue(value)
    def ready(self,window,identity,count):wait(lambda:len(self.groups(window,identity))==count and not window.count_timer.isActive())
    def targets(self,window,identity):return [window.targets[index].currentData() for index in self.groups(window,identity)]
    def snapshot(self):return {name:self.db.rows('SELECT * FROM '+name) for name in ('stock','storage_drawers','storage_contents','action_undo','settings')}
    def parts(self):return [self.db.get_item(self.part),self.db.get_item(self.other)]
    def actual_row(self,window,identity):return next(row for row in range(window.table.rowCount()) if window.visible_thumbnail_rows()[row]['id']==identity)
    def assert_adjacent(self,window,identity):
        by_id={d['id']:d for d in window.plan['available']};self.assertTrue(connected([by_id[target] for target in self.targets(window,identity)]))

    def test_count_is_edited_inline_and_preview_updates_without_writing(self):
        before=self.snapshot();window=self.window(allocate_quantities=True);anchor=self.targets(window,self.part)[0]
        self.assertIn('3005',window.table.item(self.actual_row(window,self.part),3).text())
        self.edit(window,self.part,2);self.ready(window,self.part,2)
        self.assertTrue(window.criteria['reference'].isChecked());self.assertEqual(window.drawer_counts,{self.part:2});self.assertEqual(self.targets(window,self.part)[0],anchor);self.assert_adjacent(window,self.part)
        preview=window.proposal_preview.snapshot;targets=self.targets(window,self.part)
        self.assertEqual([preview['contents'][target][0]['stored_quantity'] for target in targets],[20,20]);self.assertEqual(self.snapshot(),before)

    def test_manual_destinations_of_other_references_survive_count_changes(self):
        window=self.window();other=self.groups(window,self.other)[0];target=window.plan['available'][-1]['id'];window.targets[other].setCurrentIndex(window.targets[other].findData(target))
        self.edit(window,self.part,2);self.ready(window,self.part,2)
        self.assertEqual(self.targets(window,self.other),[target]);self.assert_adjacent(window,self.part)
        self.edit(window,self.part,1);self.ready(window,self.part,1);self.assertEqual(self.targets(window,self.other),[target])

    def test_manually_placed_anchor_is_kept_and_automatic_neighbour_makes_room(self):
        window=self.window();index=self.groups(window,self.part)[0];anchor=window.plan['available'][1]['id'];window.targets[index].setCurrentIndex(window.targets[index].findData(anchor))
        self.edit(window,self.part,2);self.ready(window,self.part,2)
        self.assertEqual(self.targets(window,self.part)[0],anchor);self.assert_adjacent(window,self.part)
        chosen=[widget.currentData() for widget in window.targets];self.assertEqual(len(chosen),len(set(chosen)));self.assertTrue(window.apply_button.isEnabled())

    def test_split_does_not_wrap_from_end_of_row_to_unrelated_start(self):
        window=self.window();index=self.groups(window,self.part)[0];anchor=window.plan['available'][2]['id'];window.targets[index].setCurrentIndex(window.targets[index].findData(anchor))
        self.edit(window,self.part,2);self.ready(window,self.part,2)
        by_id={d['id']:d for d in window.plan['available']};selected=[by_id[target] for target in self.targets(window,self.part)]
        self.assertEqual(selected[0]['id'],anchor);self.assertTrue(neighbours(*selected));self.assertEqual(selected[1]['row'],selected[0]['row'])

    def test_sorted_main_table_edits_the_displayed_reference_and_keeps_sort(self):
        window=self.window(allocate_quantities=True);window.table.sortItems(3,Qt.SortOrder.DescendingOrder);row=self.actual_row(window,self.part);window.table.cellWidget(row,7).setValue(2);self.ready(window,self.part,2)
        self.assertEqual(window.table.horizontalHeader().sortIndicatorSection(),3)
        self.assertEqual(window.drawer_counts,{self.part:2});self.assertEqual(len(self.groups(window,self.other)),1)
        for row in range(window.table.rowCount()):
            index=row_index(window.table,row);self.assertIs(window.table.cellWidget(row,4),window.targets[index]);self.assertEqual(window.visible_thumbnail_rows()[row]['id'],window.plan['groups'][index]['entries'][0][0])
        window.table.sortItems(7,Qt.SortOrder.DescendingOrder);self.assertEqual(window.table.item(0,7).data(Qt.ItemDataRole.DisplayRole),2)
        window.table.cellWidget(0,7).setValue(3);self.ready(window,self.part,3);self.assertEqual(window.drawer_counts,{self.part:3})

    def test_sorted_selection_and_preview_drawer_select_the_same_group(self):
        window=self.window();window.criteria['reference'].setChecked(True);window.table.sortItems(3,Qt.SortOrder.DescendingOrder);row=self.actual_row(window,self.part);window.table.setCurrentCell(row,3);app.processEvents()
        target=self.targets(window,self.part)[0];self.assertEqual(window.proposal_preview.selected_id,target)
        window.proposal_preview.choose_drawer(self.targets(window,self.other)[0]);self.assertEqual([window.visible_thumbnail_rows()[index.row()]['id'] for index in window.table.selectionModel().selectedRows()],[self.other])

    def test_many_quick_edits_use_the_last_value_and_close_cancels_pending_update(self):
        before=self.snapshot();window=self.window()
        for count in (2,4,3):self.edit(window,self.part,count)
        self.ready(window,self.part,3);self.assertTrue(all(spin.value()==3 for identity,spin in window.count_spins if identity==self.part))
        self.edit(window,self.part,2);window.reject();app.processEvents();self.assertFalse(window.count_timer.isActive());self.assertEqual(self.snapshot(),before)

    def test_apply_flushes_pending_count_and_exactly_matches_preview_then_undo(self):
        before=self.snapshot();window=self.window(allocate_quantities=True);self.edit(window,self.part,2)
        with patch.object(QMessageBox,'information'):window.apply()
        self.assertEqual(len(self.groups(window,self.part)),2);targets=self.targets(window,self.part)
        self.assertEqual([walls.contents(self.db,target)[0]['stored_quantity'] for target in targets],[20,20])
        for target in targets:self.assertEqual(window.proposal_preview.snapshot['contents'][target][0]['stored_quantity'],walls.contents(self.db,target)[0]['stored_quantity'])
        self.assertEqual(self.db.rows('SELECT * FROM stock'),before['stock']);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),before['storage_contents'])

    def test_split_colours_update_all_count_fields_and_preserve_totals(self):
        self.db.add('stock',self.part,'1',7);window=self.window(allocate_quantities=True);window.colors.setChecked(True);self.edit(window,self.part,2)
        self.ready(window,self.part,4);self.assertTrue(all(spin.value()==2 for identity,spin in window.count_spins if identity==self.part))
        totals={}
        for index in self.groups(window,self.part):
            for entry,value in window.plan['groups'][index]['quantities'].items():totals[entry]=totals.get(entry,0)+value
        self.assertEqual(totals,{(self.part,'1'):7,(self.part,'4'):40})

    def test_mixed_size_group_asks_for_reference_criterion_before_editing(self):
        variant=self.item('part','3005p01','Brick 1 x 1 with Pattern');self.db.run("UPDATE items SET category='Bricks' WHERE id=?",(variant,));self.db.add('stock',variant,'4',3);window=self.window()
        row=self.actual_row(window,self.part);self.assertIsNone(window.table.cellWidget(row,7));self.assertIn('Coche Référence',window.table.item(row,7).toolTip())
        window.criteria['reference'].setChecked(True);row=self.actual_row(window,self.part);self.assertIsNotNone(window.table.cellWidget(row,7));self.edit(window,self.part,2);self.ready(window,self.part,2)
        self.assertEqual(len(self.groups(window,variant)),1)

    def test_legacy_counts_window_keeps_reviewed_destinations(self):
        window=self.window();index=self.groups(window,self.other)[0];target=window.plan['available'][-1]['id'];window.targets[index].setCurrentIndex(window.targets[index].findData(target))
        with patch.object(ReferenceDrawerCountsDialog,'exec',return_value=ReferenceDrawerCountsDialog.DialogCode.Accepted),patch.object(ReferenceDrawerCountsDialog,'counts',return_value={self.part:2}):window.choose_drawer_counts()
        self.assertEqual(self.targets(window,self.other),[target]);self.assert_adjacent(window,self.part)

    def test_impossible_neighbours_are_reported_without_overriding_manual_choices(self):
        window=self.window();self.edit(window,self.part,2);self.ready(window,self.part,2)
        for index,target in zip(self.groups(window,self.part),(window.plan['available'][0]['id'],window.plan['available'][-1]['id'])):
            window.targets[index].setCurrentIndex(0);window.targets[index].setCurrentIndex(window.targets[index].findData(target))
        self.assertIn('Tiroirs espacés',window.summary.text());chosen=self.targets(window,self.part)
        self.edit(window,self.other,2);self.ready(window,self.other,2);self.assertEqual(self.targets(window,self.part),chosen);self.assertIn('Tiroirs espacés',window.summary.text())

    def test_occupied_named_drawers_are_never_used_for_neighbouring_splits(self):
        drawer=walls.drawers(self.db,self.wall)[1];self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE id=?",(drawer['id'],));before=self.snapshot();window=self.window();self.edit(window,self.part,2);self.ready(window,self.part,2)
        self.assertNotIn(drawer['id'],[target.currentData() for target in window.targets]);self.assert_adjacent(window,self.part);self.assertEqual(self.snapshot(),before)

    def test_manual_mode_keeps_free_grouping_and_disables_inline_counts(self):
        window=self.window();window.grouping.setCurrentIndex(window.grouping.findData('manual'));self.assertTrue(all(not spin.isEnabled() for identity,spin in window.count_spins));window.table.sortItems(3,Qt.SortOrder.DescendingOrder)
        row=self.actual_row(window,self.part);window.table.selectRow(row);target=window.plan['available'][0]
        with patch.object(QInputDialog,'getItem',return_value=(walls.address(target),True)):window.combine_selection()
        self.assertEqual(window.proposal_preview.snapshot['contents'][target['id']][0]['id'],self.part);self.assertIsNone(self.targets(window,self.other)[0])

    def test_secondary_window_sorts_headers_and_numeric_counts_without_swapping_settings(self):
        dialog=self.keep(ReferenceDrawerCountsDialog(self.db,self.parts(),{self.part:10,self.other:2},{self.part:40,self.other:12}));dialog.show();app.processEvents();table=dialog.table
        header=table.horizontalHeader();point=QPoint(header.sectionViewportPosition(2)+header.sectionSize(2)//2,header.height()//2);QTest.mouseClick(header.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
        self.assertEqual([table.item(row,2).text() for row in range(table.rowCount())],['3005','3001'])
        table.sortItems(5,Qt.SortOrder.AscendingOrder);self.assertEqual([table.cellWidget(row,5).value() for row in range(2)],[2,10])
        table.cellWidget(0,5).setValue(20);app.processEvents();self.assertEqual(dialog.counts(),{self.part:10,self.other:20});self.assertEqual([table.cellWidget(row,5).value() for row in range(2)],[10,20])
        table.sortItems(4,Qt.SortOrder.AscendingOrder);self.assertEqual([table.item(row,4).data(Qt.ItemDataRole.DisplayRole) for row in range(2)],[12,40])
        for row in range(2):self.assertIs(table.cellWidget(row,5),dialog.spins[dialog.visible_rows()[row]['id']])

    def test_async_thumbnail_results_after_sort_stay_with_the_displayed_reference(self):
        root=Path(self.temp.name)/'ldraw';(root/'parts').mkdir(parents=True);(root/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
        parts=[dict(part,ref='inline-model-'+str(index)) for index,part in enumerate(self.parts())]
        for part in parts:(root/'parts'/(part['ref']+'.dat')).write_text('0 Brick test\n4 16 -10 0 -10 10 0 -10 10 0 10 -10 0 10\n4 16 -10 20 -10 10 20 -10 10 20 10 -10 20 10\n')
        self.db.set_setting('ldraw',str(root));engine=VisualEngine(self.db);self.engines.append(engine);started=threading.Event();release=threading.Event()
        from atelier.thumbnails import load_thumbnail
        def delayed(*args):started.set();release.wait(3);return load_thumbnail(*args)
        with patch('atelier.thumbnails.load_thumbnail',side_effect=delayed):
            dialog=self.keep(ReferenceDrawerCountsDialog(self.db,parts,{},{self.part:40,self.other:12},engine));dialog.show();wait(started.is_set)
            dialog.table.sortItems(2,Qt.SortOrder.DescendingOrder);release.set();wait(lambda:len(dialog.thumbs.applied)==2 and not dialog.thumbs.running)
            for row in range(2):self.assertEqual(dialog.thumbs.applied[row][0],dialog.visible_rows()[row]['id']);self.assertFalse(dialog.table.item(row,0).icon().isNull(),dialog.table.item(row,0).toolTip())
            dialog.reject();self.assertFalse(dialog.thumbs.active)

    def test_initial_all_cabinet_proposal_uses_one_cabinet_for_a_split_when_possible(self):
        self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE wall_id=?",(self.wall,));first=walls.drawers(self.db,self.wall)[0];self.db.run("UPDATE storage_drawers SET name='' WHERE id=?",(first['id'],));second=walls.create_wall(self.db,'Autre meuble',2,1)
        plan=assignment.propose(self.db,None,criteria=['reference'],drawer_counts={self.part:2});drawers={d['id']:d for d in plan['available']};selected=[drawers[g['drawer_id']] for g in plan['groups'] if g['entries'][0][0]==self.part]
        self.assertEqual([drawer['wall_id'] for drawer in selected],[second,second]);self.assertTrue(neighbours(*selected))

    def test_unavailable_neighbouring_space_is_visible_in_the_live_proposal(self):
        drawers=walls.drawers(self.db,self.wall);self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE wall_id=?",(self.wall,))
        for drawer in (drawers[0],drawers[-1]):self.db.run("UPDATE storage_drawers SET name='' WHERE id=?",(drawer['id'],))
        before=self.snapshot();window=self.window(entries=[(self.part,'4')]);self.edit(window,self.part,2);self.ready(window,self.part,2)
        self.assertIn('Tiroirs espacés pour RB 3005',window.summary.text());self.assertEqual(self.snapshot(),before);self.assertTrue(window.apply_button.isEnabled())

    def test_custom_wide_drawer_uses_the_actual_shared_edge_for_neighbours(self):
        first=walls.drawers(self.db,self.wall)[0];walls.save_drawer(self.db,self.wall,1,1,2,1,'',first['id']);window=self.window(entries=[(self.part,'4')]);self.edit(window,self.part,2);self.ready(window,self.part,2)
        drawers={d['id']:d for d in window.plan['available']};selected=[drawers[target] for target in self.targets(window,self.part)]
        self.assertEqual(selected[0]['width'],2);self.assertEqual(selected[1]['col'],3);self.assertTrue(neighbours(*selected))

    def test_typing_count_then_clicking_apply_commits_the_typed_number(self):
        window=self.window(allocate_quantities=True);spin=next(spin for identity,spin in window.count_spins if identity==self.part);spin.setFocus();spin.lineEdit().selectAll();QTest.keyClicks(spin,'2')
        with patch.object(QMessageBox,'information'):QTest.mouseClick(window.apply_button,Qt.MouseButton.LeftButton)
        self.assertEqual(len(self.groups(window,self.part)),2);self.assertEqual([walls.contents(self.db,target)[0]['stored_quantity'] for target in self.targets(window,self.part)],[20,20])

    def test_main_thumbnail_rows_remain_aligned_after_sort_and_inline_split(self):
        from PySide6.QtWidgets import QWidget
        for identity,ref in ((self.part,'preview-inline-a'),(self.other,'preview-inline-b')):self.db.run('UPDATE items SET ref=? WHERE id=?',(ref,identity))
        root=Path(self.temp.name)/'ldraw';(root/'parts').mkdir(parents=True);(root/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
        for ref in ('preview-inline-a','preview-inline-b'):(root/'parts'/f'{ref}.dat').write_text('0 Brick test\n4 16 -10 0 -10 10 0 -10 10 0 10 -10 0 10\n4 16 -10 20 -10 10 20 -10 10 20 10 -10 20 10\n')
        self.db.set_setting('ldraw',str(root));engine=VisualEngine(self.db);self.engines.append(engine);parent=self.keep(QWidget());parent.engine=engine;window=self.window(parent=parent,allocate_quantities=True)
        wait(lambda:len(window.thumbs.applied)==2 and not window.thumbs.running);window.table.sortItems(3,Qt.SortOrder.DescendingOrder);self.edit(window,self.part,2);self.ready(window,self.part,2)
        wait(lambda:len(window.thumbs.applied)==3 and not window.thumbs.running)
        for row in range(3):self.assertEqual(window.thumbs.applied[row][0],window.visible_thumbnail_rows()[row]['id']);self.assertFalse(window.table.item(row,5).icon().isNull())

    def test_same_reference_text_in_another_source_keeps_its_own_count(self):
        alternative=self.item('part','3005','Brick 1 x 1','BL');self.db.run("UPDATE items SET category='Bricks' WHERE id=?",(alternative,));self.db.add('stock',alternative,'4',8);window=self.window();window.criteria['reference'].setChecked(True);window.table.sortItems(3,Qt.SortOrder.AscendingOrder)
        self.edit(window,alternative,2);self.ready(window,alternative,2);self.assertEqual(len(self.groups(window,self.part)),1);self.assertEqual(window.drawer_counts,{alternative:2})

    def test_stale_stock_after_live_update_cannot_apply_unreviewed_quantities(self):
        window=self.window(allocate_quantities=True);self.edit(window,self.part,2);self.ready(window,self.part,2);self.db.add('stock',self.part,'4',3);before=self.snapshot()
        with patch.object(QMessageBox,'warning') as warning:window.apply()
        warning.assert_called_once();self.assertEqual(self.snapshot(),before)
