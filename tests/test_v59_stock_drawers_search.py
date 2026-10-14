"""Regression scenarios for loose-only builds, split drawers and excluded words."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QSpinBox,QDialog
from atelier.data import Database
from atelier.build_stock import find_builds,build_details,InventoryReader,BuildStockDialog
from atelier.stock_filter import StockFilterDialog
from atelier.stock_mocs import StockMocsDialog
from atelier.storage_panel import StoragePanel
from atelier import storage_wall as walls,storage_quantities as quantities
from atelier.catalogue import Catalogue
from atelier.search_filters import FilterDialog

app=QApplication.instance() or QApplication([])

class V59Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'db.sqlite');self.widgets=[]
        self.db.run("INSERT INTO colors VALUES(4,'Rouge','FF0000',0)")
        self.db.run("INSERT INTO colors VALUES(1,'Bleu','0000FF',0)")
        self.part=self.item('part','3005','Brick 1 x 1','Bricks')
        self.set=self.item('set','100-1','Test set','Test theme')
        self.db.run("INSERT INTO inventories VALUES(1,1,'100-1')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',4,5,0,'')")
        self.db.add('stock',self.part,'4',40)
        self.wall=walls.create_wall(self.db,'Briques',3,2);self.drawers=[r['id'] for r in walls.drawers(self.db,self.wall)]
    def tearDown(self):
        for w in reversed(self.widgets):w.close();w.deleteLater()
        app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.db.close();self.tmp.cleanup()
    def keep(self,w):self.widgets.append(w);return w
    def item(self,kind,ref,name,category='',source='RB'):
        return self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',(source,kind,ref,name,category,(ref+' '+name+' '+category).lower()))
    def count(self,drawer,item=None,color='4'):
        rows=self.db.rows('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer,item or self.part,color))
        return rows[0]['quantity'] if rows else None
    def place(self,drawer,quantity,item=None,color='4'):
        quantities.put_entry(self.db,drawer,item or self.part,color,quantity)
    def snapshot(self):
        return (self.db.rows('SELECT * FROM stock ORDER BY id'),self.db.rows('SELECT * FROM storage_contents ORDER BY drawer_id,item_id,color'),self.db.rows('SELECT * FROM action_history ORDER BY id'))
    @staticmethod
    def immediate(owner,work,done,*_):done(work(lambda *_:None))
    def test_loose_only_uses_no_owned_set_components(self):
        self.db.add('stock_sets',self.set,quantity=1)
        full=find_builds(self.db,copies=9)[0];self.assertEqual(full[0]['percent'],100)
        self.assertEqual(find_builds(self.db,copies=9,include_set_stock=False)[0],[])
        row=find_builds(self.db,copies=9,minimum=0,include_set_stock=False)[0][0];self.assertEqual(row['missing'],5)
        detail=build_details(self.db,self.db.get_item(self.set),copies=9,include_set_stock=False)[0][0]
        self.assertEqual(detail[-2:],(40,5))
    def test_global_exclusion_also_covers_new_sets_and_untracked_sets(self):
        self.db.add('stock_sets',self.set,quantity=1)
        unknown=-self.db.run("INSERT INTO stock_sets(item_id,color,quantity) VALUES(?,'x',1)",(self.set,))
        with self.db.connect() as c:
            value=InventoryReader(c,excluded_entries=[unknown],include_set_stock=False).stock()
        self.assertEqual(sum(value.values()),40)
    def test_filter_shows_loose_quantities_and_preserves_individual_set_choices(self):
        self.db.add('stock_sets',self.set,quantity=1)
        sid=-self.db.rows('SELECT id FROM stock_sets')[0]['id'];self.db.set_setting('build_excluded_entries',[sid])
        d=self.keep(StockFilterDialog(self.db));d.include_sets.setChecked(False)
        p=next(i for i,r in enumerate(d.rows) if r['kind']=='part')
        self.assertEqual(d.table.item(p,6).text(),'40')
        s=next(i for i,r in enumerate(d.rows) if r['kind']=='set')
        self.assertFalse(d.table.item(s,0).flags()&Qt.ItemFlag.ItemIsEnabled)
        d.set_visible(Qt.CheckState.Checked);d.save()
        self.assertFalse(self.db.setting('build_include_set_stock'));self.assertEqual(self.db.setting('build_excluded_entries'),[sid])
        again=self.keep(StockFilterDialog(Database(self.db.path)));again.include_sets.setChecked(True)
        self.assertEqual(again.table.item(s,0).checkState(),Qt.CheckState.Unchecked)
    def test_cancelling_stock_filter_does_not_save_the_mode(self):
        d=self.keep(StockFilterDialog(self.db));d.include_sets.setChecked(False);d.reject()
        self.assertTrue(self.db.setting('build_include_set_stock',True))
    def test_build_details_keep_the_selected_mode_snapshot(self):
        self.db.add('stock_sets',self.set,quantity=1);self.db.set_setting('build_include_set_stock',False)
        with patch('atelier.build_stock.async_task',side_effect=self.immediate):
            d=self.keep(BuildStockDialog(self.db));d.minimum.setValue(0);d.copies.setValue(9);d.start()
            self.assertEqual(d.detail_rows[0][-2:],(40,5))
            self.db.set_setting('build_include_set_stock',True);d.detail()
            self.assertEqual(d.detail_rows[0][-2:],(40,5))
    def test_mocs_use_the_saved_loose_only_mode(self):
        sid=self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.part,))[0]['id']
        self.db.change_entries('stock',[sid],'quantity',4);self.db.add('stock_sets',self.set,quantity=1)
        self.db.set_setting('build_include_set_stock',False);self.db.set_setting('api_rb','test-key')
        with patch('atelier.stock_mocs.async_task',side_effect=self.immediate),patch('atelier.stock_mocs.fetch_alternates') as api:
            d=self.keep(StockMocsDialog(self.db,None,[]));d.start();self.assertEqual(d.sets,[]);api.assert_not_called()
    def test_partial_transfer_40_to_20_keeps_stock_and_colors(self):
        a,b=self.drawers[:2];self.place(a,40);self.db.add('stock',self.part,'1',10);self.place(a,10,color='1');before=self.db.rows('SELECT * FROM stock ORDER BY id')
        quantities.transfer_entries(self.db,a,b,[(self.part,'4',20,40)])
        self.assertEqual((self.count(a),self.count(b),self.count(a,color='1')),(20,20,10))
        self.assertEqual(self.db.rows('SELECT * FROM stock ORDER BY id'),before)
        self.assertTrue(self.db.undo_last_action());self.assertEqual((self.count(a),self.count(b)),(40,None))
        self.assertTrue(self.db.redo_last_action());self.assertEqual((self.count(a),self.count(b)),(20,20))
    def test_full_transfer_removes_origin_and_merges_destination(self):
        a,b=self.drawers[:2];self.place(a,30);self.place(b,10)
        quantities.transfer_entries(self.db,a,b,[(self.part,'4',30,30)])
        self.assertEqual((self.count(a),self.count(b)),(None,40))
    def test_stale_transfer_refuses_without_partial_updates(self):
        a,b=self.drawers[:2];self.place(a,40)
        quantities.set_quantity(self.db,a,self.part,'4',39);before=self.snapshot()
        with self.assertRaises(ValueError):quantities.transfer_entries(self.db,a,b,[(self.part,'4',20,40)])
        self.assertEqual(self.snapshot(),before)
    def test_batch_transfer_is_atomic_if_a_later_reference_changed(self):
        a,b=self.drawers[:2];self.place(a,40);other=self.item('part','3001','Brick 2 x 4')
        self.db.add('stock',other,'4',5);self.place(a,5,other);before=self.snapshot()
        with self.assertRaises(ValueError):quantities.transfer_entries(self.db,a,b,[(self.part,'4',20,40),(other,'4',2,6)])
        self.assertEqual(self.snapshot(),before)
    def test_unknown_count_can_move_without_becoming_zero(self):
        a,b=self.drawers[:2];self.place(a,None)
        quantities.transfer_entries(self.db,a,b,[(self.part,'4',None,None)])
        self.assertEqual(walls.contents(self.db,a),[]);self.assertIsNone(walls.contents(self.db,b)[0]['stored_quantity'])
    def test_real_drop_opens_quantity_choice_then_moves_20(self):
        a,b=self.drawers[:2];self.place(a,40);panel=self.keep(StoragePanel(self.db,None));panel.activate_wall(self.wall)
        self.assertTrue(panel.drop_parts(b,{'origin':a,'entries':[(self.part,'4')]}))
        dialogs=[d for d in panel.findChildren(QDialog) if d.windowTitle()=='Quantités à déplacer'];self.assertEqual(len(dialogs),1)
        d=dialogs[0];d.findChildren(QSpinBox)[0].setValue(20);d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual((self.count(a),self.count(b)),(20,20))
        self.assertEqual(sum(r['quantity'] for r in self.db.rows('SELECT * FROM stock')),40)
    def test_cancelled_drop_changes_neither_drawer_nor_history(self):
        a,b=self.drawers[:2];self.place(a,40);panel=self.keep(StoragePanel(self.db,None));before=self.snapshot()
        panel.drop_parts(b,{'origin':a,'entries':[(self.part,'4')]})
        d=next(d for d in panel.findChildren(QDialog) if d.windowTitle()=='Quantités à déplacer');d.reject()
        self.assertEqual(self.snapshot(),before)
    def test_addition_updates_one_fully_counted_drawer_and_undo_both(self):
        a=self.drawers[0];self.place(a,40);self.db.add('stock',self.part,'4',10)
        self.assertEqual(self.count(a),50);self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],50)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(self.count(a),40);self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],40)
        self.assertTrue(self.db.redo_last_action());self.assertEqual(self.count(a),50)
    def test_split_drawers_do_not_duplicate_new_stock(self):
        a,b=self.drawers[:2];self.place(a,20);self.place(b,20);self.db.add('stock',self.part,'4',10)
        self.assertEqual((self.count(a),self.count(b)),(20,20))
        with self.db.read() as c:self.assertEqual(quantities.available(c,self.part,'4'),10)
    def test_partial_or_unknown_counts_are_not_overwritten_by_stock_additions(self):
        a=self.drawers[0];self.place(a,20);self.db.add('stock',self.part,'4',10);self.assertEqual(self.count(a),20)
        quantities.set_quantity(self.db,a,self.part,'4',0)
        self.db.run('UPDATE storage_contents SET quantity=NULL');self.db.add('stock',self.part,'4',5);self.assertIsNone(self.count(a))
    def test_set_components_do_not_update_loose_drawer_count(self):
        a=self.drawers[0];self.place(a,40);self.db.add('stock_sets',self.set,quantity=1)
        self.assertEqual(self.count(a),40)
    def test_refresh_shows_the_new_physical_count(self):
        a=self.drawers[0];self.place(a,40);panel=self.keep(StoragePanel(self.db,None));panel.show();app.processEvents();panel.choose_drawer(a)
        self.db.add('stock',self.part,'4',10);panel.refresh()
        self.assertEqual(panel.rows[0]['stored_quantity'],50)
        self.assertEqual(panel.items[a].parts[0]['stored_quantity'],50)
    def test_negative_words_work_with_and_without_the_index(self):
        plain=self.item('part','x1','Brick standard','Bricks')
        modulex=self.item('part','x2','Brick Modulex','Bricks')
        category=self.item('part','x3','Brick special','Modulex')
        duplo=self.item('part','x4','Brick Duplo','Bricks')
        for indexed in (True,False):
            self.db.search_index_available=indexed
            ids={r['id'] for r in self.db.query(search='brick -modulex -duplo',advanced={'categories':['Bricks','Modulex']})[0]}
            self.assertIn(plain,ids);self.assertFalse({modulex,category,duplo}&ids)
    def test_negative_word_only_keeps_unrelated_rows_and_null_themes(self):
        modulex=self.item('part','modulex-1','Modulex brick')
        neutral=self.item('set','75192-1','Falcon')
        self.db.run('UPDATE items SET category_id=NULL WHERE id=?',(neutral,))
        for indexed in (True,False):
            self.db.search_index_available=indexed
            ids={r['id'] for r in self.db.query(search='-modulex')[0]}
            self.assertNotIn(modulex,ids);self.assertIn(neutral,ids)
            self.assertEqual(self.db.query(search='75192-1')[0][0]['id'],neutral)
    def test_negative_wildcards_stay_literal(self):
        wildcard=self.item('part','x5','Brick 50%')
        ordinary=self.item('part','x6','Brick 50')
        for indexed in (True,False):
            self.db.search_index_available=indexed
            ids={r['id'] for r in self.db.query(search='brick -50%')[0]}
            self.assertNotIn(wildcard,ids);self.assertIn(ordinary,ids)
    def test_advanced_filter_keeps_and_applies_exclusion_text(self):
        self.item('part','x7','Brick Modulex','Bricks')
        cat=self.keep(Catalogue(self.db,'RB','part'));dialog=self.keep(FilterDialog(cat));dialog.search.setText('brick -modulex')
        cat.apply_filter_state(dialog.state())
        self.assertEqual(cat.total,1);self.assertEqual(cat.rows[0]['id'],self.part)

if __name__=='__main__':unittest.main()

