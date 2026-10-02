import tempfile,unittest,json,zipfile
from pathlib import Path
from unittest.mock import patch
from atelier.data import Database
from atelier.backups import create_backup,queue_restore,cancel_restore,apply_pending,validate_archive,REQUEST,REPORT
class BackupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.root=self.home/'BrickLabo'/'Donnees';self.db=Database(self.root/'atelier.sqlite');self.zip=self.home/'save.zip'
  self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('BL','part','3001','Brick','brick')");self.db.add('stock',1,'86',4);self.db.set_setting('api_rb','private-key')
  for folder in ['images','Notices','temp','cache','logs','downloads']:
   (self.root/folder).mkdir(exist_ok=True);(self.root/folder/'file').write_bytes(b'test')
 def tearDown(self):self.tmp.cleanup()
 def save(self):return create_backup(self.db,self.zip)
 def test_snapshot_content_private_keys_and_exclusions(self):
  self.save();manifest=validate_archive(self.zip)
  self.assertIn('images/file',manifest['files']);self.assertIn('Notices/file',manifest['files']);self.assertNotIn('temp/file',manifest['files']);self.assertNotIn('cache/file',manifest['files'])
  queue_restore(self.db,self.zip);apply_pending(self.root);restored=Database(self.db.path);self.assertEqual(restored.setting('api_rb'),'private-key');self.assertEqual(restored.rows('SELECT quantity FROM stock')[0]['quantity'],4)
 def test_apply_at_restart_and_previous_preserved(self):
  self.save();queue_restore(self.db,self.zip);self.db.add('stock',1,'86',3)
  self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],7);apply_pending(self.root)
  self.assertEqual(Database(self.db.path).rows('SELECT quantity FROM stock')[0]['quantity'],4)
  report=json.loads((self.root/REPORT).read_text());previous=Database(Path(report['previous'])/'atelier.sqlite');self.assertEqual(previous.rows('SELECT quantity FROM stock')[0]['quantity'],7)
 def test_cancel(self):
  self.save();stage=queue_restore(self.db,self.zip);cancel_restore(self.db);self.assertFalse(stage.exists());self.assertFalse((self.root/REQUEST).exists());self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],4)
 def test_inside_data_rejected(self):
  with self.assertRaises(ValueError):create_backup(self.db,self.root/'save.zip')
 def test_stage_tamper_preserves_current_data(self):
  self.save();stage=queue_restore(self.db,self.zip);(stage/'Donnees'/'images'/'file').write_bytes(b'bad');apply_pending(self.root)
  self.assertFalse(json.loads((self.root/REPORT).read_text())['success']);self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],4)
 def test_traversal_rejected(self):
  self.save()
  with zipfile.ZipFile(self.zip,'a') as z:z.writestr('Donnees/../escape',b'bad')
  with self.assertRaises(ValueError):queue_restore(self.db,self.zip)
  self.assertFalse((self.home/'escape').exists())
 def test_relocation(self):
  self.db.set_setting('output',str(self.root/'Exports'));self.save();new=Database(self.home/'New'/'Donnees'/'atelier.sqlite');queue_restore(new,self.zip);apply_pending(new.path.parent)
  self.assertEqual(Database(new.path).setting('output'),str(new.path.parent/'Exports'))
 def test_swap_failure_rolls_back(self):
  self.save();stage=queue_restore(self.db,self.zip);original=Path.rename
  def rename(path,target):
   if path==stage/'Donnees':raise OSError('Simulated locked destination')
   return original(path,target)
  with patch.object(Path,'rename',rename):apply_pending(self.root)
  self.assertFalse(json.loads((self.root/REPORT).read_text())['success']);self.assertEqual(self.db.rows('SELECT quantity FROM stock')[0]['quantity'],4)
