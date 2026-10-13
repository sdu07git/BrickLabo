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
    def test_uncheck_search_results_removes_all_duplo_categories_only(self):
        tags=self.keep(CategoryTags(['Bricks','DUPLO Bricks','Duplo Figures','duplo Vehicles','Plates'],show_tags=False))
        tags.select_all.click();tags.search.setText('duplo')
        with patch.object(tags,'update_selection',wraps=tags.update_selection) as updates:tags.uncheck_matches.click()
        self.assertEqual(updates.call_count,1)
        self.assertEqual(set(tags.values()),{'Bricks','Plates'})
        self.assertFalse(tags.bar.isVisible())
        tags.check_matches.click();self.assertEqual(len(tags.values()),5)
        tags.search.setText('absent');before=tags.values();tags.uncheck_matches.click()
        self.assertEqual(tags.values(),before);self.assertFalse(tags.uncheck_matches.isEnabled())
    def test_category_popup_and_advanced_filters_share_selection_without_tags(self):
        from atelier.catalogue import Catalogue
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QPushButton
        for category,ref in [('Bricks','a'),('Duplo Bricks','b'),('Duplo Plates','c'),('Plates','d')]:
            self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part',?,?,?,?)",(ref,category,category,category))
        cat=self.keep(Catalogue(self.db,'RB','part'));cat.resize(420,600);cat.show();app.processEvents()
        initial_y=cat.table.y();cat.category.showPopup();app.processEvents();picker=cat.category.picker
        picker.select_all.click();picker.search.setText('duplo');picker.uncheck_matches.click()
        self.assertEqual(cat.total,2);self.assertEqual(set(cat.advanced['categories']),{'Bricks','Plates'})
        self.assertTrue(cat.category.menu.isVisible());self.assertFalse(picker.bar.isVisible())
        cat.category.hidePopup();app.processEvents();self.assertEqual(cat.table.y(),initial_y)
        dialog=self.keep(FilterDialog(cat));dialog.show();app.processEvents()
        self.assertEqual(set(dialog.categories.values()),{'Bricks','Plates'});self.assertFalse(dialog.categories.bar.isVisible())
        dialog.categories.search.setText('plate');dialog.categories.uncheck_matches.click();cat.apply_filter_state(dialog.state())
        self.assertEqual(cat.total,1);self.assertEqual(cat.rows[0]['ref'],'a')
        cat.category.showPopup();app.processEvents();self.assertEqual(cat.category.picker.values(),['Bricks'])
        cat.category.hidePopup();dialog.close();cat.close()
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
