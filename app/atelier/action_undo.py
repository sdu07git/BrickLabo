"""Colour and drawer transactions recorded in the shared undo/redo history."""
from contextlib import contextmanager
import json

from .i18n import tr


def prepare(c):
    c.execute('CREATE TABLE IF NOT EXISTS action_undo(id INTEGER PRIMARY KEY CHECK(id=1),description TEXT NOT NULL,payload TEXT NOT NULL)')
    from .action_history import prepare as prepare_history
    prepare_history(c)


def record(c,description,payload):
    c.execute('INSERT OR REPLACE INTO action_undo VALUES(1,?,?)',(description,json.dumps(payload,ensure_ascii=False)))
    from .action_history import record_payload
    record_payload(c,description,payload)


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
        from .action_history import validate
        validate(c)
        identities={row['item_id'] for row in before['links']+after['links']}
        record(c,description,{'kind':'storage','before':before,'after':after,'items':item_identities(c,identities)})


def description(db):
    from .action_history import description as history_description
    return history_description(db)


def undo(db):
    from .action_history import restore
    return restore(db)
