import ast,importlib,json,os,shutil,string,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from atelier import i18n
from atelier.data import Database

class TranslationTests(unittest.TestCase):
 def tearDown(self):i18n.set_language('fr')
 def test_french_default_and_unsupported_language(self):
  i18n.set_language('unknown');self.assertEqual(i18n.language(),'fr');self.assertEqual(i18n.tr('Couleurs des contours — aperçu de l’étiquette'),'Couleurs des contours — aperçu de l’étiquette')
 def test_english_messages_and_data_fallback(self):
  i18n.set_language('en');self.assertEqual(i18n.tr('Mise à jour des données'),'Data updates');self.assertEqual(i18n.tr('3037pr0013'),'3037pr0013');self.assertEqual(i18n.tr('Custom stock name'),'Custom stock name')
 def test_dynamic_count_and_reference_preserved(self):
  i18n.set_language('en');self.assertEqual(i18n.tf('{0} résultats · {2} sélection(s)',123,None,7),'123 results · 7 selected')
  text=i18n.tf('Importer {1} lignes pour le set {3} ?\nL’inventaire précédent de ce set sera remplacé. Les quantités déjà présentes dans Mon stock resteront inchangées.\nLes variantes et équivalents sont conservés mais exclus des ajouts automatiques ; les pièces supplémentaires sont incluses.',None,765,None,'75192-1',None)
  self.assertIn('765',text);self.assertIn('75192-1',text);self.assertIn('previous inventory',text)
 def test_all_placeholders_are_preserved(self):
  formatter=string.Formatter()
  for source,translated in i18n.ENGLISH.items():
   fields=lambda value:[(key,spec,conversion) for _,key,spec,conversion in formatter.parse(value) if key is not None]
   self.assertEqual(fields(source),fields(translated),source)
   self.assertTrue(translated,source)
 def test_literal_translation_coverage(self):
  for p in Path(i18n.__file__).parent.glob('*.py'):
   if p.name=='i18n.py':continue
   for node in ast.walk(ast.parse(p.read_text())):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('tr','tf') and node.args and isinstance(node.args[0],ast.Constant):
     source=node.args[0].value;self.assertIn(source,i18n.ENGLISH,str(p)+': '+str(source))
 def test_database_names_and_import_headers_unchanged(self):
  with tempfile.TemporaryDirectory() as folder:
   db=Database(Path(folder)/'atelier.sqlite');db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('BL','part','3001','Brique','Catégorie personnalisée','brique')");before=db.rows('SELECT * FROM items')
   i18n.set_language('en');file=Path(folder)/'parts.csv';file.write_text('part_num,name,part_cat_id\n3037,Slope 45 2 x 4,1\n');db.import_file(file)
   self.assertEqual(db.get_item(before[0]['id'])['name'],'Brique');self.assertEqual(db.get_item(before[0]['id'])['category'],'Catégorie personnalisée');self.assertEqual(db.rows("SELECT name FROM items WHERE source='RB'")[0]['name'],'Slope 45 2 x 4')
 def test_saved_language_and_read_only_lookup(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'atelier.sqlite';db=Database(path);self.assertEqual(i18n.read_language(path),'fr');db.set_setting('ui_language','en');self.assertEqual(i18n.read_language(path),'en');db.set_setting('ui_language','invalid');self.assertEqual(i18n.read_language(path),'fr')
   self.assertEqual(i18n.read_language(Path(folder)/'missing.sqlite'),'fr');self.assertFalse((Path(folder)/'missing.sqlite').exists())
 def test_document_selection(self):
  i18n.set_language('en');self.assertEqual(i18n.document('AIDE').name,'AIDE.en.html');self.assertEqual(i18n.document('SOURCES_ET_LICENCES').name,'SOURCES_ET_LICENCES.en.html')
  i18n.set_language('fr');self.assertEqual(i18n.document('AIDE').name,'AIDE.html')
 def test_english_docs_have_all_major_features(self):
  i18n.set_language('en');text=i18n.document('AIDE').read_text()
  for value in ['Data updates','Original box','Alternate','Backups','Language','3D edges','Print preview','PDF','Ctrl','Import date']:
   self.assertIn(value,text)
  self.assertTrue((i18n.ROOT/'README.en.md').is_file())
  for name in ['SOURCES_ET_LICENCES.en.html','NOUVEAUTES.txt']:self.assertTrue((i18n.ROOT/'documentation'/name).is_file())
 def test_language_selector_persists_choice_without_live_switch(self):
  from PySide6.QtWidgets import QApplication,QDialog,QComboBox,QMessageBox
  app=QApplication.instance() or QApplication([])
  with tempfile.TemporaryDirectory() as folder:
   db=Database(Path(folder)/'atelier.sqlite');i18n.set_language('fr')
   def accept(dialog):
    dialog.findChild(QComboBox).setCurrentIndex(1);return QDialog.DialogCode.Accepted
   with patch.object(QDialog,'exec',accept),patch.object(QMessageBox,'information') as message:i18n.language_dialog(db,None)
   self.assertEqual(db.setting('ui_language'),'en');self.assertEqual(i18n.language(),'fr');message.assert_called_once()
 def test_startup_english_headers_menus_and_unchanged_catalogue(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);shutil.copytree(Path(i18n.__file__).parent,root/'atelier',ignore=shutil.ignore_patterns('__pycache__'))
   (root/'ressources'/'langues').mkdir(parents=True);shutil.copy(i18n.ROOT/'ressources'/'langues'/'en.json',root/'ressources'/'langues'/'en.json')
   db=Database(root/'Donnees'/'atelier.sqlite');db.set_setting('ui_language','en');db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','3037','Slope original','Original category','slope')");db.add('stock',1,quantity=4)
   code='''import json
from atelier.i18n import language,install_qt_language
from atelier.app import MainWindow,NAV
from atelier.catalogue import COLUMNS
from atelier.data import Database
from PySide6.QtWidgets import QApplication,QPushButton
from unittest.mock import patch
from pathlib import Path
app=QApplication([]);install_qt_language(app);db=Database(Path('Donnees/atelier.sqlite'))
with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.preview.Preview.refresh'):
 w=MainWindow(db);w.startup_timer.stop()
 assert language()=='en'
 assert NAV[0][0]=='Rebrickable catalogue'
 assert dict(COLUMNS)['category']=='Category'
 assert 'Language' in [b.text() for b in w.findChildren(QPushButton)]
 assert 'Data updates' in [b.text() for b in w.findChildren(QPushButton)]
 assert 'Print labels' in [b.text() for b in w.findChildren(QPushButton)]
 assert db.get_item(1)['category']=='Original category'
 assert db.rows('SELECT quantity FROM stock')[0]['quantity']==4
 w.close()
print('ENGLISH_STARTUP_OK')
'''
   env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONPATH=str(root)+os.pathsep+os.environ.get('PYTHONPATH',''))
   result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,timeout=30)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('ENGLISH_STARTUP_OK',result.stdout)
 def test_english_errors_keep_reference(self):
  i18n.set_language('en')
  with tempfile.TemporaryDirectory() as folder:
   db=Database(Path(folder)/'atelier.sqlite')
   with self.assertRaisesRegex(ValueError,'Reference missing'):db.add('stock',99999)

 def test_help_dialog_loads_english_file_with_working_relative_links(self):
  from PySide6.QtWidgets import QApplication,QDialog,QTextBrowser
  from atelier.dialogs import help_dialog
  app=QApplication.instance() or QApplication([]);i18n.set_language('en');seen=[]
  def inspect(dialog):
   browser=dialog.findChild(QTextBrowser);seen.append(browser.source().toLocalFile());self.assertIn('Top toolbar',browser.toPlainText());return QDialog.DialogCode.Rejected
  with patch.object(QDialog,'exec',inspect):help_dialog(None)
  self.assertEqual(Path(seen[0]).name,'AIDE.en.html')

 def test_restored_language_applies_before_next_interface_start(self):
  from atelier.backups import create_backup,queue_restore,apply_pending,REPORT
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'BrickLabo'/'Donnees';db=Database(root/'atelier.sqlite');db.set_setting('ui_language','en');archive=Path(folder)/'backup.zip';create_backup(db,archive)
   db.set_setting('ui_language','fr');i18n.set_language('fr');queue_restore(db,archive);apply_pending(root)
   self.assertEqual(i18n.read_language(db.path),'en');self.assertEqual(i18n.language(),'en');self.assertIn('Backup restored',json.loads((root/REPORT).read_text())['message'])
