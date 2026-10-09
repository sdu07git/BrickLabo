"""Exercise zoom, rendered thumbnail sizes and actual drawer/cabinet controls."""
from contextlib import contextmanager
import sqlite3
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF,QRectF
from PySide6.QtGui import QImage,QPixmap,QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox,QLineEdit,QMessageBox
import shiboken6

from atelier import storage_wall as walls
from atelier.storage_panel import StoragePanel
from atelier.result_tables import row_index
from test_storage_and_inventory_batches import Fixture,app


class StorageControlsTests(Fixture):
    def seed(self,columns=4):
        a=walls.create_wall(self.db,'Briques',columns,2);b=walls.create_wall(self.db,'Accessoires',2,2)
        da=walls.drawers(self.db,a)[0];db=walls.drawers(self.db,b)[0]
        walls.assign(self.db,da['id'],[(self.part,'4'),(self.other,'4')]);walls.assign(self.db,db['id'],[(self.part,'4')])
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1100,850);panel.show();app.processEvents();panel.front.setChecked(True);panel.fit();panel.choose_drawer(da['id'])
        return panel,a,b,da,db
    def quantities(self):return {name:self.db.rows('SELECT * FROM '+name) for name in ('stock','stock_sets','stock_set_components','stock_undo','stock_revision')}
    def wheel(self,view,delta=120,modifiers=Qt.KeyboardModifier.NoModifier):
        position=QPointF(view.viewport().rect().center())
        event=QWheelEvent(position,QPointF(view.viewport().mapToGlobal(position.toPoint())),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,modifiers,Qt.ScrollPhase.NoScrollPhase,False)
        app.sendEvent(view.viewport(),event);app.processEvents()
    def test_wheel_and_buttons_zoom_without_reading_or_writing_stock(self):
        panel,*_=self.seed();item=next(iter(panel.items.values()));scale=panel.view.transform().m11()
        with patch.object(self.db,'connect',side_effect=AssertionError('Zoom wrote to SQLite')),patch.object(self.db,'rows',side_effect=AssertionError('Zoom queried SQLite')):
            self.wheel(panel.view);self.assertGreater(panel.view.transform().m11(),scale)
            QTest.mouseClick(panel.zoom_out,Qt.MouseButton.LeftButton);QTest.mouseClick(panel.zoom_in,Qt.MouseButton.LeftButton)
            self.assertIs(next(iter(panel.items.values())),item);self.assertTrue(shiboken6.isValid(item));self.assertIn('%',panel.zoom_label.text())
    def test_zoom_works_below_old_minimum_and_keeps_cursor_location(self):
        panel,*_=self.seed(100);panel.fit();scale=panel.view.transform().m11();self.assertLess(scale,.2)
        position=panel.view.viewport().rect().center();before=panel.view.mapToScene(position)
        self.wheel(panel.view);self.assertGreater(panel.view.transform().m11(),scale)
        self.assertLess((panel.view.mapToScene(position)-before).manhattanLength(),25)
    def test_shift_wheel_scrolls_without_zooming(self):
        panel,*_=self.seed();panel.view.zoom(3);scale=panel.view.transform().m11()
        self.wheel(panel.view,modifiers=Qt.KeyboardModifier.ShiftModifier);self.assertEqual(panel.view.transform().m11(),scale)
    def test_focus_and_full_view_frame_all_cabinets_after_pan_and_single_mode(self):
        panel,a,b,da,db=self.seed();walls.position_wall(self.db,b,-8,-7);panel.redraw();panel.fit();scale=panel.view.transform().m11()
        panel.choose_drawer(db['id']);QTest.mouseClick(panel.focus_button,Qt.MouseButton.LeftButton);self.assertGreater(panel.view.transform().m11(),scale)
        visible=panel.view.mapToScene(panel.view.viewport().rect()).boundingRect();self.assertTrue(visible.contains(panel.cabinets[b].sceneBoundingRect()))
        panel.all_walls.setChecked(False);panel.view.zoom(4);panel.view.centerOn(10000,10000)
        QTest.mouseClick(panel.fit_button,Qt.MouseButton.LeftButton);app.processEvents()
        self.assertTrue(panel.all_walls.isChecked());self.assertEqual(set(panel.cabinets),{a,b})
        visible=panel.view.mapToScene(panel.view.viewport().rect()).boundingRect()
        for cabinet in panel.cabinets.values():self.assertTrue(visible.contains(cabinet.sceneBoundingRect()))
        for _ in range(3):QTest.mouseClick(panel.fit_button,Qt.MouseButton.LeftButton)
        self.assertAlmostEqual(panel.view.transform().m11(),scale,delta=.02)
    def test_thumbnail_size_changes_actual_pixels_without_new_files_and_saves_once(self):
        panel,a,b,da,db=self.seed();walls.unassign(self.db,da['id'],[(self.other,'4')]);panel.refresh();panel.all_walls.setChecked(False)
        icon=QPixmap(100,65);icon.fill(Qt.GlobalColor.red);panel.icons[(self.part,'4')]=icon
        item=panel.items[da['id']];before=self.quantities();files={p.relative_to(self.temp.name) for p in self.db.path.parent.rglob('*')}
        def red_pixels():
            image=panel.view.viewport().grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            pixels=np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)
            return int(((pixels[:,:,0]>230)&(pixels[:,:,1]<20)&(pixels[:,:,2]<20)).sum())
        with patch.object(self.db,'set_setting',wraps=self.db.set_setting) as saved:
            panel.thumbnail_size.setSliderDown(True);panel.thumbnail_size.setValue(25);small=red_pixels()
            for value in (35,50,75,100):panel.thumbnail_size.setValue(value)
            large=red_pixels();self.assertGreater(large,small*8);self.assertEqual(saved.call_count,0)
            panel.thumbnail_size.setValue(75);panel.thumbnail_size.setSliderDown(False);self.assertEqual(saved.call_count,1)
        self.assertIs(panel.items[da['id']],item);self.assertEqual(self.quantities(),before);self.assertEqual({p.relative_to(self.temp.name) for p in self.db.path.parent.rglob('*')},files)
        self.assertEqual(self.db.setting('storage_thumbnail_size'),75)
        again=self.keep(StoragePanel(self.db,None));self.assertEqual(again.thumbnail_size.value(),75)
    def test_mixed_large_drawer_previews_stay_inside_face_and_clear_header_handle(self):
        panel,a,b,da,db=self.seed();walls.save_drawer(self.db,a,1,1,2,2,'Casques et armes',da['id']);panel.refresh()
        item=panel.items[da['id']];boxes=item.thumbnail_boxes();self.assertEqual(len(boxes),2)
        for _,box in boxes:self.assertTrue(QRectF(0,20,item.w,item.h-30).contains(box));self.assertGreater(box.height(),25)
        self.assertFalse(boxes[0][1].intersects(boxes[1][1]));self.assertIn('Casques et armes',item.toolTip())
    def test_sorted_selected_rows_remove_only_the_selected_reference(self):
        panel,a,b,da,db=self.seed();before=self.quantities();panel.table.sortItems(1,Qt.SortOrder.DescendingOrder)
        visual=next(r for r in range(panel.table.rowCount()) if panel.rows[row_index(panel.table,r)]['id']==self.part)
        panel.table.selectRow(visual);QTest.mouseClick(panel.remove_references,Qt.MouseButton.LeftButton)
        self.assertEqual([p['id'] for p in walls.contents(self.db,da['id'])],[self.other]);self.assertEqual(walls.contents(self.db,db['id'])[0]['id'],self.part)
        self.assertEqual(panel.table.rowCount(),1);self.assertEqual(len(panel.items[da['id']].parts),1);self.assertEqual(self.quantities(),before)
    def test_no_selection_confirms_clear_and_cancel_preserves_links(self):
        panel,a,b,da,db=self.seed();before=self.quantities();panel.table.clearSelection()
        with patch('atelier.storage_panel.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as question:
            QTest.mouseClick(panel.remove_references,Qt.MouseButton.LeftButton);question.assert_called_once()
        self.assertEqual(len(walls.contents(self.db,da['id'])),2)
        with patch('atelier.storage_panel.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):QTest.mouseClick(panel.remove_references,Qt.MouseButton.LeftButton)
        self.assertEqual(walls.contents(self.db,da['id']),[]);self.assertEqual(panel.table.rowCount(),0);self.assertFalse(panel.remove_references.isEnabled());self.assertEqual(self.quantities(),before)
        self.assertEqual(len(walls.contents(self.db,db['id'])),1)
    def test_remove_distinguishes_two_colours_of_same_reference(self):
        panel,a,b,da,db=self.seed();self.db.add('stock',self.part,'1',3);walls.assign(self.db,da['id'],[(self.part,'1')]);panel.refresh();before=self.quantities()
        visual=next(r for r in range(panel.table.rowCount()) if (panel.rows[row_index(panel.table,r)]['id'],panel.rows[row_index(panel.table,r)]['chosen_color'])==(self.part,'1'))
        panel.table.selectRow(visual);panel.unassign()
        self.assertEqual({(p['id'],p['chosen_color']) for p in walls.contents(self.db,da['id'])},{(self.part,'4'),(self.other,'4')});self.assertEqual(self.quantities(),before)
    def test_clear_rolls_back_if_a_later_link_cannot_be_deleted(self):
        panel,a,b,da,db=self.seed();before=walls.contents(self.db,da['id']);stock=self.quantities()
        self.db.run(f"CREATE TRIGGER prevent_remove BEFORE DELETE ON storage_contents WHEN OLD.item_id={self.other} BEGIN SELECT RAISE(ABORT,'locked reference'); END")
        with self.assertRaises(sqlite3.IntegrityError):walls.unassign(self.db,da['id'])
        self.assertEqual(walls.contents(self.db,da['id']),before);self.assertEqual(self.quantities(),stock)
    def test_remove_failure_is_reported_and_keeps_visible_contents(self):
        panel,a,b,da,db=self.seed();panel.table.selectAll();before=walls.contents(self.db,da['id'])
        with patch('atelier.storage_panel.store.unassign',side_effect=sqlite3.OperationalError('locked')),patch('atelier.storage_panel.QMessageBox.warning') as warning:
            QTest.mouseClick(panel.remove_references,Qt.MouseButton.LeftButton);warning.assert_called_once()
        self.assertEqual(walls.contents(self.db,da['id']),before);self.assertEqual(panel.table.rowCount(),2)
    def test_rename_form_targets_captured_cabinet_and_preserves_selection_and_position(self):
        panel,a,b,da,db=self.seed();before=self.quantities();dialog=panel.rename_dialog();self.assertFalse(dialog.isModal())
        panel.choose_drawer(db['id']);walls.position_wall(self.db,a,-5,3);dialog.findChild(QLineEdit,'cabinet_name').setText('  Mur de briques  ')
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton);app.processEvents()
        cabinet=self.db.rows('SELECT * FROM storage_walls WHERE id=?',(a,))[0]
        self.assertEqual((cabinet['name'],cabinet['x'],cabinet['y']),('Mur de briques',-5.,3.));self.assertEqual(panel.wall.itemText(panel.wall.findData(a)),'Mur de briques')
        self.assertEqual((panel.wall_id,panel.drawer_id),(b,db['id']));self.assertEqual(len(walls.contents(self.db,da['id'])),2);self.assertEqual(self.quantities(),before)
    def test_blank_name_is_rejected_and_unchanged_name_does_not_update(self):
        panel,a,b,da,db=self.seed();dialog=panel.rename_dialog();dialog.findChild(QLineEdit,'cabinet_name').clear()
        with patch('atelier.storage_panel.QMessageBox.warning') as warning:
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton);warning.assert_called_once()
        self.assertTrue(dialog.isVisible());dialog.reject();statements=[];original=self.db.connect
        @contextmanager
        def traced():
            with original() as c:c.set_trace_callback(statements.append);yield c
        with patch.object(self.db,'connect',traced):walls.rename_wall(self.db,a,' Briques ')
        self.assertFalse(any(sql.startswith('UPDATE ') for sql in statements));self.assertEqual(walls.walls(self.db)[0]['name'],'Briques')
