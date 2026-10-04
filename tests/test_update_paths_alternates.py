import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import errno,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.error import HTTPError
from PIL import Image
from PySide6.QtWidgets import QApplication
from atelier.fileio import atomic_output,temporary_path,error_message,compact_digest
from atelier.thumbnail_cache import ThumbnailCache
from atelier.alternates import fetch_alternates,AlternatesDialog,set_reference
from atelier.data import Database
app=QApplication.instance() or QApplication([])

class UpdateTests(unittest.TestCase):
 def test_atomic_failure_preserves_previous_and_cleans_temp(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'export.pdf';path.write_bytes(b'previous')
   with self.assertRaises(OSError):
    with atomic_output(path) as temp:
     self.assertLessEqual(len(temp.name),13);temp.write_bytes(b'partial');raise OSError(errno.ENAMETOOLONG,'long path')
   self.assertEqual(path.read_bytes(),b'previous');self.assertEqual(list(Path(folder).iterdir()),[path])
   with patch('atelier.fileio.os.replace',side_effect=OSError(206,'failure')):
    with self.assertRaises(OSError):
     with atomic_output(path) as temp:temp.write_bytes(b'new')
   self.assertEqual(path.read_bytes(),b'previous');self.assertEqual(list(Path(folder).iterdir()),[path])
 def test_short_names_and_unique_temps_and_memory_fallback(self):
  with tempfile.TemporaryDirectory() as folder:
   cache=ThumbnailCache(folder);key=(12,'a'*500)
   self.assertEqual(len(compact_digest('x')),43);self.assertLess(len(cache.path(key).name),52)
   a=temporary_path(folder);b=temporary_path(folder);self.assertNotEqual(a,b)
   with patch('atelier.fileio.temporary_path',side_effect=OSError(errno.ENAMETOOLONG,'too long')):
    cache.put(key,Image.new('RGB',(200,200),'red'))
   self.assertIsNotNone(cache.get(key));self.assertIn('trop long',error_message(OSError(errno.ENAMETOOLONG,'x')))
 def test_api_pages_errors_and_rejected_external_pagination(self):
  base='https://rebrickable.com/api/v3/lego/sets/75192-1/alternates/'
  payload={'results':[{'set_num':'MOC-1','name':'Test','moc_url':'https://rebrickable.com/mocs/MOC-1/'}],'count':101,'next':base+'?page=2'}
  with patch('atelier.alternates.request',return_value=json.dumps(payload).encode()) as request:
   rows,page,total=fetch_alternates('fake','75192-1');self.assertEqual(total,101);self.assertEqual(rows[0]['name'],'Test');fetch_alternates('fake','75192-1',page)
   self.assertEqual(request.call_args.args[0],page)
   with self.assertRaises(ValueError):fetch_alternates('fake','75192-1','https://evil.test/page')
   self.assertEqual(request.call_count,2)
  with patch('atelier.alternates.request',side_effect=HTTPError(base,429,'rate',None,None)):
   with self.assertRaisesRegex(ValueError,'Limite'):fetch_alternates('fake','75192-1')
  with self.assertRaisesRegex(ValueError,'clé'):fetch_alternates('','75192-1')
  self.assertEqual(set_reference({'source':'BL','ref':'75192'}),'75192-1')
  self.assertEqual(set_reference({'source':'ALT','ref':'75192'}),'')
 def test_dialog_paging_empty_error_and_close_during_request(self):
  with tempfile.TemporaryDirectory() as folder:
   db=Database(Path(folder)/'atelier.sqlite');db.set_setting('api_rb','fake')
   def task(owner,work,done,fail,*args):
    try:result=work(lambda x:None)
    except Exception as error:fail(str(error))
    else:done(result)
   row={'set_num':'MOC-1','name':'Test','num_parts':42,'moc_url':'https://rebrickable.com/mocs/MOC-1/'}
   with patch('atelier.alternates.async_task',side_effect=task),patch('atelier.alternates.fetch_alternates',return_value=([row],'next',2)):
    d=AlternatesDialog(db,None,{'source':'RB','ref':'75192-1','name':'Falcon'});self.assertEqual(d.table.rowCount(),1);self.assertTrue(d.more.isEnabled());self.assertTrue(d.open.isEnabled())
    with patch('atelier.alternates.fetch_alternates',return_value=([dict(row,set_num='MOC-2')],None,2)):d.load(False)
    self.assertEqual(d.table.rowCount(),2);self.assertFalse(d.more.isEnabled())
    with patch('atelier.alternates.fetch_alternates',side_effect=ValueError('Connexion impossible')):d.load(True)
    self.assertIn('Connexion',d.status.text());self.assertTrue(d.refresh.isEnabled())
    with patch('atelier.alternates.fetch_alternates',return_value=([],None,0)):d.load(True)
    self.assertIn('Aucune',d.status.text());d.reject()
   callbacks=[]
   with patch('atelier.alternates.async_task',side_effect=lambda owner,work,done,fail:callbacks.append(done)):
    d=AlternatesDialog(db,None,{'source':'RB','ref':'75192-1'});d.reject();callbacks[0](([row],None,1));self.assertEqual(d.table.rowCount(),0)

if __name__=='__main__':unittest.main()
