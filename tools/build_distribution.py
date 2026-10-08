"""Build the Windows launcher and package one authoritative app source tree.

Usage: python tools/build_distribution.py PREVIOUS_COMPLETE_ZIP OUTPUT_DIR
Requires MinGW-w64 on Linux. The archived runtime is reused without downloading
new dependencies; user data and test reports never enter either archive.
"""
import argparse
import json
import re
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from check_distribution import check

SOURCE=Path(__file__).resolve().parent.parent
VERSION=json.loads((SOURCE/'app'/'structure.json').read_text(encoding='utf-8'))['version']
FOLDERS=('app','ressources','documentation','licences')
ROOT_FILES=('LISEZ-MOI.txt','PROJET_GITHUB.url')
EXTRA_SOURCE=('README.md','README.en.md')

def excluded(path):
    vendor=any(path.parts[:len(prefix)]==prefix for prefix in (('app','lib'),('BrickLabo','app','lib'),('Lib','site-packages')))
    hidden=any(part.startswith('.') for part in path.parts)
    staging=bool(re.fullmatch(r'\..+\.(?:dll|zip)\.[A-Za-z0-9_-]{6,}',path.name,re.I))
    return '__pycache__' in path.parts or hidden and (not vendor or staging) or path.suffix.lower() in ('.pyc','.pyo','.bat','.log','.obj','.pdb','.tmp','.part')

def copy_tree(source,destination):
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source)
        if path.is_file() and not excluded(relative):
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)

def extract_runtime(original,root):
    files=0
    with ZipFile(original) as archive:
        for info in archive.infolist():
            path=PurePosixPath(info.filename)
            if info.is_dir() or '..' in path.parts or not info.filename.startswith('BrickLabo/'):continue
            relative=path.relative_to('BrickLabo')
            if excluded(relative):continue
            if relative.parts[:2]==('Lib','site-packages'):
                target=root/'app'/'lib'/Path(*relative.parts[2:])
            elif relative.parts[:2]==('app','lib'):
                target=root/Path(*relative.parts)
            elif len(relative.parts)==2 and relative.parts[0]=='app' and (relative.suffix.lower() in ('.dll','.pyd') or relative.name in ('python.exe','pythonw.exe','python312.zip','python.cat')):
                target=root/Path(*relative.parts)
            elif len(relative.parts)==1 and (relative.suffix.lower() in ('.dll','.pyd') or relative.name in ('python.exe','pythonw.exe','python312.zip','python.cat')):
                target=root/'app'/relative.name
            else:continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as reader,target.open('wb') as writer:shutil.copyfileobj(reader,writer)
            files+=1
    required=('python.exe','pythonw.exe','python312.dll','python312.zip','_sqlite3.pyd','lib/PySide6/QtWidgets.pyd','lib/PySide6/plugins/platforms/qwindows.dll','lib/PIL/Image.py','lib/numpy/__init__.py')
    for name in required:
        if not (root/'app'/name).is_file():raise RuntimeError('Missing archived runtime: '+name)
    (root/'app'/'python312._pth').write_text('python312.zip\n.\nlib\nimport site\n',encoding='utf-8')
    print('Archived runtime files:',files,flush=True)

def launcher(root,work):
    resource=Path(work)/'launcher.o'
    subprocess.run(['x86_64-w64-mingw32-windres','launcher.rc','-O','coff','-o',str(resource)],cwd=SOURCE/'tools',check=True)
    subprocess.run(['x86_64-w64-mingw32-gcc','-municode','-mwindows','-O2','-static','-s','-Wall','-Wextra',str(SOURCE/'tools'/'launcher.c'),str(resource),'-o',str(root/'BrickLabo.exe')],check=True)

def package(root,path):
    with ZipFile(path,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(root.rglob('*')):
            if not file.is_file():continue
            mode=ZIP_STORED if file.suffix.lower() in ('.zip','.gz','.png','.jpg','.jpeg','.webp','.gif') else ZIP_DEFLATED
            archive.write(file,'BrickLabo/'+file.relative_to(root).as_posix(),compress_type=mode)
    with ZipFile(path) as archive:
        bad=archive.testzip()
        if bad:raise RuntimeError('ZIP checksum failure: '+bad)
        if any(excluded(PurePosixPath(name)) for name in archive.namelist()):raise RuntimeError('Excluded file packaged')
    print(path.name,path.stat().st_size,'bytes',flush=True)

def build(original,output):
    original=Path(original).resolve();output=Path(output).resolve()
    if output.is_relative_to(SOURCE):raise ValueError('Output must be outside the source tree')
    if (SOURCE/'app'/'lib').exists():raise ValueError('Source tree must not contain embedded runtime libraries')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bricklabo-build-',dir=output) as work:
        full=Path(work)/'complete'/'BrickLabo';source=Path(work)/'sources'/'BrickLabo'
        for root in (full,source):
            root.mkdir(parents=True)
            for folder in FOLDERS:copy_tree(SOURCE/folder,root/folder)
            for name in ROOT_FILES:shutil.copyfile(SOURCE/name,root/name)
        for folder in ('tests','tools'):copy_tree(SOURCE/folder,source/folder)
        for name in EXTRA_SOURCE:
            shutil.copyfile(SOURCE/name,source/name)
            (full/'documentation'/name).write_text((SOURCE/name).read_text(encoding='utf-8').replace('(documentation/','('),encoding='utf-8')
        extract_runtime(original,full);launcher(full,work)
        print(json.dumps(check(full),ensure_ascii=False),flush=True)
        if sorted(p.name for p in full.iterdir() if p.is_file())!=sorted(('BrickLabo.exe',)+ROOT_FILES):raise RuntimeError('Unexpected root file')
        for folder in FOLDERS:
            for file in (source/folder).rglob('*'):
                if file.is_file() and file.read_bytes()!=(full/file.relative_to(source)).read_bytes():raise RuntimeError('Source/runtime mismatch: '+str(file))
        package(full,output/('BrickLabo_v'+VERSION+'_Complet.zip'))
        package(source,output/('BrickLabo_v'+VERSION+'_Sources.zip'))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous_complete_zip',type=Path);parser.add_argument('output_directory',type=Path)
    args=parser.parse_args();build(args.previous_complete_zip,args.output_directory)
