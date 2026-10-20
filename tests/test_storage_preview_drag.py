"""Real preview mouse gestures edit only the draft and keep quantities attached."""
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QCoreApplication,QThreadPool
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from atelier import storage_wall as walls
from atelier.result_tables import row_index
from atelier.storage_tools import StoragePlanDialog
from atelier.task_lifetime import drain_tasks
from test_storage_and_inventory_batches import Fixture,app
from test_storage_preview_and_undo import wait


class PreviewDragFixture(Fixture):
    def setUp(self):
        super().setUp();self.db.run("UPDATE items SET category='Bricks'");self.wall=walls.create_wall(self.db,'Meuble',3,3)
    def tearDown(self):
        for window in self.windows:window.close()
        QThreadPool.globalInstance().waitForDone(5000);drain_tasks();app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        super().tearDown()
    def window(self,all_cabinets=False,**kwargs):
        window=self.keep(StoragePlanDialog(self.db,None if all_cabinets else self.wall,**kwargs));window.resize(1360,820);window.show();app.processEvents();window.proposal_preview.fit();app.processEvents();return window
    def snapshot(self):return {name:self.db.rows('SELECT * FROM '+name) for name in ('stock','storage_drawers','storage_contents','settings','action_undo')}
    def targets(self,window):return [target.currentData() for target in window.targets]
    def point(self,window,identity):
        preview=window.proposal_preview;item=preview.items[identity];point=preview.view.mapFromScene(item.mapToScene(item.front.boundingRect().center()));self.assertTrue(preview.view.viewport().rect().contains(point));return point
    def move(self,view,point):
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(point),QPointF(view.viewport().mapToGlobal(point)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);app.sendEvent(view.viewport(),event)
    def begin(self,window,source,target):
        view=window.proposal_preview.view;start=self.point(window,source);end=self.point(window,target);QTest.mousePress(view.viewport(),Qt.MouseButton.LeftButton,pos=start);self.move(view,end);return view,end
    def drag(self,window,source,target):
        view,end=self.begin(window,source,target);QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=end);app.processEvents()
    def group(self,window,identity):return next(index for index,group in enumerate(window.plan['groups']) if any(item==identity for item,color in group['entries']))


