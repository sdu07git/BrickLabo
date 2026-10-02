import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import csv,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.preview import Preview,VisualEngine
app=QApplication.instance() or QApplication([])
resources=Path(__file__).resolve().parent.parent/'ressources'

class BrickLinkFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite')
    def tearDown(self):self.temp.cleanup()
    def test_real_supplied_files_and_source_ids(self):
        for name,count in [('codes.txt',110891),('colors.txt',215),('categories.txt',1218),('itemtypes.txt',9)]:
            self.assertEqual(self.db.import_file(resources/name),count)
        palette=self.db.setting('bl_colors');self.assertEqual(palette['11']['name'],'Black');self.assertEqual(palette['11']['rgb'],'2E2E2E')
        item={'source':'BL','kind':'part','ref':'44'}
        colors=self.db.available_colors(item)
        black=next(c for c in colors if c['id']=='11')
        self.assertIn('4221514',black['element_codes']);self.assertIn('4660886',black['element_codes'])
        self.db.run('INSERT INTO colors VALUES(?,?,?,?)',(11,'Different RB colour','ff0000',0))
        self.assertEqual(VisualEngine(self.db).color_rgb(item,'11'),'#2E2E2E')
        self.assertEqual(self.db.available_colors(dict(item,kind='minifig')),[])
        self.assertEqual(self.db.available_colors(dict(item,ref='missing')),[])
        with (resources/'codes.txt').open(encoding='utf-8-sig') as f:
            names={r['Color'] for r in csv.DictReader(f,delimiter='\t')}
        self.assertTrue(names.issubset({c['name'] for c in palette.values()}))
        before=self.db.rows('SELECT COUNT(*) n FROM bl_codes')[0]['n']
        self.db.import_file(resources/'codes.txt');self.assertEqual(self.db.rows('SELECT COUNT(*) n FROM bl_codes')[0]['n'],before)
        print('Imported 4 BrickLink files; distinct part/color/code records:',before,'mapped color names:',len(names))
    def test_imports_replace_transactionally_and_update_categories(self):
        f=Path(self.temp.name)/'categories.txt';f.write_text('Category ID\tCategory Name\n1\tBricks\n')
        self.db.run('INSERT INTO items(source,kind,ref,name,category,category_id,search) VALUES(?,?,?,?,?,?,?)',('BL','part','44','Brick','Old','1','44'))
        self.db.import_file(f);self.assertEqual(self.db.rows('SELECT category FROM items')[0]['category'],'Bricks')
        f.write_text('Category ID\tCategory Name\n2\tNew\n3\t\n')
        with self.assertRaises(ValueError):self.db.import_file(f)
        self.assertEqual(self.db.rows('SELECT * FROM bl_categories'),[{'id':'1','name':'Bricks'}])
    def test_available_ui_uses_local_codes_without_api(self):
        for n in ('colors.txt','codes.txt'):self.db.import_file(resources/n)
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL','part','44','Brick','Bricks','44'))
        w=Preview(self.db,VisualEngine(self.db))
        with patch.object(w,'refresh'),patch.object(w,'fetch_colors') as api:
            w.set_item(self.db.get_item(iid))
            api.assert_not_called();self.assertTrue(w.load_colors.isHidden());self.assertTrue(w.available.isEnabled())
            index=w.available.findData('11');self.assertGreater(index,0);w.available.setCurrentIndex(index)
            self.assertEqual(self.db.visual(iid)['color'],'11');w.close()
    def test_upgrade_offers_new_bundled_files_and_skips_completed_imports(self):
        from atelier.app import MainWindow
        original=MainWindow.first_import
        self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',('BL','part','44','Brick','44'))
        with patch.object(MainWindow,'first_import',lambda self:None):w=MainWindow(self.db)
        try:
            with patch.object(w,'imports') as show:
                original(w);show.assert_called_once()
                self.assertEqual({Path(p).name for p in show.call_args[0][0]},{'codes.txt','colors.txt','categories.txt','itemtypes.txt','Original Boxes.txt'})
            for n in ('codes.txt','colors.txt','categories.txt','itemtypes.txt','Original Boxes.txt'):self.db.import_file(resources/n)
            with patch.object(w,'imports') as show:original(w);show.assert_not_called()
        finally:w.close()
