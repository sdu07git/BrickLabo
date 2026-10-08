"""Exercise the actual app modules independent of the caller's directory."""
import os
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'app'))
os.environ['PYTHONPATH']=str(ROOT/'app')+os.pathsep+os.environ.get('PYTHONPATH','')
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    raise SystemExit(not result.wasSuccessful())
