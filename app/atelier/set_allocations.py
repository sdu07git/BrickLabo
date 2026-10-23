"""Exclusive claims on owned set copies, independent of loose stock/pick ledgers."""
from collections import Counter
import json

from .i18n import tr

TABLES=('project_set_sources','project_set_allocations')


def prepare(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS project_set_sources(
        project_id INTEGER PRIMARY KEY REFERENCES construction_projects(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS project_set_allocations(
        project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
        set_entry_id INTEGER NOT NULL REFERENCES stock_sets(id),copies INTEGER NOT NULL CHECK(copies>0),
        components TEXT NOT NULL,PRIMARY KEY(project_id,set_entry_id));''')
    for table in TABLES:
        for op in ('INSERT','UPDATE','DELETE'):
            c.execute('CREATE TRIGGER IF NOT EXISTS revision_'+table+'_'+op.lower()+' AFTER '+op+' ON '+table+' BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')


def unpack(value):
    return Counter({(int(identity),str(color)):int(quantity) for identity,color,quantity in json.loads(value)})


def pack(counts):return json.dumps([[i,color,q] for (i,color),q in sorted(counts.items()) if q>0],ensure_ascii=False)


def allocated_counts(c,project_id=None,entry_id=None):
    conditions=[];args=[]
    if project_id is not None:conditions.append('project_id=?');args.append(project_id)
    if entry_id is not None:conditions.append('set_entry_id=?');args.append(entry_id)
    counts=Counter()
    for row in c.execute('SELECT components FROM project_set_allocations'+(' WHERE '+' AND '.join(conditions) if conditions else ''),args):counts.update(unpack(row['components']))
    return counts


def entry_components(c,entry_id):
    row=c.execute('SELECT s.*,i.source,i.ref FROM stock_sets s JOIN items i ON i.id=s.item_id WHERE s.id=?',(entry_id,)).fetchone()
    if not row or row['quantity']<=0:raise ValueError(tr('Set possédé introuvable.'))
    tracked=c.execute('SELECT item_id,color,quantity FROM stock_set_components WHERE set_entry_id=?',(entry_id,)).fetchall()
    if tracked:return Counter({(r['item_id'],str(r['color'])):int(r['quantity']) for r in tracked}),int(row['quantity']),False
    from .build_stock import InventoryReader
    reader=InventoryReader(c);identities={}
    def expand(source,ref,trail=()):
        if (source,ref) in trail:return Counter(),False
        children,complete=reader.children(source,'set',ref);counts=Counter()
        for src,kind,num,color,quantity,spare in children:
            if quantity<=0:continue
            if kind=='set':
                nested,ok=expand(src,num,trail+((source,ref),));complete=complete and ok;counts.update({key:value*quantity for key,value in nested.items()})
            elif kind in ('part','minifig'):
                key=(src,kind,num)
                if key not in identities:
                    item=c.execute('SELECT id FROM items WHERE source=? AND kind=? AND ref=?',key).fetchone();identities[key]=item['id'] if item else None
                if identities[key] is None:complete=False
                else:counts[(identities[key],str(color))]+=quantity
            else:complete=False
        return counts,complete and bool(counts)
    counts,complete=expand(row['source'],row['ref'])
    if not complete:raise ValueError(tr('Charge d’abord l’inventaire complet de ce set.'))
    return Counter({key:q*int(row['quantity']) for key,q in counts.items()}),int(row['quantity']),True


def choices(db,project_id):
    with db.read() as c:
        c.execute('BEGIN');rows=[dict(r) for r in c.execute('''SELECT s.id AS entry_id,s.quantity AS owned_copies,i.*,COALESCE((SELECT SUM(a.copies) FROM project_set_allocations a WHERE a.set_entry_id=s.id AND a.project_id<>?),0) AS other_copies,
            COALESCE((SELECT copies FROM project_set_allocations a WHERE a.set_entry_id=s.id AND a.project_id=?),0) AS selected_copies
            FROM stock_sets s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 ORDER BY i.source,i.ref''',(project_id,project_id))]
        for row in rows:
            try:
                counts,total,fallback=entry_components(c,row['entry_id']);row.update(group_only=any(q%total for q in counts.values()),fallback=fallback,error='')
            except ValueError as error:row.update(group_only=False,fallback=False,error=str(error))
        return rows


def assign(db,project_id,selection,all_free=False):
    from .action_history import change
    if type(all_free) is not bool or not isinstance(selection,dict) or any(type(k) is not int or type(v) is not int or not 0<=v<=1000000000 for k,v in selection.items()):raise ValueError(tr('Sélection de sets invalide.'))
    with db.connect() as c,change(c,('construction_projects',)+TABLES,tr('Affectation des sets à un projet')):
        if not c.execute('SELECT 1 FROM construction_projects WHERE id=?',(project_id,)).fetchone():raise ValueError(tr('Projet introuvable.'))
        c.execute('DELETE FROM project_set_allocations WHERE project_id=?',(project_id,))
        c.execute('DELETE FROM project_set_sources WHERE project_id=?',(project_id,))
        if not all_free:
            c.execute('INSERT INTO project_set_sources VALUES(?)',(project_id,))
            for entry_id,copies in selection.items():
                if not copies:continue
                counts,total,fallback=entry_components(c,entry_id)
                used=c.execute('SELECT COALESCE(SUM(copies),0) FROM project_set_allocations WHERE set_entry_id=?',(entry_id,)).fetchone()[0]
                if copies+used>total:raise ValueError(tr('Ces exemplaires sont déjà affectés à un autre projet.'))
                if any(q%total for q in counts.values()) and copies!=total:raise ValueError(tr('L’inventaire commun de ces exemplaires est incomplet. Affecte le groupe entier ou sépare son suivi avant de choisir un exemplaire.'))
                selected=Counter({key:q*copies//total for key,q in counts.items()})
                c.execute('INSERT INTO project_set_allocations VALUES(?,?,?,?)',(project_id,entry_id,copies,pack(selected)))
        c.execute('UPDATE construction_projects SET include_set_stock=1 WHERE id=?',(project_id,))


def pool(c,project_id,free_pool=None):
    if c.execute('SELECT 1 FROM project_set_sources WHERE project_id=?',(project_id,)).fetchone():return allocated_counts(c,project_id)
    if free_pool is not None:return free_pool
    from .project_stock import owned_sets
    return owned_sets(c)[0]


def validate(c):
    for row in c.execute('SELECT set_entry_id,SUM(copies) AS copies FROM project_set_allocations GROUP BY set_entry_id'):
        counts,total,fallback=entry_components(c,row['set_entry_id'])
        claimed=allocated_counts(c,entry_id=row['set_entry_id'])
        if row['copies']>total or any(q>counts[key] for key,q in claimed.items()):raise ValueError(tr('Des exemplaires ou pièces de ce set sont affectés à un projet. Libère cette affectation avant de modifier le stock set.'))
