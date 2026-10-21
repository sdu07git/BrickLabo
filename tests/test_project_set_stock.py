"""Owned-set availability is optional and never becomes loose-stock ownership."""
import json
from unittest.mock import patch

from test_projects_quantities_history import Fixture, app
from atelier import projects, preferences_backup, collection_workflows as work
from atelier.data import Database


class ProjectSetStockFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.db.run('UPDATE stock SET quantity=0')
        # Representative inventory: the regression is source selection, not a
        # claim that these fixture quantities describe the official 30363-1.
        self.db.run("UPDATE items SET ref='30363-1' WHERE id=?", (self.set,))
        self.db.run("INSERT INTO inventories VALUES(1,1,'30363-1')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',4,6,0,'')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3001',1,2,0,'')")
        self.db.add('stock_sets', self.set, quantity=1)
        self.entry = self.db.rows('SELECT id FROM stock_sets')[0]['id']

    def project(self, **options):
        return projects.from_set(self.db, self.set, **options)

    def state(self, pid):
        return next(p for p in projects.list_projects(self.db) if p['id'] == pid)


class ProjectSetStockTests(ProjectSetStockFixture):
    def test_owned_complete_set_is_complete_only_when_option_is_enabled(self):
        pid = self.project()
        self.assertEqual(self.state(pid)['missing'], 8)
        projects.set_include_set_stock(self.db, pid, True)
        self.assertEqual(self.state(pid)['missing'], 0)
        self.assertEqual(sum(r['set_quantity'] for r in projects.detail(self.db, pid)), 8)
        projects.set_include_set_stock(self.db, pid, False)
        self.assertEqual(self.state(pid)['missing'], 8)

    def test_creation_custom_projects_and_source_choices_are_independent(self):
        a = self.project(include_set_stock=True)
        b = self.project()
        custom = projects.create(self.db, 'MOC', [dict(item_id=self.part, color='4', quantity=6)], include_set_stock=True)
        self.assertEqual((self.state(a)['missing'], self.state(b)['missing'], self.state(custom)['missing']), (0, 8, 0))
        self.assertFalse(self.state(a)['ignore_colors'])

    def test_multiple_copies_use_tracked_totals_once(self):
        pid = self.project(copies=2, include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 8)
        self.db.add('stock_sets', self.set, quantity=1)
        self.assertEqual(self.state(pid)['missing'], 0)
        pid = self.project(copies=3, include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 8)

    def test_partial_tracked_inventory_never_becomes_complete_from_catalogue(self):
        self.db.run('UPDATE stock_set_components SET quantity=2 WHERE item_id=?', (self.part,))
        self.db.run('UPDATE stock_set_components SET quantity=0 WHERE item_id=?', (self.other,))
        pid = self.project(include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 6)
        self.db.run('UPDATE stock_set_components SET quantity=0')
        self.assertEqual(self.state(pid)['missing'], 8)

    def test_colours_and_black_zero_are_respected_and_can_be_ignored(self):
        self.db.run("UPDATE stock_set_components SET color='0' WHERE item_id=?", (self.part,))
        pid = self.project(include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 6)
        projects.set_ignore_colors(self.db, pid, True)
        self.assertEqual(self.state(pid)['missing'], 0)
        projects.set_ignore_colors(self.db, pid, False)
        self.assertEqual(self.state(pid)['missing'], 6)

    def test_same_reference_in_several_requested_colours_shares_one_set_pool(self):
        pid = projects.create(self.db, 'MOC', [dict(item_id=self.part, color=color, quantity=4) for color in ('1', '4')], ignore_colors=True, include_set_stock=True)
        rows = projects.detail(self.db, pid)
        self.assertEqual((sum(r['set_quantity'] for r in rows), sum(r['missing'] for r in rows)), (6, 2))
        self.assertEqual(self.state(pid)['missing'], 2)
        self.db.add('stock', self.part, '0', 2)
        self.assertEqual(self.state(pid)['missing'], 0)
        self.assertEqual(sum(r['set_quantity'] for r in projects.detail(self.db, pid)), 6)

    def test_vrac_and_sets_add_up_but_only_vrac_is_reservable(self):
        self.db.add('stock', self.part, '4', 2)
        pid = projects.create(self.db, 'MOC', [dict(item_id=self.part, color='4', quantity=8)], include_set_stock=True)
        before = self.db.rows('SELECT * FROM stock_set_components')
        row = projects.detail(self.db, pid)[0]
        self.assertEqual((row['free_quantity'], row['set_quantity'], row['missing'], row['reservable_quantity']), (2, 6, 0, 2))
        projects.reserve(self.db, pid)
        row = projects.detail(self.db, pid)[0]
        self.assertEqual((row['reserved'], row['set_quantity'], row['missing']), (2, 6, 0))
        with self.assertRaises(ValueError):
            projects.reserve(self.db, pid, quantity=8)
        self.assertEqual(before, self.db.rows('SELECT * FROM stock_set_components'))
        self.assertEqual(self.db.rows('SELECT SUM(quantity) AS n FROM stock')[0]['n'], 2)

    def test_other_project_reservations_remove_only_loose_stock(self):
        self.db.add('stock', self.part, '4', 2)
        other = projects.create(self.db, 'Autre', [dict(item_id=self.part, color='4', quantity=2)])
        projects.reserve(self.db, other)
        pid = projects.create(self.db, 'MOC', [dict(item_id=self.part, color='4', quantity=8)], include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 2)
        projects.release(self.db, other)
        self.assertEqual(self.state(pid)['missing'], 0)

    def test_sources_and_alternative_brands_do_not_merge_silently(self):
        pid = projects.create(self.db, 'BL', [dict(item_id=self.bl, color='4', quantity=6)], include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 6)

    def test_add_remove_and_transfer_refresh_without_counting_parts_twice(self):
        pid = self.project(include_set_stock=True)
        self.db.remove('stock_sets', [self.entry], remove_set_parts=True)
        self.assertEqual(self.state(pid)['missing'], 8)
        self.db.undo_last_action()
        self.assertEqual(self.state(pid)['missing'], 0)
        self.db.remove('stock_sets', [self.entry])  # transfer to loose ledger
        self.assertEqual(self.state(pid)['missing'], 0)
        self.assertEqual(sum(r['set_quantity'] for r in projects.detail(self.db, pid)), 0)
        self.assertEqual(sum(r['free_quantity'] for r in projects.detail(self.db, pid)), 8)

    def test_legacy_untracked_set_uses_complete_catalogue_and_warns(self):
        self.db.run('DELETE FROM stock_set_components')
        self.db.run('UPDATE stock_sets SET quantity=2')
        pid = self.project(copies=2, include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 0)
        self.assertTrue(self.state(pid)['set_stock_warnings'])
        self.db.run('DELETE FROM inventory_parts')
        self.assertEqual(self.state(pid)['missing'], 16)
        self.assertIn('indisponible', self.state(pid)['set_stock_warnings'][0])

    def test_minifigures_and_spares_use_the_same_units_as_project_requirements(self):
        fig = self.item('RB', 'minifig', 'fig-1', 'Figurine')
        self.db.run("INSERT INTO inventory_minifigs VALUES(1,'fig-1',1)")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',0,1,1,'')")
        self.db.remove('stock_sets', [self.entry], remove_set_parts=True)
        self.db.add('stock_sets', self.set)
        pid = self.project(spares=True, include_set_stock=True)
        self.assertEqual(self.state(pid)['missing'], 0)
        self.assertEqual(next(r['required'] for r in projects.detail(self.db, pid) if r['id'] == fig), 1)
        self.db.run('DELETE FROM stock_set_components')
        self.assertEqual(self.state(pid)['missing'], 0)

    def test_option_survives_restart_undo_redo_and_old_history(self):
        pid = self.project()
        projects.set_include_set_stock(self.db, pid, True)
        self.db.close(); self.db = Database(self.root / 'atelier.sqlite')
        self.assertTrue(self.state(pid)['include_set_stock'])
        self.db.undo_last_action(); self.assertFalse(self.state(pid)['include_set_stock'])
        self.db.redo_last_action(); self.assertTrue(self.state(pid)['include_set_stock'])
        self.db.undo_last_action()
        row = self.db.rows('SELECT id,payload FROM action_history WHERE applied=1 ORDER BY id DESC LIMIT 1')[0]
        payload = json.loads(row['payload'])
        for change in payload['changes']:
            if change['table'] == 'construction_projects':
                for state in ('before', 'after'):
                    if change[state]: change[state].pop('include_set_stock', None)
        self.db.run('UPDATE action_history SET payload=? WHERE id=?', (json.dumps(payload), row['id']))
        self.db.undo_last_action(); self.db.redo_last_action()
        self.assertFalse(self.state(pid)['include_set_stock'])

    def test_selective_backup_preserves_source_choice_and_legacy_defaults(self):
        pid = self.project(include_set_stock=True)
        files = [preferences_backup.export_family(self.db, family, self.root / (family + '.json')) for family in ('sets', 'projects')]
        target = Database(self.root / 'restored.sqlite')
        try:
            preferences_backup.restore_families(target, files)
            row = projects.list_projects(target)[0]
            self.assertTrue(row['include_set_stock']); self.assertEqual(row['missing'], 0)
            payload = json.loads(files[1].read_text())
            payload['data']['projects'][0].pop('include_set_stock')
            files[1].write_text(json.dumps(payload))
            preferences_backup.restore_families(target, [files[1]])
            self.assertFalse(projects.list_projects(target)[0]['include_set_stock'])
        finally:
            target.close()

    def test_v68_database_migrates_with_vrac_only_and_reservations_intact(self):
        self.db.add('stock', self.part, '4', 3)
        pid = self.project(); projects.reserve(self.db, pid)
        with self.db.connect() as c:
            c.execute('ALTER TABLE construction_projects DROP COLUMN include_set_stock')
        self.db.close(); self.db = Database(self.root / 'atelier.sqlite')
        self.assertFalse(self.state(pid)['include_set_stock'])
        self.assertEqual(self.state(pid)['reserved'], 3)

    def test_invalid_source_choices_do_not_change_projects(self):
        pid = self.project()
        for value in (1, None, 'true'):
            with self.assertRaises(ValueError): projects.set_include_set_stock(self.db, pid, value)
            with self.assertRaises(ValueError): self.project(include_set_stock=value)
        with self.assertRaises(ValueError): projects.set_include_set_stock(self.db, -1, True)
        self.assertEqual(len(projects.list_projects(self.db)), 1)

    def test_comparison_transmits_its_set_stock_choice(self):
        result = work.compare_builds(self.db, [(self.set, 1)], include_set_stock=True)
        ids = work.create_comparison_projects(self.db, result)
        self.assertEqual(len(ids), 1)
        self.assertEqual(self.state(ids[0])['missing'], 0)
        self.assertTrue(self.state(ids[0])['include_set_stock'])


