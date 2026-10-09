import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QWidget

from atelier import temp_area
from atelier.services import RequestCancelled, request, request_scope
from atelier.ui_common import Task, TaskBridge

app = QApplication.instance() or QApplication([])


class TemporaryShutdownTests(unittest.TestCase):
    def setUp(self):
        temp_area.close()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        temp_area.close()
        app.processEvents()
        self.temp.cleanup()

    def test_cancelled_download_closes_handles_removes_partial_file_and_keeps_destination(self):
        session = temp_area.configure(self.root)
        destination = self.root / 'saved.bin'
        destination.write_bytes(b'previous complete file')
        cancel = threading.Event()
        class Response(BytesIO):
            def read1(self, size):
                cancel.set()
                return super().read1(size)
        response = Response(b'partial download')
        with patch('urllib.request.urlopen', return_value=response), request_scope(cancel):
            with self.assertRaises(RequestCancelled):request('https://example.test/file', destination=destination)
        self.assertTrue(response.closed)
        self.assertEqual(destination.read_bytes(), b'previous complete file')
        self.assertEqual([p.name for p in session.iterdir()], ['actif'])
        temp_area.close()
        self.assertFalse(session.exists())

    def test_cancelled_requests_never_open_the_network_and_context_is_restored(self):
        cancel = threading.Event(); cancel.set()
        with patch('urllib.request.urlopen') as open_url, request_scope(cancel):
            with self.assertRaises(RequestCancelled):request('https://example.test/file')
            open_url.assert_not_called()
        response = BytesIO(b'whole result')
        with patch('urllib.request.urlopen', return_value=response):
            self.assertEqual(request('https://example.test/file'), b'whole result')
        self.assertTrue(response.closed)

    def test_task_skips_queued_work_after_shutdown(self):
        cancel = threading.Event(); cancel.set(); factory = Mock()
        task = Task(factory, cancel)
        results = []
        task.signals.result.connect(results.append)
        task.run()
        factory.assert_not_called()
        self.assertEqual(results, [None])

    def test_closing_blocks_result_error_and_progress_callbacks(self):
        owner = QWidget(); owner.nav = object(); owner.refresh_counts = Mock(); owner._closing = True
        done, failed, progress = Mock(), Mock(), Mock()
        bridge = TaskBridge(owner, done, failed, progress)
        bridge.progress('Late update'); bridge.complete('Late result')
        done.assert_not_called(); failed.assert_not_called(); progress.assert_not_called()
        bridge = TaskBridge(owner, done, failed, progress)
        with patch('atelier.ui_common.QMessageBox.warning') as warning:bridge.failed('Late error'); warning.assert_not_called()
        owner.deleteLater()

    def test_cleanup_releases_the_lease_before_removing_the_session(self):
        session = temp_area.configure(self.root)
        lease = temp_area._lease
        original = temp_area.shutil.rmtree
        def remove(path, **kwargs):
            self.assertTrue(lease.closed)
            self.assertFalse(temp_area.is_live(path))
            return original(path, **kwargs)
        with patch.object(temp_area.shutil, 'rmtree', side_effect=remove):temp_area.close()
        self.assertFalse(session.exists())

    def test_readonly_temporary_files_are_retried_without_changing_other_files(self):
        session = temp_area.configure(self.root)
        file = session / 'render.tmp'; file.write_bytes(b'work'); file.chmod(stat.S_IREAD)
        external = self.root / 'original.dat'; external.write_bytes(b'original'); external.chmod(stat.S_IREAD)
        temp_area._remove_readonly(os.unlink, file, PermissionError('Windows read-only file'))
        self.assertFalse(file.exists())
        self.assertEqual(external.read_bytes(), b'original')
        self.assertFalse(external.stat().st_mode & stat.S_IWRITE)
        external.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_locked_cleanup_is_reported_and_abandoned_session_is_retried_at_startup(self):
        session = temp_area.configure(self.root)
        file = session / 'busy.tmp'; file.write_bytes(b'locked')
        with patch.object(temp_area.shutil, 'rmtree', side_effect=PermissionError('Sharing violation')), \
             self.assertLogs('bricklabo', level='WARNING') as logs:
            temp_area.close()
        self.assertTrue(file.exists())
        self.assertIn(str(session), logs.output[0])
        with self.assertRaises(PermissionError):temp_area._remove_readonly(os.unlink, file, PermissionError('Sharing violation'))
        new_session = temp_area.configure(self.root)
        self.assertNotEqual(new_session, session)
        self.assertFalse(session.exists())

    def test_cleanup_handles_long_temporary_paths_and_does_not_follow_links(self):
        folder = self.root
        for number in range(5):folder = folder / ('d' * 60 + str(number))
        session = temp_area.configure(folder)
        file = session / 'temporary.bin'; file.write_bytes(b'work')
        self.assertGreater(len(str(file)), 300)
        external = self.root / 'outside'; external.mkdir(); (external / 'original').write_bytes(b'keep')
        if os.name != 'nt':(session / 'external').symlink_to(external, target_is_directory=True)
        temp_area.close()
        self.assertFalse(session.exists())
        self.assertEqual((external / 'original').read_bytes(), b'keep')

    def test_window_stays_visible_until_workers_finish_then_process_exits_without_temp_locks(self):
        code = '''from pathlib import Path
import json,sys,threading
from PySide6.QtCore import QTimer,QThreadPool
from PySide6.QtWidgets import QApplication
from atelier.app import MainWindow
from atelier.data import Database
from atelier.temp_area import configure,close
from atelier.ui_common import async_task
root=Path(sys.argv[1]);session=configure(root);db=Database(root/'db.sqlite')
app=QApplication([]);window=MainWindow(db);window.startup_timer.stop();window.show()
started=threading.Event();release=threading.Event();pool=QThreadPool.globalInstance();pool.setMaxThreadCount(1)
def work(progress):
    with (session/'work.tmp').open('wb') as file:
        file.write(b'work');file.flush();started.set()
        assert release.wait(4)
def close_window():
    assert started.wait(2)
    assert not window.close()
    assert window.isVisible() and window._closing
    assert 'Fermeture' in window.statusBar().currentMessage()
    QTimer.singleShot(80,release.set)
async_task(window,work,lambda result:(_ for _ in ()).throw(AssertionError('Late callback')))
async_task(window,lambda progress:(_ for _ in ()).throw(AssertionError('Queued work ran')),lambda result:None)
QTimer.singleShot(0,close_window)
QTimer.singleShot(5000,app.quit)
status=app.exec();assert pool.waitForDone(1000)
window.engine.close();db.close();close()
assert not session.exists()
print(json.dumps({'status':status,'temp_deleted':True,'request_cancelled':window._request_cancel.is_set()}))
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root)],
                                capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"temp_deleted": true', result.stdout)
        self.assertIn('"request_cancelled": true', result.stdout)


if __name__ == '__main__':unittest.main()
