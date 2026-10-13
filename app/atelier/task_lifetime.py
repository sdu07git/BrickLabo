"""Keep Python runnables and their Qt signals alive until pool completion.

QRunnable auto-deletion otherwise releases the last Signals reference on a
worker, although that QObject belongs to the GUI thread. Retaining a runnable
also prevents cyclic GC from traversing its wrapper during native deletion.
Only the GUI thread registers, retires and deletes these objects.
"""
from PySide6.QtCore import QCoreApplication, QObject, QThread, QThreadPool, QTimer
from shiboken6 import isValid, delete


class TaskLifetime(QObject):
    def __init__(self, application):
        super().__init__(application)
        self.tasks = {}
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.collect)

    def hold(self, task, bridge):
        task.signals.setParent(self)
        self.tasks[id(task)] = (task, bridge)
        if not self.timer.isActive():
            self.timer.start()

    def release(self, key, task, bridge):
        # Callbacks can capture QWidget instances. Break those references on
        # the GUI thread, after run() has returned, rather than in the pool.
        if isValid(bridge) and not bridge._disposed:
            bridge.dispose()
        task.fn = None
        task.cancel = None
        if isValid(task.signals):
            task.signals.deleteLater()
        # The pool transfers native ownership even with autoDelete disabled.
        # Releasing only the Python reference would leak that QRunnable.
        if isValid(task):
            delete(task)
        self.tasks.pop(key, None)

    def abort(self, task):
        entry = self.tasks.get(id(task))
        if entry is not None:
            self.release(id(task), *entry)
        if not self.tasks:
            self.timer.stop()

    def collect(self, force=False):
        if not self.tasks:
            self.timer.stop()
            return True
        # A Python flag set at the end of run() is insufficient: the native
        # pool can still be unwinding the virtual call. This nonblocking join
        # establishes that no runnable can still touch its signal objects.
        if not QThreadPool.globalInstance().waitForDone(0):
            return False
        for key, (task, bridge) in list(self.tasks.items()):
            if not task.finished.is_set():
                continue
            # A result handler can open a modal dialog. Its nested event loop
            # must not destroy the bridge while that handler is still active.
            if not force and isValid(bridge) and not bridge._disposed:
                continue
            self.release(key, task, bridge)
        if not self.tasks:
            self.timer.stop()
        return not self.tasks


def lifetime():
    application = QCoreApplication.instance()
    if application is None or QThread.currentThread() != application.thread():
        raise RuntimeError('Background tasks must be started from the GUI thread.')
    manager = getattr(application, '_bricklabo_task_lifetime', None)
    if manager is None or not isValid(manager):
        manager = TaskLifetime(application)
        application._bricklabo_task_lifetime = manager
    return manager


def drain_tasks():
    """Retire completed tasks after the application has joined its pool."""
    application = QCoreApplication.instance()
    manager = getattr(application, '_bricklabo_task_lifetime', None)
    if manager is not None and isValid(manager):
        return manager.collect(force=True)
    return True
