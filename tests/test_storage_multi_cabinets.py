"""Multiple cabinet scope, independently combined criteria and split quantities."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QDialog,QMessageBox
from atelier import storage_assignment as assignment,storage_wall as walls
from atelier.data import Database
from atelier.storage_tools import StoragePlanDialog,ReferenceDrawerCountsDialog
from atelier.storage_preview import proposal_snapshot
from atelier.preview import VisualEngine
from atelier.storage_panel import StoragePanel
from test_storage_and_inventory_batches import Fixture,app
from test_storage_preview_and_undo import wait


class StorageFixture(Fixture):
    def setUp(self):
        super().setUp();self.db.run("UPDATE items SET category='Bricks'")
        self.first=walls.create_wall(self.db,'Haut gauche',1,2)
        self.second=walls.create_wall(self.db,'Haut droite',1,2)
        self.last=walls.create_wall(self.db,'Bas',1,2)
        for identity,x,y in [(self.first,0,0),(self.second,3,0),(self.last,0,4)]:self.db.run('UPDATE storage_walls SET x=?,y=? WHERE id=?',(x,y,identity))
    def extra(self,ref,name,category='Bricks',color='4',quantity=5):
        identity=self.item('part',ref,name);self.db.run('UPDATE items SET category=? WHERE id=?',(category,identity));self.db.add('stock',identity,color,quantity);return identity
    def snapshot(self):return walls.print_snapshot(self.db)
    def dialog(self,wall=None,**kwargs):
        window=self.keep(StoragePlanDialog(self.db,wall,**kwargs));window.show();app.processEvents();return window
    def propose(self,**kwargs):return assignment.propose(self.db,None,**kwargs)



class MultiCabinetTests(StorageFixture):
    def test_all_cabinets_follow_physical_order_not_creation_order(self):
        self.db.run('UPDATE storage_walls SET x=0,y=8 WHERE id=?',(self.first,))
        for size in range(2,7):self.extra('size'+str(size),'Brick 1 x '+str(size))
        plan=self.propose();self.assertEqual([w['id'] for w in plan['preview']['walls']],[self.second,self.last,self.first])
        self.assertEqual([d['wall_id'] for d in plan['available']],[self.second]*2+[self.last]*2+[self.first]*2)
        self.assertIsNone(plan['groups'][-1]['drawer_id'])
    def test_one_cabinet_scope_and_all_scope_use_different_capacity(self):
        for size in range(2,5):self.extra('size'+str(size),'Brick 1 x '+str(size))
        single=assignment.propose(self.db,self.first);all_plan=self.propose()
        self.assertEqual(len(single['available']),2);self.assertEqual(len(all_plan['available']),6)
        self.assertEqual(sum(g['drawer_id'] is not None for g in single['groups']),2)
        self.assertTrue(all(g['drawer_id'] is not None for g in all_plan['groups']))
    def test_duplicate_cabinet_names_get_distinct_full_drawer_labels(self):
        self.db.run("UPDATE storage_walls SET name='Meuble'")
        plan=self.propose();labels=[assignment.drawer_label(plan,d) for d in plan['available']]
        self.assertEqual(len(set(labels)),6);self.assertIn('Meuble (1)',labels[0]);self.assertIn('Meuble (2)',labels[2])
    def test_multi_cabinet_apply_and_persistent_undo_are_one_action(self):
        self.extra('middle','Brick 2 x 2');self.extra('long','Brick 1 x 10');before=self.snapshot();stock=self.db.rows('SELECT * FROM stock')
        plan=self.propose(allocate_quantities=True);assignment.apply_proposal(self.db,plan)
        self.assertTrue(walls.wall_contents(self.db,self.first));self.assertTrue(walls.wall_contents(self.db,self.second));self.assertEqual(self.db.rows('SELECT * FROM stock'),stock)
        reopened=Database(self.db.path)
        try:self.assertTrue(reopened.undo_last_action());self.assertEqual(walls.print_snapshot(reopened),before)
        finally:reopened.close()
    def test_error_in_second_cabinet_rolls_back_every_cabinet(self):
        self.extra('middle','Brick 2 x 2');self.extra('long','Brick 1 x 10');plan=self.propose();before=self.snapshot()
        self.db.run("CREATE TRIGGER fail_second BEFORE INSERT ON storage_contents WHEN NEW.drawer_id IN (SELECT id FROM storage_drawers WHERE wall_id="+str(self.second)+") BEGIN SELECT RAISE(ABORT,'refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):assignment.apply_proposal(self.db,plan)
        self.assertEqual(self.snapshot(),before)
    def test_new_cabinet_invalidates_all_cabinet_proposal(self):
        plan=self.propose();walls.create_wall(self.db,'Nouveau',1,1);before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'changé'):assignment.apply_proposal(self.db,plan)
        self.assertEqual(self.snapshot(),before)
    def test_named_empty_and_mixed_drawers_stay_protected_in_all_scope(self):
        tile=self.extra('tile','Tile 1 x 1','Tiles');a=walls.drawers(self.db,self.first)[0];b=walls.drawers(self.db,self.second)[0]
        self.db.run("UPDATE storage_drawers SET name='Réservé' WHERE id=?",(a['id'],));walls.assign(self.db,b['id'],[(self.part,'4'),(tile,'4')])
        plan=self.propose(category='Bricks',reorganize=True)
        self.assertNotIn(a['id'],[d['id'] for d in plan['available']]);self.assertNotIn(b['id'],[d['id'] for d in plan['available']])
        assignment.apply_proposal(self.db,plan);self.assertEqual(len(walls.contents(self.db,b['id'])),2);self.assertEqual(walls.contents(self.db,a['id']),[])
    def test_all_cabinet_reorganisation_moves_known_quantities_without_inflating(self):
        a=walls.drawers(self.db,self.last)[0];walls.assign(self.db,a['id'],[(self.part,'4')]);self.db.run('UPDATE storage_contents SET quantity=20 WHERE drawer_id=?',(a['id'],))
        plan=self.propose(category='Bricks',reorganize=True,allocate_quantities=True);assignment.apply_proposal(self.db,plan)
        self.assertEqual(self.db.rows('SELECT SUM(quantity) AS n FROM storage_contents WHERE item_id=?',(self.part,))[0]['n'],40)
        self.assertEqual(walls.contents(self.db,a['id']),[])
    def test_destination_switch_refreshes_whole_preview_without_writing(self):
        before=self.snapshot();window=self.dialog(self.first);self.assertEqual(len(window.proposal_preview.cabinets),1)
        window.destination.setCurrentIndex(window.destination.findData(None));self.assertEqual(len(window.proposal_preview.cabinets),3)
        self.assertEqual({d['wall_id'] for d in window.plan['available']},{self.first,self.second,self.last});self.assertEqual(self.snapshot(),before)
        window.destination.setCurrentIndex(window.destination.findData(self.second));self.assertEqual(set(window.proposal_preview.cabinets),{self.second})
    def test_all_destination_survives_drawer_selection_and_refresh(self):
        panel=self.keep(StoragePanel(self.db,None));selector=panel.stock_browser
        selector.target_wall.setCurrentIndex(selector.target_wall.findData('all'));panel.choose_drawer(walls.drawers(self.db,self.first)[0]['id']);selector.reload_target_walls(self.second)
        self.assertEqual(selector.target_wall.currentData(),'all')
    def test_category_only_includes_unknown_sizes_and_size_only_crosses_categories(self):
        special=self.extra('special','Special brick');tile=self.extra('tile','Tile 1 x 1','Tiles')
        category=self.propose(criteria=['category']);self.assertEqual(len(category['groups']),2);self.assertEqual(category['unknown'],[])
        self.assertIn((special,'4'),category['groups'][0]['entries'])
        size=self.propose(criteria=['size']);self.assertEqual(set(size['groups'][0]['entries']),{(self.part,'4'),(tile,'4')});self.assertEqual([p['id'] for p in size['unknown']],[special])
    def test_reference_only_and_combined_checks_preserve_reference_identity(self):
        variant=self.extra('3005p01','Brick 1 x 1 with Pattern');special=self.extra('special','Special piece')
        for criteria in (['reference'],['category','reference'],['size','reference'],['category','size','reference']):
            plan=self.propose(criteria=criteria);self.assertEqual(len(plan['groups']),4)
            self.assertTrue(all(len({identity for identity,color in g['entries']})==1 for g in plan['groups']));self.assertEqual(plan['unknown'],[])
            self.assertIn((special,'4'),{entry for g in plan['groups'] for entry in g['entries']})
    def test_all_checkboxes_can_be_combined_and_empty_selection_blocks_apply(self):
        window=self.dialog();window.criteria['reference'].setChecked(True);self.assertEqual(window.plan['criteria'],['category','reference','size'])
        for checkbox in window.criteria.values():checkbox.setChecked(False)
        self.assertIsNone(window.plan);self.assertFalse(window.apply_button.isEnabled());self.assertIn('Coche au moins',window.summary.text())
        window.criteria['category'].setChecked(True);self.assertEqual(window.plan['criteria'],['category'])
    def test_none_or_invalid_criteria_are_not_silently_accepted(self):
        for criteria in ([],['colour'],'reference'):
            with self.assertRaises(ValueError):self.propose(criteria=criteria)
    def test_preview_board_contains_all_cabinets_and_correct_full_address(self):
        window=self.dialog();preview=window.proposal_preview;self.assertEqual(len(preview.cabinets),3)
        second=walls.drawers(self.db,self.second)[0];window.targets[0].setCurrentIndex(window.targets[0].findData(second['id']));preview.open_drawer(second['id'])
        self.assertIn('Haut droite',preview.detail_title.text());self.assertEqual(preview.rows[0]['id'],self.part)


class ReferenceSplitTests(StorageFixture):
    def plan_split(self,count=3,**kwargs):return self.propose(criteria=['reference'],drawer_counts={self.part:count},**kwargs)
    def test_three_drawers_keep_both_colour_totals_and_remainder(self):
        self.db.add('stock',self.part,'1',7);plan=self.plan_split(allocate_quantities=True)
        groups=[g for g in plan['groups'] if (self.part,'4') in g['entries']]
        self.assertEqual(sorted(g['quantities'][(self.part,'4')] for g in groups),[13,13,14]);self.assertEqual(sorted(g['quantities'][(self.part,'1')] for g in groups),[2,2,3]);self.assertEqual(sorted(sum(g['quantities'].values()) for g in groups),[15,16,16])
        assignment.apply_proposal(self.db,plan)
        self.assertEqual({r['color']:r['n'] for r in self.db.rows('SELECT color,SUM(quantity) AS n FROM storage_contents WHERE item_id=? GROUP BY color',(self.part,))},{'1':7,'4':40})
        self.assertEqual(len({row['id'] for row in walls.search(self.db,'3005')}),3)
    def test_unquantified_associations_remain_unknown_in_every_drawer(self):
        plan=self.plan_split();assignment.apply_proposal(self.db,plan)
        self.assertEqual([r['quantity'] for r in self.db.rows('SELECT quantity FROM storage_contents WHERE item_id=?',(self.part,))],[None]*3)
    def test_remaining_stock_excludes_quantities_in_other_drawers(self):
        drawer=walls.drawers(self.db,self.last)[0];walls.assign(self.db,drawer['id'],[(self.part,'4')]);self.db.run('UPDATE storage_contents SET quantity=10 WHERE drawer_id=?',(drawer['id'],))
        plan=self.plan_split(2,allocate_quantities=True);groups=[g for g in plan['groups'] if (self.part,'4') in g['entries']];self.assertEqual([g['quantities'][(self.part,'4')] for g in groups],[15,15])
        assignment.apply_proposal(self.db,plan);self.assertEqual(self.db.rows('SELECT SUM(quantity) AS n FROM storage_contents WHERE item_id=?',(self.part,))[0]['n'],40)
    def test_split_colors_get_the_chosen_count_for_each_color(self):
        self.db.add('stock',self.part,'1',7);plan=self.plan_split(2,split_colors=True,allocate_quantities=True)
        self.assertEqual(len([g for g in plan['groups'] if any(identity==self.part for identity,color in g['entries'])]),4)
        assignment.apply_proposal(self.db,plan);self.assertEqual(self.db.rows('SELECT SUM(quantity) AS n FROM storage_contents WHERE item_id=?',(self.part,))[0]['n'],47)
    def test_partial_split_cannot_silently_drop_pieces(self):
        plan=self.plan_split(allocate_quantities=True);targets=[g['drawer_id'] for g in plan['groups']];targets[next(i for i,g in enumerate(plan['groups']) if (self.part,'4') in g['entries'])]=None;before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'tous les tiroirs'):assignment.apply_proposal(self.db,plan,targets)
        self.assertEqual(self.snapshot(),before)
    def test_insufficient_capacity_blocks_a_partially_assigned_reference(self):
        plan=assignment.propose(self.db,self.first,criteria=['reference'],drawer_counts={self.part:3},allocate_quantities=True);self.assertIsNone(plan['groups'][2]['drawer_id'])
        with self.assertRaisesRegex(ValueError,'tous les tiroirs'):assignment.apply_proposal(self.db,plan)
    def test_skipping_all_split_rows_keeps_that_reference_unlocated(self):
        plan=self.plan_split(allocate_quantities=True);targets=[None if (self.part,'4') in g['entries'] else g['drawer_id'] for g in plan['groups']]
        assignment.apply_proposal(self.db,plan,targets);self.assertEqual(walls.search(self.db,'3005'),[]);self.assertTrue(walls.search(self.db,'3001'))
    def test_preview_quantities_equal_persisted_contents_and_undo_restores_all(self):
        plan=self.plan_split(allocate_quantities=True);targets=[g['drawer_id'] for g in plan['groups']];snap=proposal_snapshot(plan,targets);before=self.snapshot();stock=self.db.rows('SELECT * FROM stock')
        assignment.apply_proposal(self.db,plan)
        for target in targets:self.assertEqual([(p['id'],p['chosen_color'],p['stored_quantity']) for p in walls.contents(self.db,target)],[(p['id'],p['chosen_color'],p['stored_quantity']) for p in snap['contents'][target]])
        self.assertEqual(self.db.rows('SELECT * FROM stock'),stock);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.snapshot(),before)
    def test_catalogue_split_never_claims_owned_quantities(self):
        plan=assignment.propose(self.db,None,entries=[(self.part,'')],from_catalogue=True,criteria=['reference'],drawer_counts={self.part:3});assignment.apply_proposal(self.db,plan)
        self.assertEqual([r['quantity'] for r in self.db.rows('SELECT quantity FROM storage_contents')],[None]*3)
    def test_count_configuration_is_per_reference_and_cancel_preserves_plan(self):
        window=self.dialog();before=self.snapshot()
        with patch.object(ReferenceDrawerCountsDialog,'exec',return_value=QDialog.DialogCode.Rejected):window.choose_drawer_counts()
        self.assertEqual(window.drawer_counts,{});self.assertEqual(self.snapshot(),before)
        with patch.object(ReferenceDrawerCountsDialog,'exec',return_value=QDialog.DialogCode.Accepted),patch.object(ReferenceDrawerCountsDialog,'counts',return_value={self.part:3}):window.choose_drawer_counts()
        self.assertTrue(window.criteria['reference'].isChecked());self.assertEqual(len([g for g in window.plan['groups'] if (self.part,'4') in g['entries']]),3)
        window.criteria['reference'].setChecked(False);self.assertEqual(window.drawer_counts,{})
    def test_negative_fractional_or_excessive_drawer_counts_are_rejected(self):
        for count in (0,-1,1.5,True,1001):
            with self.assertRaises(ValueError):self.plan_split(count)
    def test_split_is_explicitly_reference_based(self):
        with self.assertRaisesRegex(ValueError,'Coche Référence'):self.propose(criteria=['category'],drawer_counts={self.part:2})


class StorageThumbnailTests(Fixture):
    def test_table_uses_shared_real_thumbnail_and_stops_loading_on_close(self):
        root=Path(self.temp.name)/'ldraw';(root/'parts').mkdir(parents=True)
        (root/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
        for ref in ('3005','3001'):(root/'parts'/f'{ref}.dat').write_text('0 Brick test\n4 16 -10 0 -10 10 0 -10 10 0 10 -10 0 10\n4 16 -10 20 -10 10 20 -10 10 20 10 -10 20 10\n')
        self.db.set_setting('ldraw',str(root));self.db.run("UPDATE items SET category='Bricks'");wall=walls.create_wall(self.db,'Meuble',2,2);engine=VisualEngine(self.db)
        try:
            parent=self.keep(StoragePanel(self.db,engine));window=self.keep(StoragePlanDialog(self.db,wall,parent,allocate_quantities=True));window.show();app.processEvents()
            wait(lambda:len(window.thumbs.applied)==2 and not window.thumbs.running)
            self.assertFalse(window.table.item(0,5).icon().isNull());self.assertEqual(window.table.item(0,6).text(),'40');self.assertEqual(window.table.horizontalHeader().visualIndex(5),0)
            window.resize(800,540);app.processEvents();self.assertLessEqual(window.width(),800);self.assertLessEqual(window.height(),540)
            self.assertTrue(window.rect().contains(window.split_references.mapTo(window,window.split_references.rect().center())));self.assertGreater(window.proposal_preview.view.viewport().height(),90)
            window.reject();self.assertFalse(window.thumbs.active)
        finally:engine.close()
