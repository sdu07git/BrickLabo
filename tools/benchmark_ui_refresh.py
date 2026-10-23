"""Measure visible/hidden panel refreshes on a disposable benchmark collection.

Network and image rendering are disabled for both versions so this measures
database queries and table updates. Never use a personal collection.
"""
import argparse,json,os,sys
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--database',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();sys.path.insert(0,str(args.source_root.resolve()/'app'));os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    from atelier.data import Database
    from atelier.app import MainWindow
    from atelier.gui_gc import GuiGarbageCollector
    from atelier.task_lifetime import drain_tasks
    from atelier.version import VERSION
    app=QApplication([]);collector=GuiGarbageCollector(app);collector.timer.stop();db=Database(args.database)
    try:
        if not db.setting('benchmark_queries'):raise ValueError('Not a disposable benchmark collection')
        with patch('atelier.preview.Preview.refresh'),patch('atelier.catalogue.Catalogue.load_thumbnails'),patch('atelier.thumbnails.PartThumbnails.load'),patch('atelier.storage_panel.StoragePanel.load_icons'):
            start=perf_counter();window=MainWindow(db);window.startup_timer.stop();window.resize(1200,800);window.show();app.processEvents();initial=perf_counter()-start
            result=dict(version=VERSION,initial_seconds=initial)
            for name,index in [('catalogue_visible',0),('stock_visible',8),('projects_visible',13)]:
                window.nav.setCurrentRow(index);app.processEvents();times=[]
                for _ in range(5):
                    start=perf_counter();window.refresh_counts();app.processEvents();times.append(perf_counter()-start)
                result[name]=dict(first_seconds=times[0],warm_median_seconds=median(times[1:]))
            window.close();QThreadPool.globalInstance().waitForDone(10000);app.processEvents();drain_tasks();collector.collect_if_idle(force=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    finally:collector.stop();db.close()


if __name__=='__main__':main()