class PreviewDragTests(PreviewDragFixture):
    def test_drag_exchanges_two_proposed_drawers_in_table_and_preview_without_writes(self):
        before=self.snapshot();window=self.window(allocate_quantities=True);source,target=self.targets(window);self.drag(window,source,target)
        self.assertEqual(self.targets(window),[target,source]);preview=window.proposal_preview
        self.assertEqual([(p['id'],p['stored_quantity']) for p in preview.snapshot['contents'][target]],[(self.part,40)]);self.assertEqual([(p['id'],p['stored_quantity']) for p in preview.snapshot['contents'][source]],[(self.other,12)])
        self.assertEqual(preview.selected_id,target);self.assertTrue(window.apply_button.isEnabled());self.assertEqual(self.snapshot(),before)

    def test_drag_to_an_empty_drawer_moves_the_entire_proposed_contents(self):
        window=self.window();source=self.targets(window)[0];empty=window.plan['available'][-1]['id'];self.drag(window,source,empty)
        self.assertEqual(self.targets(window)[0],empty);self.assertEqual(window.proposal_preview.snapshot['contents'][source],[]);self.assertEqual(window.proposal_preview.snapshot['contents'][empty][0]['id'],self.part)

    def test_hover_marks_the_destination_then_release_clears_the_marker(self):
        window=self.window();source,target=self.targets(window);view,end=self.begin(window,source,target)
        self.assertTrue(view.dragging);self.assertEqual(view.hovered,target);self.assertTrue(window.proposal_preview.items[target].drag_target)
        QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=end);self.assertIsNone(view.hovered);self.assertTrue(all(not drawer.drag_target for drawer in window.proposal_preview.items.values()))

    def test_click_and_small_motion_only_select_the_drawer(self):
        window=self.window();before=self.targets(window);view=window.proposal_preview.view;start=self.point(window,before[0]);QTest.mousePress(view.viewport(),Qt.MouseButton.LeftButton,pos=start);self.move(view,start+QPoint(1,0));QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=start+QPoint(1,0))
        self.assertEqual(self.targets(window),before);self.assertEqual(window.proposal_preview.selected_id,before[0])

    def test_escape_cancels_drag_without_closing_the_proposal(self):
        window=self.window();before=self.targets(window);view,end=self.begin(window,*before);QTest.keyClick(view,Qt.Key.Key_Escape);QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(self.targets(window),before);self.assertTrue(window.isVisible());self.assertIsNone(view.source)

    def test_releasing_over_blank_space_or_the_source_keeps_the_draft(self):
        window=self.window();before=self.targets(window);view,end=self.begin(window,*before);QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(-10,-10));self.assertEqual(self.targets(window),before)
        view,end=self.begin(window,*before);QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=self.point(window,before[0]));self.assertEqual(self.targets(window),before)

    def test_named_empty_drawer_and_existing_occupied_drawer_are_protected(self):
        drawers=walls.drawers(self.db,self.wall);self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE id=?",(drawers[-1]['id'],));outside=self.item('part','protected','Tile 1 x 2');self.db.add('stock',outside,'4',3);walls.assign(self.db,drawers[-2]['id'],[(outside,'4')]);before=self.snapshot();window=self.window();original=self.targets(window)
        for drawer in drawers[-2:]:
            self.drag(window,original[0],drawer['id']);self.assertEqual(self.targets(window),original)
        self.assertEqual(self.snapshot(),before)

    def test_empty_or_protected_drawer_cannot_start_a_drag(self):
        reserved=walls.drawers(self.db,self.wall)[-1]['id'];self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE id=?",(reserved,));window=self.window();before=self.targets(window);empty=window.plan['available'][-1]['id']
        for source in (empty,reserved):
            view,end=self.begin(window,source,before[0]);self.assertIsNone(view.source);QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=end);self.assertEqual(self.targets(window),before)

    def test_double_click_still_opens_the_drawer_inventory(self):
        window=self.window();before=self.targets(window);preview=window.proposal_preview;QTest.mouseDClick(preview.view.viewport(),Qt.MouseButton.LeftButton,pos=self.point(window,before[0]));app.processEvents()
        self.assertEqual(preview.tabs.currentIndex(),1);self.assertEqual({part['id'] for part in preview.rows},{self.part});self.assertEqual(self.targets(window),before);self.assertIsNone(preview.view.source)

    def test_all_cabinet_preview_can_move_a_draft_to_another_cabinet(self):
        other=walls.create_wall(self.db,'Autre meuble',2,2);window=self.window(all_cabinets=True);source=self.targets(window)[0];empty=next(drawer['id'] for drawer in window.plan['available'] if drawer['wall_id']==other);self.drag(window,source,empty)
        self.assertEqual(self.targets(window)[0],empty);self.assertEqual(window.proposal_preview.snapshot['contents'][empty][0]['id'],self.part)

    def test_out_of_scope_destination_is_rejected_by_the_exchange_handler(self):
        other=walls.create_wall(self.db,'Hors sélection',1,1);window=self.window();before=self.targets(window);window.exchange_preview_drawers(before[0],walls.drawers(self.db,other)[0]['id']);window.exchange_preview_drawers(-1,before[0]);window.exchange_preview_drawers(before[0],before[0]);self.assertEqual(self.targets(window),before)

    def test_sorted_table_keeps_widgets_labels_and_selection_with_each_reference(self):
        window=self.window();window.criteria['reference'].setChecked(True);window.table.sortItems(3,Qt.SortOrder.DescendingOrder);source,target=self.targets(window);self.drag(window,source,target)
        for row in range(window.table.rowCount()):
            index=row_index(window.table,row);self.assertIs(window.table.cellWidget(row,4),window.targets[index]);self.assertEqual(window.table.item(row,4).text(),window.targets[index].currentText())
        self.assertEqual({window.plan['groups'][row_index(window.table,index.row())]['entries'][0][0] for index in window.table.selectionModel().selectedRows()},{self.part})

    def test_drag_choices_survive_a_later_inline_count_change(self):
        window=self.window();source,target=self.targets(window);self.drag(window,source,target);next(spin for identity,spin in window.count_spins if identity==self.part).setValue(2);wait(lambda:not window.count_timer.isActive())
        self.assertEqual(window.targets[self.group(window,self.part)].currentData(),target);self.assertEqual(window.targets[self.group(window,self.other)].currentData(),source)

    def test_count_rebuild_during_drag_cancels_the_old_gesture(self):
        window=self.window();view,end=self.begin(window,*self.targets(window));next(spin for identity,spin in window.count_spins if identity==self.part).setValue(2);wait(lambda:not window.count_timer.isActive());before=self.targets(window);QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(self.targets(window),before);self.assertIsNone(view.source)

    def test_closing_during_drag_cancels_the_gesture_without_writes(self):
        before=self.snapshot();window=self.window();view,end=self.begin(window,*self.targets(window));window.reject();app.processEvents();self.assertIsNone(view.source);self.assertFalse(window.count_timer.isActive());self.assertEqual(self.snapshot(),before)

    def test_split_quantities_move_with_their_own_row_and_apply_in_one_undo(self):
        before=self.snapshot();window=self.window(allocate_quantities=True);next(spin for identity,spin in window.count_spins if identity==self.part).setValue(2);wait(lambda:not window.count_timer.isActive());part=self.group(window,self.part);other=self.group(window,self.other);source=window.targets[part].currentData();target=window.targets[other].currentData();self.drag(window,source,target)
        expected={drawer:[(p['id'],p['chosen_color'],p['stored_quantity']) for p in parts] for drawer,parts in window.proposal_preview.snapshot['contents'].items()}
        with patch.object(QMessageBox,'information'):window.apply()
        for drawer in set(self.targets(window)):self.assertEqual([(p['id'],p['chosen_color'],p['stored_quantity']) for p in walls.contents(self.db,drawer)],expected[drawer])
        self.assertEqual(self.db.rows('SELECT * FROM stock'),before['stock']);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),before['storage_contents'])

    def test_colours_and_unknown_counts_stay_attached_to_the_dragged_reference(self):
        self.db.add('stock',self.part,'1',7);window=self.window();source,target=self.targets(window);self.drag(window,source,target);parts=window.proposal_preview.snapshot['contents'][target]
        self.assertEqual({(p['id'],p['chosen_color'],p['stored_quantity']) for p in parts},{(self.part,'4',None),(self.part,'1',None)})

    def test_free_grouping_exchanges_the_whole_proposed_drawer_not_one_reference(self):
        third=self.item('part','3023','Plate 1 x 2');self.db.add('stock',third,'4',8);window=self.window();window.grouping.setCurrentIndex(window.grouping.findData('manual'));source,target=[drawer['id'] for drawer in window.plan['available'][:2]]
        for index,combo in enumerate(window.targets):combo.setCurrentIndex(combo.findData(source if index<2 else target))
        first={window.plan['groups'][index]['entries'][0][0] for index in (0,1)};last={window.plan['groups'][2]['entries'][0][0]};self.drag(window,source,target)
        self.assertEqual({p['id'] for p in window.proposal_preview.snapshot['contents'][target]},first);self.assertEqual({p['id'] for p in window.proposal_preview.snapshot['contents'][source]},last);self.assertTrue(window.apply_button.isEnabled())

    def test_stock_change_after_a_drag_still_requires_a_new_proposal(self):
        window=self.window(allocate_quantities=True);self.drag(window,*self.targets(window));self.db.add('stock',self.part,'4',1);before=self.snapshot()
        with patch.object(QMessageBox,'warning') as warning:window.apply()
        warning.assert_called_once();self.assertEqual(self.snapshot(),before)

    def test_drag_works_after_zoom_and_in_a_compact_window(self):
        window=self.window();window.resize(800,540);app.processEvents();window.proposal_preview.fit();app.processEvents();window.proposal_preview.view.zoom(1.1);before=self.targets(window);self.drag(window,*before);self.assertEqual(self.targets(window),list(reversed(before)))
