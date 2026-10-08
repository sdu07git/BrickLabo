"""Create a minimal licensed LDraw supplement with recursive dependencies."""
from __future__ import annotations

from .i18n import tr,tf
import json,re,zipfile,hashlib,os,threading
from contextlib import ExitStack
from .fileio import atomic_output
from .temp_area import workspace
MODEL_LOCK=threading.RLock()
from pathlib import Path
from .render import RenderError

URLS={'official':'https://library.ldraw.org/library/updates/complete.zip','unofficial':'https://library.ldraw.org/library/unofficial/ldrawunf.zip'}

def build_pack(records,archives,destination,existing=None):
    with ExitStack() as stack:return _build_pack(records,archives,destination,existing,stack)

def _build_pack(records,archives,destination,existing,stack):
    files={};origins={};licenses={};contents={}
    for status,path in archives:
        z=stack.enter_context(zipfile.ZipFile(path))
        for member in z.namelist():
            name=member.replace('\\','/').lower().removeprefix('ldraw/')
            if name.endswith('/') or '..' in name.split('/'):continue
            if name.startswith(('parts/','p/')) and name.endswith('.dat'):
                if name not in files:files[name]=(z,member);origins[name]=status
            elif Path(name).name in ('careadme.txt','calicense.txt','calicense4.txt'):
                licenses[status+'/'+Path(name).name]=z.read(member)
    def content(key):
        if key not in contents:
            archive,member=files[key];contents[key]=archive.read(member)
        return contents[key]
    selected={};missing={}
    existing_names=set()
    if existing:
        with zipfile.ZipFile(existing) as base:existing_names={n.lower().removeprefix('ldraw/') for n in base.namelist()}
    def resolve(name):
        name=name.replace('\\','/').lower()
        for key in [name,'parts/'+name,'p/'+name]:
            if key in files:return key
        raise RenderError(tr('Dépendance absente : ')+name)
    def walk(name,used):
        key=resolve(name)
        if key in used:return
        used.add(key)
        text=content(key).decode('utf-8','replace')
        for line in text.splitlines():
            tokens=line.split()
            if tokens and tokens[0]=='1' and len(tokens)>=15:walk(' '.join(tokens[14:]),used)
    for record in records:
        statuses={}
        for model in record.get('models',[]):
            try:
                used=set();walk(model,used)
                for key in used:
                    if key not in existing_names:selected[key]=content(key)
                statuses[model]=origins[resolve(model)]
            except RenderError as error:statuses[model]='unavailable';missing[model]=str(error)
        record['model_status']=statuses
    # Retain license files and authorship headers; no textures or website images.
    destination=Path(destination)
    with atomic_output(destination) as temp,zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for key,value in selected.items():z.writestr(key,value)
        for key,value in licenses.items():z.writestr('licenses/'+key,value)
        z.writestr('ORIGINES.json',json.dumps({'downloads':URLS,'files':{key:{'status':origins[key],'sha256':hashlib.sha256(value).hexdigest(),'authors':re.findall(r'^0 Author: (.+)',value.decode('utf-8','replace'),re.M),'license':re.findall(r'^0 !LICENSE (.+)',value.decode('utf-8','replace'),re.M),'modified':False} for key,value in selected.items()}},ensure_ascii=False,indent=2))
    return {'files':len(selected),'missing':missing}


def ensure_models(db,record):
    with MODEL_LOCK:return _ensure_models(db,record)

def _ensure_models(db,record):
    with ExitStack() as stack:return _download_models(db,record,stack)

def _download_models(db,record,stack):
    """Fetch a missing public LDraw bundle, retaining files and attribution."""
    from .render import LDraw
    from .services import request
    folder=stack.enter_context(workspace(db.path.parent))
    supplement=db.path.parent/'brickarchitect_ldraw.zip'
    renderer=LDraw(db.setting('ldraw'),supplement) if db.setting('ldraw') else None
    if renderer:stack.callback(renderer.close)
    statuses=record.setdefault('model_status',{})
    for model in record.get('models',[]):
        if renderer:
            try:
                content=renderer.read(model)
                statuses[model]='unofficial' if '!LDRAW_ORG Unofficial' in content else 'official'
                continue
            except RenderError:pass
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+\.dat',model):statuses[model]='unavailable';continue
        for status in ('unofficial','official'):
            url='https://library.ldraw.org/library/'+status+'/parts/'+model.removesuffix('.dat')+'.zip'
            path=folder/(status+'.zip')
            try:
                request(url,destination=path,timeout=25)
                with zipfile.ZipFile(path) as archive:
                    files={n.lower().removeprefix('ldraw/'):archive.read(n) for n in archive.namelist() if n.lower().endswith('.dat') and n.replace('\\','/').lower().removeprefix('ldraw/').startswith(('parts/','p/')) and '..' not in n.split('/')}
                if 'parts/'+model.lower() not in files:continue
                existing={}
                if supplement.exists():
                    with zipfile.ZipFile(supplement) as old:existing={n:old.read(n) for n in old.namelist()}
                existing.update(files)
                meta=json.loads(existing.get('ORIGINES.json',b'{"files":{}}'))
                for name,value in files.items():
                    meta.setdefault('files',{})[name]={'status':status,'source':url,'sha256':hashlib.sha256(value).hexdigest(),'authors':re.findall(r'^0 Author: (.+)',value.decode('utf-8','replace'),re.M),'license':re.findall(r'^0 !LICENSE (.+)',value.decode('utf-8','replace'),re.M),'modified':False}
                existing['ORIGINES.json']=json.dumps(meta,ensure_ascii=False,indent=2).encode()
                with atomic_output(supplement) as temporary,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as new:
                    for name,value in existing.items():new.writestr(name,value)
                statuses[model]=status
                break
            except Exception:continue
        else:statuses[model]='unavailable'
    return record
