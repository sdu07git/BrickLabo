from contextlib import closing
from pathlib import Path,PureWindowsPath
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from atelier import sqlite_file
from atelier.data import Database
from atelier.backups import create_backup,validate_archive

class SqlitePathTests(unittest.TestCase):
    def test_unicode_and_uri_characters_keep_read_only_database_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'étiquette #1 ? stock.sqlite'
            with closing(sqlite_file.connect(path)) as c:c.execute('CREATE TABLE stock(value)');c.execute('INSERT INTO stock VALUES(7)');c.commit()
            with closing(sqlite_file.connect(path,read_only=True)) as c:
                self.assertEqual(c.execute('SELECT value FROM stock').fetchone()[0],7)
                with self.assertRaises(sqlite3.OperationalError):c.execute('INSERT INTO stock VALUES(9)')
            self.assertEqual(len(list(Path(folder).iterdir())),1)

    def test_windows_opener_requests_long_path_vfs_and_read_only_mode(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(sqlite_file,'IS_WINDOWS',True),patch.object(sqlite_file.sqlite3,'connect') as open_db:
            path=Path(folder)/'a # & ? é.sqlite';sqlite_file.connect(path,timeout=90,read_only=True)
            args,kwargs=open_db.call_args;parsed=urlsplit(args[0]);self.assertEqual(parse_qs(parsed.query),{'mode':['ro'],'vfs':['win32-longpath']});self.assertEqual(kwargs,{'uri':True,'timeout':90});self.assertIn('%23',parsed.path);self.assertIn('%3F',parsed.path)

    def test_unc_uri_does_not_require_sqlite_uri_authority_extension(self):
        with patch.object(sqlite_file,'IS_WINDOWS',True):uri=sqlite_file.database_uri(PureWindowsPath(r'\\server\share\Mon stock #1\atelier.sqlite'),True)
        parsed=urlsplit(uri);self.assertFalse(parsed.netloc);self.assertTrue(parsed.path.startswith('//server/share/'));self.assertIn('%23',parsed.path);self.assertEqual(parse_qs(parsed.query)['vfs'],['win32-longpath'])

    def test_long_unicode_root_preserves_stock_and_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for index in range(6):root=root/('Un dossier utilisateur avec espaces et caractères éà '+str(index))
            self.assertGreater(len(str(root)),300);db=Database(root/'Donnees'/'atelier.sqlite');iid=db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','3001','Brick','brick')");db.add('stock',iid,'4',7)
            archive=root/'Sauvegardes'/'stock.zip';create_backup(db,archive);self.assertEqual(validate_archive(archive)['application'],'BrickLabo');db.undo_last_action();self.assertEqual(db.query(scope='stock')[1],0)

    def test_cant_open_preserves_sqlite_code_and_explains_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'absent'/'stock.sqlite'
            with self.assertRaisesRegex(sqlite3.OperationalError,'chemin plus court') as failure:sqlite_file.connect(path)
            self.assertEqual(failure.exception.sqlite_errorcode,sqlite3.SQLITE_CANTOPEN);self.assertIn(str(path),str(failure.exception));self.assertFalse(path.parent.exists())
