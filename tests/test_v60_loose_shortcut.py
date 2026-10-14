"""Direct loose-only selection restores transferred inventories without set parts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import csv,io,json,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QDialog,QLabel
from atelier.data import Database,normalize
from atelier.stock_filter import StockFilterDialog,select_all_loose_stock
from atelier.build_stock import BuildStockDialog,InventoryReader,find_builds
from atelier.stock_mocs import StockMocsDialog
from atelier.catalogue import Catalogue
from atelier.dialogs import RelationsDialog
from atelier import projects

app=QApplication.instance() or QApplication([])

class LooseShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'stock.sqlite');self.widgets=[]
        self.db.run("INSERT INTO colors VALUES(4,'Rouge','FF0000',0)")
        self.part=self.item('part','3005','Brick 1 x 1')
        self.set=self.item('set','100-1','Test set')
        self.db.run("INSERT INTO inventories VALUES(1,1,'100-1')")
        self.db.run("INSERT INTO inventory_parts VALUES(1,'3005',4,5,0,'')")
        self.db.add('stock',self.part,'4',40)
        self.db.add('stock_sets',self.set,quantity=1)
        self.loose_id=self.db.rows('SELECT id FROM stock WHERE item_id=?',(self.part,))[0]['id']
        self.set_id=-self.db.rows('SELECT id FROM stock_sets')[0]['id']
    def tearDown(self):
        for widget in reversed(self.widgets):widget.close();widget.deleteLater()
        app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.db.close();self.tmp.cleanup()
    def keep(self,widget):self.widgets.append(widget);return widget
    def item(self,kind,ref,name):
        return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('RB',kind,ref,name,normalize(ref+' '+name)))
    def snapshot(self):
        return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','project_parts','action_history','storage_contents')}
    @staticmethod
    def immediate(owner,work,done,fail=None,*_):done(work(lambda *_:None))
    def test_direct_choice_clears_loose_exclusions_and_preserves_possession(self):
        self.db.set_setting('build_excluded_entries',[self.loose_id,self.set_id])
        before=self.snapshot();revision=self.db.stock_revision()
        select_all_loose_stock(self.db)
        self.assertFalse(self.db.setting('build_include_set_stock'))
        self.assertEqual(self.db.setting('build_excluded_entries'),[self.set_id])
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.db.stock_revision(),revision)
        with self.db.read() as c:self.assertEqual(sum(InventoryReader(c,ignore_colors=True,include_set_stock=False).stock().values()),40)
        reopened=Database(self.db.path)
        self.assertFalse(reopened.setting('build_include_set_stock'));self.assertEqual(reopened.setting('build_excluded_entries'),[self.set_id]);reopened.close()
    def test_picker_action_checks_hidden_loose_rows_and_clears_table_search(self):
        fig=self.item('minifig','fig-test','Figure');self.db.add('stock',fig,'',1)
        loose_ids=[r['id'] for r in self.db.rows('SELECT id FROM stock')]
        self.db.set_setting('build_excluded_entries',loose_ids+[self.set_id])
        picker=self.keep(StockFilterDialog(self.db));picker.search.setText('set');picker.loose_only.click()
        self.assertEqual(picker.search.text(),'');self.assertFalse(picker.include_sets.isChecked())
        for i,row in enumerate(picker.rows):
            if row['kind']=='set':
                self.assertFalse(picker.table.item(i,0).flags()&Qt.ItemFlag.ItemIsEnabled)
                self.assertEqual(picker.table.item(i,0).checkState(),Qt.CheckState.Unchecked)
            else:self.assertEqual(picker.table.item(i,0).checkState(),Qt.CheckState.Checked)
        picker.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertEqual(self.db.setting('build_excluded_entries'),[self.set_id])
    def test_cancelling_picker_keeps_original_choices(self):
        self.db.set_setting('build_excluded_entries',[self.loose_id,self.set_id])
        picker=self.keep(StockFilterDialog(self.db));picker.loose_only.click();picker.reject()
        self.assertTrue(self.db.setting('build_include_set_stock',True))
        self.assertEqual(self.db.setting('build_excluded_entries'),[self.loose_id,self.set_id])
    def test_main_button_runs_search_once_with_current_criteria(self):
        self.db.add('stock',self.part,'4',5)
        self.db.set_setting('build_excluded_entries',[self.loose_id,self.set_id])
        with patch('atelier.build_stock.async_task',side_effect=self.immediate):
            window=self.keep(BuildStockDialog(self.db));window.minimum.setValue(1);window.copies.setValue(9);window.ignore.setChecked(True);window.search.setText('100-1')
            with patch.object(window,'start',wraps=window.start) as search:window.loose_only.click();search.assert_called_once()
        self.assertEqual(window.results[0]['percent'],100);self.assertEqual(window.detail_rows[0][-2:],(45,0))
        self.assertFalse(window.last_include_sets);self.assertTrue(window.last_ignore);self.assertEqual(window.last_copies,9)
        self.assertEqual(window.minimum.value(),1);self.assertEqual(window.search.text(),'100-1')
    def test_button_disabled_while_running_and_restored_on_failure(self):
        tasks=[]
        with patch('atelier.build_stock.async_task',side_effect=lambda *args:tasks.append(args)):
            window=self.keep(BuildStockDialog(self.db));window.start()
            self.assertFalse(window.loose_only.isEnabled());window.use_loose_stock()
            self.assertTrue(self.db.setting('build_include_set_stock',True));self.assertEqual(len(tasks),1)
            tasks[0][3]('Test error');self.assertTrue(window.loose_only.isEnabled());self.assertFalse(window.busy)
    def test_future_sets_excluded_and_transferred_set_inventory_remains_loose(self):
        select_all_loose_stock(self.db);self.db.add('stock_sets',self.set,quantity=1)
        self.assertEqual(find_builds(self.db,ignore_colors=True,copies=10,minimum=0,include_set_stock=False)[0][0]['missing'],10)
        eid=abs(self.set_id);self.db.remove('stock_sets',[eid])
        result=find_builds(self.db,ignore_colors=True,copies=10,include_set_stock=False)[0][0]
        self.assertEqual(result['percent'],100);self.assertFalse(self.db.rows('SELECT * FROM stock_sets'))
    def test_moc_window_reads_updated_loose_choices_after_it_was_opened(self):
        self.db.add('stock',self.part,'4',5);self.db.set_setting('api_rb','test-key')
        self.db.set_setting('build_excluded_entries',[self.loose_id])
        window=self.keep(StockMocsDialog(self.db,None,[self.loose_id]))
        select_all_loose_stock(self.db)
        with patch('atelier.stock_mocs.async_task',side_effect=self.immediate),patch('atelier.stock_mocs.fetch_alternates',return_value=([],None,0)) as fetch:
            window.start();fetch.assert_called_once();self.assertEqual(window.sets[0]['ref'],'100-1')
    def test_loose_shortcut_preserves_reservations_and_reports_actual_missing(self):
        project=projects.create(self.db,'Reserved pieces',[{'item_id':self.part,'color':'4','quantity':3}])
        projects.reserve(self.db,project);self.db.set_setting('build_excluded_entries',[self.loose_id])
        before=self.snapshot();select_all_loose_stock(self.db)
        self.assertEqual(self.snapshot(),before)
        row=find_builds(self.db,copies=8,minimum=1,include_set_stock=False)[0][0]
        self.assertEqual(row['missing'],3);self.assertEqual(row['percent'],92.5)
    def inventory_window(self):
        window=self.keep(QDialog());window.db=self.db;window.active_set=self.db.get_item(self.set)
        window.parts=self.db.components(window.active_set);window.progress_label=QLabel(window);return window
    def test_incomplete_catalogue_cannot_silently_add_partial_inventory(self):
        self.db.run("INSERT INTO inventory_parts VALUES(1,'missing-part',4,2,0,'')")
        window=self.inventory_window();self.assertEqual(len(window.parts),1);before=self.snapshot()
        with patch('atelier.dialogs.QMessageBox.warning') as warning:RelationsDialog.add_parts(window,'stock',True)
        self.assertEqual(self.snapshot(),before);warning.assert_called_once()
        self.assertIn('missing-part',warning.call_args.args[-1])
    def test_changed_inventory_requires_reopening_before_full_add(self):
        window=self.inventory_window();self.db.run('UPDATE inventory_parts SET quantity=6 WHERE inventory_id=1');before=self.snapshot()
        with patch('atelier.dialogs.QMessageBox.warning') as warning:RelationsDialog.add_parts(window,'stock',True)
        self.assertEqual(self.snapshot(),before);self.assertIn('Rouvre',warning.call_args.args[-1])
    def test_minifigure_composition_can_still_be_added_in_full(self):
        figure=self.item('minifig','fig-legacy','Legacy figure')
        window=self.inventory_window();window.active_set=self.db.get_item(figure)
        with patch('atelier.dialogs.QMessageBox.warning') as warning:RelationsDialog.add_parts(window,'stock',True)
        warning.assert_not_called()
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE id=?',(self.loose_id,))[0]['quantity'],45)
    def test_classic_inventories_10696_and_10698_added_by_catalogue_are_found(self):
        resources=Path(__file__).resolve().parent.parent/'ressources'
        def records(name):
            with ZipFile(resources/(name+'.csv.zip')) as z:
                with z.open(z.namelist()[0]) as f:yield from csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))
        refs={'10696-1','10698-1'};inventories=[r for r in records('inventories') if r['set_num'] in refs]
        ids={r['id'] for r in inventories};parts=[r for r in records('inventory_parts') if r['inventory_id'] in ids]
        part_refs={r['part_num'] for r in parts};classic=Database(Path(self.tmp.name)/'classic.sqlite')
        with classic.connect() as c:
            c.executemany('INSERT INTO inventories VALUES(?,?,?)',[(r['id'],r['version'],r['set_num']) for r in inventories])
            c.executemany('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',[(r['inventory_id'],r['part_num'],r['color_id'],r['quantity'],int(r['is_spare'].lower() in ('true','1')),r['img_url']) for r in parts])
            for r in records('parts'):
                if r['part_num'] in part_refs:c.execute('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('RB','part',r['part_num'],r['name'],normalize(r['part_num']+' '+r['name'])))
            for r in records('sets'):
                if r['set_num'] in refs:c.execute('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('RB','set',r['set_num'],r['name'],normalize(r['set_num']+' '+r['name'])))
        catalogue=self.keep(Catalogue(classic,'RB','set'))
        with patch.object(catalogue,'selection',return_value=classic.rows("SELECT * FROM items WHERE kind='set'")):catalogue.add_selected('set_parts_stock')
        classic.set_setting('build_excluded_entries',[r['id'] for r in classic.rows('SELECT id FROM stock')])
        classic.set_setting('build_include_set_stock',False)
        self.assertEqual(find_builds(classic,minimum=1,ignore_colors=True,include_set_stock=False,excluded_entries=classic.setting('build_excluded_entries'))[0],[])
        with patch('atelier.build_stock.async_task',side_effect=self.immediate):
            window=self.keep(BuildStockDialog(classic));window.minimum.setValue(1);window.ignore.setChecked(True);window.loose_only.click()
        self.assertEqual({r['ref'] for r in window.results},refs)
        self.assertTrue(all(r['percent']==100 and r['missing']==0 for r in window.results))
        self.assertEqual(classic.rows('SELECT SUM(quantity) AS n FROM stock')[0]['n'],1299)
        # A single complete 10698 inventory must also match in exact colours.
        with classic.connect() as c:c.execute('DELETE FROM stock')
        chosen=classic.rows("SELECT * FROM items WHERE kind='set' AND ref='10698-1'")[0]
        with patch.object(catalogue,'selection',return_value=[chosen]):catalogue.add_selected('set_parts_stock')
        excluded=[r['id'] for r in classic.rows("SELECT s.id FROM stock s JOIN items i ON i.id=s.item_id WHERE i.ref IN ('87697','98138pr0008')")]
        self.assertEqual(len(excluded),2);classic.set_setting('build_excluded_entries',excluded)
        partial=next(r for r in find_builds(classic,minimum=1,include_set_stock=False,excluded_entries=excluded)[0] if r['ref']=='10698-1')
        self.assertEqual(partial['missing'],8);self.assertEqual(round(partial['percent'],1),99)
        with patch('atelier.build_stock.async_task',side_effect=self.immediate):
            window.ignore.setChecked(False);window.loose_only.click()
        row=next(r for r in window.results if r['ref']=='10698-1')
        self.assertEqual((row['percent'],row['missing']),(100,0))
        window.close();catalogue.close();classic.close()

if __name__=='__main__':unittest.main()
