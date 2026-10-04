"""Short generated names and atomic writes, all beside their target files."""
import base64
from contextlib import contextmanager
import errno
import hashlib
import logging
import os
from pathlib import Path
import tempfile
from .i18n import tr


def compact_digest(value):
    # Full SHA-256, encoded without Windows-forbidden filename characters.
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode('utf-8')).digest()).decode('ascii').rstrip('=')


def temporary_path(folder):
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
        yield temp
        os.replace(temp,destination)
    finally:
        if temp is not None:
            try:temp.unlink(missing_ok=True)
            except OSError:logging.getLogger('bricklabo').warning('Temporary file cleanup failed: %s',temp)
