import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.catalogue import Catalogue
app=QApplication.instance() or QApplication([])

class SetYearFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.windows=[]
        for n in range(155):self.insert('RB',f'old-{n:03}','Set old','City','1997')
        self.insert('RB','new-001','Space Rocket','Space','2026');self.insert('RB','old-space','Space Rocket','Space','1997');self.insert('RB','unknown','Unknown','City','')
        self.insert('BL','bl-1','City truck','City','2004');self.insert('ALT','alt-1','Alternative City','City','1997')
        self.insert('RB','part','Brick','Bricks','2020',kind='part')
    def insert(self,source,ref,name,category,year,kind='set'):
        self.db.run('INSERT INTO items(source,kind,ref,name,category,year,search) VALUES(?,?,?,?,?,?,?)',(source,kind,ref,name,category,year,(ref+' '+name).lower()))
    def tearDown(self):
        for w in self.windows:w.close();w.deleteLater()
        app.processEvents();self.temp.cleanup()
    def catalogue(self,source,kind='set'):
        w=Catalogue(self.db,source,kind);self.windows.append(w);return w
    def test_filter_counts_and_sorts_across_all_pages(self):
        rows,total,pages,page=self.db.query('RB','set',year='1997',size=50,page=3,sort='ref',descending=True)
        self.assertEqual((total,pages,page),(156,4,3));self.assertEqual(len(rows),50);self.assertTrue(all(r['year']=='1997' for r in rows))
        self.assertEqual(rows[0]['ref'],'old-055')
        rows,total,_,_=self.db.query('RB','set',year='1997',category='Space',search='rocket');self.assertEqual(total,1);self.assertEqual(rows[0]['ref'],'old-space')
    def test_menus_separate_catalogues_and_keep_part_catalogue_unchanged(self):
        for source,years in [('RB',['2026','1997','__unknown__']),('BL',['2004']),('ALT',['1997'])]:
            w=self.catalogue(source);self.assertEqual([w.year.itemData(i) for i in range(1,w.year.count())],years);self.assertEqual(w.year.itemText(0),'Toutes les années')
        self.assertIsNone(self.catalogue('RB','part').year)
    def test_menu_resets_page_and_combines_with_category_and_search(self):
        w=self.catalogue('RB');w.go_page(2);self.assertEqual(w.page,2)
        w.year.setCurrentIndex(w.year.findData('1997'));self.assertEqual(w.page,1);self.assertEqual(w.total,156)
        w.category.setCurrentIndex(w.category.findData('Space'));self.assertEqual(w.total,1)
        w.search.setText('rocket');w.timer.stop();w.reset();self.assertEqual(w.rows[0]['ref'],'old-space')
        w.reload_categories();self.assertEqual(w.year.currentData(),'1997');self.assertEqual(w.category.currentData(),'Space')
        w.year.setCurrentIndex(0);self.assertEqual(w.total,2)
    def test_missing_year_and_years_after_new_set(self):
        w=self.catalogue('RB');w.year.setCurrentIndex(w.year.findData('__unknown__'));self.assertEqual(w.total,1);self.assertEqual(w.rows[0]['ref'],'unknown')
        self.insert('RB','added','New set','City','2025');w.reload_categories();self.assertNotEqual(w.year.findData('2025'),-1);self.assertEqual(w.year.currentData(),'__unknown__')
