"""The actual checklist supports all categories, hidden rows and saved filters."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QComboBox,QCheckBox
from atelier.category_tags import CategoryTags
from atelier.search_filters import FilterDialog
from atelier import i18n
from test_storage_and_inventory_batches import Fixture,app


class CategorySelectionTests(Fixture):
    def test_all_includes_hidden_categories_then_uncheck_and_tag_removal(self):
        tags=self.keep(CategoryTags(['Briques','Chapeaux','Armes','Briques']))
        tags.search.setText('brique');tags.select_all.click()
        self.assertEqual(set(tags.values()),{'Briques','Chapeaux','Armes'})
        self.assertTrue(tags.list.item(0).isHidden())
        tags.list.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(set(tags.values()),{'Briques','Chapeaux'})
        tags.bar.removed.emit('Chapeaux');self.assertEqual(tags.values(),['Briques'])
        tags.search.clear();self.assertFalse(any(tags.list.item(i).isHidden() for i in range(tags.list.count())))
        tags.set_values([]);self.assertEqual(tags.values(),[]);self.assertIn('Aucun filtre',tags.count.text())
    def test_selection_uses_one_tag_rebuild_for_all_and_remembers_preset_names(self):
        tags=self.keep(CategoryTags(['Briques','Armes']))
        tags.set_values(['Catégorie importée']);tags.search.setText('armes')
        with patch.object(tags.bar,'set_tags',wraps=tags.bar.set_tags) as updates:tags.select_all.click()
        self.assertEqual(updates.call_count,1)
        self.assertEqual(set(tags.values()),{'Briques','Armes','Catégorie importée'})
    def test_saved_advanced_filter_excludes_removed_category_in_real_fts_query(self):
        for category,ref in [('Briques','3010'),('Armes','4000'),('Chapeaux','5000')]:
            self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part',?,?,?,?)",(ref,category,category,category))
        catalogue=self.keep(QWidget());catalogue.db=self.db;catalogue.key='RBpart';catalogue.source='RB';catalogue.kind='part';catalogue.scope='catalogue'
        catalogue.category=QComboBox();catalogue.category.addItem('Toutes','')
        for value in ['Briques','Armes','Chapeaux']:catalogue.category.addItem(value,value)
        catalogue.search=QComboBox();catalogue.hide_decorated=QCheckBox();catalogue.advanced={};catalogue.year=None;catalogue.filter_state=lambda:{}
        dialog=self.keep(FilterDialog(catalogue))
        dialog.categories.select_all.click();dialog.categories.remove('Armes');state=dialog.state()
        self.db.set_setting(dialog.preset_key,{'Sans armes':state})
        reopened=self.keep(FilterDialog(catalogue));reopened.presets_combo.setCurrentText('Sans armes');reopened.load_preset()
        self.assertEqual(set(reopened.categories.values()),{'Briques','Chapeaux'})
        rows,total,_,_=self.db.query('RB','part',advanced=reopened.state()['advanced'])
        self.assertEqual(total,2);self.assertEqual({r['ref'] for r in rows},{'3010','5000'})
    def test_english_controls_keep_database_category_names(self):
        try:
            i18n.set_language('en');tags=self.keep(CategoryTags(['Briques','Armes']));tags.select_all.click()
            self.assertEqual(tags.select_all.text(),'Select all categories');self.assertEqual(set(tags.values()),{'Briques','Armes'})
        finally:i18n.set_language('fr')
