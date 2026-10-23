"""Cross-workflow conservation, exclusive set claims and recoverable user data."""
from pathlib import Path
import http.cookiejar,json,tempfile,urllib.request,urllib.error

from test_storage_and_inventory_batches import Fixture,app
from atelier import projects,storage_wall as walls,storage_assignment as assignment,storage_shapes,storage_capacity
from atelier import set_allocations,project_shopping as shopping,moc_import,lot_analysis,automatic_backups


class CollectionFixture(Fixture):
    def inventory(self,ref='90001-1',quantity=6,copies=1):
        identity=self.item('set',ref,ref);iid=self.db.run('INSERT INTO inventories(version,set_num) VALUES(1,?)',(ref,))
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,0,?)',(iid,'3005',4,quantity,''))
        if copies:self.db.add('stock_sets',identity,quantity=copies)
        rows=self.db.rows('SELECT id FROM stock_sets WHERE item_id=?',(identity,));return identity,rows[0]['id'] if rows else None
    def project(self,name='MOC',quantity=6,**options):return projects.create(self.db,name,[dict(item_id=self.part,color='4',quantity=quantity)],**options)


class ShapeTests(CollectionFixture):
    def seed(self):
        for ref,name in [('3004','Brick 1 x 2'),('3622','Brick 1 x 3'),('3010','Brick 1 x 4'),('3003','Brick 2 x 2'),('3002','Brick 2 x 3')]:
            i=self.item('part',ref,name);self.db.add('stock',i,'4',1)
        self.db.run("UPDATE items SET category='Bricks'");return walls.create_wall(self.db,'Bricks',10,3)
    def test_3010_follows_1_by_n_before_square_3003(self):
        wall=self.seed();plan=assignment.propose(self.db,wall,criteria=['category','shape','size','reference'])
        self.assertEqual([g['references'][0].split()[-1] for g in plan['groups']],['3005','3004','3622','3010','3003','3002','3001'])
        self.assertNotEqual(plan['groups'][3]['shape'],plan['groups'][4]['shape']);self.assertEqual(self.db.get_item(self.part)['category'],'Bricks')
    def test_shape_is_optional_without_changing_previous_surface_sort(self):
        wall=self.seed();plan=assignment.propose(self.db,wall,criteria=['category','size','reference']);self.assertTrue(all(g['shape']=='' for g in plan['groups']))
    def test_override_is_undoable_and_invalidates_unreviewed_proposal(self):
        wall=self.seed();plan=assignment.propose(self.db,wall,criteria=['shape','reference']);storage_shapes.set_family(self.db,[self.part],'Petites briques')
        with self.assertRaises(ValueError):assignment.apply_proposal(self.db,plan)
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT * FROM storage_shape_overrides'),[])
        self.db.redo_last_action();self.assertEqual(self.db.rows('SELECT family FROM storage_shape_overrides')[0]['family'],'Petites briques')
        storage_shapes.set_family(self.db,[self.part]);self.assertEqual(self.db.rows('SELECT * FROM storage_shape_overrides'),[])
    def test_table_and_preview_retain_the_family(self):
        from atelier.storage_tools import StoragePlanDialog
        window=self.keep(StoragePlanDialog(self.db,self.seed()));self.assertTrue(window.criteria['shape'].isChecked());self.assertEqual(window.table.columnCount(),9)
        self.assertTrue(any(window.table.item(r,8).text() for r in range(window.table.rowCount())))


