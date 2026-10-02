"""Persistent UTF-8 text diagnostics for the Windows portable application."""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import threading

from .version import APP_NAME,VERSION
from .storage import data_directory

_crash_stream=None
_log_directory=None

def log_directory():
    return data_directory()/'logs'

def setup_logging(directory=None):
    global _crash_stream,_log_directory
    folder=Path(directory) if directory is not None else log_directory()
    folder.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('bricklabo');logger.setLevel(logging.INFO);logger.propagate=False
    if _log_directory!=folder:
        for handler in list(logger.handlers):logger.removeHandler(handler);handler.close()
        handler=RotatingFileHandler(folder/'BrickLabo_logs.txt',maxBytes=2_000_000,backupCount=3,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
        logger.addHandler(handler)
        if _crash_stream is not None:
            faulthandler.disable();_crash_stream.close()
        _crash_stream=(folder/'BrickLabo_crash.txt').open('a',encoding='utf-8',buffering=1)
        faulthandler.enable(file=_crash_stream,all_threads=True)
        _log_directory=folder
    logger.info('Démarrage %s v%s | Python %s | %s',APP_NAME,VERSION,platform.python_version(),platform.platform())
    _crash_stream.write('\nDémarrage '+APP_NAME+' v'+VERSION+'\n');_crash_stream.flush()
    def exception(typ,value,tb):logger.critical('Exception non interceptée',exc_info=(typ,value,tb))
    sys.excepthook=exception
    def thread_exception(args):logger.critical('Exception du thread %s',args.thread.name if args.thread else '?',exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
    threading.excepthook=thread_exception
    def unraisable(args):logger.error('Exception ignorée : %s',args.err_msg or 'finalisation',exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
    sys.unraisablehook=unraisable
    return logger,folder
