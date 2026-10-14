"""User workflows: real CSV headers, versioned stock, projects and drawer edits."""
import csv
import json
import threading
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QPointF,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog,QMessageBox
from shiboken6 import isValid
from test_storage_and_inventory_batches import Fixture,app
from atelier import projects,storage_wall as walls,inventory_batches as batches,stock_import_jobs as imports
from atelier.stock_import import read_list,import_rows,resolve_rows
from atelier.build_stock import find_builds,build_details,BuildStockDialog,export_build_parts
from atelier.drawer_inventory import DrawerInventoryDialog,drawer_tooltip,color_names
from atelier.storage_quantities import put_entry
from atelier.set_picker import SetPicker,SetImagePreview
from atelier.projects_panel import ProjectsPanel,NewProjectDialog
from atelier.preview import Preview
from atelier.catalogue import Catalogue
from atelier.result_tables import fill_table,row_index
from atelier.label_models import set_kind_model,set_category_model
from atelier.labels import template_for_item,preset_template,individual_template_key
from atelier.editor import LabelEditor
from atelier.preferences_backup import export_family,restore_families,collect_family
from atelier.task_lifetime import drain_tasks


class WorkflowFixture(Fixture):
    def tearDown(self):
        for window in reversed(self.windows):
            if isValid(window):window.close();window.deleteLater()
        self.assertTrue(QThreadPool.globalInstance().waitForDone(5000));drain_tasks()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents();self.windows.clear()
        self.db.close();self.temp.cleanup()

    def inventory(self,ref,amount=5,version=1,part='3005'):
        iid=self.db.rows('SELECT COALESCE(MAX(id),0)+1 AS id FROM inventories')[0]['id']
        self.db.run('INSERT INTO inventories VALUES(?,?,?)',(iid,version,ref));self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(iid,part,4,amount,0,''));return iid

    def set_with_figure(self):
        item=self.db.get_item(self.item('set','100-1','Demo set'));iid=self.inventory(item['ref'])
        self.db.run('INSERT INTO inventory_minifigs VALUES(?,?,?)',(iid,'fig-test',1));return item

    def cache_part(self,quantity,source='RB',kind='part',ref='3005'):
        return {'source':source,'kind':kind,'ref':ref,'name':'Brick','color':'4','quantity':quantity}

    def csv(self,text):
        path=Path(self.temp.name)/'collection.csv';path.write_text(text,encoding='utf-8-sig');return path

    def drawer(self):
        wall=walls.create_wall(self.db,'Atelier',2,2);drawer=walls.drawers(self.db,wall)[0]
        walls.assign(self.db,drawer['id'],[(self.part,'4')]);return drawer


