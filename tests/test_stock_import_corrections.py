"""Resume real mixed files, correct sorted rows and undo without duplicate stock."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QThreadPool
from PySide6.QtWidgets import QApplication,QPushButton
from atelier.data import Database
from atelier import stock_import_jobs as imports
from atelier.stock_import import resolve_rows
from atelier.stock_import_dialog import StockImportDialog,ImportItemPicker
from atelier.ui_common import STYLE
from atelier.app import MainWindow,NAV
from atelier import storage_wall,i18n

app=QApplication.instance() or QApplication([])


class ImportCorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=Database(self.root/'data.sqlite');self.windows=[]
        self.part=self.item('RB','part','3001');self.other=self.item('RB','part','3005');self.bl=self.item('BL','part','3001')
        self.set=self.item('RB','set','100-1');self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)")
        self.db.run("INSERT INTO inventories VALUES(1,1,'100-1')");self.db.run("INSERT INTO inventory_parts VALUES(1,'3001',4,5,0,'')")

    def tearDown(self):
        for window in reversed(self.windows):window.close();window.deleteLater()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents();self.db.close();self.temp.cleanup();i18n.set_language('fr')

    def item(self,source,kind,ref):return self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,kind,ref,'Name '+ref,ref))
    def keep(self,window):self.windows.append(window);return window
    def file(self,body):
        path=self.root/'collection.csv';path.write_text('Part,Color,Quantity\n'+body,encoding='utf-8');return path
    def quantity(self,item):
        rows=self.db.rows('SELECT SUM(quantity) AS n FROM stock WHERE item_id=?',(item,));return rows[0]['n'] or 0
    def mixed(self):return imports.create_job(self.db,self.file('3001,4,2\nmissing,4,3\n'))
    def correct(self,job,ordinal=2,**changes):
        row=next(row for row in imports.job_rows(self.db,job) if row['ordinal']==ordinal);imports.update_row(self.db,job,ordinal,dict(row,**changes))

    def test_partial_import_survives_restart_without_original_file(self):
        job=self.mixed();self.assertEqual(imports.import_ready(self.db,job),{'imported':1,'pending':1});self.file('').unlink()
        self.db.close();self.db=Database(self.root/'data.sqlite');rows=imports.job_rows(self.db,job)
        self.assertEqual([(r['ref'],r['imported']) for r in rows],[('3001',True),('missing',False)]);self.assertEqual(rows[1]['original']['Part'],'missing')
        self.correct(job,ref='3001',quantity='3');self.assertEqual(imports.import_ready(self.db,job)['imported'],1);self.assertEqual(self.quantity(self.part),5)
        self.assertEqual(imports.import_ready(self.db,job),{'imported':0,'pending':0});self.assertEqual(self.quantity(self.part),5);self.assertEqual(imports.jobs(self.db),[])

    def test_bad_quantity_colour_and_reference_stay_pending(self):
        job=imports.create_job(self.db,self.file('3001,4,2\n3005,4,-1\n3001,99999,3\n../bad,4,2\n'))
        result=imports.import_ready(self.db,job);self.assertEqual(result,{'imported':1,'pending':3});self.assertEqual(self.quantity(self.part),2)
        self.correct(job,2,quantity='7');self.correct(job,3,color='4');self.correct(job,4,ref='3005');self.assertEqual(imports.import_ready(self.db,job)['imported'],3)
        self.assertEqual((self.quantity(self.part),self.quantity(self.other)),(5,9))

    def test_rebrickable_native_column_names_are_detected(self):
        path=self.root/'native.csv';path.write_text('part_num,color_id,quantity\n3001,4,2\n')
        job=imports.create_job(self.db,path);self.assertEqual(imports.job_rows(self.db,job)[0]['source'],'RB');imports.import_ready(self.db,job);self.assertEqual(self.quantity(self.part),2)

    def test_bricklink_ids_are_kept_in_their_own_palette(self):
        path=self.root/'list.xml';path.write_text('<INVENTORY><ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>3001</ITEMID><COLOR>4</COLOR><MINQTY>3</MINQTY></ITEM><ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>3001</ITEMID><COLOR>99999</COLOR><MINQTY>1</MINQTY></ITEM></INVENTORY>')
        job=imports.create_job(self.db,path);self.assertEqual(imports.import_ready(self.db,job),{'imported':1,'pending':1})
        self.assertEqual(self.db.rows('SELECT item_id,color,quantity FROM stock WHERE quantity>0'),[{'item_id':self.bl,'color':'4','quantity':3}]);self.assertEqual(self.quantity(self.part),0)

    def test_unsupported_xml_type_is_preserved_for_correction(self):
        path=self.root/'list.xml';path.write_text('<INVENTORY><ITEM><ITEMTYPE>B</ITEMTYPE><ITEMID>3001</ITEMID><MINQTY>2</MINQTY></ITEM></INVENTORY>')
        job=imports.create_job(self.db,path);self.assertEqual(imports.import_ready(self.db,job)['pending'],1)
        self.correct(job,1,kind='part',color='4');imports.import_ready(self.db,job);self.assertEqual(self.quantity(self.bl),2)

    def test_set_with_missing_inventory_does_not_block_known_parts(self):
        self.item('RB','set','200-1');path=self.root/'mixed.csv';path.write_text('Type,Part,Set,Color,Quantity\nP,3001,,4,2\nS,,200-1,,2\n')
        job=imports.create_job(self.db,path);self.assertEqual(imports.import_ready(self.db,job),{'imported':1,'pending':1})
        self.db.run("INSERT INTO inventories VALUES(2,1,'200-1')");self.db.run("INSERT INTO inventory_parts VALUES(2,'3001',4,5,0,'')")
        self.assertEqual(imports.import_ready(self.db,job)['imported'],1);self.assertEqual(self.quantity(self.part),12)

    def test_stock_and_import_markers_roll_back_together(self):
        job=imports.create_job(self.db,self.file('3001,4,2\n3005,4,3\n'))
        self.db.run(f"CREATE TRIGGER stop_import BEFORE INSERT ON stock WHEN NEW.item_id={self.other} BEGIN SELECT RAISE(ABORT,'cannot write'); END")
        with self.assertRaises(sqlite3.IntegrityError):imports.import_ready(self.db,job)
        self.assertEqual(self.quantity(self.part),0);self.assertFalse(any(row['imported'] for row in imports.job_rows(self.db,job)))
        self.db.run('DROP TRIGGER stop_import');self.assertEqual(imports.import_ready(self.db,job)['imported'],2)

    def test_partial_personal_inventory_reuses_the_same_target(self):
        job=self.mixed();imports.update_destination(self.db,job,'stock_sets',name='Mes briques');imports.import_ready(self.db,job)
        entry=self.db.rows('SELECT * FROM stock_sets')[0]['id'];self.correct(job,ref='3005',quantity='3');imports.import_ready(self.db,job)
        self.assertEqual(len(self.db.rows('SELECT * FROM stock_sets')),1);self.assertEqual(self.db.rows('SELECT * FROM stock_sets')[0]['id'],entry)
        self.assertEqual([(r['ref'],r['chosen_quantity']) for r in self.db.owned_components(entry)],[('3001',2),('3005',3)]);self.assertEqual(self.quantity(self.part),0)

    def test_undo_restores_pending_rows_and_new_inventory_destination(self):
        job=self.mixed();imports.update_destination(self.db,job,'stock_sets',name='Mes briques');imports.import_ready(self.db,job)
        self.assertTrue(self.db.undo_last_action());self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
        self.assertIsNone(self.db.rows('SELECT target_entry FROM stock_import_jobs WHERE id=?',(job,))[0]['target_entry']);self.assertFalse(any(r['imported'] for r in imports.job_rows(self.db,job)))
        imports.import_ready(self.db,job);self.assertEqual(len(self.db.rows('SELECT * FROM stock_sets')),1)

    def test_corrected_parts_can_be_named_after_only_sets_were_imported(self):
        path=self.root/'mixed.csv';path.write_text('Type,Part,Set,Color,Quantity\nS,,100-1,,1\nP,missing,,4,2\n')
        window=self.keep(StockImportDialog(self.db,destination='stock_sets'));window.path=path;window.load();window.commit.click()
        self.assertFalse(window.destination.isEnabled());self.assertTrue(window.name.isEnabled());self.assertTrue(window.target.isEnabled())
        window.edit_ref.setText('3005');window.save_correction();self.assertFalse(window.commit.isEnabled());window.name.setText('Pièces corrigées');window.commit.click()
        self.assertEqual(len(self.db.rows('SELECT * FROM stock_sets')),2);self.assertEqual(self.quantity(self.other),0)
        personal=self.db.rows("SELECT s.id FROM stock_sets s JOIN items i ON i.id=s.item_id WHERE i.name='Pièces corrigées'")[0]['id']
        self.assertEqual(self.db.owned_components(personal)[0]['chosen_quantity'],2)

    def test_deleted_inventory_can_be_replaced_without_reimporting_old_rows(self):
        job=self.mixed();imports.update_destination(self.db,job,'stock_sets',name='Ancien inventaire');imports.import_ready(self.db,job)
        entry=self.db.rows('SELECT id FROM stock_sets')[0]['id'];self.db.remove('stock_sets',[entry]);self.assertEqual(self.quantity(self.part),2)
        imports.update_destination(self.db,job,'stock_sets',name='Nouvel inventaire');self.correct(job,ref='3005');imports.import_ready(self.db,job)
        new=self.db.rows('SELECT id FROM stock_sets')[0]['id'];self.assertEqual([(r['ref'],r['chosen_quantity']) for r in self.db.owned_components(new)],[('3005',3)])
        self.assertEqual(self.quantity(self.part),2)

    def test_two_open_assistants_cannot_apply_the_same_row_twice(self):
        job=self.mixed();other=Database(self.db.path)
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(imports.import_ready,db,job) for db in (self.db,other)]
                self.assertEqual(sorted(f.result()['imported'] for f in futures),[0,1])
            self.assertEqual(self.quantity(self.part),2)
        finally:other.close()

    def test_imported_rows_and_destination_are_locked(self):
        job=self.mixed();imports.import_ready(self.db,job)
        with self.assertRaises(ValueError):self.correct(job,1,quantity='20')
        with self.assertRaises(ValueError):imports.update_destination(self.db,job,'stock_sets',name='Autre')
        self.assertEqual(self.quantity(self.part),2)

    def test_sorted_dialog_corrects_the_selected_file_row(self):
        window=self.keep(StockImportDialog(self.db));window.path=self.file('3001,4,2\nz-missing,4,3\n');window.load();window.table.sortItems(3,Qt.SortOrder.DescendingOrder);window.table.selectRow(0)
        self.assertEqual(window.current_ordinal(),2);window.edit_ref.setText('3005');window.edit_quantity.setText('7');window.save_row.click();window.commit.click()
        self.assertEqual((self.quantity(self.part),self.quantity(self.other)),(2,7));self.assertFalse(window.commit.isEnabled())
        self.assertTrue(all(row['imported'] for row in imports.job_rows(self.db,window.job_id)))

    def test_colour_source_change_requires_an_explicit_new_colour(self):
        window=self.keep(StockImportDialog(self.db));window.path=self.file('missing,4,2\n');window.load();window.edit_source.setCurrentIndex(window.edit_source.findData('BL'))
        self.assertEqual(window.edit_color.currentData(),'');window.edit_ref.setText('3001');window.save_correction();self.assertFalse(window.commit.isEnabled())
        window.edit_color.setCurrentIndex(window.edit_color.findData('4'));window.save_correction();window.commit.click();self.assertEqual(self.quantity(self.bl),2)

    def test_resume_and_undo_refresh_do_not_restore_a_stale_target(self):
        job=self.mixed();imports.update_destination(self.db,job,'stock_sets',name='Mes briques');imports.import_ready(self.db,job)
        window=self.keep(StockImportDialog(self.db));window.pending.setCurrentIndex(window.pending.findData(job));window.resume();self.assertFalse(window.destination.isEnabled())
        self.db.undo_last_action();window.stock_changed();self.assertTrue(window.destination.isEnabled());self.assertIsNone(window.target.currentData());window.commit.click()
        self.assertEqual(len(self.db.rows('SELECT * FROM stock_sets')),1)

    def test_picker_searches_local_names_and_does_not_change_stock(self):
        picker=self.keep(ImportItemPicker(self.db,'RB','part',None));picker.search.setText('3005');picker.timer.stop();picker.reload();picker.table.selectRow(0);picker.choose()
        self.assertEqual(picker.item['id'],self.other);self.assertEqual(self.db.rows('SELECT * FROM stock'),[])

    def assert_buttons_fit(self,widget):
        for button in widget.findChildren(QPushButton):
            if button.isVisible():
                self.assertGreaterEqual(button.width(),button.minimumSizeHint().width(),button.text())
                self.assertTrue(button.parentWidget().rect().contains(button.geometry()),button.text())

    def test_small_import_window_keeps_save_and_commit_accessible(self):
        previous=app.styleSheet();app.setStyleSheet(STYLE)
        try:
            window=self.keep(StockImportDialog(self.db));window.path=self.file('missing,4,2\n');window.load();window.resize(680,520);window.show()
            for _ in range(4):app.processEvents()
            self.assert_buttons_fit(window);window.body_scroll.ensureWidgetVisible(window.save_row);app.processEvents()
            point=window.save_row.mapTo(window.body_scroll.viewport(),window.save_row.rect().center());self.assertTrue(window.body_scroll.viewport().rect().contains(point))
            self.assertTrue(window.rect().contains(window.commit.geometry()))
        finally:app.setStyleSheet(previous)

    def test_small_main_window_buttons_fit_in_all_tabs(self):
        previous=app.styleSheet();app.setStyleSheet(STYLE);storage_wall.create_wall(self.db,'Parkside',6,5)
        try:
            with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.preview.Preview.refresh'):
                window=self.keep(MainWindow(self.db));window.startup_timer.stop();window.resize(950,650);window.show();window.preview.set_item(self.db.get_item(self.bl))
                for index in range(len(NAV)):
                    window.nav.setCurrentRow(index)
                    for _ in range(4):app.processEvents()
                    self.assert_buttons_fit(window.centralWidget())
                scroll=window.storage.controls_scroll;scroll.ensureWidgetVisible(window.storage.remove_references);app.processEvents()
                point=window.storage.remove_references.mapTo(scroll.viewport(),window.storage.remove_references.rect().center());self.assertTrue(scroll.viewport().rect().contains(point))
                for button in window.preview.findChildren(QPushButton):
                    if button.isVisible():
                        window.right_scroll.ensureWidgetVisible(button);app.processEvents()
                        point=button.mapTo(window.right_scroll.viewport(),button.rect().center());self.assertTrue(window.right_scroll.viewport().rect().contains(point),button.text())
        finally:app.setStyleSheet(previous)


if __name__=='__main__':unittest.main()
