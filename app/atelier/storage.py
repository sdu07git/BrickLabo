"""Application-owned files live beside the executable; no user-profile fallback."""

from .i18n import tr,tf
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import uuid
from .sqlite_file import connect


def application_directory():
    from .paths import application_root
    return application_root()

def data_directory():
    return application_directory()/'Donnees'


def _remap(value,old,new):
    if isinstance(value,str):
        normalized=value.replace('\\','/');prefix=str(old).replace('\\','/').rstrip('/')
        if normalized.casefold()==prefix.casefold():return str(new)
        if normalized.casefold().startswith(prefix.casefold()+'/'):
            return str(Path(new)/normalized[len(prefix)+1:])
    elif isinstance(value,list):return [_remap(v,old,new) for v in value]
    elif isinstance(value,dict):return {k:_remap(v,old,new) for k,v in value.items()}
    return value


def relocate_database(path,old,new):
    if not Path(path).is_file():return
    with closing(connect(path)) as connection,connection:
        if connection.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError(tr('Base de données endommagée : déplacement interrompu.'))
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'settings' in tables:
            for key,value in connection.execute('SELECT key,value FROM settings').fetchall():
                original=json.loads(value);changed=_remap(original,old,new)
                if changed!=original:connection.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(changed,ensure_ascii=False),key))
        for table,column in (('visual','image'),('items','image'),('imports','path')):
            if table in tables:
                for rowid,value in connection.execute('SELECT rowid,'+column+' FROM '+table).fetchall():
                    changed=_remap(value,old,new)
                    if changed!=value:connection.execute('UPDATE '+table+' SET '+column+'=? WHERE rowid=?',(changed,rowid))


def _digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').digest()


def migrate_legacy(source,target):
    source=Path(source);target=Path(target)
    if not (source/'atelier.sqlite').is_file():return False
    if target.resolve().is_relative_to(source.resolve()):raise ValueError(tr('Déplace le dossier du logiciel en dehors de l’ancien dossier LEGOAtelier avant la migration.'))
    if target.exists():
        # Keep the active portable database and archive a separate older profile locally.
        archive=target/('Ancien_profil_'+uuid.uuid4().hex)
        migrate_legacy(source,archive)
        return False
    stage=target.parent/('.migration-'+uuid.uuid4().hex)
    try:
        shutil.copytree(source,stage)
        for file in source.rglob('*'):
            if file.is_file() and _digest(file)!=_digest(stage/file.relative_to(source)):
                raise ValueError(tr('Les données ont changé pendant le déplacement. Ferme les autres instances du logiciel et réessaie.'))
        relocate_database(stage/'atelier.sqlite',source,target)
        (stage/'emplacement.json').write_text(json.dumps({'data':str(target),'app':str(target.parent)}),encoding='utf-8')
        stage.rename(target)
    except BaseException:
        if stage.exists():shutil.rmtree(stage)
        raise
    # The verified copy is already in place before removing the old application folder.
    try:shutil.rmtree(source)
    except OSError as error:
        raise OSError(tr('Les données sont copiées dans ')+str(target)+tr(', mais l’ancien dossier ')+str(source)+tr(' n’a pas pu être supprimé. Ferme les anciennes instances et supprime ce dossier après vérification.')) from error
    return True


_prepared_root=None

def prepare_portable_storage():
    global _prepared_root
    root=data_directory()
    if _prepared_root==root and root.exists():return root
    from .backups import apply_pending
    apply_pending(root)
    from .i18n import read_language,set_language
    set_language(read_language(root/'atelier.sqlite'))
    legacy_base=os.environ.get('LOCALAPPDATA')
    if legacy_base:migrate_legacy(Path(legacy_base)/'LEGOAtelier',root)
    root.mkdir(parents=True,exist_ok=True)
    probe=root/('.ecriture-'+uuid.uuid4().hex)
    try:probe.write_bytes(b'');probe.unlink()
    except OSError as error:raise OSError(tr('Le dossier du logiciel doit être accessible en écriture. Déplace BrickLabo dans un dossier où tu peux enregistrer des fichiers.')) from error
    marker=root/'emplacement.json'
    if marker.exists():
        previous=json.loads(marker.read_text(encoding='utf-8'))
        if previous.get('data')!=str(root):relocate_database(root/'atelier.sqlite',previous['data'],root)
        if previous.get('app') and previous['app']!=str(root.parent):relocate_database(root/'atelier.sqlite',previous['app'],root.parent)
    location={'data':str(root),'app':str(root.parent)}
    if not marker.exists() or json.loads(marker.read_text())!=location:marker.write_text(json.dumps(location),encoding='utf-8')
    from .temp_area import configure
    configure(root)
    _prepared_root=root
    return root


def configure_portable_database(db):
    root=db.path.parent;output=Path(db.setting('output',str(root/'Exports')))
    if not output.is_absolute() or not output.is_relative_to(application_directory()):output=root/'Exports'
    output.mkdir(parents=True,exist_ok=True);db.set_setting('output',str(output))