class RebrickableCSVTests(WorkflowFixture):
    def test_database_import_window_routes_collection_to_review_without_changing_stock(self):
        from atelier.dialogs import ImportDialog
        path=self.csv('Set Number,Quantity,Inventory Ver\n100-1,4,1\n');self.item('set','100-1');self.inventory('100-1')
        before=self.db.rows('SELECT * FROM stock');window=self.keep(ImportDialog(self.db,None,[str(path)]));window.start()
        review=window._consultation_windows[0];self.keep(review);self.assertEqual(review.destination.currentData(),'stock_sets');self.assertTrue(review.commit.isEnabled());self.assertEqual(len(review.rows),1)
        self.assertEqual(self.db.rows('SELECT * FROM stock'),before);self.assertEqual(window.paths,[])

    def test_catalogue_csvs_are_not_mistaken_for_collections(self):
        from atelier.stock_import import list_kind
        for text in ('set_num,name,year,theme_id\n100-1,Demo,2020,1\n','inventory_id,set_num,quantity\n1,100-1,2\n','inventory_id,part_num,color_id,quantity\n1,3005,4,2\n'):
            self.assertIsNone(list_kind(self.csv(text)))

    def test_native_set_list_headers_quantity_and_inventory_version(self):
        path=self.csv('Set Number,Quantity,Inventory Ver\n100-1,4,1\n200-1,2,3\n')
        rows=read_list(path);self.assertEqual([(r['source'],r['kind'],r['ref'],r['quantity'],r['inventory_version']) for r in rows],[('RB','set','100-1',4,'1'),('RB','set','200-1',2,'3')])
        self.assertTrue(all(r['color']=='' for r in rows))

    def test_set_list_uses_requested_version_instead_of_latest_and_undo_is_complete(self):
        identity=self.item('set','100-1');self.inventory('100-1',5,1);self.inventory('100-1',9,2)
        before=self.db.rows('SELECT * FROM stock');job=imports.create_job(self.db,self.csv('Set Number,Quantity,Inventory Ver\n100-1,4,1\n'),'auto','stock_sets')
        self.assertEqual(imports.import_ready(self.db,job),{'imported':1,'pending':0})
        entry=self.db.rows('SELECT * FROM stock_sets')[0];self.assertEqual(entry['quantity'],4);self.assertEqual(self.db.owned_components(entry['id'])[0]['chosen_quantity'],20)
        self.assertEqual(self.db.rows('SELECT * FROM stock'),before);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
        self.assertFalse(imports.job_rows(self.db,job)[0]['imported']);self.assertTrue(self.db.redo_last_action());self.assertEqual(imports.import_ready(self.db,job)['imported'],0)

    def test_csv_inventory_into_loose_stock_multiplies_by_number_of_sets(self):
        self.item('set','100-1');self.inventory('100-1',5,1);self.inventory('100-1',9,2)
        import_rows(self.db,read_list(self.csv('Set Number;Quantity;Inventory Ver\n100-1;4;1\n')))
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],60);self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])

    def test_missing_version_remains_pending_and_can_be_corrected_after_restart(self):
        self.item('set','100-1');self.inventory('100-1',5,1)
        path=self.csv('Set Number,Quantity,Inventory Ver\n100-1,2,3\n');job=imports.create_job(self.db,path)
        self.assertEqual(imports.import_ready(self.db,job)['pending'],1);self.assertIn('Version',resolve_rows(self.db,imports.job_rows(self.db,job))[0]['issue'])
        path.unlink();self.db.close();from atelier.data import Database;self.db=Database(Path(self.temp.name)/'db.sqlite')
        row=imports.job_rows(self.db,job)[0];self.assertEqual(row['inventory_version'],'3');imports.update_row(self.db,job,1,dict(row,inventory_version='1'));self.assertEqual(imports.import_ready(self.db,job)['imported'],1)

    def test_invalid_version_cannot_silently_use_latest(self):
        self.item('set','100-1');self.inventory('100-1')
        for version in ('0','-1','abc','1.5'):
            with self.subTest(version=version):
                path=self.csv('Set Number,Quantity,Inventory Ver\n100-1,1,'+version+'\n')
                with self.assertRaises(ValueError):read_list(path)
                self.assertTrue(resolve_rows(self.db,read_list(path,strict=False))[0]['issue'])

    def test_blank_version_uses_current_inventory_and_aliases_accept_parts_and_figures(self):
        self.item('set','100-1');self.inventory('100-1',5,1);self.inventory('100-1',9,2)
        rows=read_list(self.csv('Set Number,Quantity,Inventory Ver\n100-1,1,\n'));import_rows(self.db,rows)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],49)
        self.assertEqual(read_list(self.csv('Part Number,Color,Quantity\n3005,4,2\n'))[0]['kind'],'part')
        self.assertEqual(read_list(self.csv('Minifig Number,Quantity\nfig-test,2\n'))[0]['kind'],'minifig')

    def test_correcting_quantity_keeps_inventory_version(self):
        job=imports.create_job(self.db,self.csv('Set Number,Quantity,Inventory Ver\n100-1,1,2\n'))
        imports.update_row(self.db,job,1,{'source':'RB','kind':'set','ref':'100-1','color':'','quantity':'4'})
        self.assertEqual(imports.job_rows(self.db,job)[0]['inventory_version'],'2')


