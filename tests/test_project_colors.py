"""Ignore requested colours while retaining real, exclusive stock reservations."""
import json
from pathlib import Path
from unittest.mock import patch
from test_projects_quantities_history import Fixture,app
from atelier import projects,collection_workflows as work,preferences_backup,stock_clear
from atelier.storage_quantities import put_entry
from atelier.data import Database


class ProjectColorTests(Fixture):
    def need(self,quantity=12,ignore=True,color='1'):
        return projects.create(self.db,'Sans couleurs',[dict(item_id=self.part,color=color,quantity=quantity)],ignore_colors=ignore)
    def green_stock(self,quantity=8):
        self.db.run('UPDATE stock SET quantity=0 WHERE item_id=?',(self.part,))
        if quantity:self.db.add('stock',self.part,'2',quantity)
    def test_mode_can_change_an_existing_project_without_changing_original_needs(self):
        pid=self.need(ignore=False);self.assertEqual(projects.detail(self.db,pid)[0]['missing'],12)
        projects.set_ignore_colors(self.db,pid,True);row=projects.detail(self.db,pid)[0]
        self.assertEqual((row['missing'],row['chosen_color']),(0,'1'));self.assertEqual(projects.list_projects(self.db)[0]['missing'],0)
        projects.set_ignore_colors(self.db,pid,False);self.assertEqual(projects.detail(self.db,pid)[0]['missing'],12)
        self.db.undo_last_action();self.assertTrue(projects.list_projects(self.db)[0]['ignore_colors'])
    def test_two_requested_colours_share_one_pool_without_double_counting(self):
        self.green_stock();pid=projects.create(self.db,'Deux couleurs',[dict(item_id=self.part,color=color,quantity=6) for color in ('1','4')],ignore_colors=True)
        rows=projects.detail(self.db,pid);self.assertEqual(sum(r['missing'] for r in rows),4);self.assertEqual(sum(r['free_quantity'] for r in rows),8)
        self.assertEqual(projects.list_projects(self.db)[0]['missing'],4);projects.reserve(self.db,pid)
        self.assertEqual([r['reserved'] for r in projects.detail(self.db,pid)],[6,2]);self.assertEqual(sum(r['reserved'] for r in self.db.rows('SELECT * FROM project_stock_reservations')),8)
        self.assertEqual({r['color'] for r in self.db.rows('SELECT * FROM project_stock_reservations')},{'2'})
    def test_physical_reservations_block_other_projects_and_stock_reductions(self):
        self.green_stock();pid=self.need(8);projects.reserve(self.db,pid);other=self.need(8,color='2',ignore=False);projects.reserve(self.db,other)
        self.assertEqual(projects.detail(self.db,other)[0]['reserved'],0)
        row=next(r for r in self.db.query(scope='stock')[0] if r['id']==self.part and r['chosen_color']=='2')
        self.assertEqual((row['reserved_quantity'],row['available_quantity']),(8,0))
        with self.assertRaises(ValueError):self.db.change_entries('stock',[row['entry_id']],'quantity',7)
        self.assertEqual(projects.detail(self.db,pid)[0]['reserved_colors'],{'2':8})
    def test_two_projects_cannot_reuse_other_colour_units(self):
        self.green_stock();a=self.need(5);b=self.need(5);projects.reserve(self.db,a);projects.reserve(self.db,b)
        self.assertEqual(projects.detail(self.db,a)[0]['reserved'],5);self.assertEqual(projects.detail(self.db,b)[0]['reserved'],3)
        self.assertEqual(projects.detail(self.db,b)[0]['missing'],2)
    def test_colour_zero_and_different_sources_remain_distinct(self):
        self.green_stock(0);self.db.add('stock',self.part,'0',4);pid=self.need(6)
        self.assertEqual(projects.detail(self.db,pid)[0]['missing'],2);projects.reserve(self.db,pid)
        self.assertEqual(projects.detail(self.db,pid)[0]['reserved_colors'],{'0':4})
    def test_toggling_preserves_exact_reservations_and_rejects_other_colours_on_return(self):
        pid=self.need(5,color='4',ignore=False);projects.reserve(self.db,pid);projects.set_ignore_colors(self.db,pid,True)
        self.assertEqual(projects.detail(self.db,pid)[0]['reserved_colors'],{'4':5});projects.set_ignore_colors(self.db,pid,False);projects.release(self.db,pid)
        self.green_stock();pid=self.need(5);projects.reserve(self.db,pid)
        with self.assertRaisesRegex(ValueError,'Libère'):projects.set_ignore_colors(self.db,pid,False)
        self.assertTrue(next(p for p in projects.list_projects(self.db) if p['id']==pid)['ignore_colors'])
        projects.release(self.db,pid);projects.set_ignore_colors(self.db,pid,False)
    def test_mixed_colours_in_same_drawer_can_be_taken_and_returned(self):
        self.green_stock(5);self.db.add('stock',self.part,'0',3);drawer=self.drawers[0]['id']
        put_entry(self.db,drawer,self.part,'2',5);put_entry(self.db,drawer,self.part,'0',3);pid=self.need(8,color='1')
        rows=work.pick_list(self.db,pid);self.assertEqual(sum(r['suggested'] for r in rows if r['drawer_id']),8)
        for row in rows:work.pick(self.db,pid,self.part,row['color'],drawer,row['suggested'],row['quantity'],need_color=row['need_color'])
        self.assertEqual(sum(r['quantity'] for r in self.db.rows('SELECT * FROM project_physical_picks')),8)
        self.assertEqual(work.pick_list(self.db,pid),[])
        with self.assertRaises(ValueError):projects.release(self.db,pid)
        with self.assertRaises(ValueError):projects.delete(self.db,pid)
        with self.assertRaises(ValueError):stock_clear.clear(self.db,'stock')
        work.return_picks(self.db,pid);self.assertEqual(self.count(drawer,color='2'),5);self.assertEqual(self.count(drawer,color='0'),3)
        self.db.undo_last_action();self.assertEqual(self.count(drawer,color='2'),0)
        self.db.undo_last_action();self.assertGreater(sum(r['quantity'] for r in self.db.rows('SELECT * FROM storage_contents')),0)
    def test_pick_plan_does_not_offer_one_drawer_to_two_requested_colours_twice(self):
        self.green_stock();drawer=self.drawers[0]['id'];put_entry(self.db,drawer,self.part,'2',8)
        pid=projects.create(self.db,'Deux besoins',[dict(item_id=self.part,color=color,quantity=6) for color in ('1','4')],ignore_colors=True)
        rows=work.pick_list(self.db,pid);self.assertEqual(sum(r['suggested'] for r in rows if r['drawer_id']),8)
        for row in [r for r in rows if r['drawer_id']]:
            current=self.count(drawer,color='2');work.pick(self.db,pid,self.part,row['color'],drawer,row['suggested'],current,need_color=row['need_color'])
        self.assertEqual(sum(r['quantity'] for r in self.db.rows('SELECT * FROM project_physical_picks')),8)
    def test_new_stock_of_any_colour_recalculates_missing(self):
        self.green_stock(2);pid=self.need(8);projects.reserve(self.db,pid);self.assertEqual(projects.detail(self.db,pid)[0]['missing'],6)
        self.db.add('stock',self.part,'0',6);self.assertEqual(projects.detail(self.db,pid)[0]['missing'],0);projects.reserve(self.db,pid)
        self.assertEqual(sum(projects.detail(self.db,pid)[0]['reserved_colors'].values()),8)
    def test_selective_backup_restores_mode_original_colours_and_physical_reservations(self):
        self.green_stock();pid=self.need(8);projects.reserve(self.db,pid)
        files=[preferences_backup.export_family(self.db,family,self.root/(family+'.json')) for family in ('loose','projects')]
        target=Database(self.root/'restored.sqlite')
        try:
            preferences_backup.restore_families(target,files);row=projects.list_projects(target)[0];part=projects.detail(target,row['id'])[0]
            self.assertTrue(row['ignore_colors']);self.assertEqual((part['chosen_color'],part['reserved_colors']),('1',{'2':8}))
        finally:target.close()
    def test_clear_and_undo_restore_real_colour_reservations(self):
        self.green_stock();pid=self.need(8);projects.reserve(self.db,pid);stock_clear.clear(self.db,'stock')
        self.assertEqual(projects.detail(self.db,pid)[0]['reserved'],0);self.db.undo_last_action();self.assertEqual(projects.detail(self.db,pid)[0]['reserved_colors'],{'2':8})
    def test_legacy_project_action_without_mode_still_undoes(self):
        pid=self.need(4,ignore=False)
        row=self.db.rows('SELECT * FROM action_history ORDER BY id DESC LIMIT 1')[0];payload=json.loads(row['payload'])
        for change in payload['changes']:
            if change['table']=='construction_projects':
                for state in ('before','after'):
                    if change[state]:change[state].pop('ignore_colors')
        self.db.run('UPDATE action_history SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        self.db.undo_last_action();self.db.redo_last_action();self.assertFalse(projects.list_projects(self.db)[0]['ignore_colors'])

    def test_reserved_other_colours_are_removed_from_build_search_stock(self):
        from atelier.build_stock import InventoryReader
        self.green_stock();pid=self.need(5)
        with self.db.read() as c:before=InventoryReader(c,ignore_colors=True,include_set_stock=False).stock()[('RB','3005','*')]
        projects.reserve(self.db,pid)
        with self.db.read() as c:
            reader=InventoryReader(c,ignore_colors=True,include_set_stock=False);pool=reader.stock()
            self.assertEqual(before-pool[('RB','3005','*')],5)
    def test_alternatives_can_supply_other_colours_without_displacing_native_stock(self):
        from atelier.alternative_catalogue import copy_items
        self.green_stock(2);alt=copy_items(self.db,[self.db.get_item(self.part)])['target_ids'][0];self.db.add('stock',alt,'0',3)
        self.db.run('INSERT INTO inventories VALUES(1,1,?)',('test-1',));self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',1,5,0,'')")
        pid=projects.from_set(self.db,self.set,ignore_colors=True,allow_alternatives=True);parts=projects.detail(self.db,pid)
        self.assertEqual({p['id']:p['required'] for p in parts},{self.part:2,alt:3});self.assertEqual(sum(p['missing'] for p in parts),0)
        projects.reserve(self.db,pid);self.assertEqual({p['id']:p['reserved_colors'] for p in projects.detail(self.db,pid)},{self.part:{'2':2},alt:{'0':3}})

    def test_delete_and_undo_keep_colour_allocations(self):
        self.green_stock();pid=self.need(5);projects.reserve(self.db,pid);projects.delete(self.db,pid)
        self.assertFalse(self.db.rows('SELECT * FROM project_color_reservations'));self.db.undo_last_action()
        self.assertEqual(projects.detail(self.db,pid)[0]['reserved_colors'],{'2':5})
    def test_new_mode_survives_restart_and_existing_project_migrates_to_exact(self):
        pid=self.need(5,ignore=False);projects.set_ignore_colors(self.db,pid,True)
        self.db.close();self.db=Database(self.root/'atelier.sqlite');self.assertTrue(projects.list_projects(self.db)[0]['ignore_colors'])
        projects.set_ignore_colors(self.db,pid,False);self.assertFalse(projects.list_projects(self.db)[0]['ignore_colors'])
    def test_picked_colours_can_be_preserved_when_changing_mode(self):
        pid=self.need(4,ignore=False,color='4');drawer=self.drawers[0]['id'];put_entry(self.db,drawer,self.part,'4',10)
        work.pick(self.db,pid,self.part,'4',drawer,2);projects.set_ignore_colors(self.db,pid,True)
        self.assertEqual(work.pick_list(self.db,pid)[0]['suggested'],2);projects.set_ignore_colors(self.db,pid,False)
        work.return_picks(self.db,pid);self.assertEqual(self.count(drawer),10)
    def test_reserving_more_keeps_colours_already_picked(self):
        self.green_stock();drawer=self.drawers[0]['id'];put_entry(self.db,drawer,self.part,'2',8);pid=self.need(8)
        work.pick(self.db,pid,self.part,'2',drawer,3,need_color='1');self.db.add('stock',self.part,'0',10)
        projects.reserve(self.db,pid);self.assertGreaterEqual(projects.detail(self.db,pid)[0]['reserved_colors']['2'],3)
        with self.assertRaises(ValueError):projects.reserve(self.db,pid,quantity=2)
    def test_forged_backup_cannot_restore_reservations_without_real_colours(self):
        self.green_stock();pid=self.need(8);projects.reserve(self.db,pid);path=preferences_backup.export_family(self.db,'projects',self.root/'projects.json')
        payload=json.loads(path.read_text());payload['data']['projects'][0]['parts'][0]['allocations']=[];path.write_text(json.dumps(payload));before=projects.detail(self.db,pid)
        with self.assertRaises(ValueError):preferences_backup.restore_families(self.db,[path])
        self.assertEqual(projects.detail(self.db,pid),before)


class ProjectColorUITests(Fixture):
    def seed_set(self):
        self.db.run('INSERT INTO inventories VALUES(1,1,?)',('test-1',));self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',1,12,0,'')")
        return self.db.get_item(self.set)
    def panel(self):
        from atelier.projects_panel import ProjectsPanel
        panel=ProjectsPanel(self.db);self.windows.append(panel);return panel
    def test_new_project_and_existing_project_both_offer_the_mode(self):
        from atelier.projects_panel import NewProjectDialog
        panel=self.panel();dialog=panel.create_from_item(self.seed_set(),ignore_colors=True)
        self.assertTrue(dialog.ignore_colors.isChecked());dialog.save();row=projects.list_projects(self.db)[0]
        self.assertTrue(row['ignore_colors']);self.assertEqual(row['missing'],0);self.assertIn('100.0',panel.summary.text())
        panel.ignore_colors.setChecked(False);self.assertEqual(projects.list_projects(self.db)[0]['missing'],12)
        self.assertNotIn('100.0',panel.summary.text())
    def test_build_results_transmit_ignore_colours_to_project(self):
        from atelier.build_stock import BuildStockDialog
        from atelier.result_tables import fill_table
        item=self.seed_set();window=BuildStockDialog(self.db,None);self.windows.append(window)
        window.results=[dict(item,total=12,missing=0,percent=100)];window.last_ignore=True
        fill_table(window.table,[(item['source'],item['ref'])]);window.table.selectRow(0)
        dialog=window.create_project();self.assertTrue(dialog.ignore_colors.isChecked());dialog.save()
        self.assertEqual(projects.list_projects(self.db)[0]['missing'],0);self.assertTrue(projects.list_projects(self.db)[0]['ignore_colors'])
    def test_mode_is_per_project_and_failed_toggle_restores_checkbox(self):
        a=projects.create(self.db,'A',[dict(item_id=self.part,color='1',quantity=4)],ignore_colors=True)
        b=projects.create(self.db,'B',[dict(item_id=self.part,color='1',quantity=4)])
        panel=self.panel();panel.refresh(a);self.assertTrue(panel.ignore_colors.isChecked());panel.refresh(b);self.assertFalse(panel.ignore_colors.isChecked())
        panel.refresh(a);projects.reserve(self.db,a)
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox,'warning') as warning:panel.ignore_colors.setChecked(False)
        warning.assert_called_once();self.assertTrue(panel.ignore_colors.isChecked())
    def test_pick_dialog_uses_actual_colour_for_different_requested_colour(self):
        from atelier.collection_dialogs import PickListDialog
        from PySide6.QtWidgets import QInputDialog
        drawer=self.drawers[0]['id'];put_entry(self.db,drawer,self.part,'4',10)
        pid=projects.create(self.db,'A',[dict(item_id=self.part,color='1',quantity=4)],ignore_colors=True)
        dialog=PickListDialog(self.db,pid);self.windows.append(dialog);dialog.table.selectRow(0)
        with patch.object(QInputDialog,'getInt',return_value=(4,True)):dialog.take()
        self.assertEqual(self.count(drawer),6);self.assertEqual(self.db.rows('SELECT color,need_color FROM project_physical_picks')[0],dict(color='4',need_color='1'))
    def test_comparison_projects_keep_ignore_colours(self):
        item=self.seed_set();result=work.compare_builds(self.db,[(item['id'],1)],ignore_colors=True,include_set_stock=False)
        ids=work.create_comparison_projects(self.db,result,ignore_colors=True)
        self.assertEqual(len(ids),1);self.assertTrue(projects.list_projects(self.db)[0]['ignore_colors']);self.assertEqual(projects.list_projects(self.db)[0]['missing'],0)
