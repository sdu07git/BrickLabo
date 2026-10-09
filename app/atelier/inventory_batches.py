"""Resumable catalogue inventory loading, separate from ownership and stock."""
import json
import threading
import urllib.parse
from .data import normalize
from .i18n import tr
from .services import API


def prepare(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS catalogue_inventory(source TEXT NOT NULL,ref TEXT NOT NULL,loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      parts TEXT NOT NULL,PRIMARY KEY(source,ref));
    CREATE TABLE IF NOT EXISTS inventory_jobs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,batch_size INTEGER NOT NULL,force INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS inventory_job_items(job_id INTEGER NOT NULL REFERENCES inventory_jobs(id) ON DELETE CASCADE,
      ordinal INTEGER NOT NULL,source TEXT NOT NULL,ref TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',error TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(job_id,ordinal),UNIQUE(job_id,source,ref));
    CREATE INDEX IF NOT EXISTS idx_inventory_pending ON inventory_job_items(job_id,status,ordinal);
    ''')


def cached_components(db,source,ref):
    found=db.rows('SELECT parts FROM catalogue_inventory WHERE source=? AND ref=?',(source,ref))
    if not found:return None
    rows=[]
    for part in json.loads(found[0]['parts']):
        items=db.rows('SELECT * FROM items WHERE source=? AND kind=? AND ref=?',(part['source'],part.get('kind','part'),part['ref']))
        if not items:raise ValueError(tr('Référence absente de l’inventaire : ')+part['ref'])
        rows.append(dict(items[0],chosen_color=part['color'],chosen_quantity=part['quantity'],is_spare=part.get('is_spare',False),inventory_image=part.get('image','')))
    return rows


def available(c,source,ref):
    from .build_stock import InventoryReader
    return InventoryReader(c).inventory(source,'set',ref)[1]


def create_job(db,items,batch_size=10,force=False):
    if not 10<=batch_size<=1000:raise ValueError(tr('Choisir un lot de 10 à 1000 sets.'))
    values=list(dict.fromkeys((i['source'],str(i['ref'])) for i in items))
    if not values:raise ValueError(tr('Sélectionne les sets à charger.'))
    if any(s not in ('RB','BL') or not r or len(r)>100 for s,r in values):raise ValueError(tr('Références de sets Rebrickable ou BrickLink requises.'))
    with db.connect() as c:
        for source,ref in values:
            if not c.execute("SELECT 1 FROM items WHERE source=? AND kind='set' AND ref=?",(source,ref)).fetchone():raise ValueError(tr('Set absent du catalogue : ')+ref)
        job=c.execute('INSERT INTO inventory_jobs(name,batch_size,force) VALUES(?,?,?)',(str(len(values))+tr(' sets'),batch_size,int(force))).lastrowid
        c.executemany('INSERT INTO inventory_job_items(job_id,ordinal,source,ref) VALUES(?,?,?,?)',((job,n,s,r) for n,(s,r) in enumerate(values)))
    return job


def jobs(db):return db.rows('SELECT * FROM inventory_jobs ORDER BY id DESC LIMIT 50')


def summary(db,job):
    out={r['status']:r['n'] for r in db.rows('SELECT status,COUNT(*) AS n FROM inventory_job_items WHERE job_id=? GROUP BY status',(job,))}
    return dict(total=sum(out.values()),pending=out.get('pending',0),loaded=out.get('loaded',0),skipped=out.get('skipped',0),errors=out.get('error',0))


def retry_errors(db,job):db.run("UPDATE inventory_job_items SET status='pending',error='' WHERE job_id=? AND status='error'",(job,))


def _rb_parts(api,ref,cancel):
    path='sets/'+urllib.parse.quote(ref,safe='')+'/parts/?page_size=1000&inc_minifig_parts=1&inc_part_details=1'
    parts=[];seen=set()
    while path:
        if cancel.is_set():return None
        if path in seen:raise ValueError(tr('Pagination d’inventaire répétée.'))
        seen.add(path);data=api.rb(path)
        if not isinstance(data.get('results'),list):raise ValueError(tr('Réponse d’inventaire invalide.'))
        for entry in data['results']:
            obj=entry['part'];color=entry['color'];quantity=int(entry['quantity'])
            if not obj.get('part_num') or quantity<=0 or color.get('id') is None:raise ValueError(tr('Ligne d’inventaire invalide.'))
            parts.append({'source':'RB','kind':'part','ref':obj['part_num'],'name':obj.get('name') or obj['part_num'],'category_id':str(obj.get('part_cat_id','')),
              'color':str(color['id']),'color_data':color,'quantity':quantity,'is_spare':bool(entry.get('is_spare')),'image':entry.get('part_img_url') or obj.get('part_img_url') or '',
              'bricklink_refs':obj.get('external_ids',{}).get('BrickLink',[])})
        path=data.get('next')
        if path and not path.startswith('https://rebrickable.com/api/v3/lego/'):raise ValueError(tr('Pagination Rebrickable invalide'))
    if not parts:raise ValueError(tr('Inventaire vide : aucune donnée enregistrée.'))
    return parts


def _bl_parts(api,ref,cancel):
    groups=api.bl('items/SET/'+urllib.parse.quote(ref,safe='')+'/subsets?break_minifigs=true&break_subsets=true')
    if cancel.is_set():return None
    parts=[]
    for group in groups:
        for entry in group.get('entries',[]):
            if entry.get('is_alternate') or entry.get('is_counterpart'):continue
            obj=entry['item']
            if obj['type'] not in ('PART','MINIFIG'):continue
            quantity=int(entry.get('quantity',0))
            if quantity<=0:raise ValueError(tr('Quantité d’inventaire invalide.'))
            parts.append({'source':'BL','kind':'minifig' if obj['type']=='MINIFIG' else 'part','ref':obj['no'],'name':obj.get('name') or obj['no'],
              'category_id':str(obj.get('category_id','')),'color':str(entry.get('color_id','')),'quantity':quantity,'is_spare':bool(entry.get('is_extra',False)),'image':''})
    if not parts:raise ValueError(tr('Inventaire vide : aucune donnée enregistrée.'))
    return parts


def store_inventory(db,source,ref,parts):
    if not parts:raise ValueError(tr('Inventaire vide.'))
    with db.connect() as c:
        for part in parts:
            c.execute('''INSERT INTO items(source,kind,ref,name,category_id,image,search) VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(source,kind,ref) DO UPDATE SET image=excluded.image WHERE items.image='' AND excluded.image<>'' ''',
              (part['source'],part.get('kind','part'),part['ref'],part['name'],part.get('category_id',''),part.get('image',''),normalize(part['ref']+' '+part['name'])))
            color=part.get('color_data')
            if color:c.execute('INSERT INTO colors(id,name,rgb,is_trans) VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING',(color['id'],color.get('name',''),color.get('rgb',''),int(bool(color.get('is_trans')))))
            if part.get('bricklink_refs'):
                key='rb_bricklink_refs_part_'+part['ref']
                c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE settings.value<>excluded.value',(key,json.dumps(part['bricklink_refs'])))
        c.execute('''INSERT INTO catalogue_inventory(source,ref,parts) VALUES(?,?,?) ON CONFLICT(source,ref)
          DO UPDATE SET parts=excluded.parts,loaded_at=CURRENT_TIMESTAMP WHERE catalogue_inventory.parts<>excluded.parts''',(source,ref,json.dumps(parts,ensure_ascii=False)))


def run_batch(db,job,cancel=None,progress=lambda _:None,api_factory=API):
    cancel=cancel or threading.Event()
    config=db.rows('SELECT * FROM inventory_jobs WHERE id=?',(job,))
    if not config:raise ValueError(tr('Chargement introuvable.'))
    config=config[0]
    rows=db.rows("SELECT * FROM inventory_job_items WHERE job_id=? AND status='pending' ORDER BY ordinal LIMIT ?",(job,config['batch_size']))
    api=api_factory(db);api.cancel=cancel
    for row in rows:
        if cancel.is_set():break
        source,ref=row['source'],row['ref'];progress(source+' · '+ref)
        try:
            with db.read() as c:ready=available(c,source,ref)
            if ready and not config['force']:status='skipped'
            else:
                parts=_rb_parts(api,ref,cancel) if source=='RB' else _bl_parts(api,ref,cancel)
                if cancel.is_set() or parts is None:break
                store_inventory(db,source,ref,parts);status='loaded'
            db.run('UPDATE inventory_job_items SET status=?,error=? WHERE job_id=? AND ordinal=?',(status,'',job,row['ordinal']))
        except Exception as error:
            if cancel.is_set():break
            message=str(error)
            # Keep the pending rows available after authentication/throttling failures.
            from urllib.error import HTTPError
            if isinstance(error,HTTPError) and error.code in (401,403,429):raise
            if 'manquante' in message or 'Consumer Key' in message:raise
            db.run("UPDATE inventory_job_items SET status='error',error=? WHERE job_id=? AND ordinal=?",(message,job,row['ordinal']))
    return summary(db,job)