class ReconstructionTests(WorkflowFixture):
    def test_excluding_unknown_figures_makes_model_buildable_and_project_matches(self):
        item=self.set_with_figure();before=self.db.rows('SELECT * FROM stock')
        self.assertEqual(find_builds(self.db)[0],[])
        results=find_builds(self.db,copies=2,exclude_minifigs=True)[0];self.assertEqual((results[0]['total'],results[0]['percent']),(10,100))
        identity=projects.from_set(self.db,item['id'],2,exclude_minifigs=True)
        self.assertEqual([(p['id'],p['required']) for p in projects.detail(self.db,identity)],[(self.part,10)]);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)

    def test_nested_sets_skip_figures_but_keep_all_model_parts(self):
        child=self.set_with_figure();parent=self.db.get_item(self.item('set','200-1'));iid=self.inventory('200-1',2,part='3001');self.db.run('INSERT INTO inventory_sets VALUES(?,?,?)',(iid,child['ref'],2))
        rows=self.db.components(parent,strict=True,exclude_minifigs=True);self.assertEqual(sum(r['chosen_quantity'] for r in rows),12)
        self.assertEqual(next(r for r in find_builds(self.db,exclude_minifigs=True)[0] if r['id']==parent['id'])['total'],12)

    def test_excluded_figures_in_stock_stay_intact(self):
        item=self.set_with_figure();figure=self.item('minifig','fig-test');self.inventory('fig-test',3);self.db.add('stock',figure,'',4)
        normal,ok=build_details(self.db,item);excluded,ok=build_details(self.db,item,exclude_minifigs=True)
        self.assertEqual((normal[0][4],normal[0][5]),(8,52));self.assertEqual((excluded[0][4],excluded[0][5]),(5,40))

    def test_flattened_api_cache_stores_a_separate_model_inventory(self):
        item=self.db.get_item(self.item('set','100-1'));batches.store_inventory(self.db,'RB','100-1',[self.cache_part(8)],[self.cache_part(5)])
        self.assertEqual(find_builds(self.db,exclude_minifigs=True)[0][0]['total'],5)
        identity=projects.from_set(self.db,item['id'],exclude_minifigs=True);self.assertEqual(projects.detail(self.db,identity)[0]['required'],5)
        self.assertEqual(find_builds(self.db)[0][0]['total'],8)

    def test_legacy_cache_uses_local_csv_or_explicitly_requests_refresh(self):
        item=self.set_with_figure();batches.store_inventory(self.db,'RB',item['ref'],[self.cache_part(8)])
        self.assertEqual(find_builds(self.db,exclude_minifigs=True)[0][0]['total'],5)
        self.db.run('DELETE FROM inventories');result=find_builds(self.db,exclude_minifigs=True);self.assertEqual(result[0],[]);self.assertTrue(any('actualiser' in w for w in result[1]))
        with self.assertRaisesRegex(ValueError,'Actualise'):projects.from_set(self.db,item['id'],exclude_minifigs=True)

    def test_figure_only_nested_set_does_not_make_parent_incomplete(self):
        child=self.item('set','100-1');parent=self.db.get_item(self.item('set','200-1'));iid=self.inventory('200-1')
        self.db.run('INSERT INTO inventory_sets VALUES(?,?,?)',(iid,'100-1',1));batches.store_inventory(self.db,'RB','100-1',[self.cache_part(3)],[])
        self.assertEqual(find_builds(self.db,exclude_minifigs=True)[0][0]['ref'],'200-1');self.assertEqual(sum(p['chosen_quantity'] for p in self.db.components(parent,strict=True,exclude_minifigs=True)),5)

    def test_api_batch_downloads_both_variants_and_upgrades_legacy_without_force(self):
        item=self.db.get_item(self.item('set','100-1'));batches.store_inventory(self.db,'RB',item['ref'],[self.cache_part(8)])
        calls=[]
        class API:
            def __init__(self,db):pass
            def rb(self,path):
                calls.append(path);return {'results':[{'part':{'part_num':'3005','name':'Brick'},'color':{'id':4},'quantity':5 if 'inc_minifig_parts=0' in path else 8}],'next':None}
        before=self.db.rows('SELECT * FROM stock');job=batches.create_job(self.db,[item]);self.assertEqual(batches.run_batch(self.db,job,api_factory=API)['loaded'],1)
        self.assertEqual(len(calls),2);self.assertEqual(find_builds(self.db,exclude_minifigs=True)[0][0]['total'],5);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)

    def test_bricklink_model_request_retains_parts_and_skips_intact_figures(self):
        api=Mock();api.bl.return_value=[{'entries':[{'item':{'type':'MINIFIG','no':'fig','name':'Figure'},'quantity':1},{'item':{'type':'PART','no':'3005','name':'Brick'},'quantity':2,'color_id':4}]}]
        parts=batches._bl_parts(api,'100-1',threading.Event(),False);self.assertEqual([p['ref'] for p in parts],['3005']);self.assertIn('break_minifigs=false',api.bl.call_args.args[0])

    def test_export_marks_exclusion_and_keeps_column_order(self):
        path=Path(self.temp.name)/'parts.csv';export_build_parts(path,{'source':'RB','ref':'100-1'},[('RB','3005','Brick','RB:4',10,4,6)],'missing',2,False,True)
        with path.open(encoding='utf-8-sig') as f:rows=list(csv.reader(f,delimiter=';'))
        self.assertEqual(rows[0][-1],'minifigurines_exclues');self.assertEqual(rows[1][13:],[ '6','1'])


