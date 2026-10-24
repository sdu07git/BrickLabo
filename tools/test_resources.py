"""Close resources owned by disposable unittest fixtures before deleting them.

Legacy fixtures explicitly delete their TemporaryDirectory in tearDown while
retaining a Database or ZipFile on self. POSIX permits unlinking those files;
Windows correctly refuses. This test-only scope releases those handles first.
It does not change application code, ignore deletion errors, or touch resources
outside the directory being cleaned.
"""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
import weakref
from zipfile import ZipFile


class FixtureResources:
    def __init__(self, before_close=lambda: None):
        self.before_close = before_close
        self.databases = weakref.WeakSet()
        self.archives = weakref.WeakSet()
        self.lock = threading.RLock()
        self.stack = ExitStack()

    def __enter__(self):
        from atelier.data import Database
        db_init, zip_init = Database.__init__, ZipFile.__init__
        cleanup = tempfile.TemporaryDirectory.cleanup
        owner = self

        def database_init(instance, *args, **kwargs):
            db_init(instance, *args, **kwargs)
            with owner.lock:
                owner.databases.add(instance)

        def archive_init(instance, *args, **kwargs):
            zip_init(instance, *args, **kwargs)
            with owner.lock:
                owner.archives.add(instance)

        def directory_cleanup(instance):
            owner.close_under(instance.name)
            return cleanup(instance)

        self.stack.enter_context(patch.object(Database, '__init__', database_init))
        self.stack.enter_context(patch.object(ZipFile, '__init__', archive_init))
        self.stack.enter_context(patch.object(tempfile.TemporaryDirectory, 'cleanup', directory_cleanup))
        return self

    def close_under(self, folder):
        directory = Path(folder).resolve()
        def inside(path):
            return isinstance(path, (str, Path)) and Path(path).resolve().is_relative_to(directory)
        with self.lock:
            databases = [db for db in self.databases if db._reader is not None and inside(db.path)]
            archives = [archive for archive in self.archives if archive.fp is not None and inside(archive.filename)]
        if databases or archives:
            self.before_close()
        for db in databases:
            db.close()
        for archive in archives:
            archive.close()

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
