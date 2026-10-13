"""Real hover timing, closing windows and contextual button explanations."""
import ast
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent,QPoint,Qt
from PySide6.QtGui import QCursor,QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton,QDialog,QVBoxLayout,QDialogButtonBox,QFormLayout,QCheckBox,QComboBox,QToolTip
from shiboken6 import delete

from atelier.button_help import install_button_help,button_description,descriptions
from atelier import button_help
from atelier.data import Database
from atelier.dialogs import APIDialog
from atelier.i18n import tr,set_language

app=QApplication.instance() or QApplication([])


class ButtonHelpTests(unittest.TestCase):
    def setUp(self):
        set_language('fr');self.manager=install_button_help(app);self.manager.cancel();QToolTip.hideText();self.windows=[]

    def tearDown(self):
        self.manager.cancel();QToolTip.hideText()
        for window in self.windows:window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents();set_language('fr')

    def window(self,caption='Générer',enabled=True):
        window=QDialog();window.move(40,40);layout=QVBoxLayout(window);button=QPushButton(caption);button.setEnabled(enabled);layout.addWidget(button)
        window.resize(420,130);window.show();self.windows.append(window);app.processEvents();return window,button

    def hover(self,button):
        QCursor.setPos(button.mapToGlobal(button.rect().center()));QTest.mouseMove(button,button.rect().center());app.processEvents()
        # Enter is platform-dependent for synthetic mouse events offscreen.
        QCoreApplication.sendEvent(button,QEvent(QEvent.Type.Enter));app.processEvents()

    def test_help_appears_after_two_seconds_without_a_click(self):
        _,button=self.window();self.hover(button);start=time.monotonic()
        QTest.qWait(1850);self.assertFalse(QToolTip.isVisible());self.assertTrue(self.manager.timer.isActive())
        QTest.qWait(250);self.assertGreaterEqual(time.monotonic()-start,2);self.assertTrue(QToolTip.isVisible())
        self.assertIn('Enregistre les étiquettes',QToolTip.text().replace('\n',' '));self.assertFalse(button.isDown())

    def test_next_button_starts_a_new_delay_and_native_tip_cannot_appear_early(self):
        window,button=self.window();second=QPushButton('Aide');window.layout().addWidget(second);app.processEvents();self.hover(button)
        with patch('atelier.button_help.QToolTip.showText') as show:
            self.manager.show_help();self.assertEqual(show.call_count,1);self.hover(second)
            event=QHelpEvent(QEvent.Type.ToolTip,second.rect().center(),second.mapToGlobal(second.rect().center()))
            QCoreApplication.sendEvent(second,event);QTest.qWait(100)
            self.assertGreater(self.manager.timer.remainingTime(),1700);self.assertEqual(show.call_count,1)

    def test_leaving_clicking_and_hiding_cancel_pending_help(self):
        window,button=self.window()
        self.hover(button);QCoreApplication.sendEvent(button,QEvent(QEvent.Type.Leave));self.assertFalse(self.manager.timer.isActive());self.assertIsNone(self.manager.current())
        self.hover(button);QTest.mousePress(button,Qt.MouseButton.LeftButton);self.assertFalse(self.manager.timer.isActive());self.assertIsNone(self.manager.current());QTest.mouseRelease(button,Qt.MouseButton.LeftButton)
        self.hover(button);window.hide();app.processEvents();self.assertFalse(self.manager.timer.isActive())
        with patch('atelier.button_help.QToolTip.showText') as show:self.manager.show_help();show.assert_not_called()

    def test_deleted_button_does_not_trigger_a_stale_tooltip(self):
        _,button=self.window();self.hover(button);delete(button)
        with patch('atelier.button_help.QToolTip.showText') as show:self.manager.show_help();show.assert_not_called()
        self.assertIsNone(self.manager.current())

    def test_disabled_buttons_and_buttons_created_later_have_explanations(self):
        window,button=self.window('Charger via l’API BrickLink (facultatif)',False)
        self.assertIn('Identifiants BrickLink requis',button.toolTip())
        late=QPushButton('Mettre à jour LDraw (complete.zip)');window.layout().addWidget(late);app.processEvents()
        self.assertIn('bibliothèque officielle LDraw',late.toolTip());self.assertIs(install_button_help(app),self.manager)

    def test_existing_explanation_and_link_are_preserved(self):
        _,button=self.window('Ouvrir');button.setToolTip('Cette notice est déjà enregistrée sur le PC.')
        self.assertEqual(button_description(button),'Cette notice est déjà enregistrée sur le PC.')
        button.setToolTip('https://example.test/notice');self.assertIn('Ouvre cette page',button_description(button));self.assertEqual(button.toolTip(),'https://example.test/notice')

    def test_a_changed_caption_updates_generated_help(self):
        _,button=self.window('Masquer stickers et sérigraphies');first=button.toolTip()
        button.setText('Réafficher stickers et sérigraphies');self.hover(button)
        self.assertNotEqual(button.toolTip(),first);self.assertIn('Réaffiche',button.toolTip())

    def test_editor_undo_is_distinct_from_a_child_dialog_cancel(self):
        class LabelEditor(QDialog):pass
        editor=LabelEditor();self.windows.append(editor);layout=QVBoxLayout(editor);undo=QPushButton('Annuler');layout.addWidget(undo)
        self.assertIn('dernière modification du brouillon',button_description(undo))
        child=QDialog(editor);self.windows.append(child);box=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel,child)
        cancel=box.button(QDialogButtonBox.StandardButton.Cancel);cancel.setText('Annuler')
        self.assertIn('Ferme la fenêtre',button_description(cancel))

    def test_form_label_explains_a_checkbox_without_button_text(self):
        window=QDialog();self.windows.append(window);form=QFormLayout(window);checkbox=QCheckBox();form.addRow('Verrouillé',checkbox)
        window.show();app.processEvents();self.assertIn('Empêche de déplacer',button_description(checkbox))

    def test_english_explanations_and_dynamic_states(self):
        set_language('en');_,button=self.window(tr('Mettre à jour LDraw (complete.zip)'))
        self.assertIn('Downloads and validates',button_description(button))
        button.setText(tr('Réafficher stickers et sérigraphies'));self.hover(button);self.assertIn('Shows decorated parts',button.toolTip())

    def test_help_does_not_reveal_credentials_or_change_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Database(Path(temp)/'db.sqlite');db.set_setting('api_rb','private-test-value');window=APIDialog(db,None);self.windows.append(window);window.show();app.processEvents()
            for button in window.findChildren(QPushButton)+window.findChildren(QCheckBox):self.assertNotIn('private-test-value',button_description(button))
            self.assertEqual(window.rb.text(),'private-test-value');self.assertEqual(window.rb.echoMode(),window.rb.EchoMode.Password);window.close();db.close()

    def test_non_button_tooltips_and_model_preview_are_not_intercepted(self):
        window,_=self.window();combo=QComboBox();combo.addItem('Main and bottom views');combo.setToolTip('Model preview');window.layout().addWidget(combo)
        event=QHelpEvent(QEvent.Type.ToolTip,QPoint(2,2),combo.mapToGlobal(QPoint(2,2)))
        self.assertFalse(self.manager.eventFilter(combo,event))

    def test_missing_optional_help_file_does_not_break_a_window(self):
        descriptions.cache_clear();button_help._canonical_captions.cache_clear()
        try:
            with tempfile.TemporaryDirectory() as temp,patch('atelier.button_help.resources_directory',return_value=Path(temp)):
                with self.assertLogs('bricklabo',level='WARNING'):
                    _,button=self.window();self.assertTrue(button.toolTip());self.hover(button)
        finally:descriptions.cache_clear();button_help._canonical_captions.cache_clear()

    def test_static_button_captions_have_specific_short_bilingual_help(self):
        root=Path(__file__).resolve().parent.parent/'app/atelier';known=descriptions()['buttons'];missing=set()
        def literal(node):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('tr','tf') and node.args:return literal(node.args[0])
        for path in root.glob('*.py'):
            tree=ast.parse(path.read_text())
            for function in (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef)):
                for call in (node for node in ast.walk(function) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('QPushButton','WrappedButton','QCheckBox','QRadioButton') and node.args):
                    caption=literal(call.args[0])
                    if caption and caption not in known:missing.add((path.name,caption))
        self.assertEqual(missing,set())
        for value in list(known.values())+list(descriptions()['contexts'].values()):
            for lang in ('fr','en'):self.assertTrue(value[lang]);self.assertLess(len(value[lang]),190)