class SetProjectUITests(WorkflowFixture):
    def test_main_window_shows_project_set_and_clears_preview_for_custom_project(self):
        from atelier.app import MainWindow,NAV
        item=self.set_with_figure();identity=projects.from_set(self.db,item['id'],exclude_minifigs=True)
        with patch.object(Catalogue,'load_thumbnails'),patch.object(Preview,'refresh'),patch('atelier.thumbnails.PartThumbnails.schedule'):
            window=self.keep(MainWindow(self.db));window.show();app.processEvents();window.nav.setCurrentRow(next(i for i,row in enumerate(NAV) if row[3]=='projects'));window.projects.refresh(identity)
            self.assertEqual(window.preview.item['id'],item['id']);self.assertIn(item['ref'],window.preview.title.text())
            custom=projects.create(self.db,'Custom');window.projects.refresh(custom);self.assertIsNone(window.preview.item);self.assertEqual(window.preview.title.text(),'Aperçu')

    def test_context_project_action_uses_clicked_sorted_row(self):
        one=self.db.get_item(self.item('set','100-1'));two=self.db.get_item(self.item('set','200-1'));window=self.keep(BuildStockDialog(self.db,None));window.results=[one,two]
        fill_table(window.table,[(one['ref'],),(two['ref'],)]);window.table.sortItems(0,Qt.SortOrder.DescendingOrder)
        with patch('atelier.build_stock.async_task'),patch('atelier.build_stock.QMenu') as menu,patch.object(window,'create_project') as create:
            menu.return_value.addAction.side_effect=lambda text,fn:fn() if 'projet' in text else Mock()
            window.context_menu(window.table.visualItemRect(window.table.item(0,0)).center());self.assertEqual(create.call_args.args[0]['id'],two['id'])

    def test_picker_combines_filters_and_clears_hidden_selection(self):
        first=self.item('set','100-1','Demo castle');second=self.item('set','200-1','Space')
        self.db.run("UPDATE items SET category='Castle',year='2000' WHERE id=?",(first,));self.db.run("UPDATE items SET category='Space',year='2001' WHERE id=?",(second,))
        picker=self.keep(SetPicker(self.db));picker.catalogue.apply_filter_state({'search':'castle','year':'2000','advanced':{'categories':['Castle'],'sources':['RB']}})
        self.assertEqual(picker.chosen['id'],first);self.assertIn('Demo castle',picker.preview.title.text());self.assertTrue(picker.choose_button.isEnabled())
        picker.catalogue.search.setText('no-match');picker.catalogue.timer.stop();picker.catalogue.reset();self.assertIsNone(picker.chosen);self.assertFalse(picker.choose_button.isEnabled())
        self.assertEqual(len(self.db.rows('SELECT * FROM stock_sets')),0)

    def test_picker_accepts_a_set_on_later_page_without_old_page_selection(self):
        for n in range(106):self.item('set',f'{n:04d}-1')
        picker=self.keep(SetPicker(self.db));picker.catalogue.go_page(2);chosen=picker.catalogue.rows[-1];picker.catalogue.table.selectRow(len(picker.catalogue.rows)-1);picker.choose();self.assertEqual(picker.chosen['id'],chosen['id'])

    def test_stale_photo_result_never_overwrites_new_selection(self):
        one=self.db.get_item(self.item('set','100-1'));two=self.db.get_item(self.item('set','200-1'));preview=self.keep(SetImagePreview(Mock()));callbacks=[]
        with patch('atelier.set_picker.async_task',side_effect=lambda parent,work,done,fail:callbacks.append(done)):
            preview.set_item(one);preview.timer.stop();preview.load();preview.set_item(two);preview.timer.stop();old=Image.new('RGB',(20,20),'red');callbacks[0](old)
            self.assertIsNone(preview.image);preview.timer.stop();preview.load();new=Image.new('RGB',(20,20),'blue');callbacks[1](new);self.assertIs(preview.image,new)
            preview.stop();callbacks[1](old);self.assertIs(preview.image,new)

    def test_build_result_creates_project_with_search_options(self):
        item=self.set_with_figure();window=self.keep(BuildStockDialog(self.db,None));window.results=[dict(item,total=10,missing=0,percent=100)];window.last_copies=2;window.last_exclude_minifigs=True
        fill_table(window.table,[(item['source'],item['ref'])]);window.table.selectRow(0)
        with patch('atelier.build_stock.async_task'):
            dialog=self.keep(window.create_project());self.assertEqual(dialog.copies.value(),2);self.assertTrue(dialog.exclude_minifigs.isChecked());dialog.save()
        self.assertEqual(projects.list_projects(self.db)[0]['required'],10)

    def test_checkbox_invalidates_results_and_persists(self):
        window=self.keep(BuildStockDialog(self.db,None));window.results=[{'ref':'old'}];window.export_missing.setEnabled(True);window.project_button.setEnabled(True);window.exclude_minifigs.setChecked(True)
        self.assertEqual(window.results,[]);self.assertFalse(window.export_missing.isEnabled());self.assertFalse(window.project_button.isEnabled());self.assertTrue(self.keep(BuildStockDialog(self.db,None)).exclude_minifigs.isChecked())

    def test_projects_emit_set_preview_on_selection_and_double_click_opens_set(self):
        item=self.set_with_figure();identity=projects.from_set(self.db,item['id'],exclude_minifigs=True);panel=self.keep(ProjectsPanel(self.db));received=[];panel.selected.connect(received.append);panel.show();panel.refresh(identity)
        self.assertEqual(received[-1]['id'],item['id']);self.assertTrue(panel.view_set.isEnabled())
        with patch('atelier.dialogs.RelationsDialog',return_value=QDialog()) as factory:
            opened=self.keep(panel.open_project());self.assertEqual(factory.call_args.args[2]['id'],item['id'])
        custom=projects.create(self.db,'Custom');panel.refresh(custom);self.assertIsNone(received[-1]);self.assertFalse(panel.view_set.isEnabled())

    def test_hidden_project_refresh_does_not_steal_another_tabs_preview(self):
        panel=self.keep(ProjectsPanel(self.db));signal=Mock();panel.selected.connect(signal);panel.hide();panel.refresh();signal.assert_not_called()

    def test_new_project_picker_is_modeless_and_closes_with_parent(self):
        self.item('set','100-1');panel=self.keep(ProjectsPanel(self.db));dialog=self.keep(NewProjectDialog(panel));dialog.choose_set();picker=dialog.picker;self.assertTrue(picker.isVisible());dialog.reject();self.assertFalse(picker.isVisible());self.assertTrue(picker.preview.closed)


