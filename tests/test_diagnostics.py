import os,subprocess,sys,tempfile,unittest
from pathlib import Path
from atelier.version import VERSION

class DiagnosticsTests(unittest.TestCase):
    def test_uncaught_python_error_is_written_to_txt(self):
        with tempfile.TemporaryDirectory() as folder:
            script='from atelier.diagnostics import setup_logging\nimport sys\nsetup_logging(sys.argv[1])\nraise RuntimeError("Erreur de test du journal")'
            result=subprocess.run([sys.executable,'-c',script,folder],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            text=(Path(folder)/'BrickLabo_logs.txt').read_text(encoding='utf-8')
            self.assertIn('RuntimeError: Erreur de test du journal',text);self.assertIn('v'+VERSION,text);self.assertIn('Traceback',text)
    def test_native_crash_writes_a_text_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            script='import os,sys\nif sys.platform!="win32":\n import resource\n resource.setrlimit(resource.RLIMIT_CORE,(0,0))\nfrom atelier.diagnostics import setup_logging\nsetup_logging(sys.argv[1])\nos.abort()'
            result=subprocess.run([sys.executable,'-c',script,folder],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            text=(Path(folder)/'BrickLabo_crash.txt').read_text(encoding='utf-8')
            self.assertIn('Démarrage BrickLabo by SDU7 v'+VERSION,text)
            self.assertIn('Fatal Python error',text)
    def test_thread_exception_is_logged(self):
        with tempfile.TemporaryDirectory() as folder:
            script='from atelier.diagnostics import setup_logging\nimport sys,threading\nsetup_logging(sys.argv[1])\ndef fail():raise ValueError("Erreur thread")\nt=threading.Thread(target=fail,name="test-worker");t.start();t.join()'
            result=subprocess.run([sys.executable,'-c',script,folder],capture_output=True,text=True,check=True)
            text=(Path(folder)/'BrickLabo_logs.txt').read_text(encoding='utf-8')
            self.assertIn('test-worker',text);self.assertIn('ValueError: Erreur thread',text)
