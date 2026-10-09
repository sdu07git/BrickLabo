"""Modeless consultation windows owned by the application, including nested ones."""
from PySide6.QtCore import Qt


def application_owner(widget):
    current=widget
    while current is not None:
        if hasattr(current,'refresh_counts') and hasattr(current,'nav'):return current
        parent=current.parent()
        if parent is None:return current
        current=parent
    return widget


def show_window(window,parent=None,on_finished=None):
    owner=application_owner(parent or window.parent())
    if owner is None:owner=window
    flags=Qt.WindowType.Window|Qt.WindowType.WindowMinimizeButtonHint|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowCloseButtonHint
    if owner is not window:window.setParent(owner,flags)
    else:window.setWindowFlags(flags)
    window.setModal(False);window.setWindowModality(Qt.WindowModality.NonModal)
    window._modeless_managed=True;window._active_tasks=0;window._closed_by_manager=False
    from .ui_common import TaskBridge
    for bridge in window.findChildren(TaskBridge):
        if bridge.owner is None:bridge.owner=window;window._active_tasks+=1
    if not hasattr(owner,'_consultation_windows'):owner._consultation_windows=[]
    owner._consultation_windows.append(window)
    def finished(result):
        window._closed_by_manager=True
        if window in owner._consultation_windows:owner._consultation_windows.remove(window)
        if on_finished:on_finished(result)
        if hasattr(owner,'refresh_counts'):owner.refresh_counts()
        if not window._active_tasks:window.deleteLater()
    window.finished.connect(finished)
    window.show()
    return window


def task_owner(widget):
    while widget is not None:
        if getattr(widget,'_modeless_managed',False):return widget
        widget=widget.parent()
    return None


def notify_changed(widget):
    owner=application_owner(widget)
    if hasattr(owner,'refresh_counts'):owner.refresh_counts()