class DrawerInventoryTests(WorkflowFixture):
    def test_replace_reference_color_and_count_is_atomic_undoable_and_keeps_stock(self):
        drawer=self.drawer();put_entry(self.db,drawer['id'],self.part,'4',10,walls.contents(self.db,drawer['id'])[0]);old=walls.contents(self.db,drawer['id'])[0];before=self.db.rows('SELECT * FROM stock')
        put_entry(self.db,drawer['id'],self.other,'4',7,old);self.assertEqual([(p['id'],p['stored_quantity']) for p in walls.contents(self.db,drawer['id'])],[(self.other,7)])
        self.assertTrue(self.db.undo_last_action());self.assertEqual(walls.contents(self.db,drawer['id'])[0]['stored_quantity'],10);self.assertTrue(self.db.redo_last_action());self.assertEqual(self.db.rows('SELECT * FROM stock'),before)

    def test_combined_drawer_counts_cannot_exceed_stock(self):
        drawer=self.drawer();other=walls.drawers(self.db,drawer['wall_id'])[1];put_entry(self.db,drawer['id'],self.part,'4',30,walls.contents(self.db,drawer['id'])[0]);put_entry(self.db,other['id'],self.part,'4',10)
        before=walls.contents(self.db,other['id']);history=self.db.undo_description()
        with self.assertRaises(ValueError):put_entry(self.db,other['id'],self.part,'4',11,before[0])
        self.assertEqual(walls.contents(self.db,other['id']),before);self.assertEqual(self.db.undo_description(),history)

    def test_color_change_obeys_its_own_stock_limit(self):
        drawer=self.drawer();old=walls.contents(self.db,drawer['id'])[0]
        with self.assertRaises(ValueError):put_entry(self.db,drawer['id'],self.part,'1',1,old)
        self.assertEqual(walls.contents(self.db,drawer['id'])[0]['chosen_color'],'4')

    def test_duplicate_target_is_not_overwritten_or_merged(self):
        drawer=self.drawer();put_entry(self.db,drawer['id'],self.other,'4',None);before=walls.contents(self.db,drawer['id'])
        with self.assertRaisesRegex(ValueError,'déjà'):put_entry(self.db,drawer['id'],self.other,'4',7,before[1] if before[1]['id']==self.part else before[0])
        self.assertEqual(walls.contents(self.db,drawer['id']),before)

    def test_stale_editor_cannot_replace_later_count(self):
        drawer=self.drawer();old=walls.contents(self.db,drawer['id'])[0];put_entry(self.db,drawer['id'],self.part,'4',5,old)
        with self.assertRaisesRegex(ValueError,'changé'):put_entry(self.db,drawer['id'],self.part,'4',6,old)
        self.assertEqual(walls.contents(self.db,drawer['id'])[0]['stored_quantity'],5)

    def test_unknown_and_zero_remain_distinct_in_tooltips(self):
        drawer=self.drawer();parts=walls.contents(self.db,drawer['id']);tooltip=drawer_tooltip(drawer,parts);self.assertIn('À renseigner',tooltip);self.assertIn('Brique 1 x 1',tooltip);self.assertNotIn('>40<',tooltip)
        put_entry(self.db,drawer['id'],self.part,'4',0,parts[0]);tooltip=drawer_tooltip(drawer,walls.contents(self.db,drawer['id']));self.assertIn('>0<',tooltip);self.assertNotIn('À renseigner',tooltip)

    def test_hover_uses_source_color_names_without_new_redraw_queries(self):
        drawer=self.drawer();part=walls.wall_contents(self.db)[0];self.assertEqual(part['color_name'],'Rouge');self.assertIn('Rouge (4)',drawer_tooltip(drawer,[part]))
        figure=self.item('part','BL-demo',source='BL');self.db.set_setting('bl_colors',{'4':{'name':'Custom BL'}});put_entry(self.db,drawer['id'],figure,'4',None)
        self.assertIn('Custom BL (4)',drawer_tooltip(drawer,walls.wall_contents(self.db)))

    def test_inventory_editor_saves_captured_drawer_and_refreshes_on_undo(self):
        drawer=self.drawer();window=self.keep(DrawerInventoryDialog(self.db,None,drawer['id']));window.table.selectRow(0);editor=self.keep(window.edit());editor.unknown.setChecked(False);editor.quantity.setValue(6);editor.save()
        self.assertEqual(window.rows[0]['stored_quantity'],6);self.db.undo_last_action();window.refresh_action_history();self.assertIsNone(window.rows[0]['stored_quantity'])

    def test_closing_inventory_closes_all_entry_editors(self):
        drawer=self.drawer();window=self.keep(DrawerInventoryDialog(self.db,None,drawer['id']));editor=window.open_editor();self.assertTrue(editor.isVisible());window.reject();self.assertFalse(editor.isVisible())

    def test_real_drawer_double_click_opens_inventory(self):
        from atelier.storage_panel import StoragePanel
        drawer=self.drawer();put_entry(self.db,drawer['id'],self.part,'4',10,walls.contents(self.db,drawer['id'])[0]);panel=self.keep(StoragePanel(self.db,None));panel.resize(900,800);panel.show();panel.front.setChecked(True);app.processEvents();panel.fit();app.processEvents()
        item=panel.items[drawer['id']];point=panel.view.mapFromScene(item.mapToScene(QPointF(40,35)));QTest.mouseDClick(panel.view.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point);app.processEvents()
        window=panel._drawer_windows[drawer['id']];self.keep(window);self.assertEqual(window.rows[0]['stored_quantity'],10)


