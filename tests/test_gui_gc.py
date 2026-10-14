"""Exercise rendering while Qt/Python cyclic destruction is deferred to idle."""
import gc
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import threading
import time
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication,QWidget
from shiboken6 import isValid
from atelier.gui_gc import GuiGarbageCollector
from atelier.ui_common import async_task
from atelier.task_lifetime import drain_tasks,lifetime
from atelier.render import LDraw

app=QApplication.instance() or QApplication([])


class GuiGCTests(unittest.TestCase):
    def setUp(self):
        self.old_enabled=gc.isenabled();self.old_threshold=gc.get_threshold();self.collector=None;self.parents=[]
        self.assertTrue(QThreadPool.globalInstance().waitForDone(5000));drain_tasks()

    def tearDown(self):
        self.assertTrue(QThreadPool.globalInstance().waitForDone(10000));drain_tasks()
        if self.collector:self.collector.stop();self.collector.deleteLater()
        for parent in self.parents:
            if isValid(parent):parent.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
        gc.set_threshold(*self.old_threshold)
        gc.enable() if self.old_enabled else gc.disable()

    def controller(self):
        self.collector=GuiGarbageCollector(app);return self.collector

    def pump(self,predicate,timeout=10):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
        self.assertTrue(predicate())

    def test_cyclic_collection_is_refused_while_native_render_is_running(self):
        controller=self.controller();parent=QWidget();self.parents.append(parent);started=threading.Event();release=threading.Event();done=[]
        def work(progress):started.set();release.wait(5);return 1
        task=async_task(parent,work,done.append,self.fail);self.assertTrue(started.wait(2))
        try:
            self.assertFalse(gc.isenabled());self.assertFalse(controller.collect_if_idle(True));self.assertFalse(controller.stop());self.assertFalse(gc.isenabled())
        finally:release.set()
        self.pump(lambda:not lifetime().tasks);self.assertTrue(controller.collect_if_idle(True));self.assertEqual(done,[1]);self.assertFalse(isValid(task))

    def test_automatic_gc_never_runs_mid_render_and_qt_cycles_die_on_gui(self):
        controller=self.controller();gc.set_threshold(10,2,2);gui=threading.get_ident();events=[];destroyed=[];parent=QWidget();self.parents.append(parent);pool=QThreadPool.globalInstance()
        def record(phase,info):
            if phase=='start':events.append((threading.get_ident(),pool.activeThreadCount()))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
            (root/'leaf.dat').write_text('3 16 0 0 0 10 0 0 0 10 0\n3 16 0 0 0 0 10 0 0 0 10\n')
            (root/'test.dat').write_text(''.join(f'1 16 {n} 0 0 1 0 0 0 1 0 0 0 1 leaf.dat\n' for n in range(20)))
            renderer=LDraw(root);done=[]
            gc.callbacks.append(record)
            def work(progress):
                for n in range(5):
                    cycles=[[] for _ in range(100)]
                    for cycle in cycles:cycle.append(cycle)
                    image,_=renderer.render('test',(60,40),'#ff0000',edge_strength=0)
                    if image.size!=(60,40):raise ValueError('Render size')
                return image
            try:
                orphan=QWidget();orphan.cycle=orphan;orphan.destroyed.connect(lambda *_:destroyed.append(threading.get_ident()));del orphan
                for _ in range(24):async_task(parent,work,done.append,self.fail)
                self.pump(lambda:len(done)==24 and not lifetime().tasks)
                self.assertEqual(events,[]);self.assertTrue(controller.collect_if_idle(True));self.assertTrue(events);self.assertTrue(all(thread==gui and active==0 for thread,active in events));self.assertEqual(destroyed,[gui])
            finally:renderer.close();gc.callbacks.remove(record)

    def test_nested_gui_result_handler_cannot_trigger_collection(self):
        controller=self.controller();parent=QWidget();self.parents.append(parent);checks=[]
        async_task(parent,lambda _:42,lambda result:checks.append(controller.collect_if_idle(True)),self.fail)
        self.pump(lambda:not lifetime().tasks);self.assertEqual(checks,[False]);self.assertTrue(controller.collect_if_idle(True))

    def test_shutdown_preserves_preexisting_disabled_gc(self):
        gc.disable();controller=self.controller();self.assertTrue(controller.stop());self.assertFalse(gc.isenabled());self.assertTrue(controller.stop())
