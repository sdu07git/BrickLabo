"""Set selection survives native deletion, reopening and late callbacks."""
from unittest.mock import Mock,patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QDialog
from shiboken6 import delete,isValid

from test_projects_quantities_history import Fixture,app
from atelier.projects_panel import NewProjectDialog,ProjectsPanel
from atelier.set_picker import SetPicker,SetImagePreview


class SetPickerLifetimeTests(Fixture):
    def dialog(self):
        panel=ProjectsPanel(self.db);self.windows.append(panel)
        dialog=NewProjectDialog(panel);self.windows.append(dialog)
        return panel,dialog

    def test_native_deletion_clears_cached_picker_and_window_registry(self):
        panel,dialog=self.dialog();dialog.choose_set();old=dialog.picker
        self.assertIn(old,panel._consultation_windows)
        delete(old)
        self.assertIsNone(dialog.picker);self.assertNotIn(old,panel._consultation_windows)
        dialog.choose_set();self.assertTrue(isValid(dialog.picker));self.assertIsNot(old,dialog.picker)
        dialog.reject();self.assertIsNone(dialog.picker)

    def test_stale_wrapper_can_be_replaced_or_closed_without_native_calls(self):
        panel,dialog=self.dialog();old=SetPicker(self.db);delete(old);dialog.picker=old
        dialog.choose_set();self.assertTrue(isValid(dialog.picker));dialog.picker.reject()
        dialog.picker=old;dialog.reject();dialog.done(QDialog.DialogCode.Rejected)
        self.assertTrue(dialog.closed);self.assertIsNone(dialog.picker)

    def test_closed_and_deleted_picker_ignore_late_selection_and_acceptance(self):
        picker=SetPicker(self.db);item=self.db.get_item(self.set)
        picker.reject();picker.choose();picker.select(item);picker.reloaded()
        self.assertEqual(picker.result(),QDialog.DialogCode.Rejected)
        delete(picker);picker.choose();picker.select(item);picker.reloaded();picker.done(QDialog.DialogCode.Accepted)

    def test_old_picker_destruction_does_not_clear_the_replacement(self):
        panel,dialog=self.dialog();dialog.choose_set();old=dialog.picker;old.reject()
        dialog.choose_set();current=dialog.picker
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
        self.assertFalse(isValid(old));self.assertIs(dialog.picker,current);self.assertTrue(isValid(current))
        dialog.reject()

    def test_photo_callback_after_native_deletion_does_not_touch_widgets(self):
        preview=SetImagePreview(Mock());callbacks=[]
        with patch('atelier.set_picker.async_task',side_effect=lambda parent,work,done,fail:callbacks.append(done)):
            preview.set_item(self.db.get_item(self.set));preview.timer.stop();preview.load();delete(preview)
            callbacks[0](None);preview.stop()
