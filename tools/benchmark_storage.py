"""Measure a disposable cabinet; never open or change a user's database.

Run with the app dependencies installed. --source-root permits the same
benchmark to measure another checkout. Timings are informational, not tests.
"""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
import tempfile
from time import perf_counter


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--columns',type=int,default=100)
    parser.add_argument('--rows',type=int,default=100)
    parser.add_argument('--repeats',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.columns<=100 or not 1<=args.rows<=100 or args.repeats<1:parser.error('Use 1–100 columns/rows and at least one repeat')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    sys.path.insert(0,str(args.source_root.resolve()/'app'))
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    from atelier.data import Database
    from atelier.gui_gc import GuiGarbageCollector
    from atelier.storage_panel import StoragePanel
    from atelier.storage_wall import create_wall
    from atelier.version import VERSION
    app=QApplication.instance() or QApplication([])
    collector=GuiGarbageCollector(app);collector.timer.stop()
    result=dict(version=VERSION,system=platform.system(),python=platform.python_version(),qt=qVersion(),drawers=args.columns*args.rows,repeats=args.repeats)
    def timed(action):
        start=perf_counter();value=action();return value,perf_counter()-start
    try:
        with tempfile.TemporaryDirectory(prefix='bricklabo-benchmark-') as temp:
            db=Database(Path(temp)/'benchmark.sqlite')
            try:
                _,result['database_seconds']=timed(lambda:create_wall(db,'Benchmark',args.columns,args.rows))
                panel,result['initialization_seconds']=timed(lambda:StoragePanel(db,None))
                panel.resize(1100,850)
                _,result['show_seconds']=timed(lambda:(panel.show(),app.processEvents()))
                refresh=[];paint=[]
                for _ in range(args.repeats):
                    _,elapsed=timed(lambda:(panel.refresh(),app.processEvents()));refresh.append(elapsed)
                    _,elapsed=timed(panel.grab);paint.append(elapsed)
                result['refresh_median_seconds']=median(refresh);result['paint_median_seconds']=median(paint)
                panel.close();app.processEvents();collector.collect_if_idle(force=True)
            finally:db.close()
    finally:collector.stop()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
