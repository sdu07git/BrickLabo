"""Storage proposals, real Qt drop events, independent thumbnails and external exports."""
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

from PIL import Image
from PySide6.QtCore import Qt,QPointF,QMimeData
from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QMessageBox

from atelier import storage_wall as walls
from atelier import storage_assignment as assignment
from atelier.storage_tools import StoragePlanDialog,MIME,read_drag
from atelier.result_tables import row_index
from atelier.storage_panel import StoragePanel
from atelier.thumbnails import ThumbnailContext,load_thumbnail
from atelier.labels import individual_template_key
from atelier.storage import configure_portable_database
from test_storage_and_inventory_batches import Fixture,app
import test_edges as edge_fixtures


class ProposalTests(Fixture):
    def setUp(self):
        super().setUp();self.db.run("UPDATE items SET category='Bricks'")
        self.wall=walls.create_wall(self.db,'Briques',5,6)
    def extra(self,ref,name,category='Bricks',source='RB',color='4'):
        identity=self.item('part',ref,name,source);self.db.run('UPDATE items SET category=? WHERE id=?',(category,identity));self.db.add('stock',identity,color,5);return identity
    def snapshot(self):return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','stock_undo','stock_revision','history')}
    def test_numeric_stud_order_rotations_heights_and_variant_identities(self):
        ten=self.extra('ten','Brick 1 x 10');square=self.extra('square','Brick 2 × 2')
        rotated=self.extra('rotated','Brick 4 x 2 with Pattern',source='BL')
        tall=self.extra('tall','Brick 2 x 4 x 3')
        before=self.snapshot();plan=assignment.propose(self.db,self.wall,'Bricks')
        self.assertEqual([g['dimensions'] for g in plan['groups']],[(1.,1.),(2.,2.),(2.,4.),(2.,4.,3.),(1.,10.)])
        self.assertEqual(set(plan['groups'][2]['entries']),{(self.other,'4'),(rotated,'4')})
        assignment.apply_proposal(self.db,plan);self.assertEqual(self.snapshot(),before)
        self.assertEqual(len(walls.wall_contents(self.db,self.wall)),6)
    def test_unknown_dimensions_named_empty_drawers_and_other_categories_are_kept(self):
        unknown=self.extra('unknown','Special brick');other=self.extra('tile','Tile 1 x 1','Tiles')
        first=walls.drawers(self.db,self.wall)[0];walls.save_drawer(self.db,self.wall,1,1,1,1,'Réservé',first['id'])
        plan=assignment.propose(self.db,self.wall,'Bricks');self.assertEqual(plan['unknown'][0]['id'],unknown)
        self.assertNotIn(first['id'],[g['drawer_id'] for g in plan['groups']]);assignment.apply_proposal(self.db,plan)
        self.assertEqual(walls.contents(self.db,first['id']),[]);self.assertEqual(walls.search(self.db,'unknown'),[]);self.assertEqual(walls.search(self.db,'tile'),[])
    def test_colours_group_together_or_split_without_palette_conversion(self):
        self.db.add('stock',self.part,'1',7);same=self.extra('blpart','Brick 1 x 1',source='BL',color='5')
        plan=assignment.propose(self.db,self.wall,'Bricks');self.assertEqual(len(plan['groups'][0]['entries']),3)
        split=assignment.propose(self.db,self.wall,'Bricks',split_colors=True)
        self.assertEqual(len(split['groups']),4);before=self.snapshot();assignment.apply_proposal(self.db,split)
        self.assertEqual(self.snapshot(),before);self.assertEqual({p['chosen_color'] for p in walls.wall_contents(self.db,self.wall) if p['id']==same},{'5'})
    def test_capacity_shortfall_keeps_unassigned_groups_and_second_run_does_not_duplicate(self):
        small=walls.create_wall(self.db,'Petit',1,1);plan=assignment.propose(self.db,small,'Bricks')
        self.assertIsNone(plan['groups'][1]['drawer_id']);assignment.apply_proposal(self.db,plan)
        again=assignment.propose(self.db,small,'Bricks');self.assertEqual(len(again['groups']),1);self.assertIsNone(again['groups'][0]['drawer_id'])
        self.assertEqual(len(walls.wall_contents(self.db,small)),1);self.assertEqual(len(assignment.stock_rows(self.db,unlocated=True)),1)
    def test_reorganisation_retains_mixed_drawers_other_cabinets_and_zero_stock_links(self):
        other_wall=walls.create_wall(self.db,'Autre',1,1);other_drawer=walls.drawers(self.db,other_wall)[0]
        drawers=walls.drawers(self.db,self.wall);tile=self.extra('tile','Tile 1 x 1','Tiles')
        walls.assign(self.db,drawers[0]['id'],[(self.part,'4'),(tile,'4')]);walls.assign(self.db,drawers[-1]['id'],[(self.other,'4')])
        walls.assign(self.db,other_drawer['id'],[(tile,'4')]);self.db.run('UPDATE stock SET quantity=0 WHERE item_id=?',(self.other,))
        before=self.snapshot();plan=assignment.propose(self.db,self.wall,'Bricks',reorganize=True);assignment.apply_proposal(self.db,plan)
        self.assertEqual(self.snapshot(),before);self.assertEqual(len(walls.contents(self.db,drawers[0]['id'])),2);self.assertEqual(len(walls.contents(self.db,other_drawer['id'])),1)
        found=walls.search(self.db,'3001');self.assertEqual(len(found),1);self.assertEqual(found[0]['stock_quantity'],0)
    def test_stale_stock_contents_and_names_reject_before_any_mutation(self):
        for change in (lambda:self.db.run('UPDATE stock SET quantity=quantity+1'),lambda:walls.rename_wall(self.db,self.wall,'Modifié'),lambda:walls.assign(self.db,walls.drawers(self.db,self.wall)[0]['id'],[(self.part,'4')])):
            plan=assignment.propose(self.db,self.wall,'Bricks');change();before=walls.print_snapshot(self.db)
            with self.assertRaises(ValueError):assignment.apply_proposal(self.db,plan)
            self.assertEqual(walls.print_snapshot(self.db),before)
    def test_duplicate_destinations_and_failed_write_roll_back(self):
        plan=assignment.propose(self.db,self.wall,'Bricks');before=walls.print_snapshot(self.db)
        with self.assertRaises(ValueError):assignment.apply_proposal(self.db,plan,[plan['available'][0]['id']]*2)
        self.db.run("CREATE TRIGGER reject_location BEFORE INSERT ON storage_contents WHEN NEW.item_id="+str(self.other)+" BEGIN SELECT RAISE(ABORT,'write refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):assignment.apply_proposal(self.db,plan)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_reorganisation_cannot_drop_existing_unknown_or_overflowing_contents(self):
        unknown=self.extra('unknown','Special brick');first=walls.drawers(self.db,self.wall)[0]
        walls.assign(self.db,first['id'],[(unknown,'4')]);plan=assignment.propose(self.db,self.wall,'Bricks',reorganize=True);before=walls.print_snapshot(self.db)
        with self.assertRaises(ValueError):assignment.apply_proposal(self.db,plan)
        self.assertEqual(walls.print_snapshot(self.db),before)
    def test_cancelled_preview_and_custom_destination_have_no_unreviewed_effect(self):
        before=walls.print_snapshot(self.db);window=self.keep(StoragePlanDialog(self.db,self.wall));self.assertEqual(walls.print_snapshot(self.db),before)
        window.targets[0].setCurrentIndex(window.targets[0].findData(window.plan['available'][7]['id']));chosen=[w.currentData() for w in window.targets]
        with patch('atelier.storage_tools.QMessageBox.information'):window.apply()
        self.assertEqual(walls.contents(self.db,window.plan['available'][7]['id'])[0]['id'],self.part)
        before=walls.print_snapshot(self.db);another=self.keep(StoragePlanDialog(self.db,self.wall));another.reject();self.assertEqual(walls.print_snapshot(self.db),before)
    def test_preview_keeps_categories_dimensions_and_destination_widgets_aligned(self):
        self.extra('tile','Tile 2 x 2','Tiles');window=self.keep(StoragePlanDialog(self.db,self.wall))
        self.assertTrue(window.table.isSortingEnabled())
        for column in (0,1,3,4,6,7):
            window.table.sortItems(column,Qt.SortOrder.DescendingOrder)
            for row in range(window.table.rowCount()):
                group=window.plan['groups'][row_index(window.table,row)]
                self.assertEqual(window.table.item(row,0).text(),group['category']);self.assertEqual(window.table.item(row,1).text(),assignment.dimensions_text(group['dimensions']))
                self.assertEqual(window.table.cellWidget(row,4).currentData(),group['drawer_id'])
    def test_fractional_dimensions_and_bad_names(self):
        self.assertEqual(assignment.stud_dimensions('Brick 1 1/2 x 2 x 1/3'),(1.5,2.,1/3))
        self.assertEqual(assignment.stud_dimensions('Brique 2,5 × 1'),(1.,2.5))
        for name in ('Unknown','Brick 0 x 2','Brick 1/0 x 2'):self.assertIsNone(assignment.stud_dimensions(name))


class PieceDropTests(Fixture):
    def panel(self):
        wall=walls.create_wall(self.db,'Meuble',3,2);panel=self.keep(StoragePanel(self.db,None));panel.resize(1100,920);panel.show();panel.front.setChecked(True);panel.fit();app.processEvents()
        panel.details_tabs.setCurrentWidget(panel.stock_browser);return panel,wall,walls.drawers(self.db,wall)
    def mime(self,table,identities):
        table.clearSelection()
        for row in range(table.rowCount()):
            identity=table.drag_rows()[row_index(table,row)]['id']
            if identity in identities:
                for column in range(table.columnCount()):table.item(row,column).setSelected(True)
        return table.mimeData(table.selectedItems())
    def drop(self,panel,mime,drawer,position=None):
        item=panel.items[drawer['id']];point=position if position is not None else panel.view.mapFromScene(item.mapToScene(item.transform_face.map(QPointF(40,32))))
        enter=QDragEnterEvent(point,Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);QApplication.sendEvent(panel.view.viewport(),enter)
        move=QDragMoveEvent(point,Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);QApplication.sendEvent(panel.view.viewport(),move)
        event=QDropEvent(QPointF(point),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);QApplication.sendEvent(panel.view.viewport(),event);app.processEvents();return event
    def test_sorted_multi_row_qt_drop_assigns_exact_references_and_updates_unlocated_table(self):
        panel,wall,drawers=self.panel();table=panel.stock_browser.table;table.sortItems(1,Qt.SortOrder.DescendingOrder);before=self.db.rows('SELECT * FROM stock')
        event=self.drop(panel,self.mime(table,{self.part,self.other}),drawers[2]);self.assertTrue(event.isAccepted())
        self.assertEqual({p['id'] for p in walls.contents(self.db,drawers[2]['id'])},{self.part,self.other});self.assertEqual(panel.stock_browser.table.rowCount(),0);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
    def test_dragging_contents_moves_only_selected_links_and_preserves_other_locations(self):
        panel,wall,drawers=self.panel();walls.assign(self.db,drawers[0]['id'],[(self.part,'4'),(self.other,'4')]);walls.assign(self.db,drawers[1]['id'],[(self.part,'4')]);panel.refresh();panel.choose_drawer(drawers[0]['id'])
        before=self.db.rows('SELECT * FROM stock');event=self.drop(panel,self.mime(panel.table,{self.part}),drawers[2]);self.assertTrue(event.isAccepted())
        self.assertEqual([p['id'] for p in walls.contents(self.db,drawers[0]['id'])],[self.other]);self.assertEqual([p['id'] for p in walls.contents(self.db,drawers[1]['id'])],[self.part]);self.assertEqual([p['id'] for p in walls.contents(self.db,drawers[2]['id'])],[self.part]);self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
    def test_drop_on_angled_drawer_works_and_drop_on_blank_area_does_not_write(self):
        panel,wall,drawers=self.panel();panel.front.setChecked(False);panel.angle.setValue(30);panel.fit();app.processEvents()
        mime=self.mime(panel.stock_browser.table,{self.part});before=walls.print_snapshot(self.db)
        event=self.drop(panel,mime,drawers[0],panel.view.viewport().rect().topLeft());self.assertFalse(event.isAccepted());self.assertEqual(walls.print_snapshot(self.db),before)
        event=self.drop(panel,mime,drawers[0]);self.assertTrue(event.isAccepted());self.assertEqual(walls.contents(self.db,drawers[0]['id'])[0]['id'],self.part)
    def test_stale_stock_and_source_links_fail_atomically(self):
        panel,wall,drawers=self.panel();mime=self.mime(panel.stock_browser.table,{self.part,self.other});self.db.run('UPDATE stock SET quantity=0 WHERE item_id=?',(self.other,));before=walls.print_snapshot(self.db)
        self.assertFalse(self.drop(panel,mime,drawers[0]).isAccepted());self.assertEqual(walls.print_snapshot(self.db),before)
        self.db.run('UPDATE stock SET quantity=1 WHERE item_id=?',(self.other,));walls.assign(self.db,drawers[0]['id'],[(self.part,'4'),(self.other,'4')]);panel.refresh();panel.choose_drawer(drawers[0]['id']);mime=self.mime(panel.table,{self.part,self.other});walls.unassign(self.db,drawers[0]['id'],[(self.other,'4')]);before=walls.print_snapshot(self.db)
        self.assertFalse(self.drop(panel,mime,drawers[1]).isAccepted());self.assertEqual(walls.print_snapshot(self.db),before)
    def test_malformed_or_foreign_drag_is_rejected(self):
        panel,wall,drawers=self.panel();mime=self.mime(panel.stock_browser.table,{self.part});data=json.loads(bytes(mime.data(MIME)));data['session']='foreign';mime.setData(MIME,json.dumps(data).encode());self.assertIsNone(read_drag(mime,self.db))
        for value in (b'[]',b'not json',b'{}',b'x'*(1024*1024+1)):
            mime.setData(MIME,value);self.assertIsNone(read_drag(mime,self.db))


from atelier.result_tables import row_index


class StableThumbnailTests(unittest.TestCase):
    def setUp(self):edge_fixtures.EdgeTests.setUp(self)
    def tearDown(self):self.db.close();edge_fixtures.EdgeTests.tearDown(self)
    def test_pixels_and_cached_thumbnail_stay_fixed_while_large_render_changes(self):
        context=ThumbnailContext(self.db);key=context.state(self.item);cache=self.engine.thumbnail_cache
        first,_=load_thumbnail(self.engine,self.item,key,cache.generation);large=self.engine.render_3d(self.item,(350,250))[0]
        self.db.set_setting('edge_settings',{'black':100.,'width':10.})
        self.assertEqual(context.state(self.item),key)
        with patch.object(self.engine,'render_3d',wraps=self.engine.render_3d) as render:
            second,_=load_thumbnail(self.engine,self.item,context.state(self.item),cache.generation);self.assertEqual(render.call_count,0)
        self.assertEqual(first.tobytes(),second.tobytes());self.assertNotEqual(large.tobytes(),self.engine.render_3d(self.item,(350,250))[0].tobytes())
        self.db.set_setting(individual_template_key(self.item),{'edge_settings':{'black':30.,'width':4.}});self.assertEqual(context.state(self.item),key)
        cache.invalidate(self.item['id']);rebuilt,_=load_thumbnail(self.engine,self.item,key,cache.generation);self.assertEqual(first.tobytes(),rebuilt.tobytes())


class ExternalExportTests(Fixture):
    def window(self):
        from atelier.app import MainWindow
        window=self.keep(MainWindow(self.db));window.startup_timer.stop();window.engine.visuals=lambda *args,**kwargs:({'main':Image.new('RGBA',(160,120),'red')},'');return window
    def test_chosen_external_folder_persists_and_receives_real_png_and_pdf(self):
        window=self.window();folder=Path(self.temp.name)/'Autre disque'/'Mes étiquettes';folder.mkdir(parents=True)
        with patch('atelier.app.QFileDialog.getExistingDirectory',return_value=str(folder)):window.output_folder()
        configure_portable_database(self.db);self.assertEqual(self.db.setting('output'),str(folder))
        self.db.add('queue',self.part,'4',1)
        def task(owner,work,done,failed):done(work(lambda *_:None))
        with patch('atelier.app.async_task',side_effect=task),patch('atelier.app.QMessageBox.information'):window.generate('export')
        png=next(folder.glob('*.png'));pdf=next(folder.glob('*.pdf'));self.assertTrue(pdf.read_bytes().startswith(b'%PDF-'))
        with Image.open(png) as image:self.assertEqual(image.format,'PNG')
        self.assertEqual(len(self.db.rows('SELECT * FROM history')),1)
    def test_missing_external_drive_does_not_reset_choice_or_record_failed_export(self):
        folder=Path(self.temp.name)/'indisponible';self.db.set_setting('output',str(folder));configure_portable_database(self.db);self.assertFalse(folder.exists());self.assertEqual(self.db.setting('output'),str(folder))
        folder.write_text('occupied by a file');window=self.window();self.db.add('queue',self.part,'4',1)
        def task(owner,work,done,failed):
            try:done(work(lambda *_:None))
            except Exception as error:failed(str(error))
        with patch('atelier.app.async_task',side_effect=task),patch('atelier.app.QMessageBox.warning') as warning:window.generate('export');warning.assert_called_once()
        self.assertEqual(self.db.rows('SELECT * FROM history'),[]);self.assertFalse(window.generating)
