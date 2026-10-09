"""Application temporary sessions, protected by process leases."""
import atexit
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
_session=None;_lease=None;_previous=None;_active=set();_lock=threading.RLock()

def _acquire(stream):
    stream.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
def is_live(folder):
    if _session and Path(folder).resolve()==_session:return True
    # A detached updater overlaps the GUI lease during a safe ownership handoff.
    for name in ('actif','maj'):
        lease=Path(folder)/name
        if not lease.exists():continue
        try:
            with lease.open('r+b') as stream:_acquire(stream)
        except OSError:return True
    return False
def purge(root,days=0,protected=(),sessions_only=False):
    root=Path(root);removed=freed=0;errors=[];cutoff=time.time()-days*86400
    if root.is_symlink() or not root.is_dir():return removed,freed,errors
    with _lock:active=set(_active)
    protected=[Path(p).resolve() for p in protected]
    # Retain the standalone recovery helper after a crash until the transaction
    # has been repaired, including when the user explicitly purges old temps.
    journal=root.parent/'maj'/'transaction.json'
    try:
        if journal.is_file() and journal.stat().st_size<1024*1024:
            transaction=json.loads(journal.read_text(encoding='utf-8'))
            stage=transaction.get('stage','')
            if transaction.get('status') in ('installing','rollback_failed') and re.fullmatch(r'u[0-9a-f]{10}',stage):protected.append((root/stage).resolve())
    except (OSError,ValueError,TypeError):pass
    for entry in root.iterdir():
        if entry.is_symlink() or sessions_only and (not entry.is_dir() or not re.fullmatch(r's[0-9a-f]{10}',entry.name)):continue
        if entry.is_dir() and is_live(entry):continue
        for path in [entry] if entry.is_file() else list(entry.rglob('*')):
            if not path.is_file() or path.is_symlink():continue
            try:
                resolved=path.resolve();stat=path.stat()
                if not resolved.is_relative_to(root.resolve()) or any(resolved==p or resolved.is_relative_to(p) for p in active) or stat.st_mtime>=cutoff or any(resolved==p or resolved.is_relative_to(p) for p in protected):continue
                path.unlink();removed+=1;freed+=stat.st_size
            except OSError as error:errors.append(str(error))
        if entry.is_dir():
            for folder in sorted((p for p in entry.rglob('*') if p.is_dir() and not p.is_symlink()),key=lambda p:len(p.parts),reverse=True):
                try:folder.rmdir()
                except OSError:pass
            try:entry.rmdir()
            except OSError:pass
    return removed,freed,errors
def configure(root):
    global _session,_lease,_previous
    temporary=Path(root)/'temp';temporary.mkdir(parents=True,exist_ok=True)
    if _session and (_session.parent!=temporary.resolve() or not _session.exists()):close()
    if _session is None:
        _previous=({k:os.environ.get(k) for k in ('TEMP','TMP','TMPDIR')},tempfile.tempdir)
        _session=(temporary/('s'+uuid.uuid4().hex[:10])).resolve();_session.mkdir();_lease=(_session/'actif').open('w+b');_lease.write(b'1');_lease.flush();_acquire(_lease)
        purge(temporary,sessions_only=True)
    for key in ('TEMP','TMP','TMPDIR'):os.environ[key]=str(_session)
    tempfile.tempdir=str(_session);return _session
def close():
    global _session,_lease,_previous
    session=_session
    if _lease:_lease.close();_lease=None
    _session=None
    if session:
        if _previous:
            for key,value in _previous[0].items():
                if os.environ.get(key)==str(session):
                    if value is None:os.environ.pop(key,None)
                    else:os.environ[key]=value
            if tempfile.tempdir==str(session):tempfile.tempdir=_previous[1]
        try:shutil.rmtree(session)
        except OSError:pass
    _previous=None
def register(path):
    with _lock:_active.add(Path(path).resolve())
def release(path):
    with _lock:_active.discard(Path(path).resolve())
def temporary_folder(fallback):return _session if _session and _session.is_dir() else Path(fallback)

@contextmanager
def workspace(root,prefix='ba'):
    folder=temporary_folder(Path(root)/'temp');folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=prefix,dir=folder) as name:
        path=Path(name);register(path)
        try:yield path
        finally:release(path)

atexit.register(close)
