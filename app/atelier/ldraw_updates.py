"""Validated official-library downloads and explicit catalogue references."""
import json
import re
import threading
import time
import zipfile
from pathlib import Path

from .i18n import tr
from .services import request
from .temp_area import workspace
from .disk_space import reuse_ldraw,ldraw_files,protected_paths

OFFICIAL_URL='https://library.ldraw.org/library/updates/complete.zip'
LIBRARY_LOCK=threading.RLock()


def header_links(path,progress=lambda *_:None,strict=False):
    """Never guess patterned IDs: retain only unique, explicit header links."""
    candidates={'RB':{},'BL':{}};count=0
    with zipfile.ZipFile(path) as archive:
        names={name.replace('\\','/').lower():name for name in archive.namelist()}
        if 'ldraw/ldconfig.ldr' not in names:raise ValueError(tr('Archive LDraw non reconnue'))
        if strict:
            if not any(name.startswith('ldraw/parts/') and name.endswith('.dat') for name in names):raise ValueError(tr('Archive LDraw non reconnue'))
            progress(tr('Vérification de l’archive LDraw…'))
            bad=archive.testzip()
            if bad:raise ValueError(tr('Archive LDraw endommagée : ')+bad)
        for name,member in names.items():
            if not re.fullmatch(r'ldraw/parts/[^/]+\.dat',name):continue
            count+=1
            with archive.open(member) as stream:text=stream.read(16384).decode('utf-8','replace')
            for line in text.splitlines():
                if not line.startswith('0 !KEYWORDS'):continue
                for match in re.finditer(r'\b(Bricklink|Rebrickable)\s+([A-Za-z0-9][A-Za-z0-9_.-]*)',line,re.I):
                    source='BL' if match[1].lower()=='bricklink' else 'RB'
                    candidates[source].setdefault(match[2].lower(),set()).add(Path(name).stem)
    return {'models':{source:{ref:next(iter(models)) for ref,models in refs.items() if len(models)==1} for source,refs in candidates.items()},
            'ambiguous':{source:sorted(ref for ref,models in refs.items() if len(models)>1) for source,refs in candidates.items()},'parts':count}


def install_library(db,path,progress=lambda *_:None,strict=False,remove_previous=False):
    with LIBRARY_LOCK:
        links=header_links(path,progress,strict);previous=Path(db.setting('ldraw',''));target=reuse_ldraw(db,path)
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for key,value in [('ldraw',str(target)),('ldraw_header_links',{'path':str(target),**links})]:
                c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,ensure_ascii=False)))
            c.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',('LDraw',str(target),time.strftime('%Y-%m-%d %H:%M'),links['parts']))
        warnings=[];removed=False
        if remove_previous and previous!=target and previous in ldraw_files(db.path.parent):
            try:
                protected=protected_paths(db)
                if previous.resolve() not in protected:previous.unlink();removed=True
            except OSError as error:warnings.append(str(error))
        return {'path':str(target),'parts':links['parts'],'removed_previous':removed,'warnings':warnings}


def update_library(db,progress=lambda *_:None):
    progress(tr('Téléchargement de complete.zip depuis LDraw…'))
    with workspace(db.path.parent,prefix='ldraw') as folder:
        path=request(OFFICIAL_URL,destination=folder/'complete.zip',timeout=60)
        progress(tr('Lecture des correspondances LDraw…'))
        return install_library(db,path,progress,strict=True,remove_previous=True)
