"""Exercise the actual app modules independent of the caller's directory."""
import os
import gc
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'app'))
sys.path.insert(0,str(ROOT/'tests'))
os.environ['PYTHONPATH']=str(ROOT/'app')+os.pathsep+os.environ.get('PYTHONPATH','')
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
if __name__=='__main__':
    from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
    from PySide6.QtWidgets import QApplication
    from atelier.gui_gc import GuiGarbageCollector
    from atelier.task_lifetime import drain_tasks
    app=QApplication.instance() or QApplication([])
    collector=GuiGarbageCollector(app);collector.timer.stop()
    class GuiResult(unittest.TextTestResult):
        def stopTest(self,test):
            gc.disable()
            if QThreadPool.globalInstance().waitForDone(0):
                app.processEvents()
                if drain_tasks():
                    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                    collector.collect_if_idle(force=True)
            super().stopTest(test)
    suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]) if len(sys.argv)>1 else unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=GuiResult).run(suite)
    joined=QThreadPool.globalInstance().waitForDone(10000);app.processEvents()
    stopped=collector.stop() if joined else False
    raise SystemExit(not (result.wasSuccessful() and joined and stopped))
