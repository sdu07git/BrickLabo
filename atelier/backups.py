"""Verified private backups; restoration happens before opening application data."""
import hashlib,json,os,shutil,sqlite3,tempfile,time,uuid,zipfile,re
from pathlib import Path,PurePosixPath
from contextlib import closing
from .version import VERSION
from .disk_space import files,digest

REQUEST='restauration_en_attente.json'
REPORT='resultat_restauration.json'
EXCLUDED={'temp','cache','logs','downloads'}

def _included(relative):
 return relative.parts[0] not in EXCLUDED and relative.name not in {REQUEST,REPORT,'atelier.sqlite','atelier.sqlite-wal','atelier.sqlite-shm'} and not relative.name.endswith(('.tmp','.part'))

def _check_db(path):
 with closing(sqlite3.connect(path)) as connection:
  if connection.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Base SQLite endommagée.')
  tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if not {'items','stock','settings'}.issubset(tables):raise ValueError('Base BrickLabo non reconnue.')

def create_backup(db,destination,progress=lambda value:None):
 root=db.path.parent.resolve();destination=Path(destination).resolve()
 if destination.is_relative_to(root):raise ValueError('Choisir un dossier de sauvegarde en dehors de Donnees.')
 destination.parent.mkdir(parents=True,exist_ok=True)
 temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.part')
 manifest={'format':1,'application':'BrickLabo','version':VERSION,'created':time.strftime('%Y-%m-%d %H:%M:%S'),'data_root':str(root),'app_root':str(root.parent),'files':{}}
 try:
  (root/'temp').mkdir(exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='bricklabo-backup-',dir=root/'temp') as temporary_dir:
   snapshot=Path(temporary_dir)/'atelier.sqlite'
   progress('Sauvegarde cohérente de la base de données…')
   with db.connect() as source,closing(sqlite3.connect(snapshot)) as target:source.backup(target)
   _check_db(snapshot)
   with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as archive:
    candidates=[(snapshot,'atelier.sqlite')]+[(p,p.relative_to(root).as_posix()) for p in files(root) if _included(p.relative_to(root))]
    for path,relative in candidates:
     progress('Sauvegarde : '+relative);before=path.stat();archive.write(path,'Donnees/'+relative);after=path.stat()
     if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Fichier modifié pendant la sauvegarde : '+relative+'. Réessayer.')
     manifest['files'][relative]={'size':after.st_size,'sha256':digest(path)}
    archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
  validate_archive(temporary,progress)
  os.replace(temporary,destination)
 finally:temporary.unlink(missing_ok=True)
 return destination

def _safe_name(name):
 path=PurePosixPath(name)
 if not name or path.as_posix()!=name or '\\' in name or path.is_absolute() or any(part in ('','..','.') or ':' in part for part in path.parts):raise ValueError('Chemin de sauvegarde invalide : '+name)
 return path

def validate_archive(path,progress=lambda value:None,stage=None):
 with zipfile.ZipFile(path) as archive:
  names=archive.namelist()
  if len({name.casefold() for name in names})!=len(names):raise ValueError('Fichiers dupliqués dans la sauvegarde.')
  if 'manifest.json' not in names:raise ValueError('Ce ZIP n’est pas une sauvegarde BrickLabo.')
  if archive.getinfo('manifest.json').file_size>16*1024*1024:raise ValueError('Manifeste de sauvegarde trop volumineux.')
  manifest=json.loads(archive.read('manifest.json'))
  if manifest.get('application')!='BrickLabo' or manifest.get('format')!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Format de sauvegarde non reconnu.')
  def version(value):return tuple(int(x) for x in value.split('.'))
  if version(manifest['version'])>version(VERSION):raise ValueError('Sauvegarde créée avec une version plus récente. Mettre BrickLabo à jour.')
  expected={'manifest.json'}
  for relative,meta in manifest['files'].items():
   _safe_name(relative);expected.add('Donnees/'+relative)
   if not isinstance(meta.get('size'),int) or meta['size']<0:raise ValueError('Taille de fichier invalide.')
  if set(names)!=expected or 'atelier.sqlite' not in manifest['files']:raise ValueError('Contenu de sauvegarde incomplet ou inattendu.')
  for name in names:_safe_name(name)
  for relative,meta in manifest['files'].items():
   name='Donnees/'+relative;info=archive.getinfo(name)
   if info.file_size!=meta['size'] or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Fichier de sauvegarde invalide : '+relative)
   progress('Vérification : '+relative);hash_value=hashlib.sha256();out=None
   try:
    if stage:
     destination=Path(stage)/'Donnees'/relative;destination.parent.mkdir(parents=True,exist_ok=True);out=destination.open('wb')
    with archive.open(name) as stream:
     while chunk:=stream.read(1024*1024):
      hash_value.update(chunk)
      if out:out.write(chunk)
   finally:
    if out:out.close()
   if hash_value.hexdigest()!=meta['sha256']:raise ValueError('Fichier endommagé dans la sauvegarde : '+relative)
  if stage:_check_db(Path(stage)/'Donnees'/'atelier.sqlite')
 return manifest