class SetAllocationTests(CollectionFixture):
    def test_each_copy_can_cover_only_one_project(self):
        self.db.run('UPDATE stock SET quantity=0');_,entry=self.inventory(copies=2);a=self.project('A');b=self.project('B',include_set_stock=True)
        set_allocations.assign(self.db,a,{entry:1});self.assertEqual(projects.detail(self.db,a)[0]['missing'],0);self.assertEqual(projects.detail(self.db,b)[0]['missing'],0)
        set_allocations.assign(self.db,b,{entry:1});c=self.project('C',include_set_stock=True);self.assertEqual(projects.detail(self.db,c)[0]['missing'],6)
        with self.assertRaises(ValueError):set_allocations.assign(self.db,c,{entry:1})
        from atelier.build_stock import InventoryReader
        with self.db.read() as connection:self.assertEqual(sum(InventoryReader(connection).stock().values()),0)
    def test_project_deletion_releases_claim_without_transferring_stock_and_undo_restores(self):
        _,entry=self.inventory();pid=self.project();set_allocations.assign(self.db,pid,{entry:1});before=self.db.rows('SELECT * FROM stock_set_components')
        projects.delete(self.db,pid);self.assertEqual(self.db.rows('SELECT * FROM project_set_allocations'),[]);self.assertEqual(self.db.rows('SELECT * FROM stock_set_components'),before)
        self.db.undo_last_action();self.assertEqual(len(self.db.rows('SELECT * FROM project_set_allocations')),1)
    def test_disabling_set_source_releases_claim_and_can_be_undone(self):
        _,entry=self.inventory();pid=self.project();set_allocations.assign(self.db,pid,{entry:1});projects.set_include_set_stock(self.db,pid,False)
        self.assertEqual(self.db.rows('SELECT * FROM project_set_allocations'),[]);self.db.undo_last_action();self.assertEqual(len(self.db.rows('SELECT * FROM project_set_allocations')),1)
    def test_nondivisible_shared_inventory_requires_whole_group(self):
        _,entry=self.inventory(copies=2);self.db.run('UPDATE stock_set_components SET quantity=11');pid=self.project()
        with self.assertRaises(ValueError):set_allocations.assign(self.db,pid,{entry:1})
        set_allocations.assign(self.db,pid,{entry:2});self.assertEqual(self.db.rows('SELECT copies FROM project_set_allocations')[0]['copies'],2)
    def test_clear_sets_and_undo_include_exclusive_claims(self):
        from atelier.stock_clear import clear
        _,entry=self.inventory();pid=self.project();set_allocations.assign(self.db,pid,{entry:1});clear(self.db,'stock_sets');self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
        self.db.undo_last_action();self.assertEqual(len(self.db.rows('SELECT * FROM project_set_allocations')),1)
    def test_legacy_fallback_is_claimed_without_rewriting_ownership(self):
        self.db.run('UPDATE stock SET quantity=0');_,entry=self.inventory();self.db.run('DELETE FROM stock_set_components');pid=self.project();set_allocations.assign(self.db,pid,{entry:1})
        self.assertEqual(projects.detail(self.db,pid)[0]['missing'],0);self.assertEqual(self.db.rows('SELECT * FROM stock_set_components'),[])
        from atelier.build_stock import InventoryReader
        with self.db.read() as connection:self.assertEqual(sum(InventoryReader(connection).stock().values()),0)
    def test_removing_assigned_set_is_rejected_atomically(self):
        import sqlite3
        from atelier.stock import mutate
        _,entry=self.inventory();pid=self.project();set_allocations.assign(self.db,pid,{entry:1});before=self.db.rows('SELECT * FROM stock_sets')
        with self.assertRaises((ValueError,sqlite3.IntegrityError)):mutate(self.db,[dict(op='remove',scope='stock_sets',ids=[entry])],'Test')
        self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),before)


