"""Window lifetimes must never own the persistent inventory queue worker."""
import threading,time
from unittest.mock import patch
from PySide6.QtCore import QThreadPool,QCoreApplication,QEvent
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid
from test_storage_and_inventory_batches import Fixture,app
from atelier.inventory_batch_dialog import InventoryBatchDialog
from atelier.inventory_background import service_for
from atelier import inventory_batches as batches
from atelier.windows import show_window


def wait_for(predicate,timeout=8):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.processEvents();QThreadPool.globalInstance().waitForDone(2)
    if not predicate():raise AssertionError('Background operation did not reach the expected state')


class BackgroundTests(Fixture):
    def job(self,count=3):
        return batches.create_job(self.db,[self.db.get_item(self.item('set','set-'+str(n))) for n in range(count)],10,True)
    def worker(self,gate,started,calls):
        db=self.db
        def run(db,job,cancel,progress):
            pending=db.rows("SELECT ordinal,ref FROM inventory_job_items WHERE job_id=? AND status='pending' ORDER BY ordinal LIMIT 10",(job,))
            for row in pending:
                started.set();progress(row['ref']);gate.wait(5)
                if cancel.is_set():break
                calls.append(row['ref']);db.run("UPDATE inventory_job_items SET status='loaded' WHERE job_id=? AND ordinal=?",(job,row['ordinal']))
            return batches.summary(db,job)
        return run
    def test_closing_and_reopening_the_window_keeps_one_worker_and_progress(self):
        job=self.job();gate=threading.Event();started=threading.Event();calls=[];service=service_for(self.db)
        first=self.keep(InventoryBatchDialog(self.db));show_window(first)
        try:
            with patch('atelier.inventory_batches.run_batch',side_effect=self.worker(gate,started,calls)) as worker:
                first.start(True);wait_for(started.is_set);first.reject();app.processEvents()
                self.assertFalse(service.cancel.is_set());self.assertTrue(service.busy)
                second=self.keep(InventoryBatchDialog(self.db));second.show();app.processEvents()
                self.assertIs(second.background,service);self.assertEqual(second.job,job);self.assertTrue(second.pause.isEnabled())
                self.assertFalse(service.start(job,10,True));self.assertEqual(worker.call_count,1)
                gate.set();wait_for(lambda:not service.busy)
                self.assertEqual(batches.summary(self.db,job)['loaded'],3);self.assertEqual(len(calls),3)
                self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        finally:gate.set();service.pause();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    def test_pause_from_a_reopened_window_keeps_pending_rows_for_resume(self):
        job=self.job();gate=threading.Event();started=threading.Event();calls=[];service=service_for(self.db)
        try:
            with patch('atelier.inventory_batches.run_batch',side_effect=self.worker(gate,started,calls)):
                service.start(job,10,True);wait_for(started.is_set)
                window=self.keep(InventoryBatchDialog(self.db));window.pause.click();gate.set();wait_for(lambda:not service.busy)
                self.assertEqual(batches.summary(self.db,job)['pending'],3);self.assertEqual(calls,[])
                service.start(job,10,True);wait_for(lambda:not service.busy)
                self.assertEqual(batches.summary(self.db,job)['loaded'],3)
        finally:gate.set();service.pause();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    def test_continuous_loading_crosses_batches_with_no_open_dialog(self):
        job=self.job(23);gate=threading.Event();gate.set();started=threading.Event();calls=[];service=service_for(self.db)
        with patch('atelier.inventory_batches.run_batch',side_effect=self.worker(gate,started,calls)) as worker:
            service.start(job,10,True);wait_for(lambda:not service.busy)
            self.assertEqual(worker.call_count,3);self.assertEqual(len(set(calls)),23)
    def test_one_batch_mode_keeps_the_rest_pending(self):
        job=self.job(23);gate=threading.Event();gate.set();started=threading.Event();calls=[];service=service_for(self.db)
        with patch('atelier.inventory_batches.run_batch',side_effect=self.worker(gate,started,calls)):
            service.start(job,10,False);wait_for(lambda:not service.busy)
            self.assertEqual(batches.summary(self.db,job)['pending'],13)
    def test_authentication_error_stops_continuation_and_stays_visible_on_reopen(self):
        job=self.job();service=service_for(self.db)
        with patch('atelier.inventory_batches.run_batch',side_effect=ValueError('API key missing')),patch('atelier.ui_common.traceback.print_exc'):
            service.start(job,10,True);wait_for(lambda:not service.busy)
        window=self.keep(InventoryBatchDialog(self.db));self.assertIn('API key missing',window.status.text())
        self.assertEqual(batches.summary(self.db,job)['pending'],3)
    def test_application_shutdown_cancels_the_worker_and_never_requeues(self):
        job=self.job(23);gate=threading.Event();started=threading.Event();calls=[];service=service_for(self.db)
        try:
            with patch('atelier.inventory_batches.run_batch',side_effect=self.worker(gate,started,calls)) as worker:
                service.start(job,10,True);wait_for(started.is_set);service.shutdown();gate.set()
                wait_for(lambda:QThreadPool.globalInstance().waitForDone(0));app.processEvents()
                self.assertEqual(worker.call_count,1);self.assertTrue(service.cancel.is_set());self.assertEqual(calls,[])
                self.assertEqual(batches.summary(self.db,job)['pending'],23)
        finally:gate.set();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    def test_main_window_close_waits_for_the_inventory_worker(self):
        from atelier.app import MainWindow
        from atelier.preview import Preview
        from atelier.catalogue import Catalogue
        gate=threading.Event();started=threading.Event();calls=[];job=self.job(23)
        with patch.object(Catalogue,'load_thumbnails'),patch.object(Preview,'refresh'):
            window=self.keep(MainWindow(self.db));window.startup_timer.stop();window.show();app.processEvents()
            service=window.inventory_background
            try:
                with patch('atelier.inventory_batches.run_batch',side_effect=self.worker(gate,started,calls)):
                    service.start(job,10,True);wait_for(started.is_set);window.close()
                    self.assertTrue(service.cancel.is_set());self.assertTrue(window._closing);self.assertTrue(window.isVisible())
                    gate.set();wait_for(lambda:not window.isVisible())
                    self.assertEqual(batches.summary(self.db,job)['pending'],23)
            finally:gate.set();service.shutdown();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
