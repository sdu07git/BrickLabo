"""Grid layout conserves drawer contents and previews exactly what Apply saves."""
from unittest.mock import patch
from PySide6.QtWidgets import QDialogButtonBox,QMessageBox
from test_storage_and_inventory_batches import Fixture,app
from atelier import storage_wall as walls
from atelier.storage_panel import StoragePanel
from atelier.storage_quantities import put_entry


class GridTests(Fixture):
    def cabinets(self,count=8,mixed=False):
        for index in range(count):walls.create_wall(self.db,'Meuble '+str(index+1),1+index%3 if mixed else 3,2+index%4 if mixed else 3)
        drawer=walls.drawers(self.db,walls.walls(self.db)[0]['id'])[0]['id']
        put_entry(self.db,drawer,self.part,'4',20)
        return drawer

    def assert_no_overlap(self,layout):
        for index,a in enumerate(layout):
            aw,ah=walls.extent(a)
            for b in layout[index+1:]:
                bw,bh=walls.extent(b)
                self.assertFalse(a['x']<b['x']+bw-1e-8 and b['x']<a['x']+aw-1e-8 and a['y']<b['y']+bh-1e-8 and b['y']<a['y']+ah-1e-8)

    def test_eight_cabinets_form_two_rows_of_four_and_undo_as_one_action(self):
        drawer=self.cabinets();before=walls.walls(self.db);contents=self.db.rows('SELECT * FROM storage_contents');stock=self.db.rows('SELECT * FROM stock')
        walls.align_walls(self.db,'grid',.2,per_row=4);after=walls.walls(self.db)
        self.assertEqual([w['y'] for w in after],[0.]*4+[3.7]*4)
        self.assertEqual([w['x'] for w in after[:4]],[0.,3.5,7.,10.5]);self.assertEqual([w['x'] for w in after[4:]],[0.,3.5,7.,10.5])
        self.assert_no_overlap(after);self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),contents);self.assertEqual(self.db.rows('SELECT * FROM stock'),stock)
        self.db.undo_last_action();self.assertEqual(walls.walls(self.db),before)
        self.db.redo_last_action();self.assertEqual(walls.walls(self.db),after)

    def test_twelve_cabinets_and_incomplete_last_row_use_largest_dimensions(self):
        self.cabinets(12,True);before=walls.walls(self.db);walls.align_walls(self.db,'grid',0,per_row=5);after=walls.walls(self.db)
        self.assertEqual(len({w['y'] for w in after}),3)
        self.assertEqual(after[0]['x'],after[5]['x']);self.assertEqual(after[0]['x'],after[10]['x'])
        self.assertEqual(after[1]['x'],after[6]['x']);self.assertEqual(after[1]['x'],after[11]['x'])
        self.assertEqual(after[5]['y'],max(w['rows']+.5 for w in before[:5]))
        self.assert_no_overlap(after)

    def test_grid_respects_current_reading_order_and_anchor(self):
        self.cabinets(3);first=walls.walls(self.db)[0];walls.position_wall(self.db,first['id'],-4,-5)
        captured=self.db.rows('SELECT * FROM storage_walls ORDER BY y,x,id');plan=walls.alignment_positions(captured,'grid',.4,2)
        self.assertEqual(plan[0],(-4.,-5.,first['id']))
        self.assertEqual(plan[1][1],-5.);self.assertEqual(plan[2][0],-4.)
        walls.align_walls(self.db,'grid',.4,captured,per_row=2)
        self.assertEqual({w['id']:(w['x'],w['y']) for w in walls.walls(self.db)},{identity:(x,y) for x,y,identity in plan})

    def test_invalid_count_and_stale_plan_make_no_changes(self):
        self.cabinets(2);before=walls.walls(self.db)
        for count in [0,-1,True,1.5,'4',None]:
            with self.subTest(count=count):
                with self.assertRaises(ValueError):walls.align_walls(self.db,'grid',per_row=count)
                self.assertEqual(walls.walls(self.db),before)
        walls.rename_wall(self.db,before[0]['id'],'Autre nom');changed=walls.walls(self.db)
        with self.assertRaises(ValueError):walls.align_walls(self.db,'grid',.2,before,per_row=2)
        self.assertEqual(walls.walls(self.db),changed)

    def test_coordinate_overflow_rolls_back_every_position(self):
        self.cabinets(2);before=walls.walls(self.db)
        walls.position_wall(self.db,before[0]['id'],walls.MAX_POSITION,0)
        walls.position_wall(self.db,before[1]['id'],walls.MAX_POSITION,5)
        before=walls.walls(self.db);history=self.db.rows('SELECT * FROM action_history')
        with self.assertRaises(ValueError):walls.align_walls(self.db,'grid',1,per_row=2)
        self.assertEqual(walls.walls(self.db),before);self.assertEqual(self.db.rows('SELECT * FROM action_history'),history)

    def test_empty_and_single_cabinet_keep_their_anchor(self):
        self.assertEqual(walls.alignment_positions([],'grid'),[])
        self.cabinets(1);wall=walls.walls(self.db)[0];walls.align_walls(self.db,'grid',per_row=4)
        self.assertEqual(walls.walls(self.db),[wall])

    def test_preview_updates_without_writing_then_apply_matches_it(self):
        self.cabinets();panel=self.keep(StoragePanel(self.db,None));dialog=panel.align_dialog();app.processEvents()
        before=walls.walls(self.db);self.assertEqual(dialog.direction.currentData(),'grid');self.assertEqual(dialog.per_row.value(),4)
        self.assertIn('2 rangée(s)',dialog.summary.text());dialog.per_row.setValue(3);dialog.gap.setValue(.8)
        self.assertIn('3 rangée(s)',dialog.summary.text());self.assertEqual(walls.walls(self.db),before)
        plan=dialog.preview.positions[:];dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        self.assertEqual({w['id']:(w['x'],w['y']) for w in walls.walls(self.db)},{identity:(x,y) for x,y,identity in plan})
        self.assertTrue(panel.all_walls.isChecked());self.assertFalse(dialog.isVisible())

    def test_cancel_is_read_only_and_linear_modes_still_work(self):
        self.cabinets(2);panel=self.keep(StoragePanel(self.db,None));dialog=panel.align_dialog();before=walls.walls(self.db)
        for mode in ('horizontal','vertical'):
            dialog.direction.setCurrentIndex(dialog.direction.findData(mode));self.assertFalse(dialog.per_row.isEnabled());self.assertEqual(walls.walls(self.db),before)
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click();self.assertEqual(walls.walls(self.db),before)
        walls.align_walls(self.db,'vertical',.5);after=walls.walls(self.db);self.assertEqual(after[1]['y'],4.)

    def test_stale_dialog_stays_open_and_preserves_the_new_cabinet(self):
        self.cabinets(2);panel=self.keep(StoragePanel(self.db,None));dialog=panel.align_dialog();walls.create_wall(self.db,'Nouveau',1,1);before=walls.walls(self.db)
        with patch.object(QMessageBox,'warning') as warning:dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        warning.assert_called_once();self.assertTrue(dialog.isVisible());self.assertEqual(walls.walls(self.db),before)
