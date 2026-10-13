"""A failed download keeps the old library; shortcuts load their sticker files."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from atelier.data import Database
from atelier.ldraw_updates import header_links,install_library,update_library,OFFICIAL_URL
from atelier.preview import VisualEngine
from atelier.render import LDraw,RenderError


class LDrawUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=Database(self.root/'Donnees'/'db.sqlite')

    def tearDown(self):self.db.close();self.temp.cleanup()

    def archive(self,name='complete.zip',extra=None):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        files={'ldraw/LDConfig.ldr':'0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n',
               'ldraw/parts/87552.dat':'0 Panel\n4 16 -20 0 0 20 0 0 20 48 0 -20 48 0\n',
               'ldraw/parts/6177954b.dat':'0 Sticker\n4 4 -10 10 0 10 10 0 10 30 0 -10 30 0\n',
               'ldraw/parts/87552d02.dat':'0 Panel with Sticker\n0 !LDRAW_ORG Shortcut UPDATE 2026-09\n0 !KEYWORDS Bricklink 87552pb065R, Set 75879\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 87552.dat\n1 16 0 0 -.1 1 0 0 0 1 0 0 0 1 6177954b.dat\n'}
        files.update(extra or {})
        with zipfile.ZipFile(path,'w') as z:
            for member,text in files.items():z.writestr(member,text)
        return path

    def test_official_download_is_validated_installed_and_indexed(self):
        path=self.archive();messages=[]
        def fetch(url,destination,timeout):
            self.assertEqual(url,OFFICIAL_URL);shutil.copyfile(path,destination);return destination
        with patch('atelier.ldraw_updates.request',side_effect=fetch):result=update_library(self.db,messages.append)
        self.assertEqual(result['parts'],3);self.assertTrue(Path(result['path']).exists());self.assertEqual(self.db.setting('ldraw'),result['path'])
        self.assertEqual(self.db.setting('ldraw_header_links')['models']['BL']['87552pb065r'],'87552d02')
        self.assertTrue(any('Vérification' in message for message in messages));self.assertEqual(list((self.db.path.parent/'temp').iterdir()),[])

    def test_update_removes_previous_managed_copy_only_after_activation(self):
        first=install_library(self.db,self.archive(),strict=True);old=Path(first['path'])
        second=install_library(self.db,self.archive(extra={'ldraw/parts/new.dat':'3 16 0 0 0 1 0 0 0 1 0\n'}),strict=True,remove_previous=True)
        self.assertFalse(old.exists());self.assertTrue(second['removed_previous']);self.assertTrue(Path(self.db.setting('ldraw')).exists())
        self.assertEqual(self.db.rows("SELECT path FROM imports WHERE file='LDraw'")[0]['path'],second['path'])

    def test_failed_download_keeps_old_archive_setting_and_import(self):
        install_library(self.db,self.archive(),strict=True);before=self.db.rows('SELECT * FROM settings ORDER BY key');imports=self.db.rows('SELECT * FROM imports');old=self.db.setting('ldraw')
        with patch('atelier.ldraw_updates.request',side_effect=OSError('offline')):
            with self.assertRaises(OSError):update_library(self.db)
        self.assertEqual(self.db.rows('SELECT * FROM settings ORDER BY key'),before);self.assertEqual(self.db.rows('SELECT * FROM imports'),imports);self.assertTrue(Path(old).exists())

    def test_broken_archive_is_rejected_without_switch_or_cleanup(self):
        install_library(self.db,self.archive(),strict=True);old=self.db.setting('ldraw')
        invalid=self.root/'broken.zip';invalid.write_bytes(b'not a ZIP')
        with self.assertRaises(zipfile.BadZipFile):install_library(self.db,invalid,strict=True,remove_previous=True)
        self.assertEqual(self.db.setting('ldraw'),old);self.assertTrue(Path(old).exists())

    def test_repeated_update_reuses_archive_without_deleting_it(self):
        source=self.archive();first=install_library(self.db,source,strict=True);second=install_library(self.db,source,strict=True,remove_previous=True)
        self.assertEqual(first['path'],second['path']);self.assertFalse(second['removed_previous']);self.assertTrue(Path(first['path']).exists())

    def test_external_active_archive_and_supplied_library_are_preserved(self):
        source=self.archive();external=self.root/'external.zip';shutil.copyfile(source,external);self.db.set_setting('ldraw',str(external))
        result=install_library(self.db,self.archive(extra={'ldraw/parts/new.dat':'3 16 0 0 0 1 0 0 0 1 0\n'}),strict=True,remove_previous=True)
        self.assertTrue(external.exists());self.assertFalse(result['removed_previous'])

    def test_a_separate_user_reference_protects_old_managed_archive(self):
        old=install_library(self.db,self.archive(),strict=True)['path'];self.db.set_setting('user_saved_library',old)
        result=install_library(self.db,self.archive(extra={'ldraw/parts/new.dat':'3 16 0 0 0 1 0 0 0 1 0\n'}),strict=True,remove_previous=True)
        self.assertTrue(Path(old).exists());self.assertFalse(result['removed_previous'])

    def test_shortcut_loads_body_and_sticker_with_catalogue_header_mapping(self):
        install_library(self.db,self.archive(),strict=True)
        renderer=LDraw(self.db.setting('ldraw'))
        try:
            plain=renderer.mesh('87552');assembled=renderer.mesh('87552d02')
            self.assertEqual(len(plain[0]),2);self.assertEqual(len(assembled[0]),4);self.assertIn(4,[color for _,color in assembled[0]])
        finally:renderer.close()
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL','part','87552pb065R','Panel with sticker','Panels','panel'))
        item=self.db.get_item(iid);self.db.save_visual(iid,mode='3d');engine=VisualEngine(self.db)
        try:
            with patch.object(engine.renderer(),'render',wraps=engine.renderer().render) as render:
                image,_=engine.render_3d(item,(100,65));self.assertEqual(render.call_args.args[0],'87552d02');self.assertIsNotNone(image.getbbox())
            self.assertEqual(self.db.get_item(iid)['ref'],'87552pb065R')
        finally:engine.close()

    def test_missing_sticker_dependency_fails_instead_of_rendering_bare_body(self):
        path=self.archive()
        with zipfile.ZipFile(path) as old:files={name:old.read(name) for name in old.namelist() if not name.endswith('6177954b.dat')}
        with zipfile.ZipFile(path,'w') as archive:
            for name,data in files.items():archive.writestr(name,data)
        renderer=LDraw(path)
        try:
            with self.assertRaisesRegex(RenderError,'6177954b.dat'):renderer.mesh('87552d02')
        finally:renderer.close()

    def test_ambiguous_headers_are_not_used_as_catalogue_correspondences(self):
        path=self.archive(extra={'ldraw/parts/other.dat':'0 !KEYWORDS Bricklink 87552pb065R\n3 16 0 0 0 1 0 0 0 1 0\n'})
        links=header_links(path);self.assertNotIn('87552pb065r',links['models']['BL']);self.assertIn('87552pb065r',links['ambiguous']['BL'])
