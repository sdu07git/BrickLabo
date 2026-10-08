"""One SQLite file opener, retaining locks and enabling Windows long paths.

SQLite's win32-longpath VFS uses the normal Windows locking implementation.
It is included in the embedded sqlite3.dll shipped with BrickLabo.
https://sqlite.org/vfs.html
"""
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

IS_WINDOWS=sys.platform=='win32'

def database_uri(path,read_only=False):
    uri=path.as_uri();parsed=urlsplit(uri)
    # SQLite builds without URI_AUTHORITY still accept UNC paths this way.
    if parsed.netloc and parsed.netloc!='localhost':uri='file:////'+parsed.netloc+parsed.path
    options=[]
    if read_only:options.append('mode=ro')
    if IS_WINDOWS:options.append('vfs=win32-longpath')
    return uri+('?'+'&'.join(options) if options else '')

def connect(path,timeout=5,read_only=False,check_same_thread=True):
    path=Path(path).resolve()
    options={} if check_same_thread else {'check_same_thread':False}
    try:
        if IS_WINDOWS or read_only:return sqlite3.connect(database_uri(path,read_only),uri=True,timeout=timeout,**options)
        return sqlite3.connect(str(path),timeout=timeout,**options)
    except sqlite3.OperationalError as error:
        if getattr(error,'sqlite_errorcode',None)==sqlite3.SQLITE_CANTOPEN:
            message='Base de données inaccessible. Vérifie les droits du dossier et essaie un chemin plus court. / Database inaccessible: check folder permissions and try a shorter path.\n'+str(path)
            failure=sqlite3.OperationalError(message);failure.sqlite_errorcode=error.sqlite_errorcode;failure.sqlite_errorname=error.sqlite_errorname
            raise failure from error
        raise