def queue_restore(db,archive,progress=lambda value:None):
 root=db.path.parent.resolve()
 if (root/REQUEST).exists():raise ValueError('Une restauration est déjà programmée. Annuler celle-ci avant d’en préparer une autre.')
 manifest=validate_archive(archive,progress)
 needed=sum(meta['size'] for meta in manifest['files'].values())
 if shutil.disk_usage(root.parent).free<needed+16*1024*1024:raise ValueError('Espace disque insuffisant pour préparer la restauration.')
 stage=root.parent/('BrickLabo_restaurer_'+uuid.uuid4().hex)
 try:
  stage.mkdir();validate_archive(archive,progress,stage)
  (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
  request=root/REQUEST;temporary=request.with_suffix('.tmp')
  temporary.write_text(json.dumps({'stage':str(stage),'manifest_hash':digest(stage/'manifest.json')}),encoding='utf-8');os.replace(temporary,request)
 except BaseException:
  if stage.exists():shutil.rmtree(stage)
  raise
 return stage

def _stage(root,value):
 original=Path(value);stage=original.resolve()
 if stage.parent!=root.parent.resolve() or not re.fullmatch(r'BrickLabo_restaurer_[0-9a-f]{32}',stage.name) or original.is_symlink():raise ValueError('Dossier de restauration invalide.')
 return stage

def cancel_restore(db):
 root=db.path.parent.resolve();request=root/REQUEST
 if not request.exists():return
 stage=_stage(root,json.loads(request.read_text(encoding='utf-8'))['stage'])
 if stage.exists():shutil.rmtree(stage)
 request.unlink()

def apply_pending(root):
 root=Path(root).resolve();request=root/REQUEST
 if not request.exists():return
 previous=None;stage=None
 try:
  pending=json.loads(request.read_text(encoding='utf-8'));stage=_stage(root,pending['stage'])
  if digest(stage/'manifest.json')!=pending['manifest_hash']:raise ValueError('Manifeste préparé modifié.')
  if (stage/'Donnees').is_symlink():raise ValueError('Dossier de données préparées invalide.')
  manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
  # Verify again at startup; staged data must not change between preparation and use.
  for relative,meta in manifest['files'].items():
   _safe_name(relative);path=stage/'Donnees'/relative
   if path.is_symlink() or not path.resolve().is_relative_to(stage/'Donnees') or path.stat().st_size!=meta['size'] or digest(path)!=meta['sha256']:raise ValueError('Données préparées modifiées : '+relative)
  _check_db(stage/'Donnees'/'atelier.sqlite')
  from .storage import relocate_database
  relocate_database(stage/'Donnees'/'atelier.sqlite',manifest['data_root'],root)
  relocate_database(stage/'Donnees'/'atelier.sqlite',manifest['app_root'],root.parent)
  (stage/'Donnees'/'emplacement.json').write_text(json.dumps({'data':str(root),'app':str(root.parent)}),encoding='utf-8')
  previous=root.parent/('Donnees_avant_restauration_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
  request.unlink();root.rename(previous)
  try:(stage/'Donnees').rename(root)
  except BaseException:
   previous.rename(root);raise
  (root/REPORT).write_text(json.dumps({'success':True,'previous':str(previous),'message':'Sauvegarde restaurée. État précédent conservé dans '+str(previous)},ensure_ascii=False),encoding='utf-8')
 except Exception as e:
  if not root.is_dir():raise
  request.unlink(missing_ok=True)
  (root/REPORT).write_text(json.dumps({'success':False,'message':'Restauration annulée : '+str(e)},ensure_ascii=False),encoding='utf-8')
 finally:
  if stage and stage.exists():shutil.rmtree(stage,ignore_errors=True)
