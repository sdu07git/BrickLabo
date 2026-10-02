import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,sqlite3
from pathlib import Path
from PySide6.QtWidgets import QApplication
from atelier.data import Database,SCHEMA
from atelier.catalogue import Catalogue
app=QApplication.instance() or QApplication([])
class ImportDateTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_existing_database_keeps_unknown_dates_and_new_rows_are_stamped(self):
  path=self.root/'db.sqlite'
  with sqlite3.connect(path) as c:
   c.executescript(SCHEMA.replace(", imported_at TEXT NOT NULL DEFAULT ''",''));c.execute("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','old','Old','old')")
  db=Database(path);self.assertEqual(db.rows("SELECT imported_at FROM items WHERE ref='old'")[0]['imported_at'],'')
  db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('BL','part','new','New','new')");self.assertRegex(db.rows("SELECT imported_at FROM items WHERE ref='new'")[0]['imported_at'],r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
 def test_reimport_keeps_first_date_and_stamps_only_new_references(self):
  db=Database(self.root/'db.sqlite');file=self.root/'parts.csv';file.write_text('part_num,name,part_cat_id\n3001,Brick,1\n');db.import_file(file);db.run("UPDATE items SET imported_at='2001-01-01 00:00:00' WHERE ref='3001'")
  file.write_text('part_num,name,part_cat_id\n3001,Updated name,1\n3002,New brick,1\n');db.import_file(file)
  old=db.rows("SELECT * FROM items WHERE ref='3001'")[0];self.assertEqual(old['imported_at'],'2001-01-01 00:00:00');self.assertEqual(old['name'],'Updated name');self.assertTrue(db.rows("SELECT imported_at FROM items WHERE ref='3002'")[0]['imported_at'])
 def test_sort_uses_all_records_before_paginating(self):
  db=Database(self.root/'db.sqlite')
  for i,date in enumerate(['2020-01-01','2023-01-01','2022-01-01','2024-01-01']):db.run('INSERT INTO items(source,kind,ref,name,search,imported_at) VALUES(?,?,?,?,?,?)',('RB','part',str(i),str(i),str(i),date))
  rows,total,pages,page=db.query('RB','part',size=2,sort='imported_at',descending=True);self.assertEqual([r['ref'] for r in rows],['3','1']);self.assertEqual(total,4)
 def test_column_added_once_and_user_can_hide_it(self):
  db=Database(self.root/'db.sqlite');cat=Catalogue(db,'RB','part');self.assertIn('imported_at',cat.visible_columns);columns=[k for k in cat.visible_columns if k!='imported_at'];db.set_setting(cat.key,columns);cat.close();other=Catalogue(db,'RB','part');self.assertNotIn('imported_at',other.visible_columns);other.close()