class ShoppingTests(CollectionFixture):
    def test_joint_shortages_do_not_reuse_free_units_or_reservations(self):
        a=self.project('A',30);b=self.project('B',30);identity=shopping.create(self.db,'Achats',[a,b]);self.assertEqual(shopping.rows(self.db,identity)[0]['missing'],20)
        projects.reserve(self.db,b,[(self.part,'4')],10);shopping.recalculate(self.db,identity);self.assertEqual(shopping.rows(self.db,identity)[0]['missing'],20)
    def test_only_owner_project_can_use_assigned_set_parts(self):
        self.db.run('UPDATE stock SET quantity=0');_,entry=self.inventory();a=self.project('A');b=self.project('B',include_set_stock=True);set_allocations.assign(self.db,a,{entry:1})
        identity=shopping.create(self.db,'Achats',[b,a]);self.assertEqual(shopping.rows(self.db,identity)[0]['missing'],6)
    def test_receipt_is_idempotent_undoable_and_recalculation_keeps_orders(self):
        pid=self.project(quantity=45);identity=shopping.create(self.db,'Achats',[pid]);shopping.set_ordered(self.db,identity,self.part,'4',5)
        for _ in range(2):shopping.receive(self.db,identity,self.part,'4',3,expected_received=0,receipt_id='receipt-1')
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],43);self.assertEqual(len(self.db.rows('SELECT * FROM shopping_receipts')),1)
        self.db.undo_last_action();self.assertEqual(shopping.rows(self.db,identity)[0]['received'],0);self.db.redo_last_action();shopping.recalculate(self.db,identity);row=shopping.rows(self.db,identity)[0]
        self.assertEqual((row['target'],row['received'],row['missing'],row['to_order']),(5,3,2,0))
    def test_stale_receipt_cannot_add_stock_twice(self):
        identity=shopping.create(self.db,'Achats',[self.project(quantity=45)]);shopping.receive(self.db,identity,self.part,'4',2,expected_received=0)
        with self.assertRaises(ValueError):shopping.receive(self.db,identity,self.part,'4',2,expected_received=0)
        self.assertEqual(shopping.rows(self.db,identity)[0]['received'],2)
    def test_wanted_xml_requires_verified_mappings_and_no_xml_declaration(self):
        identity=shopping.create(self.db,'Achats',[self.project(quantity=45)]);path=Path(self.temp.name)/'wanted.xml'
        with self.assertRaises(ValueError):shopping.wanted_xml(self.db,identity,path)
        self.assertFalse(path.exists());shopping.set_mapping(self.db,identity,self.part,'4','3005','5');shopping.wanted_xml(self.db,identity,path);self.assertTrue(path.read_text().startswith('<INVENTORY>'))
        import xml.etree.ElementTree as ET
        root=ET.parse(path).getroot();self.assertEqual(root.findtext('ITEM/ITEMID'),'3005');self.assertEqual(root.findtext('ITEM/COLOR'),'5');self.assertEqual(root.findtext('ITEM/MINQTY'),'5')
    def test_ignored_colour_receipt_requires_actual_colour(self):
        identity=shopping.create(self.db,'Achats',[self.project(quantity=45,ignore_colors=True)])
        with self.assertRaises(ValueError):shopping.receive(self.db,identity,self.part,'*',1)
        shopping.receive(self.db,identity,self.part,'*',5,actual_color='4');shopping.recalculate(self.db,identity);self.assertEqual(shopping.rows(self.db,identity)[0]['missing'],0)


class MOCAndLotTests(CollectionFixture):
    def test_moc_csv_records_requirements_without_ownership_changes(self):
        path=Path(self.temp.name)/'moc.csv';path.write_text('part_num,color_id,quantity\n3005,4,45\n3005,4,2\n');before=self.db.rows('SELECT * FROM stock');pid=moc_import.create_project(self.db,'MOC',moc_import.preview(self.db,path))
        self.assertEqual(projects.detail(self.db,pid)[0]['required'],47);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
    def test_invalid_moc_cannot_create_partial_project(self):
        path=Path(self.temp.name)/'moc.csv';path.write_text('part_num,color_id,quantity\n3005,4,4\nunknown,4,2\n')
        with self.assertRaises(ValueError):moc_import.create_project(self.db,'MOC',moc_import.preview(self.db,path))
        self.assertEqual(projects.list_projects(self.db),[])
    def test_xml_moc_and_entity_rejection(self):
        self.item('part','bl3005','Brick','BL');path=Path(self.temp.name)/'moc.xml';path.write_text('<INVENTORY><ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>bl3005</ITEMID><COLOR>5</COLOR><MINQTY>3</MINQTY></ITEM></INVENTORY>')
        rows=moc_import.preview(self.db,path);self.assertFalse(rows[0]['issue']);moc_import.create_project(self.db,'XML',rows);path.write_text('<!DOCTYPE x [<!ENTITY x "test">]><INVENTORY/>')
        with self.assertRaises(ValueError):moc_import.preview(self.db,path)
    def test_lot_combination_spends_each_unit_once_and_stale_results_are_rejected(self):
        from atelier.collection_workflows import create_lot,add_to_lot
        self.inventory('90001-1',6,copies=0);self.inventory('90002-1',5,copies=0);identity=create_lot(self.db,'Vrac');add_to_lot(self.db,identity,self.part,'4',11);before=self.db.rows('SELECT * FROM stock')
        result=lot_analysis.analyze(self.db,identity,minimum=80,max_sets=4);self.assertTrue(result['suggestions']);self.assertEqual(sum(result['available'].values()),11)
        self.assertEqual(sum(result['remaining'].values())+sum(r['allocated'] for r in result['choices']),11);lot_analysis.create_projects(self.db,result);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
        self.db.add('stock',self.part,'4',1)
        with self.assertRaises(ValueError):lot_analysis.create_projects(self.db,result)


