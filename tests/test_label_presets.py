"""Preset layouts use the actual underside, preserve settings and remain editable."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication

from atelier.data import Database
from atelier.editor import LabelEditor
from atelier.i18n import set_language
from atelier.labels import default_template,preset_template,required_views,render_label,template_for_item,individual_template_key,export_pdf
from atelier.preferences_backup import export_family,restore_families
from atelier.preview import VisualEngine

app=QApplication.instance() or QApplication([])


class LabelPresetTests(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.windows=[]
        self.db=Database(self.root/'db.sqlite')
        model=self.root/'ldraw';(model/'parts').mkdir(parents=True)
        (model/'ldconfig.ldr').write_text('0 !COLOUR Blue CODE 1 VALUE #0000FF EDGE #333333\n0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n0 !COLOUR Green CODE 2 VALUE #00FF00 EDGE #333333\n')
        # Red top, blue underside and a green mark on the underside's front right.
        (model/'parts/presettest.dat').write_text(
            '4 4 -20 -10 -20 20 -10 -20 20 -10 20 -20 -10 20\n'
            '4 1 -20 10 -20 20 10 -20 20 10 20 -20 10 20\n'
            '4 2 10 11 10 20 11 10 20 11 20 10 11 20\n')
        self.db.set_setting('ldraw',str(model));self.db.set_setting('camera_default',{})
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part','presettest','Brick 2 x 4','Bricks','presettest'))
        self.item=self.db.get_item(iid);self.engine=VisualEngine(self.db)

    def tearDown(self):
        for w in self.windows:w.reject()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
        for w in self.windows:w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
        self.engine.close();self.db.close();self.temp.cleanup();set_language('fr')

    def editor(self,individual=False):
        editor=LabelEditor(self.db,self.engine,self.item,individual=individual);self.windows.append(editor);return editor

    def choose(self,editor,key):editor.presets.setCurrentIndex(editor.presets.findData(key))

    def ready(self,editor):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            app.processEvents()
            if not editor.edge_running and not editor.edge_timer.isActive():return
            time.sleep(.01)
        self.fail('Preset preview did not finish')

    def test_presets_preserve_format_colours_transparency_and_individual_edges(self):
        base=default_template();base.update(width=80,height=30,transparent_background=True,background='#abcdef',border=.8,margin=2,category_colors={'Bricks':'#123456'},edge_settings={'black':50,'width':1.8})
        original=copy.deepcopy(base)
        for key in ('classic','main_centered','main_bottom'):
            with self.subTest(key=key):
                model=preset_template(key,base)
                for field in ('width','height','transparent_background','background','border','margin','category_colors','edge_settings'):self.assertEqual(model[field],base[field])
                self.assertTrue(all(l['x']>=0 and l['y']>=0 and l['x']+l['w']<=80 and l['y']+l['h']<=30 for l in model['layers']))
                model['category_colors']['Bricks']='#ffffff'
        self.assertEqual(base,original)

    def test_centred_main_layout_removes_secondary_views_and_centres_visible_pixels(self):
        model=preset_template('main_centered');self.assertEqual(required_views(model),('main',))
        self.assertFalse(any(l['type'] in ('top','side','bottom','divider','free') for l in model['layers']))
        image=Image.new('RGBA',(200,100));image.paste('red',(60,25,130,65))
        output=np.asarray(render_label(self.item,self.db,{'main':image},model,dpi=254))
        yy,xx=np.where((output[:,:,0]>230)&(output[:,:,1]<20)&(output[:,:,2]<20))
        self.assertGreater(len(xx),0);self.assertAlmostEqual((xx.min()+xx.max())/2,(output.shape[1]-1)/2,delta=1)
        self.assertTrue(any(l['type']=='references' for l in model['layers']))

    def test_underside_is_a_different_visible_face_with_the_correct_orientation(self):
        renderer=self.engine.renderer()
        top,bounds=renderer.render('presettest',(240,180),view='top',outlines=False)
        bottom,other=renderer.render('presettest',(240,180),view='bottom',outlines=False)
        np.testing.assert_array_equal(bounds,other)
        self.assertGreater(top.getpixel((120,90))[0],top.getpixel((120,90))[2])
        self.assertGreater(bottom.getpixel((120,90))[2],bottom.getpixel((120,90))[0])
        self.assertGreater(bottom.getpixel((177,33))[1],bottom.getpixel((177,33))[2])
        self.assertGreater(bottom.getpixel((177,147))[2],bottom.getpixel((177,147))[1])
        self.assertNotEqual(top.tobytes(),bottom.tobytes())

    def test_bottom_camera_is_fixed_and_geometry_cache_is_reused(self):
        renderer=self.engine.renderer()
        with patch.object(renderer,'_frame',wraps=renderer._frame) as frame:
            one,_=renderer.render('presettest',(180,150),view='bottom',camera={'yaw':120,'pitch':35,'roll':10})
            two,_=renderer.render('presettest',(180,150),view='bottom',camera={})
            self.assertEqual(one.tobytes(),two.tobytes());self.assertEqual(frame.call_count,1)

    def test_only_required_views_render_and_hidden_bottom_does_not_request_a_render(self):
        for key,expected in [('main_centered',['perspective']),('main_bottom',['perspective','bottom']),('classic',['perspective','top','side'])]:
            with self.subTest(key=key),patch.object(self.engine,'render_3d',wraps=self.engine.render_3d) as render:
                visual,note=self.engine.visuals(self.item,template=preset_template(key))
                self.assertEqual([c.args[3] for c in render.call_args_list],expected);self.assertEqual(note,'')
        model=preset_template('main_bottom')
        next(l for l in model['layers'] if l['type']=='bottom')['visible']=False
        self.assertEqual(required_views(model),('main',))

    def test_photo_has_no_fabricated_underside_and_reports_the_missing_view(self):
        photo=Image.new('RGB',(30,20),'red');self.db.save_visual(self.item['id'],mode='photo_rb')
        with patch.object(self.engine,'photo',return_value=photo):
            visual,note=self.engine.visuals(self.item,template=preset_template('main_bottom'))
            self.db.set_setting('template',preset_template('main_bottom'));editor=self.editor()
            self.assertIn('Vue de dessous indisponible',editor.edge_status.text())
        self.assertIs(visual['main'],photo);self.assertNotIn('bottom',visual);self.assertIn('Vue de dessous indisponible',note)

    def test_bottom_pixels_reach_label_png_pdf_and_zoom_stays_inside_its_layer(self):
        model=preset_template('main_bottom');visual,_=self.engine.visuals(self.item,template=model)
        output=render_label(self.item,self.db,visual,model,dpi=254);pixels=np.asarray(output)
        bottom=next(l for l in model['layers'] if l['type']=='bottom')
        x,y,w,h=(round(bottom[k]*10) for k in ('x','y','w','h'))
        area=pixels[y:y+h,x:x+w];self.assertGreater(int(((area[:,:,2]>100)&(area[:,:,0]<20)).sum()),100)
        path=self.root/'label.png';output.save(path)
        with Image.open(path) as reopened:self.assertEqual(output.tobytes(),reopened.tobytes())
        export_pdf([output],self.root/'label.pdf',model['width'],model['height']);self.assertIn(b'/Subtype /Image',(self.root/'label.pdf').read_bytes())
        bottom['image_zoom']=200;zoom=np.asarray(render_label(self.item,self.db,visual,model,dpi=254));mask=np.ones(pixels.shape[:2],dtype=bool);mask[y:y+h,x:x+w]=False
        np.testing.assert_array_equal(pixels[mask],zoom[mask]);self.assertFalse(np.array_equal(pixels[y:y+h,x:x+w],zoom[y:y+h,x:x+w]))

    def test_editor_updates_bottom_preview_and_keeps_choice_as_a_draft_until_apply(self):
        original=default_template();self.db.set_setting('template',original);editor=self.editor()
        self.choose(editor,'main_bottom');self.ready(editor)
        self.assertIn('bottom',editor.visuals);self.assertEqual(editor.template['preset_id'],'main_bottom');self.assertEqual(self.db.setting('template'),original)
        editor.apply();self.assertEqual(self.db.setting('template')['preset_id'],'main_bottom')

    def test_editor_undo_redo_restores_layout_and_selection_without_saving(self):
        editor=self.editor();self.choose(editor,'main_centered');self.choose(editor,'main_bottom');editor.undo()
        self.assertEqual(required_views(editor.template),('main',));self.assertEqual(editor.presets.currentData(),'main_centered')
        editor.redo();self.assertEqual(required_views(editor.template),('main','bottom'));self.assertEqual(editor.presets.currentData(),'main_bottom')
        editor.reject();self.assertIsNone(self.db.setting('template'))

    def test_individual_preset_keeps_custom_size_and_general_model_unchanged(self):
        general=default_template();general.update(width=80,height=30);self.db.set_setting('template',general)
        editor=self.editor(individual=True);self.choose(editor,'main_bottom');editor.apply()
        saved=self.db.setting(individual_template_key(self.item));self.assertEqual((saved['width'],saved['height']),(80,30));self.assertEqual(self.db.setting('template'),general)
        reopened=Database(self.db.path)
        try:self.assertEqual(required_views(template_for_item(self.item,reopened)),('main','bottom'))
        finally:reopened.close()

    def test_json_and_selective_backup_restore_bottom_layout(self):
        editor=self.editor();self.choose(editor,'main_bottom');path=self.root/'model.json'
        with patch('atelier.editor.QFileDialog.getSaveFileName',return_value=(str(path),'')):editor.save_as()
        self.choose(editor,'main_centered')
        with patch('atelier.editor.QFileDialog.getOpenFileName',return_value=(str(path),'')):editor.load()
        self.assertEqual(editor.presets.currentData(),'main_bottom');self.assertEqual(required_views(editor.template),('main','bottom'));editor.apply()
        backup=self.root/'backup.json';export_family(self.db,'labels',backup);self.db.set_setting('template',default_template());restore_families(self.db,[backup])
        self.assertEqual(required_views(self.db.setting('template')),('main','bottom'))

    def test_bottom_layer_has_image_controls_and_can_be_added_manually(self):
        editor=self.editor();editor.types.setCurrentIndex(editor.types.findData('bottom'));editor.add_layer()
        self.assertEqual(editor.current()['type'],'bottom');self.assertTrue(editor.auto_crop.isEnabled());self.assertTrue(editor.image_zoom.isEnabled())
        editor.image_zoom_value.setValue(150);self.assertEqual(editor.current()['image_zoom'],150)

    def test_english_choices_and_bottom_caption(self):
        set_language('en');editor=self.editor()
        self.assertEqual(editor.presets.itemText(editor.presets.findData('main_centered')),'Centred main view')
        self.choose(editor,'main_bottom');self.assertEqual(next(l['text'] for l in editor.template['layers'] if l['type']=='free'),'Bottom view')


if __name__=='__main__':unittest.main()