class ProjectSetStockUITests(ProjectSetStockFixture):
    # UI-specific tests share the small representative inventory fixture.
    def panel(self):
        from atelier.projects_panel import ProjectsPanel
        panel = ProjectsPanel(self.db); self.windows.append(panel); return panel

    def test_existing_checkbox_updates_percent_and_keeps_reserve_disabled_for_sets_only(self):
        pid = self.project(); panel = self.panel(); panel.refresh(pid)
        self.assertFalse(panel.include_set_stock.isChecked())
        panel.include_set_stock.setChecked(True)
        self.assertIn('100.0', panel.summary.text())
        self.assertFalse(panel.reserve_button.isEnabled())
        self.assertEqual(sum(int(panel.detail.item(r, 10).text()) for r in range(panel.detail.rowCount())), 8)
        self.assertEqual(sum(int(panel.detail.item(r, 8).text()) for r in range(panel.detail.rowCount())), 0)
        panel.include_set_stock.setChecked(False)
        self.assertNotIn('100.0', panel.summary.text())

    def test_new_project_checkbox_and_build_search_inheritance(self):
        from atelier.build_stock import BuildStockDialog
        panel = self.panel()
        dialog = panel.create_from_item(self.db.get_item(self.set)); self.windows.append(dialog)
        dialog.include_set_stock.setChecked(True); dialog.save()
        self.assertEqual(projects.list_projects(self.db)[0]['missing'], 0)
        search = BuildStockDialog(self.db); self.windows.append(search)
        for include in (False, True):
            search.last_include_sets = include
            dialog = search.create_project(self.db.get_item(self.set)); self.windows.append(dialog)
            self.assertEqual(dialog.include_set_stock.isChecked(), include)
            dialog.reject()

    def test_project_switching_and_no_selection_do_not_write_settings(self):
        a = self.project(include_set_stock=True); b = self.project()
        panel = self.panel(); before = len(self.db.rows('SELECT * FROM action_history'))
        panel.refresh(a); self.assertTrue(panel.include_set_stock.isChecked())
        panel.refresh(b); self.assertFalse(panel.include_set_stock.isChecked())
        self.assertEqual(len(self.db.rows('SELECT * FROM action_history')), before)
        projects.delete(self.db, a); projects.delete(self.db, b); panel.refresh()
        self.assertFalse(panel.include_set_stock.isEnabled())
