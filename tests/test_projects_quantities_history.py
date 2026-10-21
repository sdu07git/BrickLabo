"""End-to-end data invariants for physical storage, projects, and undo/redo."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication,QDialogButtonBox,QPushButton
from PySide6.QtCore import Qt

from atelier.data import Database,SCHEMA
from atelier import action_history as history
from atelier import storage_wall as walls
from atelier import storage_quantities as quantities
from atelier import storage_assignment as assignment
from atelier import projects,preferences_backup,build_stock
from atelier.action_undo import set_default_color,set_visual_color
from atelier.storage_preview import proposal_snapshot

app=QApplication.instance() or QApplication([])


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.db=Database(self.root/'atelier.sqlite')
        self.part=self.item('RB','part','3005','Brick 1 x 1')
        self.other=self.item('RB','part','3001','Brick 2 x 4')
        self.bl=self.item('BL','part','3005','Brick 1 x 1')
        self.set=self.item('RB','set','test-1','Test set')
        self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)")
        self.db.run("INSERT INTO colors VALUES(1,'Blue','0000FF',0)")
        self.db.add('stock',self.part,'4',100)
        self.db.add('stock',self.other,'4',40)
        self.db.add('stock',self.bl,'4',50)
        self.wall=walls.create_wall(self.db,'Meuble',2,3)
        self.drawers=walls.drawers(self.db,self.wall)
        with self.db.connect() as c:history.clear(c)
        self.windows=[]

    def item(self,source,kind,ref,name):
        return self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',(source,kind,ref,name,'Bricks',ref+' '+name))

    def count(self,drawer,item=None,color='4'):
        rows=self.db.rows('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer,item or self.part,color))
        return rows[0]['quantity'] if rows else None

    def place(self,drawer,quantity,item=None,color='4'):
        item=item or self.part
        walls.assign(self.db,drawer,[(item,color)])
        quantities.set_quantity(self.db,drawer,item,color,quantity)

    def loose(self):return self.db.rows('SELECT * FROM stock ORDER BY id')
    def remaining(self,item=None,color='4'):
        with self.db.read() as c:return quantities.available(c,item or self.part,color)
    def project(self,name='Modèle',need=60,item=None,color='4'):
        return projects.create(self.db,name,[{'item_id':item or self.part,'color':color,'quantity':need}])

    def tearDown(self):
        for window in self.windows:window.close()
        app.processEvents();self.db.close();self.temp.cleanup()


class DrawerQuantityTests(Fixture):
    def test_counts_are_distributed_without_duplicating_possession(self):
        before=self.loose();a,b=[row['id'] for row in self.drawers[:2]]
        self.place(a,30);self.place(b,70)
        self.assertEqual((self.count(a),self.count(b),self.remaining()),(30,70,0))
        self.assertEqual(self.loose(),before)
        rows=assignment.stock_rows(self.db,remaining_only=True)
        self.assertNotIn(self.part,[row['id'] for row in rows])

    def test_overallocation_is_rejected_without_changing_history_or_counts(self):
        a,b=[row['id'] for row in self.drawers[:2]];self.place(a,30);self.place(b,70)
        before=history.rows(self.db)
        with self.assertRaises(ValueError):quantities.set_quantity(self.db,b,self.part,'4',71)
        self.assertEqual((self.count(a),self.count(b)),(30,70));self.assertEqual(history.rows(self.db),before)

    def test_each_colour_and_source_has_its_own_pool(self):
        self.db.add('stock',self.part,'1',10)
        a,b=[row['id'] for row in self.drawers[:2]]
        self.place(a,100);self.place(b,10,color='1')
        self.assertEqual(self.remaining(color='1'),0)
        self.assertEqual(self.remaining(self.bl),50)

    def test_partial_transfer_and_replay_preserve_the_stock_total(self):
        a,b=[row['id'] for row in self.drawers[:2]];self.place(a,30);self.place(b,70);before=self.loose()
        quantities.transfer(self.db,a,b,self.part,'4',20)
        self.assertEqual((self.count(a),self.count(b)),(10,90));self.assertTrue(self.db.undo_last_action())
        self.assertEqual((self.count(a),self.count(b)),(30,70));self.assertTrue(self.db.redo_last_action())
        self.assertEqual((self.count(a),self.count(b)),(10,90));self.assertEqual(self.loose(),before)

    def test_drag_moves_and_merges_the_assigned_quantity(self):
        a,b=[row['id'] for row in self.drawers[:2]];self.place(a,30);self.place(b,20)
        assignment.place_entries(self.db,b,[(self.part,'4')],a)
        self.assertIsNone(self.count(a));self.assertEqual(self.count(b),50);self.assertEqual(self.remaining(),50)
        self.assertTrue(self.db.undo_last_action());self.assertEqual((self.count(a),self.count(b)),(30,20))

    def test_removing_a_location_returns_its_quantity_to_unplaced_stock(self):
        a=self.drawers[0]['id'];self.place(a,45);before=self.loose()
        walls.unassign(self.db,a,[(self.part,'4')]);self.assertEqual(self.remaining(),100)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(self.count(a),45);self.assertEqual(self.loose(),before)

    def test_stock_reduction_cannot_leave_impossible_physical_counts(self):
        a=self.drawers[0]['id'];self.place(a,90);before=self.loose();record=history.rows(self.db)
        entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.part,))[0]['id']
        with self.assertRaises(ValueError):self.db.change_entries('stock',[entry],'quantity',80)
        self.assertEqual(self.loose(),before);self.assertEqual(history.rows(self.db),record)

    def test_remaining_stock_drag_uses_the_current_unplaced_quantity(self):
        a,b=[row['id'] for row in self.drawers[:2]];self.place(a,30)
        self.assertEqual(quantities.place_remaining(self.db,b,[(self.part,'4')]),70)
        self.assertEqual(self.count(b),70);self.assertEqual(self.remaining(),0)
        set_default_color(self.db,'#112233');self.db.undo_last_action();redo=self.db.redo_description()
        self.assertEqual(quantities.place_remaining(self.db,b,[(self.part,'4')]),0)
        self.assertEqual(self.db.redo_description(),redo)

    def test_stale_stock_drop_rejects_the_whole_selection(self):
        target=self.drawers[0]['id'];self.db.run('UPDATE stock SET quantity=0 WHERE item_id=?',(self.other,))
        before=walls.print_snapshot(self.db)
        with self.assertRaises(ValueError):quantities.place_remaining(self.db,target,[(self.part,'4'),(self.other,'4')])
        self.assertEqual(walls.print_snapshot(self.db),before);self.assertEqual(self.remaining(),100)

    def test_proposal_preview_and_apply_show_only_the_remaining_quantity(self):
        a=self.drawers[0]['id'];self.place(a,30)
        plan=assignment.propose(self.db,self.wall,entries=[(self.part,'4')],grouping='reference',allocate_quantities=True)
        snap=proposal_snapshot(plan,[group['drawer_id'] for group in plan['groups']])
        target=plan['groups'][0]['drawer_id'];self.assertEqual(snap['contents'][target][0]['stored_quantity'],70)
        before=walls.print_snapshot(self.db);assignment.apply_proposal(self.db,plan)
        self.assertEqual(self.remaining(),0);self.db.undo_last_action();self.assertEqual(walls.print_snapshot(self.db),before)

    def test_reorganization_retains_counts_even_when_allocation_is_disabled(self):
        a,b=[row['id'] for row in self.drawers[:2]];self.place(a,15);self.place(b,25)
        before=walls.print_snapshot(self.db)
        plan=assignment.propose(self.db,self.wall,'Bricks',reorganize=True,entries=[(self.part,'4')])
        assignment.apply_proposal(self.db,plan)
        self.assertEqual(sum(row['quantity'] or 0 for row in self.db.rows('SELECT quantity FROM storage_contents')),40)
        self.db.undo_last_action();self.assertEqual(walls.print_snapshot(self.db),before)

    def test_catalogue_association_stays_unspecified_until_the_user_counts(self):
        a=self.drawers[0]['id'];assignment.place_entries(self.db,a,[(self.part,'')],from_catalogue=True)
        self.assertIsNone(self.count(a,color=''))
        quantities.set_quantity(self.db,a,self.part,'',35,target_color='4')
        self.assertEqual(self.count(a),35);self.assertEqual(self.remaining(),65)


class ProjectTests(Fixture):
    def test_two_projects_cannot_reserve_the_same_units_twice(self):
        first=self.project('Premier',60);second=self.project('Deuxième',60);before=self.loose()
        projects.reserve(self.db,first);projects.reserve(self.db,second)
        a,b=projects.detail(self.db,first)[0],projects.detail(self.db,second)[0]
        self.assertEqual((a['reserved'],b['reserved'],b['missing']),(60,40,20));self.assertEqual(self.loose(),before)

    def test_completed_project_keeps_reservations_until_explicit_release(self):
        first=self.project();projects.reserve(self.db,first);projects.edit(self.db,first,status='completed')
        self.assertEqual(projects.detail(self.db,first)[0]['reserved'],60)
        projects.release(self.db,first);self.assertEqual(projects.detail(self.db,first)[0]['reserved'],0)
        self.db.undo_last_action();self.assertEqual(projects.detail(self.db,first)[0]['reserved'],60)

    def test_exact_reservation_and_release_do_not_change_physical_locations(self):
        a=self.drawers[0]['id'];self.place(a,100);first=self.project();before=walls.print_snapshot(self.db)
        projects.reserve(self.db,first,quantity=45)
        self.assertEqual(projects.detail(self.db,first)[0]['reserved'],45)
        self.assertEqual(walls.print_snapshot(self.db),before)
        with self.assertRaises(ValueError):projects.reserve(self.db,first,quantity=61)

    def test_stock_reduction_requires_releasing_reservations_first(self):
        project=self.project();projects.reserve(self.db,project)
        entry=self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.part,))[0]['id']
        with self.assertRaises(ValueError):self.db.change_entries('stock',[entry],'quantity',50)
        self.assertEqual(projects.detail(self.db,project)[0]['reserved'],60)
        projects.release(self.db,project);self.db.change_entries('stock',[entry],'quantity',50)
        self.assertEqual(projects.detail(self.db,project)[0]['missing'],10)

    def test_delete_and_undo_restore_requirements_and_reserved_units(self):
        project=self.project();projects.reserve(self.db,project);before=projects.detail(self.db,project)
        projects.delete(self.db,project);self.assertEqual(projects.list_projects(self.db),[])
        self.db.undo_last_action();self.assertEqual(projects.detail(self.db,project),before)
        self.db.redo_last_action();self.assertEqual(projects.list_projects(self.db),[])

    def test_set_project_snapshots_copies_and_optional_spares(self):
        self.db.run("INSERT INTO inventories VALUES(1,1,'test-1')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',4,5,0,'')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3001',4,2,1,'')")
        project=projects.from_set(self.db,self.set,copies=2)
        self.assertEqual([(p['id'],p['required']) for p in projects.detail(self.db,project)],[(self.part,10)])
        with_spares=projects.from_set(self.db,self.set,spares=True)
        self.assertEqual(sum(p['required'] for p in projects.detail(self.db,with_spares)),7)
        self.db.run('UPDATE inventory_parts SET quantity=999')
        self.assertEqual(projects.detail(self.db,project)[0]['required'],10)

    def test_incomplete_inventory_does_not_create_a_partial_project(self):
        self.db.run("INSERT INTO inventories VALUES(1,1,'test-1')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'missing-part',4,1,0,'')")
        before=history.rows(self.db)
        with self.assertRaises(ValueError):projects.from_set(self.db,self.set)
        self.assertEqual(projects.list_projects(self.db),[]);self.assertEqual(history.rows(self.db),before)

    def test_build_search_and_stock_columns_exclude_reserved_loose_units(self):
        project=self.project();projects.reserve(self.db,project)
        with self.db.read() as c:
            counts=build_stock.InventoryReader(c).stock();key=build_stock.InventoryReader(c).canonical('RB','3005','4')
        self.assertEqual(counts[key],40)
        rows,_,_,_=self.db.query(scope='stock',sort='available_quantity')
        part=next(row for row in rows if row['id']==self.part)
        self.assertEqual((part['chosen_quantity'],part['reserved_quantity'],part['available_quantity']),(100,60,40))


class HistoryTests(Fixture):
    def test_mixed_actions_can_be_undone_and_redone_after_restart(self):
        before=self.loose();self.db.add('stock',self.part,'4',5)
        set_default_color(self.db,'#112233');a=self.drawers[0]['id'];self.place(a,35)
        project=self.project();projects.reserve(self.db,project)
        after=(self.loose(),walls.print_snapshot(self.db),projects.list_projects(self.db),self.db.setting('default_color'))
        count=len(history.rows(self.db));self.db.close();self.db=Database(self.db.path)
        for _ in range(count):self.assertTrue(self.db.undo_last_action())
        self.assertEqual(self.loose(),before);self.assertEqual(projects.list_projects(self.db),[]);self.assertEqual(walls.contents(self.db,a),[])
        for _ in range(count):self.assertTrue(self.db.redo_last_action())
        self.assertEqual((self.loose(),walls.print_snapshot(self.db),projects.list_projects(self.db),self.db.setting('default_color')),after)

    def test_branch_after_undo_discards_redo_without_losing_earlier_actions(self):
        set_default_color(self.db,'#111111');set_default_color(self.db,'#222222');self.db.undo_last_action()
        set_default_color(self.db,'#333333')
        self.assertFalse(self.db.redo_last_action());self.db.undo_last_action();self.assertEqual(self.db.setting('default_color'),'#111111')
        self.db.undo_last_action();self.assertIsNone(self.db.setting('default_color'))

    def test_noop_and_invalid_change_preserve_the_redo_branch(self):
        set_default_color(self.db,'#111111');set_default_color(self.db,'#222222');self.db.undo_last_action();before=history.rows(self.db)
        self.assertFalse(set_default_color(self.db,'#111111'))
        with self.assertRaises(ValueError):self.project(need=-1)
        self.assertEqual(history.rows(self.db),before);self.assertTrue(self.db.redo_last_action())

    def test_external_change_to_the_same_row_blocks_replay_atomically(self):
        a=self.drawers[0]['id'];self.place(a,30);self.db.run('UPDATE storage_contents SET quantity=40 WHERE drawer_id=?',(a,))
        before=history.rows(self.db)
        with self.assertRaises(ValueError):self.db.undo_last_action()
        self.assertEqual(self.count(a),40);self.assertEqual(history.rows(self.db),before)

    def test_external_child_is_not_deleted_by_undoing_project_creation(self):
        project=self.project()
        self.db.run('INSERT INTO project_parts VALUES(?,?,?,?,?)',(project,self.other,'4',1,0))
        with self.assertRaises(ValueError):self.db.undo_last_action()
        self.assertEqual(len(projects.detail(self.db,project)),2)

    def test_unrelated_drawer_changes_are_preserved_when_undoing_a_link(self):
        a=self.drawers[0]['id'];walls.assign(self.db,a,[(self.part,'4')])
        self.db.run('INSERT INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',(a,self.other,'4'))
        self.assertTrue(self.db.undo_last_action());self.assertEqual([row['id'] for row in walls.contents(self.db,a)],[self.other])

    def test_limit_preserves_a_replayable_redo_prefix(self):
        for color in ['#111111','#222222','#333333']:set_default_color(self.db,color)
        for _ in range(3):self.db.undo_last_action()
        history.set_limit(self.db,1)
        self.assertEqual(len(history.rows(self.db)),1);self.assertTrue(self.db.redo_last_action())
        self.assertEqual(self.db.setting('default_color'),'#111111');self.assertFalse(self.db.redo_last_action())

    def test_individual_colour_redo_keeps_the_photo_and_other_references(self):
        self.db.save_visual(self.part,image='personal.png',color='#111111');other=self.db.visual(self.other)
        set_visual_color(self.db,self.part,'#222222');self.db.undo_last_action();self.db.redo_last_action()
        self.assertEqual(self.db.visual(self.part)['image'],'personal.png');self.assertEqual(self.db.visual(self.part)['color'],'#222222');self.assertEqual(self.db.visual(self.other),other)


class BackupAndMigrationTests(Fixture):
    def test_selective_bundle_preserves_counts_projects_and_reference_identity(self):
        self.place(self.drawers[0]['id'],30);project=self.project();projects.reserve(self.db,project)
        files=[preferences_backup.export_family(self.db,family,self.root/(family+'.json')) for family in ('loose','storage','projects')]
        target=Database(self.root/'destination.sqlite')
        try:
            preferences_backup.restore_families(target,files)
            self.assertEqual(sum(row['quantity'] or 0 for row in target.rows('SELECT quantity FROM storage_contents')),30)
            self.assertEqual(projects.list_projects(target)[0]['reserved'],60)
            self.assertEqual(target.rows("SELECT ref FROM items WHERE id=(SELECT item_id FROM project_parts LIMIT 1)")[0]['ref'],'3005')
            self.assertEqual(history.rows(target),[])
        finally:target.close()

    def test_restore_without_required_stock_rolls_back_the_entire_bundle(self):
        project=self.project();projects.reserve(self.db,project)
        file=preferences_backup.export_family(self.db,'projects',self.root/'projects.json');target=Database(self.root/'empty.sqlite')
        try:
            with self.assertRaises(ValueError):preferences_backup.restore_families(target,[file])
            self.assertEqual(projects.list_projects(target),[]);self.assertEqual(target.rows('SELECT * FROM items'),[])
        finally:target.close()

    def test_v56_drawers_and_last_colour_action_migrate_without_inventing_counts(self):
        path=self.root/'legacy.sqlite';c=sqlite3.connect(path);c.executescript(SCHEMA)
        c.executescript('''CREATE TABLE storage_walls(id INTEGER PRIMARY KEY,name TEXT,columns INTEGER,rows INTEGER,x REAL,y REAL);
            CREATE TABLE storage_drawers(id INTEGER PRIMARY KEY,wall_id INTEGER,col INTEGER,row INTEGER,width INTEGER,height INTEGER,name TEXT);
            CREATE TABLE storage_contents(drawer_id INTEGER,item_id INTEGER,color TEXT,PRIMARY KEY(drawer_id,item_id,color));
            CREATE TABLE action_undo(id INTEGER PRIMARY KEY,description TEXT,payload TEXT);''')
        c.execute("INSERT INTO items(id,source,kind,ref,name,search) VALUES(7,'RB','part','3005','Brick','3005')")
        c.execute("INSERT INTO stock(item_id,color,quantity) VALUES(7,'4',100)")
        c.execute("INSERT INTO storage_walls VALUES(8,'Ancien meuble',1,1,0,0)");c.execute("INSERT INTO storage_drawers VALUES(9,8,1,1,1,1,'Ancien tiroir')")
        c.execute("INSERT INTO storage_contents VALUES(9,7,'4')")
        value=json.dumps('#112233');c.execute("INSERT INTO settings VALUES('default_color',?)",(value,))
        c.execute('INSERT INTO action_undo VALUES(1,?,?)',('Modification de la couleur 3D générale',json.dumps({'kind':'color','before':None,'after':{'key':'default_color','value':value}})))
        c.commit();c.close();db=Database(path)
        try:
            self.assertEqual(walls.contents(db,9)[0]['stored_quantity'],None);self.assertEqual(walls.contents(db,9)[0]['chosen_quantity'],100)
            self.assertEqual(history.rows(db)[0]['created'],'');self.assertTrue(db.undo_last_action());self.assertIsNone(db.setting('default_color'))
            self.assertTrue(db.redo_last_action());self.assertEqual(db.setting('default_color'),'#112233')
        finally:db.close()


class NewInterfaceTests(Fixture):
    def test_project_commands_follow_available_and_reserved_quantities(self):
        from atelier.projects_panel import ProjectsPanel
        panel=ProjectsPanel(self.db,None);self.windows.append(panel)
        self.assertFalse(panel.reserve_button.isEnabled());self.assertFalse(panel.release_button.isEnabled())
        project=self.project();panel.refresh(project)
        self.assertTrue(panel.reserve_button.isEnabled());self.assertFalse(panel.release_button.isEnabled())
        panel.reserve_button.click()
        self.assertFalse(panel.reserve_button.isEnabled());self.assertTrue(panel.release_button.isEnabled())
        panel.release_button.click()
        self.assertTrue(panel.reserve_button.isEnabled());self.assertFalse(panel.release_button.isEnabled())

    def test_quantity_edit_requires_one_reference_and_positive_transfer_count(self):
        from atelier.storage_panel import StoragePanel
        panel=StoragePanel(self.db,None);self.windows.append(panel)
        drawer=self.drawers[0]['id'];self.place(drawer,30);walls.assign(self.db,drawer,[(self.other,'4')])
        panel.refresh();panel.choose_drawer(drawer)
        from atelier.result_tables import row_index
        counted=next(row for row in range(panel.table.rowCount()) if panel.rows[row_index(panel.table,row)]['id']==self.part)
        panel.table.selectRow(counted)
        self.assertTrue(panel.quantity_button.isEnabled());self.assertTrue(panel.transfer_button.isEnabled())
        panel.table.setSelectionMode(panel.table.SelectionMode.MultiSelection);panel.table.selectRow(1-counted)
        self.assertFalse(panel.quantity_button.isEnabled());self.assertFalse(panel.transfer_button.isEnabled())
        self.assertIsNone(panel.edit_drawer_quantity())

    def test_sorted_project_list_keeps_the_selected_project_on_refresh(self):
        from atelier.projects_panel import ProjectsPanel
        first=self.project('Zèbre');second=self.project('Alpha')
        panel=ProjectsPanel(self.db,None);self.windows.append(panel)
        panel.table.sortItems(0,Qt.SortOrder.DescendingOrder);panel.refresh(second)
        self.assertEqual(panel.project_id,second);panel.refresh(first);self.assertEqual(panel.project_id,first)

    def test_project_creation_reservation_and_history_are_wired_to_main_window(self):
        from atelier.app import MainWindow,NAV
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.thumbnails.PartThumbnails.schedule'),patch('atelier.storage_panel.StoragePanel.schedule_icons'),patch('atelier.preview.Preview.refresh'):
            window=MainWindow(self.db);self.windows.append(window);window.startup_timer.stop();window.cleanup_timer.stop();window.show()
            window.nav.setCurrentRow(next(index for index,row in enumerate(NAV) if row[3]=='projects'))
            dialog=window.projects.create_from_item();dialog.kind.setCurrentIndex(1);dialog.name.setText('Ma construction');dialog.save();app.processEvents()
            project=window.projects.project_id;self.assertIsNotNone(project)
            projects.put_part(self.db,project,self.part,'4',60);window.refresh_counts()
            window.projects.reserve_button.click()
            self.assertEqual(projects.detail(self.db,project)[0]['reserved'],60)
            window.undo_shortcut.trigger();self.assertEqual(projects.detail(self.db,project)[0]['reserved'],0)
            self.assertTrue(window.redo_button.isEnabled());window.redo_shortcut.trigger();self.assertEqual(projects.detail(self.db,project)[0]['reserved'],60)
            panel=window.show_action_history();self.assertEqual(panel.table.rowCount(),len(history.rows(self.db)));self.assertTrue(panel.undo.isEnabled())
            window.engine.close()

    def test_quantity_dialog_applies_a_count_to_the_captured_drawer(self):
        from atelier.storage_panel import StoragePanel
        panel=StoragePanel(self.db,None);self.windows.append(panel);panel.show()
        drawer=self.drawers[0]['id'];walls.assign(self.db,drawer,[(self.part,'4')]);panel.refresh();panel.choose_drawer(drawer);panel.table.selectRow(0)
        dialog=panel.edit_drawer_quantity();self.windows.append(dialog)
        from PySide6.QtWidgets import QSpinBox
        dialog.findChild(QSpinBox).setValue(30);dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(self.count(drawer),30);self.assertEqual(panel.table.item(0,7).text(),'30')
