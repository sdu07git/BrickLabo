"""Removing storage and projects conserves stock and releases unlocated picks."""
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox
from test_projects_quantities_history import Fixture
from atelier import projects,collection_workflows as work,storage_wall as walls
from atelier.storage_quantities import put_entry,available
from atelier.data import Database


class UnlocatedPickTests(Fixture):
    def take(self,quantity=10,color='4',drawer=None,pid=None,ignore=False):
        drawer=drawer or self.drawers[0]['id']
        put_entry(self.db,drawer,self.part,'4',quantity)
        if pid is None:pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color=color,quantity=quantity)],ignore_colors=ignore)
        work.pick(self.db,pid,self.part,'4',drawer,quantity,need_color=color)
        return pid,drawer

    def assert_stock(self):
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=? AND color=?',(self.part,'4'))[0]['quantity'],100)
        self.assertEqual(self.db.rows('PRAGMA foreign_key_check'),[])

    def test_cabinet_then_project_deletion_frees_picks_without_recreating_drawers(self):
        pid,drawer=self.take();walls.delete_wall(self.db,self.wall)
        self.assertEqual(walls.walls(self.db),[]);picked=work.picked_list(self.db,pid)
        self.assertEqual((picked[0]['drawer_id'],picked[0]['quantity']),(None,10))
        self.assertEqual(picked[0]['cabinet'],'Aucun tiroir défini')
        self.assertEqual(projects.detail(self.db,pid)[0]['reserved'],10)
        projects.delete(self.db,pid)
        self.assertEqual(self.db.rows('SELECT * FROM project_physical_picks'),[])
        self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),[])
        with self.db.read() as c:self.assertEqual(available(c,self.part,'4'),100)
        self.assert_stock()

    def test_deleting_multiple_drawers_aggregates_actual_quantities_once(self):
        pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color='4',quantity=10)])
        self.take(6,pid=pid);self.take(4,pid=pid,drawer=self.drawers[1]['id'])
        walls.delete_wall(self.db,self.wall)
        self.assertEqual(len(self.db.rows('SELECT * FROM project_unlocated_picks')),1)
        self.assertEqual(work.picked_list(self.db,pid)[0]['quantity'],10);self.assert_stock()

    def test_different_projects_keep_separate_claims_after_cabinet_deletion(self):
        a,_=self.take(6);b,_=self.take(4,drawer=self.drawers[1]['id'])
        walls.delete_wall(self.db,self.wall);projects.delete(self.db,a)
        self.assertEqual(work.picked_list(self.db,b)[0]['quantity'],4)
        with self.db.read() as c:self.assertEqual(projects.free(c,self.part,'4'),96)
        self.assert_stock()

    def test_ignored_colours_keep_requested_and_actual_colours(self):
        pid=projects.create(self.db,'Projet',[dict(item_id=self.part,color=c,quantity=n) for c,n in [('1',3),('4',7)]],ignore_colors=True)
        drawer=self.drawers[0]['id'];put_entry(self.db,drawer,self.part,'4',10)
        work.pick(self.db,pid,self.part,'4',drawer,3,need_color='1');work.pick(self.db,pid,self.part,'4',drawer,7,need_color='4')
        walls.delete_wall(self.db,self.wall)
        rows=self.db.rows('SELECT color,stock_color,quantity FROM project_unlocated_picks ORDER BY color')
        self.assertEqual(rows,[dict(color='1',stock_color='4',quantity=3),dict(color='4',stock_color='4',quantity=7)])
        self.assertEqual(work.picked_list(self.db,pid)[0]['quantity'],10)
        projects.delete(self.db,pid);self.db.undo_last_action();self.assertEqual(sum(r['quantity'] for r in work.picked_list(self.db,pid)),10)
        self.assert_stock()

    def test_undo_redo_restores_cabinet_project_reservations_and_pick_origins(self):
        pid,drawer=self.take();walls.delete_wall(self.db,self.wall);projects.delete(self.db,pid)
        self.db.undo_last_action();self.assertIsNone(work.picked_list(self.db,pid)[0]['drawer_id'])
        self.db.undo_last_action();self.assertEqual(work.picked_list(self.db,pid)[0]['drawer_id'],drawer)
        self.assertEqual(walls.drawers(self.db,self.wall)[0]['id'],drawer)
        self.db.redo_last_action();self.assertIsNone(work.picked_list(self.db,pid)[0]['drawer_id'])
        self.db.redo_last_action();self.assertEqual(projects.list_projects(self.db),[]);self.assert_stock()

    def test_returning_unlocated_picks_does_not_invent_a_cabinet(self):
        pid,_=self.take();walls.delete_wall(self.db,self.wall);work.return_picks(self.db,pid)
        self.assertEqual(work.picked_list(self.db,pid),[]);self.assertEqual(walls.walls(self.db),[])
        projects.release(self.db,pid);self.assertEqual(projects.detail(self.db,pid)[0]['reserved'],0);self.assert_stock()

    def test_single_drawer_deletion_preserves_other_drawers(self):
        pid,drawer=self.take();walls.delete_drawer(self.db,drawer)
        self.assertEqual(len(walls.drawers(self.db,self.wall)),5)
        self.assertIsNone(work.picked_list(self.db,pid)[0]['drawer_id']);self.assert_stock()

    def test_project_deletion_leaves_picked_parts_unlocated_even_if_drawer_exists(self):
        pid,drawer=self.take();projects.delete(self.db,pid)
        self.assertEqual(self.count(drawer),0)
        with self.db.read() as c:self.assertEqual(available(c,self.part,'4'),100)
        self.db.undo_last_action();self.assertEqual(work.picked_list(self.db,pid)[0]['quantity'],10)
        self.assertEqual(self.count(drawer),0);self.assert_stock()

    def test_empty_looking_drawer_can_be_merged_without_losing_picked_quantities(self):
        pid,drawer=self.take();walls.unassign(self.db,drawer)
        walls.save_drawer(self.db,self.wall,1,1,width=2,drawer_id=self.drawers[1]['id'])
        self.assertEqual(len(walls.drawers(self.db,self.wall)),5)
        self.assertEqual(work.picked_list(self.db,pid)[0]['quantity'],10)
        self.assertIsNone(work.picked_list(self.db,pid)[0]['drawer_id']);self.assert_stock()

    def test_unlocated_picks_survive_database_restart(self):
        pid,_=self.take();walls.delete_wall(self.db,self.wall)
        self.db.close();self.db=Database(self.root/'atelier.sqlite')
        self.assertEqual(work.picked_list(self.db,pid)[0]['quantity'],10)
        projects.delete(self.db,pid);self.assert_stock()

    def test_storage_delete_button_succeeds_with_a_project_still_using_parts(self):
        from atelier.storage_panel import StoragePanel
        pid,drawer=self.take()
        with patch.object(StoragePanel,'schedule_icons'):
            panel=StoragePanel(self.db,None);self.windows.append(panel);panel.wall_id=self.wall;panel.drawer_id=drawer
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'warning') as warning:panel.remove_wall()
            warning.assert_not_called();self.assertEqual(walls.walls(self.db),[])
            self.assertEqual(work.picked_list(self.db,pid)[0]['quantity'],10)

    def test_pick_dialog_and_csv_keep_unlocated_reference_colour_and_quantity(self):
        from atelier.collection_dialogs import PickListDialog
        pid,_=self.take();walls.delete_wall(self.db,self.wall)
        dialog=PickListDialog(self.db,pid);self.windows.append(dialog);dialog.tabs.setCurrentIndex(1)
        self.assertEqual(dialog.taken_table.item(0,0).text(),'Aucun tiroir défini')
        self.assertEqual(dialog.taken_table.item(0,1).text(),'');self.assertEqual(dialog.taken_table.item(0,5).text(),'10')
        with patch('atelier.collection_dialogs.export_rows') as export:dialog.export()
        self.assertEqual(sum(r[6] for r in export.call_args.args[2]),10)

    def test_project_delete_button_releases_picks_without_a_return_requirement(self):
        from atelier.projects_panel import ProjectsPanel
        pid,_=self.take();walls.delete_wall(self.db,self.wall)
        panel=ProjectsPanel(self.db);self.windows.append(panel);panel.refresh(pid)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'warning') as warning:panel.delete()
        warning.assert_not_called();self.assertEqual(projects.list_projects(self.db),[]);self.assert_stock()

    def test_v68_located_picks_migrate_without_changing_quantities(self):
        pid,drawer=self.take()
        with self.db.connect() as c:
            c.execute('DROP VIEW project_physical_picks');c.execute('DROP TABLE project_unlocated_picks')
            c.execute('''CREATE VIEW project_physical_picks AS SELECT project_id,item_id,color,drawer_id,quantity,color AS need_color FROM project_pick_rows
              UNION ALL SELECT project_id,item_id,stock_color AS color,drawer_id,quantity,color AS need_color FROM project_color_pick_rows''')
        self.db.close();self.db=Database(self.root/'atelier.sqlite')
        self.assertEqual(work.picked_list(self.db,pid)[0]['drawer_id'],drawer)
        walls.delete_wall(self.db,self.wall);projects.delete(self.db,pid);self.assert_stock()

    def test_reused_drawer_ids_never_reassign_unlocated_picks(self):
        pid,drawer=self.take();walls.delete_wall(self.db,self.wall)
        replacement=walls.create_wall(self.db,'Nouveau meuble',2,3)
        self.assertIn(drawer,[r['id'] for r in walls.drawers(self.db,replacement)])
        self.assertIsNone(work.picked_list(self.db,pid)[0]['drawer_id'])
        work.return_picks(self.db,pid)
        self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),[])
        projects.delete(self.db,pid);self.assert_stock()

    def test_cabinet_delete_notifies_open_pick_list_and_undo_restores_its_location(self):
        from atelier.app import MainWindow
        from atelier.windows import show_window
        from atelier.collection_dialogs import PickListDialog
        pid,drawer=self.take()
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.thumbnails.PartThumbnails.schedule'),patch('atelier.storage_panel.StoragePanel.schedule_icons'),patch('atelier.preview.Preview.refresh'):
            owner=MainWindow(self.db);self.windows.append(owner);owner.startup_timer.stop();owner.cleanup_timer.stop()
            dialog=show_window(PickListDialog(self.db,pid,parent=owner),owner);dialog.tabs.setCurrentIndex(1)
            owner.storage.wall_id=self.wall
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):owner.storage.remove_wall()
            self.assertEqual(dialog.taken_table.item(0,0).text(),'Aucun tiroir défini')
            owner.undo_shortcut.trigger();self.assertEqual(work.picked_list(self.db,pid)[0]['drawer_id'],drawer)
            self.assertNotEqual(dialog.taken_table.item(0,0).text(),'Aucun tiroir défini')
