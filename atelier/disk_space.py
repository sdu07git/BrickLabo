"""Scoped disk maintenance: no Windows-temp access, no symlink traversal."""
import hashlib,json,os,re,time,uuid,shutil
from pathlib import Path

def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def files(folder):
 folder=Path(folder)
 if folder.is_symlink() or not folder.is_dir():return
 for base,dirs,names in os.walk(folder,followlinks=False):
  dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
  for name in names:
   p=Path(base)/name
   if not p.is_symlink():yield p

def locations(db):
 root=db.path.parent
 return {'Total du dossier Donnees':root,'Base de données':root,'Temporaires':root/'temp','Miniatures':root/'cache'/'miniatures','Images (locales et téléchargées)':root/'images','Notices':root/'Notices','Archives LDraw':root,'Téléchargements des bases':root/'downloads','Étiquettes générées':Path(db.setting('output',str(root/'Exports'))),'Fichiers fournis':Path(__file__).resolve().parent.parent/'ressources'}

def usage(db):
 root=db.path.parent;result=[]
 for label,folder in locations(db).items():
  if label=='Base de données':paths=[db.path,Path(str(db.path)+'-wal'),Path(str(db.path)+'-shm')]
  elif label=='Archives LDraw':paths=ldraw_files(root)
  else:paths=files(folder)
  size=count=0
  for p in paths:
   try:size+=p.stat().st_size;count+=1
   except OSError:pass
  result.append((label,size,count))
 return result


def ldraw_files(root):
 return sorted(p for p in Path(root).glob('ldraw*.zip') if p.is_file() and not p.is_symlink() and re.fullmatch(r'ldraw(?:_\d+|-[0-9a-f]{64})\.zip',p.name))

def reuse_ldraw(db,path):
 path=Path(path);root=db.path.parent
 source_hash=digest(path)
 active=Path(db.setting('ldraw',''))
 # Supplied resources already travel with the executable; use them in place.
 supplied=Path(__file__).resolve().parent.parent/'ressources'
 if path.resolve().is_relative_to(supplied.resolve()):return path
 for candidate in [active,*ldraw_files(root)]:
  if candidate.is_file() and not candidate.is_symlink() and (candidate.resolve()==path.resolve() or (candidate.stat().st_size==path.stat().st_size and digest(candidate)==source_hash)):return candidate
 target=root/('ldraw-'+source_hash+'.zip')
 if target.is_file():
  if digest(target)!=source_hash:raise ValueError('Archive LDraw existante endommagée : import interrompu.')
  return target
 temporary=root/('.ldraw-'+uuid.uuid4().hex+'.part')
 try:
  shutil.copy2(path,temporary)
  if digest(temporary)!=source_hash:raise ValueError('Archive modifiée pendant la copie ; réessayer.')
  os.replace(temporary,target)
 finally:temporary.unlink(missing_ok=True)
 return target

def protected_paths(db):
 result=[db.path.resolve()]
 def collect(value):
  if isinstance(value,str) and value and not value.startswith(('http://','https://')):
   p=Path(value)
   if p.is_absolute():result.append(p.resolve())
  elif isinstance(value,dict):
   for child in value.values():collect(child)
  elif isinstance(value,list):
   for child in value:collect(child)
 for row in db.rows('SELECT value FROM settings'):
  try:collect(json.loads(row['value']))
  except ValueError:pass
 for table,column in [('visual','image'),('items','image'),('imports','path')]:
  for row in db.rows('SELECT '+column+' FROM '+table):collect(row[column])
 return result

def clean_temp(db,days=7):
 cutoff=time.time()-days*86400;protected=protected_paths(db);removed=freed=0;errors=[]
 for p in files(db.path.parent/'temp'):
  try:
   stat=p.stat();resolved=p.resolve()
   if stat.st_mtime>=cutoff or any(resolved==keep or resolved.is_relative_to(keep) for keep in protected):continue
   p.unlink();removed+=1;freed+=stat.st_size
  except OSError as e:errors.append(str(e))
 return removed,freed,errors

def deduplicate_ldraw(db):
 from .storage import relocate_database
 active=Path(db.setting('ldraw','')).resolve();paths=ldraw_files(db.path.parent);paths.sort(key=lambda p:p.resolve()!=active)
 seen={};removed=freed=0;errors=[]
 # Also recognize a duplicate of the supplied archive, retaining active first.
 bundled=Path(__file__).resolve().parent.parent/'ressources'/'complete.zip'
 if bundled.is_file() and active==bundled.resolve():seen[digest(bundled)]=bundled
 for p in paths:
  try:
   stamp=p.stat();key=digest(p)
   if key not in seen:seen[key]=p;continue
   keep=seen[key]
   if p.resolve()==active:continue
   if p.stat().st_mtime_ns!=stamp.st_mtime_ns or p.stat().st_size!=stamp.st_size or digest(keep)!=key:continue
   relocate_database(db.path,p,keep)
   p.unlink();removed+=1;freed+=stamp.st_size
  except (OSError,ValueError) as e:errors.append(str(e))
 return removed,freed,errors
