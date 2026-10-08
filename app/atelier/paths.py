"""Central paths, independent of the working directory."""
import os
import sys
from pathlib import Path

def application_root():
    value=os.environ.get('BRICKLABO_ROOT')
    if value:return Path(value).resolve()
    executable=Path(sys.executable).resolve()
    if getattr(sys,'frozen',False) or executable.stem.lower() in ('bricklabo','legoatelier'):return executable.parent
    code=Path(__file__).resolve().parent.parent
    return code.parent if code.name.lower()=='app' and (code/'structure.json').exists() else code
def resources_directory():return application_root()/'ressources'
def documentation_directory():
    root=application_root();return root/'documentation' if (root/'documentation').is_dir() else root
