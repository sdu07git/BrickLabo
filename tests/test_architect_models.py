import unittest,tempfile,zipfile,json
from pathlib import Path
from atelier.architect_models import build_pack
from atelier.render import LDraw,RenderError
class ArchitectModelTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def archive(self,name,files):
  path=self.root/name
  with zipfile.ZipFile(path,'w') as z:
   for k,v in files.items():z.writestr(k,v)
  return path
 def test_recursive_pack_preserves_authors_licenses_status_and_geometry(self):
  source=self.archive('unofficial.zip',{'parts/79717-f1.dat':'0 Amortisseur\n0 Author: Example Author\n0 !LICENSE Licensed under CC BY 4.0\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 s/child.dat\n','parts/s/child.dat':'0 Child\n3 16 0 0 0 10 0 0 0 10 0\n','CAlicense4.txt':'License text','../escape.dat':'bad'})
  out=self.root/'pack.zip';r={'models':['79717-f1.dat']};build_pack([r],[('unofficial',source)],out)
  self.assertEqual(r['model_status']['79717-f1.dat'],'unofficial')
  with zipfile.ZipFile(out) as z:
   self.assertIn('parts/s/child.dat',z.namelist());self.assertNotIn('../escape.dat',z.namelist());self.assertIn('licenses/unofficial/calicense4.txt',z.namelist());meta=json.loads(z.read('ORIGINES.json'));self.assertEqual(meta['files']['parts/79717-f1.dat']['authors'],['Example Author']);self.assertFalse(meta['files']['parts/79717-f1.dat']['modified'])
  base=self.root/'ldraw';base.mkdir();(base/'ldconfig.ldr').write_text('0 Colours\n');renderer=LDraw(base,out)
  self.assertEqual(renderer.resolve('79717-f1.dat'),'79717-f1.dat');self.assertEqual(len(renderer.mesh('79717-f1')[0]),1)
 def test_broken_dependency_is_marked_unavailable_not_guessed(self):
  source=self.archive('official.zip',{'ldraw/parts/a.dat':'0 Part\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 missing.dat\n'})
  record={'models':['a.dat']};out=self.root/'pack.zip';result=build_pack([record],[('official',source)],out)
  self.assertEqual(record['model_status']['a.dat'],'unavailable');self.assertIn('a.dat',result['missing'])
  with zipfile.ZipFile(out) as z:self.assertNotIn('parts/a.dat',z.namelist())
 def test_existing_files_are_not_duplicated_in_supplement(self):
  geometry='0 Original\n3 16 0 0 0 10 0 0 0 10 0\n';original=self.archive('base.zip',{'ldraw/parts/a.dat':geometry});source=self.archive('official.zip',{'ldraw/parts/a.dat':geometry});out=self.root/'pack.zip'
  record={'models':['a.dat']};build_pack([record],[('official',source)],out,original)
  self.assertEqual(record['model_status']['a.dat'],'official')
  with zipfile.ZipFile(out) as z:self.assertNotIn('parts/a.dat',z.namelist())
if __name__=='__main__':unittest.main()
