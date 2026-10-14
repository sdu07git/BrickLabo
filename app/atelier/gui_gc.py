"""Collect Python/Qt cycles on the GUI thread, after native workers have joined.

Automatic cyclic GC can otherwise run during any allocation, including while
Shiboken is executing QRunnable.run(). Reference counting stays enabled; only
cyclic collection is deferred to an idle GUI timer. Do not collect from workers.
"""
import gc
from PySide6.QtCore import QObject, QCoreApplication, QThread, QThreadPool, QTimer
from .task_lifetime import drain_tasks


class GuiGarbageCollector(QObject):
    def __init__(self, application):
        if QThread.currentThread() != application.thread():
            raise RuntimeError('Garbage collection must be managed on the GUI thread.')
        super().__init__(application)
        self.was_enabled = gc.isenabled()
        self.closed = False
        self.collecting = False
        self.ticks = 0
        gc.disable()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.collect_if_idle)
        self.timer.start()

    def collect_if_idle(self, force=False):
        if self.closed or self.collecting:
            return False
        application = QCoreApplication.instance()
        if application is None or QThread.currentThread() != application.thread():
            raise RuntimeError('Garbage collection must run on the GUI thread.')
        if not QThreadPool.globalInstance().waitForDone(0):
            return False
        manager = getattr(application, '_bricklabo_task_lifetime', None)
        # In a modal result handler the pool may be idle but its bridge is
        # still executing. Let that handler unwind before any collection.
        if manager is not None and not manager.collect():
            return False
        self.ticks += 1
        counts, thresholds = gc.get_count(), gc.get_threshold()
        generation = 2 if force or self.ticks >= 30 else 1 if counts[1] >= thresholds[1] else 0
        if not force and generation == 0 and counts[0] < thresholds[0]:
            return True
        self.collecting = True
        try:
            gc.collect(generation)
            if generation == 2:
                self.ticks = 0
        finally:
            self.collecting = False
        return True

    def stop(self):
        if self.closed:
            return True
        if not QThreadPool.globalInstance().waitForDone(0):
            return False
        self.timer.stop()
        drain_tasks()
        self.collect_if_idle(force=True)
        self.closed = True
        if self.was_enabled:
            gc.enable()
        return True