class CapacityTests(CollectionFixture):
    def test_capacity_creates_enough_neighbouring_drawers_without_extra_ownership(self):
        wall=walls.create_wall(self.db,'A',5,2);storage_capacity.save(self.db,wall,'Small',[(self.part,1,1,15)]);plan=assignment.propose(self.db,wall,entries=[(self.part,'4')],allocate_quantities=True,use_capacities=True)
        self.assertEqual([sum(g['quantities'].values()) for g in plan['groups']],[15,15,10]);assignment.apply_proposal(self.db,plan);self.assertEqual(sum(r['quantity'] for r in self.db.rows('SELECT * FROM storage_contents')),40)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
    def test_unknown_capacity_and_overfilled_manual_targets_are_rejected(self):
        a=walls.create_wall(self.db,'A',2,1);b=walls.create_wall(self.db,'B',2,1);storage_capacity.save(self.db,a,'Large',[(self.part,1,1,40)]);storage_capacity.save(self.db,b,'Small',[(self.part,1,1,10)])
        plan=assignment.propose(self.db,None,entries=[(self.part,'4')],allocate_quantities=True,use_capacities=True)
        with self.assertRaises(ValueError):assignment.validate_targets(plan,[walls.drawers(self.db,b)[0]['id']])
        with self.assertRaises(ValueError):assignment.propose(self.db,None,allocate_quantities=True,use_capacities=True)
    def test_duplicate_retains_format_and_capacity_edits_invalidate_plan(self):
        wall=walls.create_wall(self.db,'A',5,1);storage_capacity.save(self.db,wall,'Small',[(self.part,1,1,15)]);walls.duplicate_wall(self.db,wall,'B');self.assertEqual(len(self.db.rows('SELECT * FROM storage_wall_formats')),2)
        plan=assignment.propose(self.db,wall,entries=[(self.part,'4')],allocate_quantities=True,use_capacities=True);storage_capacity.save(self.db,wall,'Small',[(self.part,1,1,10)])
        with self.assertRaises(ValueError):assignment.apply_proposal(self.db,plan)
    def test_portable_storage_restores_family_and_capacities_with_mapped_ids(self):
        from atelier.preferences_backup import export_family,restore_families
        from atelier.data import Database
        wall=walls.create_wall(self.db,'A',5,1);storage_capacity.save(self.db,wall,'Small',[(self.part,1,1,15)]);storage_shapes.set_family(self.db,[self.part],'Barres');path=Path(self.temp.name)/'storage.json';export_family(self.db,'storage',path)
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'other.sqlite')
            try:
                db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','dummy','Other','other')");restore_families(db,[path]);row=db.rows('SELECT i.ref,o.family FROM storage_shape_overrides o JOIN items i ON i.id=o.item_id')[0]
                self.assertEqual((row['ref'],row['family']),('3005','Barres'));self.assertEqual(db.rows('SELECT capacity FROM storage_capacities')[0]['capacity'],15)
            finally:db.close()
    def test_portable_projects_restore_claims_using_owned_set_identity(self):
        from atelier.preferences_backup import export_family,restore_families
        from atelier.data import Database
        self.db.run('UPDATE stock SET quantity=0');_,entry=self.inventory();pid=self.project();set_allocations.assign(self.db,pid,{entry:1});paths=[]
        for family in ('sets','projects'):
            path=Path(self.temp.name)/(family+'.json');export_family(self.db,family,path);paths.append(path)
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'other.sqlite')
            try:
                db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','dummy','Other','other')");restore_families(db,paths);self.assertEqual(projects.list_projects(db)[0]['missing'],0);self.assertEqual(len(db.rows('SELECT * FROM project_set_allocations')),1)
            finally:db.close()


