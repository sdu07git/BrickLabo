"""Persistent last-action undo for general colour and drawer associations.

The stock journal remains independent. Its writes invalidate this journal;
an empty marker prevents an older stock action resurfacing after undoing it.
"""
from contextlib import contextmanager
import json

from .i18n import tr


def prepare(c):
    c.execute('CREATE TABLE IF NOT EXISTS action_undo(id INTEGER PRIMARY KEY CHECK(id=1),description TEXT NOT NULL,payload TEXT NOT NULL)')
    for operation in ('INSERT','UPDATE','DELETE'):
        c.execute('CREATE TRIGGER IF NOT EXISTS reset_action_undo_'+operation.lower()+' AFTER '+operation+' ON stock_undo BEGIN DELETE FROM action_undo; END')


def record(c,description,payload):
    c.execute('INSERT OR REPLACE INTO action_undo VALUES(1,?,?)',(description,json.dumps(payload,ensure_ascii=False)))


def set_default_color(db,color):
    from .render import DEFAULT_PART_COLOR
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM settings WHERE key='default_color'").fetchone()
        before=dict(row) if row else None
        current=json.loads(row['value']) if row else DEFAULT_PART_COLOR
        if current==color:return False
        value=json.dumps(color,ensure_ascii=False)
        c.execute("INSERT OR REPLACE INTO settings VALUES('default_color',?)",(value,))
        record(c,tr('Modification de la couleur 3D générale'),{'kind':'color','before':before,'after':{'key':'default_color','value':value}})
    return True


def set_visual_color(db,identity,color):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        identities=item_identities(c,[identity])
        if not identities:raise ValueError(tr('Référence introuvable'))
        row=c.execute('SELECT * FROM visual WHERE item_id=?',(identity,)).fetchone()
        before=dict(row) if row else None
        if (row['color'] if row else '')==color:return False
        c.execute("INSERT INTO visual(item_id,color) VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET color=excluded.color",(identity,color))
        after=dict(c.execute('SELECT * FROM visual WHERE item_id=?',(identity,)).fetchone())
        record(c,tr('Modification de la couleur 3D d’une référence'),{'kind':'visual','before':before,'after':after,'item':identities})
    return True


def storage_state(c,drawer_ids):
    ids=sorted(set(drawer_ids));drawers=[];links=[]
    for start in range(0,len(ids),800):
        chunk=ids[start:start+800];args=','.join('?' for _ in chunk)
        drawers.extend(dict(row) for row in c.execute('SELECT * FROM storage_drawers WHERE id IN ('+args+') ORDER BY id',chunk))
        links.extend(dict(row) for row in c.execute('SELECT * FROM storage_contents WHERE drawer_id IN ('+args+') ORDER BY drawer_id,item_id,color',chunk))
    return {'ids':ids,'drawers':sorted(drawers,key=lambda r:r['id']),'links':sorted(links,key=lambda r:(r['drawer_id'],r['item_id'],r['color']))}


def item_identities(c,ids):
    result=[];ids=sorted(set(ids))
    for start in range(0,len(ids),800):
        chunk=ids[start:start+800]
        result.extend(dict(row) for row in c.execute('SELECT id,source,kind,ref FROM items WHERE id IN ('+','.join('?' for _ in chunk)+') ORDER BY id',chunk))
    return sorted(result,key=lambda r:r['id'])


@contextmanager
def storage_change(c,drawer_ids,description):
    if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
    before=storage_state(c,drawer_ids)
    yield
    after=storage_state(c,drawer_ids)
    if before!=after:
        identities={row['item_id'] for row in before['links']+after['links']}
        record(c,description,{'kind':'storage','before':before,'after':after,'items':item_identities(c,identities)})


def description(db):
    rows=db.rows('SELECT description FROM action_undo WHERE id=1')
    if rows:return rows[0]['description']
    rows=db.rows('SELECT description FROM stock_undo WHERE id=1')
    return rows[0]['description'] if rows else ''


def undo(db):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM action_undo WHERE id=1').fetchone()
        if row is None:
            from .stock import undo as undo_stock
            # End this read transaction before the stock undo acquires its own lock.
            c.rollback()
            return undo_stock(db)
        if not row['description']:return False
        payload=json.loads(row['payload'])
        if payload['kind']=='color':
            current=c.execute("SELECT * FROM settings WHERE key='default_color'").fetchone()
            if not current or dict(current)!=payload['after']:raise ValueError(tr('La couleur 3D a changé depuis cette action ; annulation impossible.'))
            c.execute("DELETE FROM settings WHERE key='default_color'")
            if payload['before']:c.execute('INSERT INTO settings VALUES(?,?)',tuple(payload['before'][k] for k in ('key','value')))
        elif payload['kind']=='storage':
            after=payload['after'];before=payload['before']
            if storage_state(c,after['ids'])!=after or item_identities(c,[r['id'] for r in payload['items']])!=payload['items']:
                raise ValueError(tr('Le rangement a changé depuis cette action ; annulation impossible.'))
            for drawer in before['drawers']:
                c.execute('UPDATE storage_drawers SET name=? WHERE id=?',(drawer['name'],drawer['id']))
            for identity in before['ids']:c.execute('DELETE FROM storage_contents WHERE drawer_id=?',(identity,))
            c.executemany('INSERT INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',[(r['drawer_id'],r['item_id'],r['color']) for r in before['links']])
        elif payload['kind']=='visual':
            identity=payload['after']['item_id'];current=c.execute('SELECT * FROM visual WHERE item_id=?',(identity,)).fetchone()
            if not current or dict(current)!=payload['after'] or item_identities(c,[identity])!=payload['item']:
                raise ValueError(tr('Le visuel de cette référence a changé depuis cette action ; annulation impossible.'))
            c.execute('DELETE FROM visual WHERE item_id=?',(identity,))
            if payload['before']:
                fields=list(payload['before']);c.execute('INSERT INTO visual('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',[payload['before'][key] for key in fields])
        else:raise ValueError(tr('Action inconnue'))
        record(c,'',{})
    return True
