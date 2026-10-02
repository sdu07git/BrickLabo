import os,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from atelier.data import Database
from atelier.disk_space import clean_temp,deduplicate_ldraw,usage
class DiskSpaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'Donnees';self.db=Database(self.root/'atelier.sqlite')
 def tearDown(self):self.tmp.cleanup()
 def archive(self,path,text='same'):
  path.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(path,'w') as z:z.writestr('ldraw/LDConfig.ldr',text)
  return path
 def test_repeated_import_reuses_one_archive_and_keeps_import_record(self):
  source=self.archive(Path(self.tmp.name)/'external'/'complete.zip');self.db.import_file(source);first=self.db.setting('ldraw');self.db.import_file(source)
  self.assertEqual(self.db.setting('ldraw'),first);self.assertEqual(len(list(self.root.glob('ldraw*.zip'))),1);self.assertEqual(self.db.rows("SELECT path FROM imports WHERE file='LDraw'")[0]['path'],first)
 def test_changed_archive_adds_new_version_without_destroying_old(self):
  source=self.archive(Path(self.tmp.name)/'external'/'complete.zip');self.db.import_file(source);first=Path(self.db.setting('ldraw'));self.archive(source,'updated');self.db.import_file(source)
  self.assertNotEqual(self.db.setting('ldraw'),str(first));self.assertTrue(first.exists());self.assertEqual(len(list(self.root.glob('ldraw*.zip'))),2)
 def test_supplied_resource_import_does_not_make_a_copy(self):
  program=Path(self.tmp.name)/'App';source=self.archive(program/'ressources'/'complete.zip')
  with patch('atelier.disk_space.__file__',str(program/'atelier'/'disk_space.py')):self.db.import_file(source)
  self.assertEqual(self.db.setting('ldraw'),str(source));self.assertEqual(list(self.root.glob('ldraw*.zip')),[])
 def test_dedup_preserves_active_and_remaps_references_only_for_identical_copy(self):
  active=self.archive(self.root/'ldraw_1.zip');duplicate=self.root/'ldraw_2.zip';duplicate.write_bytes(active.read_bytes());other=self.archive(self.root/'ldraw_3.zip','different');self.db.set_setting('ldraw',str(active));self.db.set_setting('old_reference',str(duplicate))
  count,freed,errors=deduplicate_ldraw(self.db)
  self.assertEqual(count,1);self.assertGreater(freed,0);self.assertEqual(errors,[]);self.assertTrue(active.exists());self.assertTrue(other.exists());self.assertFalse(duplicate.exists());self.assertEqual(self.db.setting('old_reference'),str(active));self.assertEqual(self.db.setting('ldraw'),str(active))
 def test_temp_cleanup_preserves_recent_files_references_and_external_symlinks(self):
  folder=self.root/'temp';folder.mkdir();old=folder/'old.tmp';recent=folder/'recent.tmp';protected=folder/'photo.png';external=Path(self.tmp.name)/'outside';external.mkdir();outside=external/'old.tmp'
  for p in [old,recent,protected,outside]:p.write_bytes(b'abc')
  for p in [old,protected,outside]:os.utime(p,(time.time()-9*86400,)*2)
  self.db.set_setting('imported_image',str(protected));(folder/'linked-folder').symlink_to(external,target_is_directory=True)
  count,freed,errors=clean_temp(self.db)
  self.assertEqual((count,freed),(1,3));self.assertFalse(old.exists());self.assertTrue(recent.exists());self.assertTrue(protected.exists());self.assertTrue(outside.exists());self.assertEqual(errors,[])
 def test_configured_output_directory_in_temp_is_preserved(self):
  out=self.root/'temp'/'Exports';out.mkdir(parents=True);file=out/'label.pdf';file.write_bytes(b'pdf');os.utime(file,(time.time()-9*86400,)*2);self.db.set_setting('output',str(out))
  self.assertEqual(clean_temp(self.db)[0],0);self.assertTrue(file.exists())
 def test_usage_measures_temp_and_images_without_following_links(self):
  folder=self.root/'temp';folder.mkdir();(folder/'test').write_bytes(b'abc');outside=Path(self.tmp.name)/'outside';outside.mkdir();(outside/'large').write_bytes(b'x'*1000);(folder/'external').symlink_to(outside,target_is_directory=True)
  stats={label:(size,count) for label,size,count in usage(self.db)};self.assertEqual(stats['Temporaires'],(3,1));self.assertEqual(stats['Images (locales et téléchargées)'],(0,0))