class MobileAndBackupTests(CollectionFixture):
    def test_mobile_auth_search_drawers_and_read_only_routes(self):
        from atelier.mobile_access import MobileAccess
        wall=walls.create_wall(self.db,'A',2,1);drawer=walls.drawers(self.db,wall)[0];walls.assign(self.db,drawer['id'],[(self.part,'4')]);service=MobileAccess(self.db)
        try:
            url=service.start('127.0.0.1')[0];client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with self.assertRaises(urllib.error.HTTPError) as error:client.open(url+'/api/search?q=3005')
            self.assertEqual(error.exception.code,401);client.open(urllib.request.Request(url+'/login',data=json.dumps({'code':service.code}).encode(),headers={'Content-Type':'application/json'})).close()
            result=json.load(client.open(url+'/api/search?q=3005'));self.assertEqual(result['rows'][0]['quantity'],40);self.assertIsNone(result['rows'][0]['drawers'][0]['quantity'])
            self.assertEqual(len(json.load(client.open(url+'/api/drawers?wall='+str(wall)))),2);self.assertEqual(json.load(client.open(url+'/api/drawer?id='+str(drawer['id'])))['parts'][0]['ref'],'3005')
            with self.assertRaises(urllib.error.HTTPError) as error:client.open(urllib.request.Request(url+'/stock',data=b'{}'))
            self.assertEqual(error.exception.code,405)
        finally:service.stop()
        self.assertFalse(service.sessions);self.assertIsNone(service.server)
    def test_backup_retention_never_deletes_unrelated_archives(self):
        with tempfile.TemporaryDirectory() as folder:
            automatic_backups.configure(self.db,dict(enabled=True,hours=24,retention=2,before_changes=True,destination=folder));path=Path(folder)/'private.zip';path.write_bytes(b'keep')
            for _ in range(3):automatic_backups.run(self.db,force=True)
            self.assertEqual(len(list(Path(folder).glob('BrickLabo_auto_*.zip'))),2);self.assertEqual(path.read_bytes(),b'keep')
            from atelier.backups import validate_archive
            for archive in Path(folder).glob('BrickLabo_auto_*.zip'):validate_archive(archive)
    def test_checkpoint_precedes_clear_and_contains_original_quantities(self):
        from atelier.stock_clear import clear
        import zipfile,sqlite3
        with tempfile.TemporaryDirectory() as folder:
            automatic_backups.configure(self.db,dict(enabled=True,hours=24,retention=2,before_changes=True,destination=folder));clear(self.db,'stock');path=Path(self.db.setting('automatic_backup_status')['path'])
            with zipfile.ZipFile(path) as z:z.extract('Donnees/atelier.sqlite',folder)
            with sqlite3.connect(Path(folder)/'Donnees/atelier.sqlite') as c:self.assertEqual(c.execute('SELECT SUM(quantity) FROM stock').fetchone()[0],52)
    def test_dashboard_does_not_add_location_counts_to_ownership(self):
        from atelier.collection_dashboard import snapshot
        wall=walls.create_wall(self.db,'A',2,1);walls.assign(self.db,walls.drawers(self.db,wall)[0]['id'],[(self.part,'4')]);result=snapshot(self.db)['metrics']
        self.assertEqual((result['loose_units'],result['unknown_locations'],result['remaining_to_store']),(52,1,52))
    def test_dashboard_counts_saved_bricklink_inventories(self):
        from atelier.collection_dashboard import snapshot
        self.item('set','100','Set','BL');self.item('set','101','Set','BL')
        self.db.run("INSERT INTO catalogue_inventory(source,ref,parts,parts_without_minifigs) VALUES('BL','100','[]','[]')")
        self.db.set_setting('bl_components_101',[dict(source='BL',kind='part',ref='3005',chosen_color='5',chosen_quantity=1)])
        row=next(r for r in snapshot(self.db)['sources'] if r['source']=='BL')
        self.assertEqual((row['sets'],row['inventories_present'],row['without_local_inventory']),(2,2,0))


class ExtensionWindowTests(CollectionFixture):
    def test_new_workflow_windows_and_editors_open_with_real_data(self):
        from atelier.collection_extensions_ui import SetAllocationDialog,MOCImportDialog,LotAnalysisDialog,ShoppingDialog
        from atelier.storage_tools import StoragePlanDialog
        from atelier.collection_dashboard import panel
        from atelier.collection_workflows import create_lot
        self.inventory();pid=self.project();create_lot(self.db,'Vrac');wall=walls.create_wall(self.db,'A',5,3)
        for window in (SetAllocationDialog(self.db,pid),MOCImportDialog(self.db),LotAnalysisDialog(self.db),ShoppingDialog(self.db)):
            self.keep(window);window.show();app.processEvents();self.assertTrue(window.isVisible())
        plan=self.keep(StoragePlanDialog(self.db,wall));plan.show();plan.edit_families();plan.edit_capacities();app.processEvents()
        for child in list(getattr(plan,'_consultation_windows',[])):child.close()
        board=self.keep(panel(self.db));board.show();board.refresh();app.processEvents()
