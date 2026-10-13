"""Actual small-window geometry, reachable controls and a persisted Qt drag."""
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from atelier.app import MainWindow
from atelier.catalogue import Catalogue
from atelier.i18n import set_language
from atelier.preferences_backup import collect_family
from atelier.ui_common import STYLE
from test_storage_and_inventory_batches import Fixture,app


class SmallScreenTests(Fixture):
    def setUp(self):
        super().setUp();self.previous_style=app.styleSheet();app.setStyleSheet(STYLE)
    def tearDown(self):
        super().tearDown();set_language('fr');app.setStyleSheet(self.previous_style)
    def settle(self):
        for _ in range(5):app.processEvents()
    def catalogue(self,source='RB',kind='part'):
        widget=self.keep(Catalogue(self.db,source,kind));widget.resize(420,650);widget.show();self.settle();return widget
    def main(self):
        window=self.keep(MainWindow(self.db));window.startup_timer.stop();window.resize(1024,600);window.show();self.settle();return window
    def test_narrow_filter_bar_uses_one_row_and_every_control_is_reachable(self):
        for language in ('fr','en'):
            set_language(language);cat=self.catalogue()
            self.assertLessEqual(cat.search.width(),240)
            self.assertLess(cat.filter_scroll.height(),65)
            self.assertGreater(cat.table.height(),250)
            self.assertGreater(cat.filter_scroll.horizontalScrollBar().maximum(),0)
            controls=[cat.search,cat.category,cat.filters_button,cat.decorated_button]
            self.assertLessEqual(max(w.geometry().center().y() for w in controls)-min(w.geometry().center().y() for w in controls),1)
            for widget in controls:
                cat.filter_scroll.ensureWidgetVisible(widget);self.settle()
                point=widget.mapTo(cat.filter_scroll.viewport(),widget.rect().center())
                self.assertTrue(cat.filter_scroll.viewport().rect().contains(point))
            self.assertNotEqual(cat.edit_labels_button.parentWidget(),cat.filter_scroll.widget())
            cat.close()
    def test_widening_and_narrowing_do_not_add_filter_rows(self):
        cat=self.catalogue();height=cat.filter_scroll.height()
        for width in (1400,520,800,420):
            cat.resize(width,650);self.settle()
            self.assertEqual(cat.filter_scroll.height(),height)
            self.assertLessEqual(cat.search.width(),240)
        cat.resize(1400,650);self.settle();self.assertEqual(cat.filter_scroll.horizontalScrollBar().maximum(),0)
    def test_year_and_alternative_catalogue_controls_remain_in_same_bar(self):
        for source,kind in (('RB','set'),('BL','set'),('ALT','part')):
            cat=self.catalogue(source,kind)
            for button in cat.filter_scroll.widget().findChildren(QPushButton):
                self.assertTrue(button.parentWidget().rect().contains(button.geometry()))
                cat.filter_scroll.ensureWidgetVisible(button);self.settle()
                self.assertTrue(cat.filter_scroll.viewport().rect().contains(button.mapTo(cat.filter_scroll.viewport(),button.rect().center())))
            if cat.year:self.assertEqual(cat.year.parentWidget(),cat.filter_scroll.widget())
            cat.close()
    def test_drag_frees_table_space_and_height_survives_reopening_and_backup(self):
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.preview.Preview.refresh'):
            window=self.main();split=window.workspace_splitter
            split.setSizes([210,split.height()-210]);self.settle()
            before=split.sizes()[0];table_height=window.catalogues[0].table.height();handle=split.handle(1)
            start=handle.rect().center();end=start-QPoint(0,130)
            QTest.mousePress(handle,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseMove(handle,end,20)
            QTest.mouseRelease(handle,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);self.settle()
            saved=split.sizes()[0]
            self.assertLess(saved,before-50)
            self.assertGreater(window.catalogues[0].table.height(),table_height+30)
            self.assertEqual(self.db.setting('top_panel_height'),saved)
            values=collect_family(self.db,'preferences')
            self.assertTrue(any(entry.get('target',{}).get('key')=='top_panel_height' and entry.get('value')==saved for entry in values['settings']))
            window.close();self.settle();reopened=self.main()
            self.assertAlmostEqual(reopened.workspace_splitter.sizes()[0],saved,delta=1)
    def test_reduced_top_panel_keeps_every_button_reachable(self):
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.preview.Preview.refresh'):
            window=self.main();window.workspace_splitter.setSizes([44,window.workspace_splitter.height()-44]);self.settle()
            self.assertGreater(window.top_scroll.verticalScrollBar().maximum(),0)
            for button in window.top_controls.findChildren(QPushButton):
                self.assertGreaterEqual(button.width(),button.minimumSizeHint().width())
                self.assertTrue(button.parentWidget().rect().contains(button.geometry()))
                window.top_scroll.ensureWidgetVisible(button);self.settle()
                self.assertTrue(window.top_scroll.viewport().rect().contains(button.mapTo(window.top_scroll.viewport(),button.rect().center())),button.text())
    def test_invalid_or_oversized_saved_height_preserves_the_main_workspace(self):
        with patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.preview.Preview.refresh'):
            for value in ('invalid',{},99999):
                self.db.set_setting('top_panel_height',value);window=self.main()
                self.assertGreater(window.workspace_splitter.sizes()[1],250)
                self.assertGreaterEqual(window.workspace_splitter.sizes()[0],44)
                window.close();self.settle()


if __name__=='__main__':
    import unittest
    unittest.main()
