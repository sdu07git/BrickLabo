import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from atelier.data import Database,normalize
from atelier.search_index import prepare_index
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox
from atelier.catalogue import Catalogue
from atelier.search_filters import FilterDialog
app=QApplication.instance() or QApplication([])

class IndexedSearchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'Donnees'/'atelier.sqlite');self.widgets=[]
 def tearDown(self):
  for w in self.widgets:w.close();w.deleteLater()
  app.processEvents();self.temp.cleanup()
 def item(self,ref,name='Brick',category='Bricks',source='RB',kind='part',year=''):
  return self.db.run('INSERT INTO items(source,kind,ref,name,category,year,search) VALUES(?,?,?,?,?,?,?)',(source,kind,ref,name,category,year,normalize(ref+' '+name)))
 def test_existing_database_index_migration_preserves_all_rows_and_settings(self):
  self.item('old','Éléphant 1 x 1','Animaux');self.db.add('stock',1,quantity=4);self.db.set_setting('private_setting','unchanged')
  before=self.db.rows('SELECT * FROM items');stock=self.db.rows('SELECT * FROM stock')
  with self.db.connect() as c:
   for name in ('insert','delete','update'):c.execute('DROP TRIGGER items_search_'+name)
   c.execute('DROP TABLE items_search')
  db=Database(self.db.path)
  self.assertEqual(db.rows('SELECT * FROM items'),before);self.assertEqual(db.rows('SELECT * FROM stock'),stock);self.assertEqual(db.setting('private_setting'),'unchanged');self.assertEqual(db.query(search='elephant 1x1 animaux')[1],1)
 def test_updates_deletes_replacements_and_transaction_rollback_keep_index_consistent(self):
  iid=self.item('3001','Old name');self.db.run('UPDATE items SET name=?,category=?,search=? WHERE id=?',('Nouveau','Nouvelle','nouveau',iid))
  self.assertEqual(self.db.query(search='nouvelle')[1],1);self.assertEqual(self.db.query(search='old')[1],0)
  with self.assertRaises(RuntimeError):
   with self.db.connect() as c:c.execute("UPDATE items SET name='Rolled back' WHERE id=?",(iid,));raise RuntimeError()
  self.assertEqual(self.db.query(search='rolled')[1],0);self.assertEqual(self.db.query(search='nouveau')[1],1)
  self.db.run("INSERT OR REPLACE INTO items(id,source,kind,ref,name,search) VALUES(?,?,?,?,?,?)",(iid,'RB','part','3001','Replacement','replacement'))
  self.assertEqual(self.db.query(search='nouveau')[1],0);self.assertEqual(self.db.query(search='replacement')[1],1)
  self.db.run('DELETE FROM items WHERE id=?',(iid,));self.assertEqual(self.db.query(search='replacement')[1],0)
 def test_indexed_results_match_legacy_for_partial_short_and_literal_terms(self):
  for args in [('3037pr0013','Slope 1 x 1','Icôns'),('xy','x 1','100%_Special'),('other','Slope 2x4','Bricks')]:self.item(*args)
  for text in ['3037','pr001','1 x 1','ICONS','xy','x','100%_','" OR 1=1 --','slope bricks','']:
   self.db.search_index_available=True;indexed=self.db.query(search=text)
   self.db.search_index_available=False;legacy=self.db.query(search=text)
   self.assertEqual([r['id'] for r in indexed[0]],[r['id'] for r in legacy[0]],text)
  self.db.search_index_available=True
 def test_index_query_plan_uses_trigram_like_constraint(self):
  with self.db.connect() as c:plan=list(c.execute("EXPLAIN QUERY PLAN SELECT rowid FROM items_search WHERE text LIKE '%brick%'"))
  self.assertTrue(any('L0' in r['detail'] for r in plan),str([dict(r) for r in plan]))
 def test_missing_tokenizer_falls_back_without_blocking_application(self):
  class MissingTokenizer:
   def execute(self,sql):
    if sql.startswith('SELECT'):return self
    raise sqlite3.OperationalError('no such tokenizer')
   def fetchone(self):return None
  with self.assertLogs('atelier.search_index',level='WARNING'):self.assertFalse(prepare_index(MissingTokenizer()))
  self.item('3037');self.db.search_index_available=False;self.assertEqual(self.db.query(search='3037')[1],1)
 def test_advanced_filters_apply_before_pagination_and_sort(self):
  for n in range(126):self.item(f'set-{n:03}','Set','City',kind='set',year='2025')
  self.item('new','Set','City',kind='set',year='2026');self.item('unknown','Set','City',kind='set')
  rows,total,pages,page=self.db.query(kind='set',advanced={'year_min':'2020','year_max':'2025'},size=50,page=3,descending=True)
  self.assertEqual((total,pages,page),(126,3,3));self.assertEqual(rows[0]['ref'],'set-025')
 def test_stock_photo_decoration_and_source_filters_compose(self):
  a=self.item('3037pr0013');b=self.item('plain',source='BL');self.item('sticker','Sticker sheet')
  self.db.add('stock',a,quantity=3);self.db.save_visual(a,image='image.png')
  self.assertEqual(self.db.query(advanced={'stock':'yes','photo':'yes','printed':'yes','sticker':'no','sources':['RB']})[1],1)
  self.assertEqual(self.db.query(advanced={'stock':'no','photo':'no','printed':'no','sticker':'no'})[0][0]['id'],b)
 def test_date_unknown_not_invented_and_values_are_bound(self):
  a=self.item('a');b=self.item('b');self.db.run("UPDATE items SET imported_at='2026-10-03 00:00:00' WHERE id=?",(a,));self.db.run("UPDATE items SET imported_at='' WHERE id=?",(b,))
  self.assertEqual(self.db.query(advanced={'import_from':'2026-10-03','import_to':'2026-10-03'})[1],1)
  with self.assertRaises(ValueError):self.db.query(advanced={'import_from':"2026' OR 1=1 --"})
  self.assertEqual(self.db.query(advanced={'sources':["RB' OR 1=1 --"],'year_min':"1 OR 1=1"})[1],2)
 def test_exact_color_filter_only_applies_to_stock_queue_history(self):
  a=self.item('a');self.db.add('stock',a,'5',2);self.db.add('stock',a,'7',3)
  self.assertEqual(self.db.query(scope='stock',advanced={'color':'5'})[0][0]['chosen_quantity'],2)
  self.assertEqual(self.db.query(scope='stock',advanced={'color':"5' OR 1=1 --"})[1],0)
  self.assertEqual(self.db.query(advanced={'color':'5'})[1],1)
 def widget(self):
  cat=Catalogue(self.db,'RB','part');self.widgets.append(cat);return cat
 def test_filter_dialog_apply_reset_and_preset_persist_after_restart(self):
  self.item('3037','Slope','Slopes');self.item('3001','Brick','Bricks');cat=self.widget();cat.search.setText('slope');cat.timer.stop()
  d=FilterDialog(cat);self.widgets.append(d);d.fields['stock'].setCurrentIndex(2)
  with patch.object(QInputDialog,'getText',return_value=('Slope preset',True)):d.save_preset()
  self.assertIn('Slope preset',Database(self.db.path).setting(d.preset_key))
  cat.apply_filter_state(d.state());self.assertEqual(cat.total,1);self.assertEqual(cat.rows[0]['ref'],'3037')
  d.set_state({});cat.apply_filter_state(d.state());self.assertEqual(cat.total,2);self.assertEqual(cat.advanced,{})
  d.load_preset();cat.apply_filter_state(d.state());self.assertEqual(cat.total,1)
  with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):d.delete_preset()
  self.assertEqual(self.db.setting(d.preset_key),{})
 def test_invalid_ranges_rejected_before_preset_save(self):
  cat=self.widget();d=FilterDialog(cat);self.widgets.append(d)
  with patch.object(QMessageBox,'warning'):
   d.fields['import_from'].setText('03/10/2026');self.assertFalse(d.validate())
   d.fields['import_from'].clear();d.fields['year_min'].setText('2026');d.fields['year_max'].setText('2020');self.assertFalse(d.validate())
 def test_filter_presets_scoped_to_each_catalogue(self):
  cat=self.widget();d=FilterDialog(cat);self.widgets.append(d)
  with patch.object(QInputDialog,'getText',return_value=('RB only',True)):d.save_preset()
  bl=Catalogue(self.db,'BL','part');self.widgets.append(bl);other=FilterDialog(bl);self.widgets.append(other);self.assertEqual(other.presets,{})
 def test_branch_backup_accepts_stable_rejects_newer_and_restores_index_presets(self):
  from atelier.backups import create_backup,validate_archive,queue_restore,apply_pending
  from atelier import backups
  self.item('3037','Slope');self.db.set_setting('search_presets_demo',{'Test':{'search':'slope'}})
  archive=Path(self.temp.name)/'backup.zip';create_backup(self.db,archive)
  with patch.object(backups,'VERSION','0.1.99'):self.assertEqual(validate_archive(archive)['version'],__import__('atelier.version',fromlist=['VERSION']).VERSION)
  with patch.object(backups,'VERSION','0.1.31'):
   with self.assertRaises(ValueError):validate_archive(archive)
  queue_restore(self.db,archive);self.db.run("UPDATE items SET name='Modified',search='modified'");apply_pending(self.db.path.parent)
  restored=Database(self.db.path);self.assertEqual(restored.query(search='slope')[1],1);self.assertEqual(restored.setting('search_presets_demo')['Test']['search'],'slope')
  # Backups from the stable baseline can be read by the alternative branch.
  with patch.object(backups,'VERSION','0.1.28'):create_backup(restored,archive)
  self.assertEqual(validate_archive(archive)['version'],'0.1.28')
