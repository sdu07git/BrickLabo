"""Context-menu additions retain the reviewed draft and cannot duplicate counts."""
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QMenu
from atelier import storage_assignment as assignment,storage_wall as walls
from atelier.storage_panel import StoragePanel
from test_storage_preview_drag import PreviewDragFixture
from test_storage_preview_and_undo import wait
from test_storage_and_inventory_batches import app


class ProposalPickerTests(PreviewDragFixture):
    def choose_part(self,picker,identity):
        row=next(row for row in range(picker.table.rowCount()) if picker.visible_rows()[row]['id']==identity);picker.table.selectRow(row);picker.choose()

    def test_context_menu_is_available_on_the_proposed_drawer(self):
        window=self.window();preview=window.proposal_preview;identity=self.targets(window)[0];point=self.point(window,identity)
        event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,point,preview.view.viewport().mapToGlobal(point))
        with patch.object(preview,'drawer_menu',wraps=preview.drawer_menu) as opened:
            app.sendEvent(preview.view.viewport(),event);opened.assert_called_once()
        menus=preview.findChildren(QMenu);self.assertTrue(menus);action=next(action for action in menus[-1].actions() if action.text()=='Ajouter une autre référence…');self.assertTrue(action.isEnabled());menus[-1].close()

    def test_add_moves_the_chosen_reference_and_preserves_counts_and_draft_only(self):
        before=self.snapshot();window=self.window(allocate_quantities=True);source,target=self.targets(window);picker=window.choose_preview_reference(source)
        self.assertNotIn(self.part,[p['id'] for p in picker.rows]);self.choose_part(picker,self.other)
        self.assertTrue(window.shared.isChecked());self.assertTrue(window.criteria['reference'].isChecked());self.assertEqual(self.targets(window),[source,source]);self.assertTrue(window.apply_button.isEnabled())
        self.assertEqual({(p['id'],p['stored_quantity']) for p in window.proposal_preview.snapshot['contents'][source]},{(self.part,40),(self.other,12)});self.assertEqual(self.snapshot(),before)

    def test_cancel_does_not_change_grouping_destinations_or_shared_setting(self):
        window=self.window();before=self.targets(window);revision=window.proposal_preview.revision;picker=window.choose_preview_reference(before[0]);picker.reject()
        self.assertFalse(window.shared.isChecked());self.assertFalse(window.criteria['reference'].isChecked());self.assertEqual(self.targets(window),before);self.assertEqual(window.proposal_preview.revision,revision)

    def test_search_and_sort_choose_the_displayed_reference(self):
        third=self.item('part','3023','Plate 1 x 2');self.db.add('stock',third,'4',8);window=self.window();target=window.targets[self.group(window,self.part)].currentData();picker=window.choose_preview_reference(target);picker.search.setText('3023');self.assertEqual(len(picker.rows),1);self.assertEqual(picker.rows[0]['id'],third);picker.search.clear();picker.table.sortItems(2,Qt.SortOrder.DescendingOrder);self.choose_part(picker,third)
        self.assertEqual(window.targets[self.group(window,third)].currentData(),target);self.assertNotEqual(window.targets[self.group(window,self.other)].currentData(),target)

    def test_mixed_size_group_is_split_into_references_without_moving_the_others(self):
        twin=self.item('part','3005b','Brick 1 x 1 alternate');self.db.run("UPDATE items SET category='Bricks' WHERE id=?",(twin,));self.db.add('stock',twin,'4',5);window=self.window(allocate_quantities=True);source,target=self.targets(window);picker=window.choose_preview_reference(target);self.choose_part(picker,twin)
        self.assertEqual(window.targets[self.group(window,self.part)].currentData(),source);self.assertEqual(window.targets[self.group(window,twin)].currentData(),target);self.assertEqual(window.targets[self.group(window,self.other)].currentData(),target)
        with patch.object(QMessageBox,'information'):window.apply()
        self.assertEqual({(p['id'],p['stored_quantity']) for p in walls.contents(self.db,source)},{(self.part,40)});self.assertEqual({(p['id'],p['stored_quantity']) for p in walls.contents(self.db,target)},{(twin,5),(self.other,12)})

    def test_new_reference_can_be_added_to_a_free_drawer(self):
        window=self.window();empty=window.plan['available'][-1]['id'];picker=window.choose_preview_reference(empty);self.choose_part(picker,self.other);self.assertEqual(window.targets[self.group(window,self.other)].currentData(),empty)

    def test_stale_picker_cannot_replace_a_changed_proposal(self):
        window=self.window();picker=window.choose_preview_reference(self.targets(window)[0]);self.drag(window,*self.targets(window));before=self.targets(window)
        with patch.object(QMessageBox,'warning') as warning:self.choose_part(picker,self.other)
        warning.assert_called_once();self.assertEqual(self.targets(window),before);self.assertFalse(window.shared.isChecked())

    def test_changed_stock_is_rejected_before_opening_the_picker(self):
        window=self.window();self.db.add('stock',self.part,'4',1)
        with patch.object(QMessageBox,'warning') as warning:picker=window.choose_preview_reference(self.targets(window)[0])
        self.assertIsNone(picker);warning.assert_called_once()

    def test_shared_drawer_survives_count_change_and_can_be_dragged_as_a_bundle(self):
        window=self.window(allocate_quantities=True);target=self.targets(window)[0];picker=window.choose_preview_reference(target);self.choose_part(picker,self.other);next(spin for identity,spin in window.count_spins if identity==self.part).setValue(2);wait(lambda:not window.count_timer.isActive())
        self.assertEqual(window.targets[self.group(window,self.part)].currentData(),target);self.assertEqual(window.targets[self.group(window,self.other)].currentData(),target);self.assertTrue(window.apply_button.isEnabled());empty=window.plan['available'][-1]['id'];self.drag(window,target,empty)
        self.assertEqual({p['id'] for p in window.proposal_preview.snapshot['contents'][empty]},{self.part,self.other});self.assertEqual(sum(p['stored_quantity'] for parts in window.proposal_preview.snapshot['contents'].values() for p in parts if p['id']==self.part),40)

    def test_same_split_reference_cannot_be_merged_into_itself_even_with_sharing(self):
        window=self.window(allocate_quantities=True);window.shared.setChecked(True);next(spin for identity,spin in window.count_spins if identity==self.part).setValue(2);wait(lambda:not window.count_timer.isActive());indices=[index for index,group in enumerate(window.plan['groups']) if group['entries'][0][0]==self.part];target=window.targets[indices[0]].currentData();picker=window.choose_preview_reference(target);self.assertNotIn(self.part,[part['id'] for part in picker.rows]);picker.reject();window.targets[indices[1]].setCurrentIndex(window.targets[indices[1]].findData(target))
        self.assertFalse(window.apply_button.isEnabled());self.assertIn(target,window.proposal_preview.snapshot['conflicts']);before=self.snapshot()
        with self.assertRaises(ValueError):assignment.apply_proposal(self.db,window.plan,self.targets(window))
        self.assertEqual(self.snapshot(),before)

    def test_shared_apply_matches_preview_and_one_undo_restores_storage(self):
        before=self.snapshot();window=self.window(allocate_quantities=True);target=self.targets(window)[0];picker=window.choose_preview_reference(target);self.choose_part(picker,self.other)
        with patch.object(QMessageBox,'information'):window.apply()
        self.assertEqual({(p['id'],p['stored_quantity']) for p in walls.contents(self.db,target)},{(self.part,40),(self.other,12)});self.assertEqual(self.db.rows('SELECT * FROM stock'),before['stock']);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),before['storage_contents'])

    def test_storage_context_adds_to_the_clicked_drawer_even_after_selection_changes(self):
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1000,760);panel.show();app.processEvents();first,second=walls.drawers(self.db,self.wall)[:2];walls.assign(self.db,first['id'],[(self.other,'4')]);panel.refresh();panel.fit();app.processEvents();before=self.db.rows('SELECT * FROM stock');captured=[];original=panel.pick_stock_for_drawer
        errors=[]
        def choose():
            menu=app.activePopupWidget()
            try:
                panel.choose_drawer(second['id']);next(action for action in menu.actions() if action.text()=='Ajouter une autre référence…').trigger()
            except Exception as error:errors.append(error)
            finally:
                if menu:menu.close()
        item=panel.items[first['id']];point=panel.view.mapFromScene(item.mapToScene(item.front.boundingRect().center()))
        with patch.object(panel,'pick_stock_for_drawer',side_effect=lambda identity:captured.append(original(identity))):QTimer.singleShot(30,choose);panel.drawer_context_menu(point)
        self.assertEqual(errors,[])
        picker=captured[0];picker.search.setText('3005');picker.reload();picker.table.selectRow(0);picker.add()
        self.assertEqual({part['id'] for part in walls.contents(self.db,first['id'])},{self.part,self.other});self.assertEqual(walls.contents(self.db,second['id']),[]);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
        picker.close();app.processEvents()

    def test_protected_drawer_disables_the_add_action_and_rejects_direct_requests(self):
        reserved=walls.drawers(self.db,self.wall)[-1]['id'];self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE id=?",(reserved,));window=self.window();before=self.snapshot();preview=window.proposal_preview;menu=preview.drawer_menu(reserved,preview.view.viewport().mapToGlobal(self.point(window,reserved)))
        self.assertFalse(next(action for action in menu.actions() if action.text()=='Ajouter une autre référence…').isEnabled());self.assertIsNone(window.choose_preview_reference(reserved));self.assertEqual(self.snapshot(),before);menu.close()

    def test_catalogue_proposal_can_share_references_without_creating_owned_stock(self):
        self.db.run('DELETE FROM stock');window=self.window(entries=[(self.part,''),(self.other,'')],from_catalogue=True);target=self.targets(window)[0];picker=window.choose_preview_reference(target);self.choose_part(picker,self.other)
        with patch.object(QMessageBox,'information'):window.apply()
        self.assertEqual({part['id'] for part in walls.contents(self.db,target)},{self.part,self.other});self.assertEqual(self.db.rows('SELECT * FROM stock'),[]);self.assertTrue(all(part['stored_quantity'] is None for part in walls.contents(self.db,target)))
