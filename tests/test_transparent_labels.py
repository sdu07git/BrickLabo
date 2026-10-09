"""Transparency survives templates, exports and the native print pipeline."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication
from atelier.data import Database
from atelier.editor import LabelEditor
from atelier.labels import default_template,render_label,export_pdf,individual_template_key,template_for_item
from atelier.printing import PrintPreview
from atelier.ui_common import label_pixmap

app=QApplication.instance() or QApplication([])


class TransparentLabelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=Database(self.root/'db.sqlite');self.windows=[]
        identity=self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','3005','Brick 1x1','Bricks','brick')")
        self.item=self.db.get_item(identity);self.visuals={'main':Image.new('RGBA',(40,40),'red'),'side':Image.new('RGBA',(40,40),'white')}
        self.engine=SimpleNamespace(visuals=lambda *args,**kwargs:(self.visuals,''))
        self.template=default_template();self.template.update(width=25,height=15,background='#70a010',category_colors={'Bricks':'#000000'},layers=[
            {'type':'main','x':2,'y':2,'w':5,'h':5},
            {'type':'side','x':12,'y':2,'w':5,'h':5}])
    def tearDown(self):
        for window in self.windows:window.reject();window.deleteLater()
        app.processEvents();self.db.close();self.temp.cleanup()
    def keep(self,window):self.windows.append(window);return window
    def image(self,transparent=True):
        template=copy.deepcopy(self.template);template['transparent_background']=transparent
        return render_label(self.item,self.db,self.visuals,template,dpi=254)
    def test_existing_templates_remain_opaque_with_their_selected_colour(self):
        template=copy.deepcopy(self.template);template.pop('transparent_background')
        old=render_label(self.item,self.db,self.visuals,template,dpi=254);new=self.image(False)
        self.assertEqual(old.mode,'RGB');self.assertEqual(old.tobytes(),new.tobytes());self.assertEqual(old.getpixel((200,100)),(112,160,16))
    def test_transparency_preserves_parts_white_pixels_and_the_outline(self):
        image=self.image();self.assertEqual(image.mode,'RGBA');self.assertEqual(image.getpixel((200,100))[3],0)
        self.assertEqual(image.getpixel((40,40)),(255,0,0,255));self.assertEqual(image.getpixel((140,40)),(255,255,255,255));self.assertEqual(image.getpixel((2,80))[3],255)
    def test_png_round_trip_keeps_alpha_without_a_checkerboard(self):
        image=self.image();preview=label_pixmap(image).toImage();self.assertEqual(preview.pixelColor(200,100).alpha(),255);self.assertEqual(image.getpixel((200,100))[3],0)
        path=self.root/'label.png';image.save(path)
        with Image.open(path) as image:
            self.assertEqual(image.mode,'RGBA');self.assertEqual(image.getpixel((200,100))[3],0);self.assertEqual(image.getpixel((40,40)),(255,0,0,255))
    def test_pdf_embeds_a_transparency_mask_and_opaque_export_stays_opaque(self):
        transparent=self.root/'transparent.pdf';opaque=self.root/'opaque.pdf'
        export_pdf([self.image()],transparent,25,15);export_pdf([self.image(False)],opaque,25,15)
        self.assertIn(b'/SMask',transparent.read_bytes());self.assertNotIn(b'/SMask',opaque.read_bytes())
    def test_editor_toggle_undo_redo_reset_and_saved_background_colour(self):
        self.db.set_setting('template',self.template);editor=self.keep(LabelEditor(self.db,self.engine,self.item))
        editor.transparent_background.setChecked(True);self.assertFalse(editor.background_button.isEnabled());self.assertEqual(editor.view.backgroundBrush().style(),Qt.BrushStyle.TexturePattern)
        editor.undo();self.assertFalse(editor.transparent_background.isChecked());self.assertTrue(editor.background_button.isEnabled())
        editor.redo();self.assertTrue(editor.transparent_background.isChecked());editor.transparent_background.setChecked(False)
        self.assertEqual(editor.template['background'],'#70a010');editor.reset();self.assertFalse(editor.transparent_background.isChecked())
    def test_individual_setting_is_saved_without_changing_the_general_template(self):
        self.db.set_setting('template',self.template);editor=self.keep(LabelEditor(self.db,self.engine,self.item,individual=True))
        editor.transparent_background.setChecked(True);editor.apply()
        self.assertTrue(self.db.setting(individual_template_key(self.item))['transparent_background']);self.assertFalse(self.db.setting('template')['transparent_background'])
        reopened=self.keep(LabelEditor(self.db,self.engine,self.item,individual=True));self.assertTrue(reopened.transparent_background.isChecked())
        self.assertTrue(template_for_item(self.item,self.db)['transparent_background'])
    def test_json_template_load_retains_transparency_and_saved_colour(self):
        self.db.set_setting('template',self.template);editor=self.keep(LabelEditor(self.db,self.engine,self.item));editor.transparent_background.setChecked(True);path=self.root/'template.json'
        with patch('atelier.editor.QFileDialog.getSaveFileName',return_value=(str(path),'')):editor.save_as()
        saved=json.loads(path.read_text());self.assertTrue(saved['transparent_background']);self.assertEqual(saved['background'],'#70a010')
        editor.transparent_background.setChecked(False)
        with patch('atelier.editor.QFileDialog.getOpenFileName',return_value=(str(path),'')):editor.load()
        self.assertTrue(editor.transparent_background.isChecked());self.assertFalse(editor.background_button.isEnabled())
    def test_native_print_pipeline_keeps_alpha(self):
        image=self.image();preview=self.keep(PrintPreview([image],25,15));self.assertEqual(preview.images[0].pixelColor(200,100).alpha(),0)
        path=self.root/'native.pdf';preview.printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat);preview.printer.setOutputFileName(str(path))
        self.assertTrue(preview.paint_pages(preview.printer));self.assertIn(b'/SMask',path.read_bytes())


if __name__=='__main__':unittest.main()
