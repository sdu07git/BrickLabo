"""Single entry point; configure portable storage before importing Qt."""
import json
import os
from pathlib import Path
import sys
import traceback
APP=Path(__file__).resolve().parent
ROOT=APP.parent
sys.path.insert(0,str(APP));sys.dont_write_bytecode=True
os.environ['BRICKLABO_ROOT']=str(ROOT)
for key in ('TEMP','TMP','TMPDIR'):os.environ[key]=str(ROOT/'Donnees'/'temp')
if os.name=='nt' and (APP/'lib'/'PySide6'/'plugins').exists():
    os.environ['QT_PLUGIN_PATH']=str(APP/'lib'/'PySide6'/'plugins')
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']=str(APP/'lib'/'PySide6'/'plugins'/'platforms')

def self_test(data):
    import tempfile
    from atelier.temp_area import temporary_folder
    from atelier.data import Database
    from atelier.preview import VisualEngine
    from atelier.paths import documentation_directory,resources_directory
    from atelier.version import VERSION
    from PySide6.QtWidgets import QApplication
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen');application=QApplication.instance() or QApplication([])
    from contextlib import ExitStack
    with tempfile.TemporaryDirectory(prefix='d',dir=temporary_folder(data/'temp')) as folder,ExitStack() as cleanup:
        db=Database(Path(folder)/'test.sqlite')
        cleanup.callback(db.close)
        iid=db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('RB','part','3005','Brick 1 x 1','brick')")
        db.add('stock',iid,'4',2)
        assert db.undo_last_action() and not db.query(scope='stock')[1]
        assert db.search_index_available
        archive=resources_directory()/'complete.zip'
        if not archive.is_file():raise RuntimeError('Archive LDraw complete.zip absente')
        db.set_setting('ldraw',str(archive));engine=VisualEngine(db)
        cleanup.callback(engine.close)
        image,bounds=engine.render_3d(db.get_item(iid),(100,65),'4')
        assert image is not None and image.getbbox() and bounds is not None
        engine.thumbnail_cache.put((iid,'diagnostic'),image)
        assert engine.thumbnail_cache.get((iid,'diagnostic')) is not None
        assert (documentation_directory()/'AIDE.html').is_file()
        report={'status':'ok','version':VERSION,'root':str(ROOT),'temp':str(temporary_folder(data/'temp')),'fts5':True,'undo':True,'render3d':True,'thumbnail':True}
        (data/'diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
    return 0

def run():
    from atelier.storage import prepare_portable_storage
    from atelier.update_installer import startup_gate
    with startup_gate(ROOT):data=prepare_portable_storage()
    from atelier.software_updates import clean_update_workspaces
    clean_update_workspaces(ROOT)
    try:
        if '--self-test' in sys.argv:return self_test(data)
        from atelier.app import main
        return main()
    finally:
        from atelier.temp_area import close
        close()

def startup():
    try:return run()
    except Exception:
        detail=traceback.format_exc();location=ROOT/'Donnees'/'logs'/'demarrage.txt'
        try:location.parent.mkdir(parents=True,exist_ok=True);location.write_text(detail,encoding='utf-8')
        except OSError:pass
        message='BrickLabo ne peut pas démarrer. / BrickLabo could not start.\n\n'+str(location)+'\n\n'+detail[-1500:]
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,message,'BrickLabo',0x10)
        else:print(message,file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(startup())
