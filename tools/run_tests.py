"""Exercise the actual app modules independent of the caller's directory."""
import os
import gc
from pathlib import Path
import sys
import unittest
import argparse
from test_reporting import ReportResult
from test_resources import FixtureResources
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'app'))
sys.path.insert(0,str(ROOT/'tests'))
os.environ['PYTHONPATH']=str(ROOT/'app')+os.pathsep+os.environ.get('PYTHONPATH','')
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tests',nargs='*')
    parser.add_argument('--report',type=Path);parser.add_argument('--junit',type=Path)
    parser.add_argument('--failfast',action='store_true',help='Stop at the first failing case while diagnosing a platform')
    args=parser.parse_args()
    from PySide6.QtCore import QCoreApplication,QEvent,QThreadPool
    from PySide6.QtWidgets import QApplication
    from atelier.gui_gc import GuiGarbageCollector
    from atelier.task_lifetime import drain_tasks
    app=QApplication.instance() or QApplication([])
    collector=GuiGarbageCollector(app);collector.timer.stop()
    class GuiResult(ReportResult):
        def stopTest(self,test):
            gc.disable()
            if QThreadPool.globalInstance().waitForDone(0):
                app.processEvents()
                if drain_tasks():
                    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                    collector.collect_if_idle(force=True)
            super().stopTest(test)
    def fixture_idle():
        if not QThreadPool.globalInstance().waitForDone(10000):
            raise RuntimeError('Fixture still has running Qt tasks during cleanup')
        app.processEvents()
        if not drain_tasks():
            raise RuntimeError('Fixture task disposal did not finish during cleanup')
    with FixtureResources(fixture_idle):
        suite=unittest.defaultTestLoader.loadTestsFromNames(args.tests) if args.tests else unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        result=unittest.TextTestRunner(verbosity=2,resultclass=GuiResult,failfast=args.failfast).run(suite)
    joined=QThreadPool.globalInstance().waitForDone(10000);app.processEvents()
    stopped=collector.stop() if joined else False
    result.save(args.report,args.junit,bool(joined and stopped))
    raise SystemExit(not (result.wasSuccessful() and joined and stopped))
