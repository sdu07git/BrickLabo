"""Qt ownership regressions for the Windows heap-corruption report."""
import gc
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
import time
import unittest
import weakref
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from shiboken6 import isValid

from atelier.brickarchitect import parse_page
from atelier.services import RequestCancelled
from atelier.task_lifetime import drain_tasks, lifetime
from atelier.ui_common import TaskBridge, async_task
from atelier.windows import show_window

app = QApplication.instance() or QApplication([])


def pump_until(predicate, timeout=5):
    deadline = time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        time.sleep(.001)
    if not predicate():
        raise AssertionError('Background task did not finish.')


class TaskLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.parents = []
        self.gui_id = threading.get_ident()
        self.assertTrue(QThreadPool.globalInstance().waitForDone(5000))
        drain_tasks()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def tearDown(self):
        self.assertTrue(QThreadPool.globalInstance().waitForDone(5000))
        drain_tasks()
        for parent in self.parents:
            if isValid(parent): parent.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()

    def parent(self):
        parent = QWidget(); self.parents.append(parent); return parent

    def test_concurrent_brickarchitect_parsing_and_gc_destroy_signals_on_gui_without_leaks(self):
        parent = self.parent(); done = []; destroyed = []; callbacks = []; tasks = []; signals = []
        html = '<a href="https://brickarchitect.com/parts/3001"><div class="tr"><span class="partname">Brick 2 x 4</span></div></a>'
        def work(progress):
            self.assertNotEqual(threading.get_ident(), self.gui_id)
            for _ in range(4):
                data = parse_page(html, 1)
                progress('parsed')
                cycle = []; cycle.append(cycle)
                gc.collect(); time.sleep(.001)
            return data
        def complete(result):
            self.assertEqual(result[0]['ref'], '3001')
            callbacks.append(threading.get_ident()); done.append(result)
        for _ in range(120):
            task = async_task(parent, work, complete, self.fail)
            task.signals.destroyed.connect(lambda *_: destroyed.append(threading.get_ident()), Qt.ConnectionType.DirectConnection)
            tasks.append(weakref.ref(task)); signals.append(weakref.ref(task.signals))
        del task
        pump_until(lambda: len(done)==120 and not lifetime().tasks, timeout=20)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete); gc.collect()
        self.assertEqual(callbacks, [self.gui_id]*120)
        self.assertEqual(destroyed, [self.gui_id]*120)
        self.assertTrue(all(ref() is None for ref in tasks))
        self.assertTrue(all(ref() is None for ref in signals))

    def test_parent_deleted_during_work_does_not_delete_the_emitter_or_deliver_callbacks(self):
        parent = self.parent(); started = threading.Event(); release = threading.Event(); done = Mock(); failed = Mock(); destroyed = []
        def work(progress):
            started.set(); self.assertTrue(release.wait(3)); progress('late'); return 42
        task = async_task(parent, work, done, failed)
        task.signals.destroyed.connect(lambda *_: destroyed.append(threading.get_ident()), Qt.ConnectionType.DirectConnection)
        self.assertTrue(started.wait(2))
        parent.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(parent)); self.assertTrue(isValid(task.signals))
        release.set(); pump_until(lambda: not lifetime().tasks)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        done.assert_not_called(); failed.assert_not_called()
        self.assertEqual(destroyed, [self.gui_id]); self.assertFalse(isValid(task))

    def test_completed_task_is_retained_while_another_native_pool_call_is_running(self):
        parent = self.parent(); release = threading.Event(); done = []
        slow = async_task(parent, lambda progress: release.wait(3), done.append, self.fail)
        fast = async_task(parent, lambda progress: 42, done.append, self.fail)
        try:
            pump_until(lambda: 42 in done)
            self.assertFalse(lifetime().collect())
            self.assertTrue(isValid(fast)); self.assertTrue(isValid(fast.signals))
            self.assertIn(id(fast), lifetime().tasks)
        finally: release.set()
        pump_until(lambda: not lifetime().tasks)
        self.assertFalse(isValid(fast)); self.assertFalse(isValid(slow))

    def test_nested_result_event_loop_keeps_the_running_callback_bridge_alive(self):
        parent = self.parent(); checks = []
        def done(result):
            loop = QEventLoop()
            def inspect():
                try:
                    checks.append(QThreadPool.globalInstance().waitForDone(0))
                    checks.append(not lifetime().collect())
                    checks.append(isValid(task.signals))
                    checks.append(id(task) in lifetime().tasks)
                finally: loop.quit()
            QTimer.singleShot(20, inspect)
            loop.exec()
        task = async_task(parent, lambda progress: 42, done, self.fail)
        pump_until(lambda: not lifetime().tasks)
        self.assertEqual(checks, [True]*4)
        self.assertFalse(isValid(task))

    def test_shutdown_drain_retires_undelivered_results_without_running_them(self):
        parent = self.parent(); done = Mock(); failed = Mock(); progress = Mock()
        task = async_task(parent, lambda emit: (emit('late'), 42)[1], done, failed, progress)
        self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
        self.assertTrue(drain_tasks()); self.assertFalse(isValid(task))
        app.processEvents(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        done.assert_not_called(); failed.assert_not_called(); progress.assert_not_called()

    def test_error_and_progress_callbacks_are_queued_on_gui_and_released(self):
        parent = self.parent(); values = []; errors = []; done = Mock()
        def work(progress):
            progress('before failure'); raise ValueError('expected test failure')
        with patch('atelier.ui_common.traceback.print_exc'):
            task = async_task(parent, work, done, lambda message: errors.append((message, threading.get_ident())), lambda value: values.append((value, threading.get_ident())))
            pump_until(lambda: not lifetime().tasks)
        self.assertEqual(values, [('before failure', self.gui_id)])
        self.assertEqual(errors, [('expected test failure', self.gui_id)])
        done.assert_not_called(); self.assertFalse(isValid(task))

    def test_cancelled_request_retires_the_task_and_reports_none(self):
        parent = self.parent(); done = []; errors = Mock()
        def work(progress): raise RequestCancelled()
        task = async_task(parent, work, done.append, errors)
        pump_until(lambda: not lifetime().tasks)
        self.assertEqual(done, [None]); errors.assert_not_called(); self.assertFalse(isValid(task))

    def test_closed_modeless_window_stays_alive_until_task_result_is_disposed(self):
        owner = self.parent(); window = QDialog(owner); self.parents.append(window)
        show_window(window, owner, refresh_counts=False)
        release = threading.Event(); done = Mock()
        task = async_task(window, lambda progress: release.wait(3), done, self.fail)
        try:
            window.reject(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertTrue(isValid(window)); self.assertEqual(window._active_tasks, 1)
        finally: release.set()
        pump_until(lambda: not lifetime().tasks)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(window)); done.assert_not_called(); self.assertFalse(isValid(task))

    def test_start_failure_clears_callbacks_and_does_not_leave_a_task_registered(self):
        parent = self.parent(); done = Mock()
        with patch.object(QThreadPool, 'start', side_effect=RuntimeError('start failed')):
            with self.assertRaisesRegex(RuntimeError, 'start failed'):
                async_task(parent, lambda progress: 42, done, self.fail)
        self.assertFalse(lifetime().tasks)
        app.processEvents(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        done.assert_not_called()

    def test_bridge_disposal_is_idempotent_and_ignores_late_messages(self):
        parent = self.parent(); done = Mock(); failed = Mock(); progress = Mock()
        bridge = TaskBridge(parent, done, failed, progress)
        bridge.complete(42); bridge.failed('late'); bridge.progress('late'); bridge.dispose()
        done.assert_called_once_with(42); failed.assert_not_called(); progress.assert_not_called()
        self.assertIsNone(bridge.done); self.assertIsNone(bridge.fail); self.assertIsNone(bridge.progress_callback)


if __name__ == '__main__': unittest.main()
