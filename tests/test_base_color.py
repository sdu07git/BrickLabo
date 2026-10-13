"""Factory colour reset remains a draft until the user applies it."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

from atelier.app import MainWindow
from atelier.base_color import DefaultColorDialog
from atelier.button_help import button_description
from atelier.data import Database
from atelier.i18n import set_language
from atelier.preview import VisualEngine
from atelier.render import DEFAULT_PART_COLOR
from atelier.task_lifetime import drain_tasks

app = QApplication.instance() or QApplication([])


class BaseColorTests(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name)/'db.sqlite')
        self.db.set_setting('default_color', '#123456')
        self.windows = []

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000); drain_tasks()
        for window in self.windows:
            window.close(); window.deleteLater()
            if isinstance(window, MainWindow): window.engine.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents(); self.db.close(); self.temp.cleanup(); set_language('fr')

    def test_top_colour_button_resets_only_after_apply_and_preserves_individual_colours(self):
        iid = self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','3001','Brick','Bricks','3001')")
        item = self.db.get_item(iid)
        self.db.save_visual(iid, color='#abcdef')
        with patch('atelier.catalogue.Catalogue.load_thumbnails'), patch('atelier.preview.Preview.refresh') as refresh, patch.object(MainWindow, 'visual_changed') as changed:
            window = MainWindow(self.db); self.windows.append(window); window.startup_timer.stop()
            button = next(b for b in window.top_controls.findChildren(QPushButton) if b.text()=='Couleur 3D')
            button.click(); dialog = window._consultation_windows[-1]
            self.assertIsInstance(dialog, DefaultColorDialog); self.assertFalse(dialog.isModal())
            self.assertTrue(dialog.testOption(dialog.ColorDialogOption.DontUseNativeDialog))
            QTest.mouseClick(dialog.defaults, Qt.MouseButton.LeftButton)
            self.assertEqual(dialog.currentColor().name(), DEFAULT_PART_COLOR)
            self.assertEqual(self.db.setting('default_color'), '#123456')
            dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
            self.assertEqual(self.db.setting('default_color'), '#123456')
            button.click(); dialog = window._consultation_windows[-1]; dialog.defaults.click()
            refresh.reset_mock(); changed.reset_mock()
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            self.assertEqual(self.db.setting('default_color'), DEFAULT_PART_COLOR)
            refresh.assert_called_once_with(); changed.assert_called_once_with(None)
            self.assertEqual(self.db.visual(iid)['color'], '#abcdef')
            self.assertEqual(window.engine.color_rgb(item, '#abcdef'), '#abcdef')
            self.assertEqual(window.engine.color_rgb(item), DEFAULT_PART_COLOR)
            reopened = Database(self.db.path)
            try: self.assertEqual(reopened.setting('default_color'), DEFAULT_PART_COLOR)
            finally: reopened.close()

    def test_custom_colour_can_still_be_applied_after_reset(self):
        with patch('atelier.catalogue.Catalogue.load_thumbnails'), patch('atelier.preview.Preview.refresh'):
            window = MainWindow(self.db); self.windows.append(window); window.startup_timer.stop()
            window.default_color(); dialog = window._consultation_windows[-1]
            dialog.defaults.click(); dialog.setCurrentColor(QColor('#778899'))
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            self.assertEqual(self.db.setting('default_color'), '#778899')

    def test_reset_button_and_specific_help_are_available_in_both_languages(self):
        for language, fragment in [('fr', 'jaune d’origine'), ('en', 'original yellow')]:
            set_language(language); dialog = DefaultColorDialog('#123456'); self.windows.append(dialog)
            self.assertIn(fragment, button_description(dialog.defaults))
            self.assertTrue(dialog.defaults.text())
            dialog.defaults.click(); self.assertEqual(dialog.currentColor().name(), DEFAULT_PART_COLOR)

    def test_factory_colour_matches_renderer_fallback_and_palette_has_priority(self):
        iid = self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','3001','Brick','Bricks','3001')")
        self.db.run("INSERT INTO colors(id,name,rgb) VALUES('4','Red','FF0000')")
        engine = VisualEngine(self.db); item = self.db.get_item(iid)
        try:
            self.assertEqual(engine.color_rgb(item), '#123456')
            self.db.set_setting('default_color', DEFAULT_PART_COLOR)
            self.assertEqual(engine.color_rgb(item), DEFAULT_PART_COLOR)
            self.assertEqual(engine.color_rgb(item, '4'), '#FF0000')
        finally: engine.close()