class AllFigureLabelsTests(WorkflowFixture):
    def test_all_catalogue_figures_get_model_including_individual_and_queue_layouts(self):
        one=self.db.get_item(self.item('minifig','fig-a'));two=self.db.get_item(self.item('minifig','fig-b',source='BL'));self.db.run("UPDATE items SET category='Figures' WHERE kind='minifig'")
        one=self.db.get_item(one['id']);set_category_model(self.db,'Figures',preset_template('main_bottom'))
        personal=preset_template('main_bottom');personal.update(edge_settings={'black':25,'width':2},category_colors={'Figures':'#123456'});self.db.set_setting(individual_template_key(one),personal)
        self.db.add('queue',two['id'],'',1);entry=self.db.rows('SELECT id FROM queue WHERE item_id=?',(two['id'],))[0]['id'];scoped=dict(two,_scope='queue',entry_id=entry);self.db.set_setting(individual_template_key(scoped),personal)
        before=self.db.rows('SELECT * FROM stock');self.assertEqual(set_kind_model(self.db,'minifig',preset_template('main_centered')),2)
        for item in (one,two,scoped):self.assertEqual(template_for_item(item,self.db)['preset_id'],'main_centered')
        self.assertEqual(template_for_item(one,self.db)['edge_settings'],personal['edge_settings']);self.assertEqual(template_for_item(scoped,self.db)['category_colors'],personal['category_colors']);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
        self.assertNotIn('preset_id',template_for_item(self.db.get_item(self.part),self.db))
        new=self.db.get_item(self.item('minifig','fig-new'));self.assertEqual(template_for_item(new,self.db)['preset_id'],'main_centered')
        self.db.set_setting(individual_template_key(new),preset_template('main_bottom'));self.assertEqual(template_for_item(new,self.db)['preset_id'],'main_bottom')

    def test_all_figure_rule_round_trips_in_label_backup(self):
        item=self.db.get_item(self.item('minifig','fig-a'));set_kind_model(self.db,'minifig',preset_template('main_centered'));path=Path(self.temp.name)/'labels.json';export_family(self.db,'labels',path)
        self.db.set_setting('label_layout_kinds',{});restore_families(self.db,[path]);self.assertEqual(template_for_item(item,self.db)['preset_id'],'main_centered')

    def test_editor_exposes_all_figures_target_and_applies_selected_model(self):
        item=self.db.get_item(self.item('minifig','fig-a'));engine=Mock();engine.visuals.return_value=({'main':Image.new('RGBA',(40,40),'yellow')},'')
        editor=self.keep(LabelEditor(self.db,engine,item));editor.destination.setCurrentIndex(editor.destination.findData('minifigs'));editor.presets.setCurrentIndex(editor.presets.findData('main_centered'));editor.apply()
        self.assertEqual(template_for_item(item,self.db)['preset_id'],'main_centered');self.assertFalse(editor.categories.isVisible())
