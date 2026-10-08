"""Short names and atomic commits using the local temporary session."""
import base64
from contextlib import contextmanager
import errno
import hashlib
import logging
import os
from pathlib import Path
import tempfile
import sys
from .i18n import tr



IS_WINDOWS=sys.platform=='win32'
def shared_reader(path):
    """A Windows archive reader permitting atomic replacement of its pathname."""
    if not IS_WINDOWS:return Path(path).open('rb')
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);create=kernel.CreateFileW
    create.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE);create.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,);kernel.CloseHandle.restype=wintypes.BOOL
    name=str(Path(path).resolve())
    if not name.startswith('\\\\?\\'):name='\\\\?\\UNC\\'+name[2:] if name.startswith('\\\\') else '\\\\?\\'+name
    handle=create(name,0x80000000,0x1|0x2|0x4,None,3,0x80,None)
    if handle==wintypes.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except BaseException:kernel.CloseHandle(handle);raise
    try:return os.fdopen(fd,'rb')
    except BaseException:os.close(fd);raise

def compact_digest(value):
    # Full SHA-256, encoded without Windows-forbidden filename characters.
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode('utf-8')).digest()).decode('ascii').rstrip('=')


def temporary_path(folder):
    from .temp_area import temporary_folder
    folder=temporary_folder(folder)
    fd,name=tempfile.mkstemp(prefix='t',suffix='.tmp',dir=folder)
    os.close(fd)
    return Path(name)


def error_message(error):
    if not isinstance(error,OSError):return str(error)
    current=error
    while current is not None:
        if isinstance(current,OSError):
            if current.errno==errno.ENAMETOOLONG or getattr(current,'winerror',None)==206:
                return tr('Chemin de fichier trop long. Le fichier n’a pas pu être enregistré ou ouvert. Choisis un dossier plus court ou déplace le dossier complet de BrickLabo, logiciel fermé.')+'\n'+str(current)
            if current.errno==errno.ENOSPC:
                return tr('Espace disque insuffisant. Le fichier n’a pas été enregistré complètement.')+'\n'+str(current)
        current=current.__cause__
    return str(error)


@contextmanager
def atomic_output(destination):
    destination=Path(destination);temp=None
    try:
        destination.parent.mkdir(parents=True,exist_ok=True)
        temp=temporary_path(destination.parent)
        from .temp_area import register,release
        register(temp)
        yield temp
        try:os.replace(temp,destination)
        except OSError as error:
            if error.errno!=errno.EXDEV:raise
            import shutil
            fd,name=tempfile.mkstemp(prefix='t',suffix='.tmp',dir=destination.parent);os.close(fd);stage=Path(name);register(stage)
            try:shutil.copyfile(temp,stage);os.replace(stage,destination)
            finally:stage.unlink(missing_ok=True);release(stage)
    finally:
        if temp is not None:
            release(temp)
            try:temp.unlink(missing_ok=True)
            except OSError:logging.getLogger('bricklabo').warning('Temporary file cleanup failed: %s',temp)
