import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication,QMenu
from atelier.data import Database
from atelier.preview import VisualEngine
from atelier.catalogue import Catalogue
from atelier.boxes import BoxDialog
app=QApplication.instance() or QApplication([])
class BoxSelectionTests(TestCase):
 def setUp(self):
   self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'BrickLabo éspace';self.program=self.root/'Programme';self.program.mkdir(parents=True);(self.program/'DISPOSITION_PORTABLE.json').write_text('{"layout":2}');self.db=Database(self.root/'Donnees'/'atelier.sqlite')
 def tearDown(self):self.temp.cleanup()
 def item(self,kind,ref):
   id=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL',kind,ref,ref,'Sets',ref));return self.db.get_item(id)
 def test_context_box_uses_right_clicked_set_among_multiple_selected(self):
   a=self.item('set','111-1');b=self.item('set','222-1');self.item('box','111-1');self.item('box','222-1');cat=Catalogue(self.db,'BL','set');cat.resize(900,500);cat.show();app.processEvents()
   cat.table.selectAll();self.assertEqual(len(cat.selection()),2)
   row=next(i for i,x in enumerate(cat.rows) if x['id']==b['id']);pos=cat.table.visualItemRect(cat.table.item(row,0)).center()
   class TestMenu(QMenu):
    def exec(menu,*args):
     next(x for x in menu.actions() if x.text()=='Afficher la boîte d’origine').trigger()
   with patch('atelier.catalogue.QMenu',TestMenu),patch.object(cat,'show_box') as show:
    cat.context_menu(pos);self.assertEqual(show.call_args[0][0]['id'],b['id'])
   cat.close()
 def test_old_photo_result_cannot_replace_new_box_or_closed_dialog(self):
   item=self.item('set','111-1');first=self.item('box','111-1');second=self.item('box','222-1');pending=[]
   def task(parent,work,done,fail):pending.append((done,fail))
   with patch('atelier.boxes.async_task',side_effect=task):
    dialog=BoxDialog(self.db,VisualEngine(self.db),item);dialog.boxes.append(second);dialog.choice.addItem('222-1');pending[0][0](Image.new('RGB',(80,60),'red'));self.assertIsNotNone(dialog.image)
    dialog.choice.setCurrentIndex(1);self.assertIsNone(dialog.image);self.assertIn('222-1',dialog.link.text());pending[0][0](Image.new('RGB',(80,60),'red'));self.assertIsNone(dialog.image)
    pending[1][0](Image.new('RGB',(80,60),'blue'));self.assertEqual(dialog.image.getpixel((0,0)),(0,0,255));dialog.reject();pending[0][0](Image.new('RGB',(80,60),'red'));self.assertEqual(dialog.image.getpixel((0,0)),(0,0,255))

 def test_containing_sets_box_action_for_parts_and_minifigs_targets_clicked_row(self):
  from atelier.dialogs import RelationsDialog
  a=self.item('set','111-1');b=self.item('set','222-1');self.item('box','222-1')
  for kind in ['part','minifig']:
   origin=self.item(kind,'origin-'+kind)
   with patch.object(self.db,'containing_sets',return_value=[a,b]),patch.object(RelationsDialog,'load_set'),patch('atelier.dialogs.async_task'),patch('atelier.preview.async_task'):
    d=RelationsDialog(self.db,VisualEngine(self.db),origin,None);d.resize(1100,700);d.show();app.processEvents()
    pos=d.set_table.visualItemRect(d.set_table.item(1,0)).center()
    class TestMenu(QMenu):
     def exec(menu,*args):
      action=menu.actions()[0];assert action.isEnabled();action.trigger()
    with patch('atelier.dialogs.QMenu',TestMenu),patch('atelier.dialogs.BoxDialog') as box:
     d.set_context_menu(pos);self.assertEqual(box.call_args.args[2]['id'],b['id']);box.return_value.exec.assert_called_once()
    d.close();d.deleteLater();app.processEvents()
 def test_containing_sets_without_box_disables_action(self):
  from atelier.dialogs import RelationsDialog
  target=self.item('set','333-1');origin=self.item('part','origin')
  with patch.object(self.db,'containing_sets',return_value=[target]),patch.object(RelationsDialog,'load_set'),patch('atelier.preview.async_task'):
   d=RelationsDialog(self.db,VisualEngine(self.db),origin,None);d.show();app.processEvents();pos=d.set_table.visualItemRect(d.set_table.item(0,0)).center()
   class TestMenu(QMenu):
    def exec(menu,*args):assert not menu.actions()[0].isEnabled()
   with patch('atelier.dialogs.QMenu',TestMenu),patch('atelier.dialogs.BoxDialog') as box:
    d.set_context_menu(pos);box.assert_not_called()
   d.close();d.deleteLater();app.processEvents()
