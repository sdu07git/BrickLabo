"""Category inheritance, scoped batch edits and non-destructive hover previews."""
import copy
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox

from atelier.catalogue import Catalogue
from atelier.data import Database
from atelier.editor import LabelEditor
from atelier.i18n import set_language
from atelier.label_models import apply_selection,set_category_model,save_named_model,delete_named_model,merge_layout,validate_template
from atelier.labels import default_template,preset_template,template_for_item,individual_template_key,render_label,required_views
from atelier.preferences_backup import export_family,restore_families

app=QApplication.instance() or QApplication([])


class Engine:
    def visuals(self,item,*args,template=None,**kwargs):
        image=Image.new('RGBA',(80,60),'#ffdd00')
        return {'main':image,'top':image,'side':image,'bottom':image},''


class LabelModelTests(unittest.TestCase):
    def setUp(self):
        set_language('fr');self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite');self.engine=Engine();self.windows=[];self.items=[]
        for ref,category in [('3001','Bricks'),('3002','Bricks'),('3020','Plates')]:
            iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part',ref,'Brick 2 x 4',category,ref))
            self.items.append(self.db.get_item(iid))
        self.db.set_setting('template',default_template())

    def tearDown(self):
        for window in self.windows:window.reject()
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
        for window in self.windows:window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
        self.db.close();self.temp.cleanup();set_language('fr')

    def editor(self,**kwargs):
        window=LabelEditor(self.db,self.engine,self.items[0],**kwargs);self.windows.append(window);return window

    def queue(self,item,color):
        self.db.add('queue',item['id'],color,2)
        entry=self.db.rows('SELECT id FROM queue WHERE item_id=? AND color=?',(item['id'],color))[0]['id']
        return dict(item,_scope='queue',entry_id=entry,chosen_color=color,chosen_quantity=2)

    def test_priority_individual_category_general_and_reset_to_category(self):
        set_category_model(self.db,'Bricks',preset_template('main_centered'))
        self.db.set_setting(individual_template_key(self.items[0]),preset_template('main_bottom'))
        self.assertEqual(template_for_item(self.items[0],self.db)['preset_id'],'main_bottom')
        self.assertEqual(template_for_item(self.items[1],self.db)['preset_id'],'main_centered')
        self.assertNotIn('preset_id',template_for_item(self.items[2],self.db))
        self.db.set_setting(individual_template_key(self.items[0]),{'use_general':True})
        self.assertEqual(template_for_item(self.items[0],self.db)['preset_id'],'main_centered')
        set_category_model(self.db,'Bricks',None)
        self.assertNotIn('preset_id',template_for_item(self.items[0],self.db))

    def test_category_follows_global_format_and_current_category_palette(self):
        model=preset_template('main_centered');model['category_colors']={'Bricks':'#ffffff'};set_category_model(self.db,'Bricks',model)
        base=default_template();base.update(width=80,height=30,category_colors={'Bricks':'#123456'})
        self.db.set_setting('template',base);resolved=template_for_item(self.items[0],self.db)
        self.assertEqual(resolved['width'],80);self.assertEqual(resolved['height'],30);self.assertEqual(resolved['category_colors'],base['category_colors'])
        self.assertAlmostEqual(next(l for l in resolved['layers'] if l['type']=='main')['w'],61*80/65)

    def test_category_applies_to_new_refs_and_scoped_queue_labels(self):
        set_category_model(self.db,'Bricks',preset_template('main_bottom'))
        scoped=self.queue(self.items[1],'4')
        self.assertEqual(template_for_item(scoped,self.db)['preset_id'],'main_bottom')
        iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('BL','part','new','New part','Bricks','new'))
        self.assertEqual(template_for_item(self.db.get_item(iid),self.db)['preset_id'],'main_bottom')

    def test_batch_changes_only_selected_entries_preserving_stock_visuals_and_edges(self):
        one=self.queue(self.items[0],'4');other=self.queue(self.items[0],'1');two=self.queue(self.items[1],'14')
        personal=default_template();personal.update(edge_settings={'black':35,'width':2},category_colors={'Bricks':'#234567'})
        self.db.set_setting(individual_template_key(one),personal)
        self.db.save_visual(self.items[0]['id'],mode='3d',color='4');self.db.set_setting('camera_item_'+str(one['id']),{'yaw':30})
        self.db.add('stock',self.items[0]['id'],'4',9)
        before={table:self.db.rows('SELECT * FROM '+table) for table in ('stock','queue','visual','history')}
        source=preset_template('main_centered');source['edge_settings']={'black':100,'width':10};source['category_colors']={'Bricks':'#ffffff'}
        self.assertEqual(apply_selection(self.db,[one,two,one],source),2)
        self.assertEqual(template_for_item(one,self.db)['edge_settings'],personal['edge_settings']);self.assertEqual(template_for_item(one,self.db)['category_colors'],personal['category_colors'])
        self.assertEqual(template_for_item(two,self.db)['preset_id'],'main_centered')
        self.assertNotIn('preset_id',template_for_item(other,self.db));self.assertNotIn('preset_id',template_for_item(self.items[0],self.db))
        for table,rows in before.items():self.assertEqual(self.db.rows('SELECT * FROM '+table),rows)
        self.assertEqual(self.db.setting('camera_item_'+str(one['id'])),{'yaw':30})

    def test_batch_validation_is_atomic_when_an_entry_has_been_removed(self):
        one=self.queue(self.items[0],'4');two=self.queue(self.items[1],'1');self.db.run('DELETE FROM queue WHERE id=?',(two['entry_id'],))
        with self.assertRaisesRegex(ValueError,'sélection a changé'):apply_selection(self.db,[one,two],preset_template('main_centered'))
        self.assertIsNone(self.db.setting(individual_template_key(one)))

    def test_batch_catalogue_layout_inherits_into_future_queue_entries(self):
        apply_selection(self.db,self.items[:2],preset_template('main_bottom'))
        queued=self.queue(self.items[0],'4')
        self.assertEqual(template_for_item(queued,self.db)['preset_id'],'main_bottom')
        self.assertNotIn('preset_id',template_for_item(self.items[2],self.db))

    def test_named_model_survives_reopen_and_delete_keeps_applied_layouts(self):
        save_named_model(self.db,'Mon modèle',preset_template('main_centered'))
        editor=self.editor();index=editor.presets.findData('custom:Mon modèle');self.assertGreater(index,0);editor.presets.setCurrentIndex(index);editor.apply()
        delete_named_model(self.db,'Mon modèle');self.assertEqual(self.db.setting('templates'),{})
        self.assertEqual(self.db.setting('template')['model_name'],'Mon modèle')
        self.assertEqual(len(self.db.setting('template')['layers']),5)

    def test_save_model_button_adds_current_draft_to_menu_without_applying_it(self):
        editor=self.editor();editor.presets.setCurrentIndex(editor.presets.findData('main_centered'))
        with patch.object(QInputDialog,'getText',return_value=('Ma disposition',True)):editor.save_model()
        self.assertGreater(editor.presets.findData('custom:Ma disposition'),0);self.assertEqual(len(self.db.setting('template')['layers']),10)
        self.assertEqual(self.db.setting('templates')['Ma disposition']['model_name'],'Ma disposition')

    def test_hover_displays_side_preview_without_selecting_or_saving(self):
        editor=self.editor();editor.show();app.processEvents();before=copy.deepcopy(editor.template);settings=self.db.rows('SELECT * FROM settings ORDER BY key')
        editor.presets.showPopup();editor.presets.preview_model(editor.presets.findData('main_bottom'));app.processEvents()
        self.assertTrue(editor.presets.hover.isVisible());self.assertFalse(editor.presets.image.pixmap().isNull())
        self.assertEqual(editor.template,before);self.assertEqual(editor.presets.currentIndex(),0);self.assertEqual(self.db.rows('SELECT * FROM settings ORDER BY key'),settings)
        editor.presets.hidePopup();self.assertFalse(editor.presets.hover.isVisible());self.assertFalse(editor.presets.timer.isActive())

    def test_batch_editor_captures_selection_and_changes_draft_at_will(self):
        targets=self.items[:2];editor=self.editor(targets=targets,selection_mode=True);targets.clear()
        self.assertEqual(len(editor.targets),2);self.assertEqual(editor.destination.currentData(),'selection');self.assertFalse(editor.width.isEnabled())
        editor.presets.setCurrentIndex(editor.presets.findData('main_centered'));editor.layer_list.setCurrentRow(1);editor.props['x'].setValue(5)
        self.assertEqual(editor.presets.currentIndex(),0);self.assertIsNone(self.db.setting(individual_template_key(self.items[0])))
        editor.apply();self.assertEqual(next(l for l in template_for_item(self.items[0],self.db)['layers'] if l['type']=='main')['x'],5)
        self.assertEqual(template_for_item(self.items[0],self.db)['layers'],template_for_item(self.items[1],self.db)['layers'])

    def test_editor_category_destination_and_reset_leave_general_unchanged(self):
        editor=self.editor();editor.presets.setCurrentIndex(editor.presets.findData('main_bottom'));editor.destination.setCurrentIndex(editor.destination.findData('category'));editor.apply()
        self.assertEqual(len(self.db.setting('template')['layers']),10);self.assertEqual(template_for_item(self.items[0],self.db)['preset_id'],'main_bottom')
        other=self.editor();other.destination.setCurrentIndex(other.destination.findData('category'));other.reset_category()
        self.assertNotIn('preset_id',template_for_item(self.items[0],self.db))

    def test_catalogue_button_uses_cross_page_selection_and_no_extra_rows(self):
        catalogue=Catalogue(self.db,'RB','part');catalogue.engine=self.engine;catalogue.ids={self.items[0]['id'],self.items[1]['id']};self.windows.append(catalogue)
        with patch('atelier.catalogue.show_window',side_effect=lambda window,*args,**kw:self.windows.append(window)):
            editor=catalogue.edit_selected_labels()
        self.assertEqual({item['id'] for item in editor.targets},{self.items[0]['id'],self.items[1]['id']});self.assertEqual(editor.destination.currentData(),'selection')
        self.windows.remove(catalogue);catalogue.deleteLater()

    def test_selective_label_backup_includes_named_category_and_scoped_layouts(self):
        save_named_model(self.db,'Perso',preset_template('main_centered'));set_category_model(self.db,'Bricks',preset_template('main_bottom'))
        queued=self.queue(self.items[0],'4');apply_selection(self.db,[queued],preset_template('main_centered'))
        path=Path(self.temp.name)/'labels.json';export_family(self.db,'labels',path)
        self.db.run("DELETE FROM settings WHERE key LIKE 'label_layout_%' OR key='templates'")
        restore_families(self.db,[path]);self.assertIn('Perso',self.db.setting('templates'));self.assertEqual(template_for_item(self.items[1],self.db)['preset_id'],'main_bottom');self.assertEqual(template_for_item(queued,self.db)['preset_id'],'main_centered')

    def test_malformed_model_rejected_before_any_writes(self):
        model=preset_template('main_centered');model['layers'][0]['x']=float('nan')
        with self.assertRaises(ValueError):apply_selection(self.db,self.items,model)
        self.assertIsNone(self.db.setting(individual_template_key(self.items[0])))

    def test_english_model_and_scope_choices(self):
        set_language('en');save_named_model(self.db,'Personal',preset_template('main_centered'));editor=self.editor(targets=self.items[:2],selection_mode=True)
        self.assertEqual(editor.presets.itemText(editor.presets.findData('custom:Personal')),'Custom: Personal')
        self.assertEqual(editor.destination.itemText(editor.destination.findData('selection')),'Selection (2 labels)')

    def test_switching_named_model_to_builtin_resets_model_name(self):
        save_named_model(self.db,'Custom',preset_template('main_centered'));editor=self.editor()
        editor.presets.setCurrentIndex(editor.presets.findData('custom:Custom'));editor.presets.setCurrentIndex(editor.presets.findData('main_bottom'))
        self.assertNotIn('model_name',editor.template);self.assertEqual(editor.presets.currentData(),'main_bottom')

    def test_async_hover_loads_missing_views_without_changing_editor_draft(self):
        class PartialEngine:
            def visuals(self,item,*args,template=None,**kwargs):
                return {kind:Image.new('RGBA',(40,30),'red' if kind=='bottom' else 'yellow') for kind in required_views(template)},''
        self.engine=PartialEngine();self.db.set_setting('template',preset_template('main_centered'));editor=self.editor();editor.show();app.processEvents()
        before=copy.deepcopy(editor.template);editor.presets.showPopup();editor.presets.preview_model(editor.presets.findData('main_bottom'))
        deadline=time.monotonic()+3
        while editor.presets.note.text()=='Chargement de l’aperçu…':
            app.processEvents();time.sleep(.01);self.assertLess(time.monotonic(),deadline)
        self.assertEqual(editor.template,before);self.assertEqual(set(editor.visuals),{'main'});self.assertTrue(editor.presets.hover.isVisible())
        editor.reject();self.assertFalse(editor.presets.hover.isVisible());self.assertTrue(editor.presets.closed)

    def test_non_general_destination_keeps_sheet_size_even_after_reset(self):
        base=default_template();base.update(width=80,height=30);self.db.set_setting('template',base)
        editor=self.editor(targets=self.items[:2],selection_mode=True);editor.reset()
        self.assertEqual((editor.template['width'],editor.template['height']),(80,30));editor.apply()
        self.assertEqual((template_for_item(self.items[1],self.db)['width'],template_for_item(self.items[1],self.db)['height']),(80,30))
