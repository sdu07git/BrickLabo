"""Cabinet format copies and user-defined family order without duplicating stock."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QDialogButtonBox,QLineEdit,QMessageBox
from atelier import storage_wall as walls,storage_assignment as assignment,storage_order
from atelier.storage_order_dialog import StorageCategoryOrderDialog
from atelier.storage_tools import StoragePlanDialog
from atelier.storage_panel import StoragePanel
from atelier.data import Database
from atelier.preferences_backup import export_family,restore_families
from test_storage_and_inventory_batches import Fixture,app


class CabinetCopyTests(Fixture):
    def setUp(self):
        super().setUp();self.wall=walls.create_wall(self.db,'Format original',3,3)
    def unchanged_data(self):
        return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','stock_revision','stock_undo','action_undo','storage_contents')}
    def test_custom_geometry_and_holes_copy_to_empty_unnamed_drawers(self):
        first=walls.drawers(self.db,self.wall)[0];walls.save_drawer(self.db,self.wall,1,1,2,2,'Briques',first['id']);walls.assign(self.db,first['id'],[(self.part,'4')])
        self.db.run('UPDATE storage_contents SET quantity=40 WHERE drawer_id=?',(first['id'],));last=walls.drawers(self.db,self.wall)[-1];self.db.run('DELETE FROM storage_drawers WHERE id=?',(last['id'],));before=self.unchanged_data();template=walls.wall_format(self.db,self.wall)
        duplicate=walls.duplicate_wall(self.db,self.wall,'Copie personnalisée',template)
        self.assertEqual(walls.wall_format(self.db,duplicate),template);self.assertTrue(all(d['name']=='' for d in walls.drawers(self.db,duplicate)));self.assertEqual(walls.wall_contents(self.db,duplicate),[]);self.assertEqual(self.unchanged_data(),before)
        all_walls=walls.walls(self.db);self.assertGreaterEqual(all_walls[1]['x'],all_walls[0]['x']+all_walls[0]['columns']+.3)
    def test_multiple_copies_are_independent_and_survive_restart(self):
        duplicate=walls.duplicate_wall(self.db,self.wall,'Copie 1');another=walls.duplicate_wall(self.db,duplicate,'Copie 2')
        first=walls.drawers(self.db,duplicate)[0];walls.save_drawer(self.db,duplicate,1,1,2,1,'Grand',first['id'])
        self.assertNotEqual(walls.wall_format(self.db,duplicate),walls.wall_format(self.db,self.wall));self.assertEqual(walls.wall_format(self.db,another),walls.wall_format(self.db,self.wall))
        reopened=Database(self.db.path)
        try:self.assertEqual(len(walls.walls(reopened)),3);self.assertEqual(walls.wall_contents(reopened,another),[])
        finally:reopened.close()
    def test_stale_format_is_rejected_but_new_content_does_not_change_the_format(self):
        template=walls.wall_format(self.db,self.wall);first=walls.drawers(self.db,self.wall)[0];walls.assign(self.db,first['id'],[(self.part,'4')]);duplicate=walls.duplicate_wall(self.db,self.wall,'Copie',template);self.assertEqual(walls.wall_contents(self.db,duplicate),[])
        walls.save_drawer(self.db,self.wall,1,1,2,1,'Large',first['id']);before=walls.print_snapshot(self.db)
        with self.assertRaisesRegex(ValueError,'format du meuble a changé'):walls.duplicate_wall(self.db,self.wall,'Ancien format',template)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_failed_drawer_copy_rolls_back_the_new_cabinet(self):
        before=walls.print_snapshot(self.db)
        self.db.run("CREATE TRIGGER reject_copy BEFORE INSERT ON storage_drawers WHEN NEW.wall_id<>"+str(self.wall)+" BEGIN SELECT RAISE(ABORT,'refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):walls.duplicate_wall(self.db,self.wall,'Refusée')
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_missing_source_or_blank_name_never_changes_storage(self):
        before=walls.print_snapshot(self.db)
        for identity,name in [(99999,'Copie'),(self.wall,'   ')]:
            with self.assertRaises(ValueError):walls.duplicate_wall(self.db,identity,name)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_dialog_cancel_and_captured_source(self):
        other=walls.create_wall(self.db,'Autre format',1,1);panel=self.keep(StoragePanel(self.db,None));panel.wall.setCurrentIndex(panel.wall.findData(self.wall));before=walls.print_snapshot(self.db)
        dialog=panel.duplicate_dialog();self.assertFalse(dialog.isModal());dialog.reject();self.assertEqual(walls.print_snapshot(self.db),before)
        dialog=panel.duplicate_dialog();dialog.findChild(QLineEdit,'duplicate_cabinet_name').setText('Ma copie');panel.wall.setCurrentIndex(panel.wall.findData(other));dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(walls.wall_format(self.db,panel.wall_id),walls.wall_format(self.db,self.wall));self.assertEqual(panel.wall.currentText(),'Ma copie');self.assertEqual(walls.wall_contents(self.db,panel.wall_id),[])
    def test_dialog_keeps_open_when_reviewed_source_layout_changes(self):
        panel=self.keep(StoragePanel(self.db,None));panel.wall.setCurrentIndex(panel.wall.findData(self.wall));dialog=panel.duplicate_dialog();first=walls.drawers(self.db,self.wall)[0];walls.save_drawer(self.db,self.wall,1,1,2,1,'',first['id'])
        with patch.object(QMessageBox,'warning') as warning:dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        warning.assert_called_once();self.assertTrue(dialog.isVisible());self.assertEqual(len(walls.walls(self.db)),1);dialog.reject()


class OrderFixture(Fixture):
    def setUp(self):
        super().setUp();self.db.run('DELETE FROM stock');self.wall=walls.create_wall(self.db,'Parkside',3,11)
    def part_in(self,ref,width,category,color='4',quantity=3):
        identity=self.item('part',ref,'Piece 1 x '+str(width));self.db.run('UPDATE items SET category=? WHERE id=?',(category,identity));self.db.add('stock',identity,color,quantity);return identity
    def sample(self):
        return [self.part_in('B8',8,'Bricks'),self.part_in('B2',2,'Bricks'),self.part_in('P4',4,'Plates'),self.part_in('P1',1,'Plates'),self.part_in('T2',2,'Tiles')]


class CategorySequenceTests(OrderFixture):
    def test_priority_precedes_footprint_while_each_family_stays_ascending(self):
        self.sample();plan=assignment.propose(self.db,self.wall,criteria=['category','size','reference'],category_order=['Plates','Bricks'])
        self.assertEqual([(g['category'],g['dimensions'][0]*g['dimensions'][1]) for g in plan['groups']],[('Plates',1),('Plates',4),('Bricks',2),('Bricks',8),('Tiles',2)])
    def test_thirty_bricks_then_twenty_three_plates_continue_into_a_copy(self):
        for number in reversed(range(1,31)):self.part_in('brick-'+str(number),number,'Bricks',quantity=number)
        for number in reversed(range(1,24)):self.part_in('plate-'+str(number),number,'Plates',quantity=number)
        duplicate=walls.duplicate_wall(self.db,self.wall,'Parkside 2');before=walls.print_snapshot(self.db);stock=self.db.rows('SELECT * FROM stock')
        plan=assignment.propose(self.db,None,criteria=['category','size','reference'],category_order=['Bricks','Plates'],allocate_quantities=True)
        self.assertEqual([g['category'] for g in plan['groups']],['Bricks']*30+['Plates']*23)
        self.assertEqual([g['dimensions'][1] for g in plan['groups'][:30]],list(range(1,31)))
        self.assertEqual([g['dimensions'][1] for g in plan['groups'][30:]],list(range(1,24)))
        assignment.apply_proposal(self.db,plan);contents=walls.wall_contents(self.db,self.wall);second=walls.wall_contents(self.db,duplicate)
        self.assertEqual([p['category'] for p in contents],['Bricks']*30+['Plates']*3);self.assertEqual([p['category'] for p in second],['Plates']*20);self.assertEqual(self.db.rows('SELECT * FROM stock'),stock)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(walls.print_snapshot(self.db),before)
    def test_category_priority_does_not_override_size_only_or_reference_only_choices(self):
        self.sample();left=assignment.propose(self.db,self.wall,criteria=['size'],category_order=['Plates']);right=assignment.propose(self.db,self.wall,criteria=['size'],category_order=['Bricks']);self.assertEqual(left['groups'],right['groups'])
        left=assignment.propose(self.db,self.wall,criteria=['reference'],category_order=['Plates']);right=assignment.propose(self.db,self.wall,criteria=['reference'],category_order=['Bricks']);self.assertEqual(left['groups'],right['groups'])
    def test_saved_order_survives_restart_and_new_categories_append(self):
        self.sample();storage_order.remember(self.db,['Tiles','Plates','Bricks']);reopened=Database(self.db.path)
        try:
            self.assertEqual(storage_order.saved(reopened),['Tiles','Plates','Bricks']);self.part_in('Animals',2,'Animals');plan=assignment.propose(reopened,self.wall)
            self.assertEqual(list(dict.fromkeys(g['category'] for g in plan['groups'])),['Tiles','Plates','Bricks','Animals'])
        finally:reopened.close()
    def test_order_is_portable_with_other_preferences(self):
        storage_order.remember(self.db,['Plates','Bricks']);path=Path(self.temp.name)/'preferences.json';export_family(self.db,'preferences',path);other=Database(Path(self.temp.name)/'other.sqlite')
        try:restore_families(other,[path]);self.assertEqual(storage_order.saved(other),['Plates','Bricks'])
        finally:other.close()
    def test_category_counts_do_not_duplicate_colours_or_split_drawers(self):
        identity=self.part_in('B2',2,'Bricks');self.db.add('stock',identity,'1',5);self.part_in('P1',1,'Plates')
        plan=assignment.propose(self.db,self.wall,criteria=['category','size','reference'],drawer_counts={identity:3},split_colors=True)
        rows={row['category']:row for row in storage_order.category_rows(plan)};self.assertEqual((rows['Bricks']['references'],rows['Bricks']['drawers']),(1,6));self.assertEqual(rows['Plates']['references'],1)
    def test_unknown_dimensions_remain_visible_in_category_counts(self):
        self.sample();special=self.item('minifig','fig-test','Personnage');self.db.run("UPDATE items SET category='Minifigs' WHERE id=?",(special,));self.db.add('stock',special,'',1)
        rows=storage_order.category_rows(assignment.propose(self.db,self.wall));unknown=next(row for row in rows if row['category']=='Minifigs');self.assertEqual((unknown['references'],unknown['drawers'],unknown['unknown']),(1,0,1))
    def test_invalid_orders_fail_and_bad_saved_preferences_fall_back(self):
        self.sample()
        for order in ('Bricks',['Bricks','Bricks'],[3],{'Bricks':1}):
            with self.assertRaises(ValueError):assignment.propose(self.db,self.wall,category_order=order)
        self.db.set_setting(storage_order.SETTING,{'corrupt':True});self.assertEqual(storage_order.saved(self.db),[]);self.assertTrue(assignment.propose(self.db,self.wall)['groups'])
    def test_subset_reordering_preserves_unseen_category_preferences(self):
        storage_order.remember(self.db,['Bricks','Tiles','Plates']);storage_order.remember(self.db,['Plates','Bricks']);self.assertEqual(storage_order.saved(self.db),['Plates','Bricks','Tiles'])
    def test_sorted_preview_remains_read_only_and_stale_stock_is_rejected(self):
        self.sample();before=walls.print_snapshot(self.db);plan=assignment.propose(self.db,self.wall,category_order=['Plates','Bricks']);self.assertEqual(walls.print_snapshot(self.db),before)
        self.db.run('UPDATE stock SET quantity=quantity+1')
        with self.assertRaisesRegex(ValueError,'changé'):assignment.apply_proposal(self.db,plan)
        self.assertEqual(walls.print_snapshot(self.db),before)


class OrderDialogTests(OrderFixture):
    def dialog(self):
        if not self.db.rows("SELECT id FROM items WHERE ref='B8'"):self.sample()
        plan=assignment.propose(self.db,self.wall);rows=storage_order.category_rows(plan);return self.keep(StorageCategoryOrderDialog(self.db,rows,[]))
    def test_position_moves_a_family_and_renumbers_the_others(self):
        dialog=self.dialog();dialog.positions['Tiles'].setValue(1);dialog.positions['Tiles'].editingFinished.emit()
        self.assertEqual(dialog.order(),['Tiles','Bricks','Plates']);self.assertEqual({k:v.value() for k,v in dialog.positions.items()},{'Tiles':1,'Bricks':2,'Plates':3})
        dialog.down.click();self.assertEqual(dialog.order(),['Bricks','Tiles','Plates']);dialog.up.click();self.assertEqual(dialog.order(),['Tiles','Bricks','Plates']);dialog.alphabetical.click();self.assertEqual(dialog.order(),['Bricks','Plates','Tiles'])
    def test_typed_position_is_committed_by_ok(self):
        dialog=self.dialog();dialog.show();app.processEvents();spin=dialog.positions['Plates'];spin.setFocus();spin.lineEdit().setText('1');dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertEqual(dialog.order(),['Plates','Bricks','Tiles']);self.assertEqual(storage_order.saved(self.db),['Plates','Bricks','Tiles'])
    def test_preference_write_error_keeps_the_dialog_open(self):
        dialog=self.dialog();dialog.show()
        with patch.object(self.db,'set_setting',side_effect=sqlite3.OperationalError('locked')),patch.object(QMessageBox,'warning') as warning:dialog.accept()
        warning.assert_called_once();self.assertTrue(dialog.isVisible());self.assertEqual(storage_order.saved(self.db),[])
    def test_cancel_and_unretained_order_do_not_write_preferences_or_storage(self):
        dialog=self.dialog();before=walls.print_snapshot(self.db);dialog.move_category('Plates',0);dialog.reject();self.assertEqual(storage_order.saved(self.db),[]);self.assertEqual(walls.print_snapshot(self.db),before)
        dialog=self.dialog();dialog.move_category('Plates',0);dialog.retain.setChecked(False);dialog.accept();self.assertEqual(storage_order.saved(self.db),[])
    def test_accept_retains_order_and_read_only_counts(self):
        dialog=self.dialog();before=walls.print_snapshot(self.db);dialog.move_category('Plates',0);dialog.accept();self.assertEqual(storage_order.saved(self.db),['Plates','Bricks','Tiles']);self.assertEqual(walls.print_snapshot(self.db),before)
    def test_parent_preview_reorders_immediately_and_enables_family_size(self):
        self.sample();window=self.keep(StoragePlanDialog(self.db,self.wall));window.criteria['category'].setChecked(False);before=walls.print_snapshot(self.db);dialog=window.choose_category_order();self.assertFalse(dialog.isModal());dialog.move_category('Plates',0);dialog.retain.setChecked(False);dialog.accept()
        self.assertTrue(window.criteria['category'].isChecked());self.assertTrue(window.criteria['size'].isChecked());self.assertEqual(window.plan['groups'][0]['category'],'Plates');self.assertEqual(walls.print_snapshot(self.db),before)
    def test_closing_parent_rejects_the_open_order_window(self):
        self.sample();window=self.keep(StoragePlanDialog(self.db,self.wall));dialog=window.choose_category_order();window.reject();self.assertFalse(dialog.isVisible());self.assertEqual(dialog.result(),dialog.DialogCode.Rejected)
    def test_small_order_window_keeps_every_action_visible(self):
        dialog=self.dialog();dialog.resize(700,480);dialog.show();app.processEvents()
        self.assertLessEqual(dialog.height(),480);self.assertTrue(dialog.rect().contains(dialog.retain.mapTo(dialog,dialog.retain.rect().center())))
        self.assertGreater(dialog.table.viewport().height(),120)
