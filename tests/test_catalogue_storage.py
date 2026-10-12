"""Catalogue-only drawer links never fabricate ownership or stock quantities."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from atelier import storage_wall as walls
from atelier import storage_assignment as assignment
from atelier.storage_panel import StoragePanel
from atelier.storage_tools import CatalogueToDrawerDialog,StoragePlanDialog,MIME,read_drag
from atelier.catalogue import Catalogue
from atelier.data import Database
from atelier.preferences_backup import export_family,restore_families
from atelier.result_tables import row_index
from test_storage_and_inventory_batches import Fixture,app
import test_storage_assignment as placement_fixtures


class CatalogueStorageTests(Fixture):
    def setUp(self):
        super().setUp();self.wall=walls.create_wall(self.db,'Rangement',3,2);self.drawers=walls.drawers(self.db,self.wall)
        self.unowned=self.item('part','3004','Brick 1 x 2');self.figure=self.item('minifig','fig-001','Mini-fig')
        self.same_bl=self.item('part','3004','Brick 1 x 2','BL');self.variant=self.item('part','3004pat0001','Brick 1 x 2 with Pattern')
        self.hidden=self.item('part','retired','Brick 1 x 3','ALT');self.set=self.item('set','123-1','Set')
        self.db.run("UPDATE items SET category='Bricks' WHERE kind='part'");self.db.run('UPDATE items SET catalogue_hidden=1 WHERE id=?',(self.hidden,))
    def quantities(self):return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','stock_undo','stock_revision','queue','history')}
    def test_all_catalogues_include_unowned_variants_and_minifigs_but_not_sets_or_hidden_refs(self):
        found=assignment.catalogue_rows(self.db);ids={p['id'] for p in found}
        self.assertTrue({self.unowned,self.figure,self.same_bl,self.variant}.issubset(ids));self.assertNotIn(self.set,ids);self.assertNotIn(self.hidden,ids)
        self.assertEqual({p['chosen_color'] for p in found},{''});self.assertTrue(all('chosen_quantity' not in p for p in found))
        self.assertEqual([p['id'] for p in assignment.catalogue_rows(self.db,source='BL')],[self.same_bl])
        self.assertEqual([p['id'] for p in assignment.catalogue_rows(self.db,kind='minifig')],[self.figure])
        self.assertIn(self.unowned,{p['id'] for p in assignment.catalogue_rows(self.db,query='1x2',category='Bricks')})
    def test_catalogue_placement_is_atomic_colour_unspecified_and_stock_stays_exactly_the_same(self):
        before=self.quantities();entries=[(self.unowned,''),(self.same_bl,''),(self.variant,''),(self.figure,'')]
        assignment.place_entries(self.db,self.drawers[0]['id'],entries,from_catalogue=True)
        self.assertEqual(self.quantities(),before);self.assertEqual({p['id'] for p in walls.contents(self.db,self.drawers[0]['id'])},{p[0] for p in entries})
        self.assertEqual({p['chosen_quantity'] for p in walls.contents(self.db,self.drawers[0]['id'])},{0})
        self.assertEqual(len(walls.search(self.db,'3004')),3)
    def test_stock_mode_still_requires_actual_owned_stock(self):
        before=walls.print_snapshot(self.db)
        with self.assertRaises(ValueError):assignment.place_entries(self.db,self.drawers[0]['id'],[(self.unowned,'')])
        self.assertEqual(walls.print_snapshot(self.db),before)
        assignment.place_entries(self.db,self.drawers[0]['id'],[(self.part,'4')]);self.assertEqual(walls.contents(self.db,self.drawers[0]['id'])[0]['chosen_color'],'4')
    def test_unspecified_colour_reports_actual_total_stock_and_specific_colour_stays_separate(self):
        self.db.add('stock',self.part,'1',8);before=self.quantities()
        assignment.place_entries(self.db,self.drawers[0]['id'],[(self.part,'')],from_catalogue=True)
        assignment.place_entries(self.db,self.drawers[1]['id'],[(self.part,'4')])
        self.assertEqual(walls.contents(self.db,self.drawers[0]['id'])[0]['chosen_quantity'],48)
        self.assertEqual(walls.contents(self.db,self.drawers[1]['id'])[0]['chosen_quantity'],40)
        self.assertEqual({p['color']:p['stock_quantity'] for p in walls.search(self.db,'3005')},{'':48,'4':40})
        self.assertEqual(walls.print_snapshot(self.db)['parts'][0]['chosen_quantity'],48);self.assertEqual(self.quantities(),before)
    def test_deleted_hidden_wrong_kind_or_invalid_mode_rejects_without_partial_links(self):
        for identity in (self.hidden,self.set,99999):
            before=walls.print_snapshot(self.db)
            with self.assertRaises(ValueError):assignment.place_entries(self.db,self.drawers[0]['id'],[(self.unowned,''),(identity,'')],from_catalogue=True)
            self.assertEqual(walls.print_snapshot(self.db),before)
        for options,entries in [({'from_catalogue':'yes'},[(self.unowned,'')]),({'from_catalogue':True},[(self.unowned,'4')]),({'from_catalogue':True,'source_drawer':self.drawers[1]['id']},[(self.unowned,'')])]:
            with self.assertRaises(ValueError):assignment.place_entries(self.db,self.drawers[0]['id'],entries,**options)
    def test_duplicate_and_move_of_unowned_catalogue_refs_preserve_other_locations(self):
        before=self.quantities()
        for drawer in self.drawers[:2]:assignment.place_entries(self.db,drawer['id'],[(self.unowned,'')],from_catalogue=True)
        assignment.place_entries(self.db,self.drawers[0]['id'],[(self.unowned,'')],from_catalogue=True)
        self.assertEqual(len(walls.contents(self.db,self.drawers[0]['id'])),1)
        assignment.place_entries(self.db,self.drawers[2]['id'],[(self.unowned,'')],source_drawer=self.drawers[0]['id'])
        self.assertEqual(walls.contents(self.db,self.drawers[0]['id']),[]);self.assertEqual(len(walls.contents(self.db,self.drawers[1]['id'])),1);self.assertEqual(len(walls.contents(self.db,self.drawers[2]['id'])),1);self.assertEqual(self.quantities(),before)
    def test_failed_catalogue_insert_rolls_back_whole_batch(self):
        before=walls.print_snapshot(self.db)
        self.db.run('CREATE TRIGGER reject_catalogue BEFORE INSERT ON storage_contents WHEN NEW.item_id='+str(self.variant)+" BEGIN SELECT RAISE(ABORT,'write refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):assignment.place_entries(self.db,self.drawers[0]['id'],[(self.unowned,''),(self.variant,'')],from_catalogue=True)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_storage_backup_restores_catalogue_only_refs_without_adding_stock(self):
        assignment.place_entries(self.db,self.drawers[0]['id'],[(self.unowned,''),(self.same_bl,'')],from_catalogue=True)
        path=Path(self.temp.name)/'storage.json';export_family(self.db,'storage',path);other=Database(Path(self.temp.name)/'other.sqlite')
        try:
            restore_families(other,[path]);self.assertEqual(other.rows('SELECT * FROM stock'),[])
            found=walls.search(other,'3004');self.assertEqual({p['source'] for p in found},{'RB','BL'});self.assertEqual({p['stock_quantity'] for p in found},{0})
        finally:other.close()
    def test_existing_catalogue_only_category_can_be_reorganised_with_no_stock(self):
        self.db.run('DELETE FROM stock');assignment.place_entries(self.db,self.drawers[-1]['id'],[(self.unowned,'')],from_catalogue=True)
        window=self.keep(StoragePlanDialog(self.db,self.wall));index=window.category.findData('Bricks');self.assertGreater(index,0)
        window.category.setCurrentIndex(index);window.reorganize.setChecked(True);self.assertEqual(window.plan['groups'][0]['entries'],[(self.unowned,'')])
        with patch('atelier.storage_tools.QMessageBox.information'):window.apply()
        self.assertEqual(self.db.rows('SELECT * FROM stock'),[]);self.assertEqual(len(walls.search(self.db,'3004')),1)
    def test_direct_catalogue_button_captures_multiselection_and_prompts_for_no_quantity(self):
        catalogue=self.keep(Catalogue(self.db,'RB','part'));catalogue.ids={self.unowned,self.variant};before=self.quantities()
        with patch('atelier.catalogue.QInputDialog.getInt',side_effect=AssertionError('asked for quantity')):catalogue.drawer_button.click()
        window=self.keep(catalogue._consultation_windows[-1]);self.assertIsInstance(window,CatalogueToDrawerDialog);self.assertFalse(window.isModal());self.assertEqual({p['id'] for p in window.items},{self.unowned,self.variant})
        window.drawer.setCurrentIndex(window.drawer.findData(self.drawers[2]['id']));window.apply()
        self.assertEqual(self.quantities(),before);self.assertEqual({p['id'] for p in walls.contents(self.db,self.drawers[2]['id'])},{self.unowned,self.variant})
    def test_cancel_and_deleted_destination_do_not_create_stock_or_change_any_links(self):
        before=self.quantities();window=self.keep(CatalogueToDrawerDialog(self.db,[self.db.get_item(self.unowned)]));window.reject();self.assertEqual(self.quantities(),before);self.assertEqual(walls.wall_contents(self.db,self.wall),[])
        window=self.keep(CatalogueToDrawerDialog(self.db,[self.db.get_item(self.unowned)]));walls.delete_wall(self.db,self.wall)
        with patch('atelier.storage_tools.QMessageBox.warning') as warning:window.apply();warning.assert_called_once()
        self.assertEqual(self.quantities(),before);self.assertEqual(self.db.rows('SELECT * FROM storage_contents'),[])
    def test_no_cabinet_stays_usable_and_refresh_finds_new_cabinet(self):
        walls.delete_wall(self.db,self.wall);window=self.keep(CatalogueToDrawerDialog(self.db,[self.db.get_item(self.unowned)]));self.assertFalse(window.apply_button.isEnabled())
        wall=walls.create_wall(self.db,'Nouveau',1,1);window.reload_walls();self.assertTrue(window.apply_button.isEnabled());window.apply();self.assertEqual(walls.wall_contents(self.db,wall)[0]['id'],self.unowned)


class CatalogueDropTests(Fixture):
    def test_native_drop_from_catalogue_not_owned_creates_only_location(self):
        unowned=self.item('part','3004','Brick 1 x 2');wall=walls.create_wall(self.db,'Meuble',3,2);drawer=walls.drawers(self.db,wall)[1]
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1100,950);panel.show();panel.pick_catalogue();panel.front.setChecked(True);panel.fit();app.processEvents()
        browser=panel.stock_browser;browser.table.sortItems(1,Qt.SortOrder.DescendingOrder);before=self.db.rows('SELECT * FROM stock')
        row=next(row for row in range(browser.table.rowCount()) if browser.rows[row_index(browser.table,row)]['id']==unowned);browser.table.selectRow(row)
        mime=browser.table.mimeData(browser.table.selectedItems());self.assertTrue(read_drag(mime,self.db)['catalogue']);self.assertTrue(browser.table.isColumnHidden(5))
        event=placement_fixtures.PieceDropTests.drop(self,panel,mime,drawer)
        self.assertTrue(event.isAccepted());self.assertEqual(walls.contents(self.db,drawer['id'])[0]['id'],unowned);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
        self.assertNotIn(unowned,{p['id'] for p in browser.rows});browser.unlocated.setChecked(False);browser.reload();self.assertIn(unowned,{p['id'] for p in browser.rows})
        browser.origin.setCurrentIndex(browser.origin.findData('stock'));self.assertFalse(browser.table.isColumnHidden(5));self.assertNotIn(unowned,{p['id'] for p in browser.rows})
    def test_source_and_type_choices_filter_exact_local_catalogues(self):
        rb=self.item('part','same','Brick 1 x 2');bl=self.item('part','same','Brick 1 x 2','BL');ba=self.item('part','architect','Brick 1 x 2','BA');alt=self.item('part','other','Brick 1 x 2','ALT');fig=self.item('minifig','fig-001','Figure')
        panel=self.keep(StoragePanel(self.db,None));browser=panel.stock_browser
        for source,expected in [('BL',{bl}),('BA',{ba}),('ALT',{alt}),('minifig',{fig})]:
            browser.origin.setCurrentIndex(browser.origin.findData(source));self.assertEqual({p['id'] for p in browser.rows},expected)
        browser.origin.setCurrentIndex(browser.origin.findData('RB'));self.assertIn(rb,{p['id'] for p in browser.rows});self.assertNotIn(bl,{p['id'] for p in browser.rows})
    def test_catalogue_mime_cannot_mix_move_origin_or_fabricated_colour(self):
        panel=self.keep(StoragePanel(self.db,None));browser=panel.stock_browser;browser.origin.setCurrentIndex(browser.origin.findData('catalogue'));browser.table.selectRow(0)
        mime=browser.table.mimeData(browser.table.selectedItems());data=json.loads(bytes(mime.data(MIME)))
        for invalid in ({'catalogue':'yes'},{'origin':1},{'entries':[[self.part,'4']]}):
            mime.setData(MIME,json.dumps(dict(data,**invalid)).encode());self.assertIsNone(read_drag(mime,self.db))
