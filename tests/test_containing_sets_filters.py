"""Reverse membership includes figure contents, nested sets and optional colours."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.containing_sets import matching
from atelier.relation_filters import RelationFilters,PartPicker
from atelier.dialogs import RelationsDialog
from atelier.preview import VisualEngine
from atelier.inventory_batches import store_inventory
from atelier.task_lifetime import drain_tasks

app=QApplication.instance() or QApplication([])

class ReverseMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.windows=[];self.engine=VisualEngine(self.db)
        self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)");self.db.run("INSERT INTO colors VALUES(1,'Blue','0000FF',0)")
        self.part=self.item('part','41850');self.other=self.item('part','3005');self.fig=self.item('minifig','fig-1')
        self.direct=self.item('set','100-1');self.indirect=self.item('set','200-1');self.nested=self.item('set','300-1')
        for identity,ref in ((1,'100-1'),(2,'fig-1'),(3,'200-1'),(4,'300-1')):self.db.run('INSERT INTO inventories VALUES(?,1,?)',(identity,ref))
        self.db.run("INSERT INTO inventory_parts VALUES(1,'41850',4,1,0,'')");self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',1,2,0,'')")
        self.db.run("INSERT INTO inventory_parts VALUES(2,'41850',1,1,0,'')");self.db.run("INSERT INTO inventory_parts VALUES(3,'3005',4,2,0,'')")
        self.db.run("INSERT INTO inventory_minifigs VALUES(3,'fig-1',1)");self.db.run("INSERT INTO inventory_sets VALUES(4,'200-1',1)")
    def tearDown(self):
        for window in self.windows:window.close()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents();drain_tasks();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.engine.close();self.db.close();self.temp.cleanup()
    def item(self,kind,ref,source='RB'):
        return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,'Test '+ref,ref))
    def get(self,identity):return self.db.get_item(identity)
    def refs(self,identity=None,color=None):return [r['ref'] for r in self.db.containing_sets(self.get(identity or self.part),color)]
    def keep(self,window):self.windows.append(window);return window
    def test_figure_and_nested_set_membership(self):self.assertEqual(self.refs(),['100-1','200-1','300-1'])
    def test_independent_exact_colour_through_figures_and_nested_sets(self):
        self.assertEqual(self.refs(color='4'),['100-1']);self.assertEqual(self.refs(color='1'),['200-1','300-1']);self.assertEqual(self.refs(color='0'),[])
    def test_all_colours_ignores_stock_and_preview_colour(self):
        self.db.save_visual(self.part,color='4');self.db.add('stock',self.part,'4',2)
        self.assertEqual(self.refs(),['100-1','200-1','300-1']);self.assertEqual(self.refs(color=''),self.refs())
    def test_common_sets_require_every_piece_with_independent_colour(self):
        p,o=self.get(self.part),self.get(self.other)
        self.assertEqual([r['ref'] for r in matching(self.db,[(p,None),(o,'4')])],['200-1','300-1'])
        self.assertEqual([r['ref'] for r in matching(self.db,[(p,'4'),(o,'1')])],['100-1'])
        self.assertEqual(matching(self.db,[(p,'1'),(o,'1')]),[])
    def test_same_piece_can_require_two_colours(self):
        p=self.get(self.part);self.assertEqual(matching(self.db,[(p,'1'),(p,'4')]),[])
        self.db.run("INSERT INTO inventory_parts VALUES(1,'41850',1,1,0,'')")
        self.assertEqual([r['ref'] for r in matching(self.db,[(p,'1'),(p,'4')])],['100-1'])
    def test_empty_criteria_not_entire_catalogue(self):self.assertEqual(matching(self.db,[]),[])
    def test_latest_inventory_removes_obsolete_direct_and_indirect_links(self):
        self.db.run("INSERT INTO inventories VALUES(5,2,'fig-1')");self.assertEqual(self.refs(),['100-1'])
        self.db.run("INSERT INTO inventories VALUES(6,2,'100-1')");self.assertEqual(self.refs(),[])
    def test_latest_inventory_tie_uses_same_id_as_forward_reader(self):
        self.db.run("INSERT INTO inventories VALUES(5,1,'100-1')");self.assertEqual(self.refs(),['200-1','300-1'])
    def test_cycles_and_duplicate_paths_are_finite_and_unique(self):
        self.db.run("INSERT INTO inventory_sets VALUES(3,'300-1',1)");self.db.run("INSERT INTO inventory_parts VALUES(3,'41850',1,1,0,'')")
        self.assertEqual(self.refs(),['100-1','200-1','300-1'])
    def test_zero_components_excluded_and_spares_retained(self):
        self.db.run('UPDATE inventory_minifigs SET quantity=0');self.assertEqual(self.refs(),['100-1'])
        self.db.run('UPDATE inventory_parts SET is_spare=1 WHERE inventory_id=1');self.assertEqual(self.refs(),['100-1'])
    def test_missing_figure_catalogue_does_not_hide_parent_sets(self):
        self.db.run('DELETE FROM items WHERE id=?',(self.fig,));self.assertEqual(self.refs(),['100-1','200-1','300-1'])
    def test_cached_batch_inventory_included_and_overrides_csv(self):
        parts=[{'source':'RB','kind':'part','ref':'41850','name':'Driver','color':'1','quantity':2}]
        store_inventory(self.db,'RB','100-1',parts,parts)
        self.assertEqual(self.refs(color='4'),[]);self.assertEqual(self.refs(color='1'),['100-1','200-1','300-1'])
    def test_cached_minifigure_inventory_reaches_csv_parent(self):
        self.db.run("DELETE FROM inventories WHERE set_num='fig-1'");self.db.set_setting('rb_minifig_components_fig-1',[dict(self.get(self.part),chosen_quantity=1,chosen_color='4')])
        self.assertEqual(self.refs(color='4'),['100-1','200-1','300-1']);self.assertEqual(self.refs(color='1'),[])
    def test_sources_are_separate_and_bricklink_cache_is_used(self):
        part=self.item('part','41850','BL');target=self.item('set','bl-set','BL')
        self.db.set_setting('bl_components_bl-set',[dict(self.get(part),chosen_quantity=2,chosen_color='11')])
        self.assertEqual(self.refs(part,'11'),['bl-set']);self.assertEqual(self.refs(part,'4'),[]);self.assertNotIn('bl-set',self.refs())
    def test_bricklink_manual_inventory_takes_priority_over_cache(self):
        part=self.item('part','41850','BL');target=self.item('set','bl-set','BL');self.db.set_setting('bl_manual_inventory_'+str(target),{'date':'today'})
        self.db.run('INSERT INTO bl_manual_inventory VALUES(?,0,?,11,1,0,0,0,0)',(target,part))
        store_inventory(self.db,'BL','bl-set',[{'source':'BL','kind':'part','ref':'other','name':'Other','color':'11','quantity':2}])
        self.assertEqual(self.refs(part,'11'),['bl-set'])
    def test_alternative_inventory_uses_physical_ids_and_colour(self):
        part=self.item('part','ALT41850','ALT');target=self.item('set','ALTset','ALT')
        self.db.add_alt_component(target,part,'4',3)
        self.assertEqual(self.refs(part,'4'),['ALTset']);self.assertEqual(self.refs(part,'1'),[])
    def test_query_does_not_mutate_stock_or_reservations(self):
        before={t:self.db.rows('SELECT * FROM '+t) for t in ('stock','stock_sets','project_parts','settings','action_history')}
        self.refs();matching(self.db,[(self.get(self.part),'1'),(self.get(self.other),None)])
        self.assertEqual(before,{t:self.db.rows('SELECT * FROM '+t) for t in before})
    def test_filter_starts_with_one_piece_any_colour_and_keeps_independent_choices(self):
        widget=self.keep(RelationFilters(self.db,None,self.get(self.part)));self.assertEqual(widget.criteria()[0][1],None)
        widget.add_items([self.get(self.other)]);combo=widget.table.cellWidget(1,2);combo.setCurrentIndex(combo.findData('4'))
        self.assertEqual([color for _,color in widget.criteria()],[None,'4']);widget.reset();self.assertEqual(len(widget.criteria()),1)
    def test_removing_last_filter_disables_search(self):
        widget=self.keep(RelationFilters(self.db,None,self.get(self.part)));widget.table.selectRow(0);widget.remove_selected()
        self.assertEqual(widget.criteria(),[]);self.assertFalse(widget.search_button.isEnabled())
    def test_picker_filters_catalogue_and_can_select_multiple_parts(self):
        picker=self.keep(PartPicker(self.db,'RB',None,None));picker.catalogue.search.setText('41850');picker.catalogue.timer.stop();picker.catalogue.reload();picker.catalogue.table.selectRow(0);picker.choose()
        self.assertEqual([row['ref'] for row in picker.chosen],['41850'])
        second=self.keep(PartPicker(self.db,'RB',None,None));second.catalogue.table.selectAll();second.choose();self.assertEqual({row['ref'] for row in second.chosen},{'41850','3005'})
    def test_relations_window_filters_common_sets_and_clears_empty_preview(self):
        with patch('atelier.dialogs.async_task',side_effect=lambda owner,work,done,*_:done(work(lambda *_:None))),patch('atelier.preview.async_task'),patch.object(RelationsDialog,'show_set_image'):
            window=self.keep(RelationsDialog(self.db,self.engine,self.get(self.part),None));window.relation_filters.add_items([self.get(self.other)])
            combo=window.relation_filters.table.cellWidget(1,2);combo.setCurrentIndex(combo.findData('4'));window.search_containing_sets();self.assertEqual([r['ref'] for r in window.sets],['200-1','300-1'])
            combo=window.relation_filters.table.cellWidget(0,2);combo.setCurrentIndex(combo.findData('4'));window.search_containing_sets();self.assertEqual(window.sets,[]);self.assertEqual(window.part_table.rowCount(),0)
    def test_late_search_after_close_is_ignored(self):
        callbacks=[]
        with patch('atelier.preview.async_task'),patch.object(RelationsDialog,'show_set_image'):
            window=self.keep(RelationsDialog(self.db,self.engine,self.get(self.part),None))
            with patch('atelier.dialogs.async_task',side_effect=lambda owner,work,done,*_:callbacks.append(done)):window.search_containing_sets()
            window.reject();before=list(window.sets);callbacks[0]([]);self.assertEqual(window.sets,before)
