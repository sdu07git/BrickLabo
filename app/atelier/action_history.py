"""Persistent, transactional undo/redo for user data, with conflict checks."""
from contextlib import contextmanager
import json
import logging

from .i18n import tr,ENGLISH

CANONICAL = {translated: source for source, translated in ENGLISH.items()}


# Parents precede children; restores never delete an unchanged child by cascade.
TABLES = {
    'settings': ('key',), 'visual': ('item_id',), 'stock': ('id',),
    'stock_sets': ('id',), 'stock_set_components': ('set_entry_id', 'item_id', 'color'),
    'queue': ('id',), 'stock_import_jobs': ('id',),
    'stock_import_applied': ('job_id', 'ordinal'),
    'storage_walls': ('id',), 'storage_drawers': ('id',),
    'storage_contents': ('drawer_id', 'item_id', 'color'),
    'construction_projects': ('id',),
    'project_parts': ('project_id', 'item_id', 'color'),
    'project_color_reservations': ('project_id','item_id','color','stock_color'),
    'purchase_lots': ('id',),
    'purchase_lot_entries': ('lot_id','scope','item_id','color'),
    'project_pick_rows': ('project_id','item_id','color','drawer_id'),
    'project_color_pick_rows': ('project_id','item_id','color','stock_color','drawer_id'),
    'project_unlocated_picks': ('project_id','item_id','color','stock_color'),
}
ORDER = {table: index for index, table in enumerate(TABLES)}


def limit(c):
    row = c.execute("SELECT value FROM settings WHERE key='undo_limit'").fetchone()
    try:
        value = json.loads(row['value']) if row else 100
        return max(1, min(500, value)) if type(value) is int else 100
    except (ValueError, TypeError):
        return 100


def prepare(c):
    c.execute('''CREATE TABLE IF NOT EXISTS action_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,description TEXT NOT NULL,
        payload TEXT NOT NULL,applied INTEGER NOT NULL DEFAULT 1,
        created TEXT NOT NULL DEFAULT (datetime('now','localtime')))''')
    for operation in ('insert', 'update', 'delete'):
        c.execute('DROP TRIGGER IF EXISTS reset_action_undo_' + operation)
    if c.execute("SELECT 1 FROM settings WHERE key='action_history_v57'").fetchone():
        return
    old = c.execute('SELECT * FROM action_undo WHERE id=1').fetchone()
    stock = c.execute('SELECT * FROM stock_undo WHERE id=1').fetchone()
    try:
        if old is not None:
            if old['description']:
                record_payload(c, old['description'], json.loads(old['payload']))
        elif stock is not None:
            record_changes(c, stock['description'], json.loads(stock['changes']))
        c.execute("UPDATE action_history SET created=''")
    except (ValueError, TypeError, KeyError):
        logging.getLogger(__name__).warning('Ancienne action incompatible avec le journal v57')
    c.execute("INSERT INTO settings VALUES('action_history_v57','true')")


def snapshot(c, tables):
    return {table: {tuple(row[key] for key in TABLES[table]): dict(row)
                    for row in c.execute('SELECT * FROM ' + table)} for table in tables}


def differences(before, after):
    changes = []
    for table in before:
        for key in sorted(before[table].keys() | after[table].keys(), key=repr):
            old, new = before[table].get(key), after[table].get(key)
            if old != new:
                changes.append({'table': table, 'key': list(key), 'before': old, 'after': new})
    return changes


def identities(c, changes):
    ids = {row[key] for change in changes for row in (change['before'], change['after'])
           if row for key in ('item_id', 'set_id') if row.get(key) is not None}
    result = []
    ordered = sorted(ids)
    for start in range(0, len(ordered), 800):
        chunk = ordered[start:start + 800]
        result.extend(dict(row) for row in c.execute(
            'SELECT id,source,kind,ref FROM items WHERE id IN (' + ','.join('?' for _ in chunk) + ') ORDER BY id', chunk))
    if len(result) != len(ids):
        raise ValueError(tr('Une référence de cette action n’existe plus.'))
    return sorted(result, key=lambda row: row['id'])


def record_changes(c, description, changes):
    changes = [change for change in changes if change['before'] != change['after']]
    if not changes:
        return False
    for change in changes:
        if change['table'] not in TABLES or len(change['key']) != len(TABLES[change['table']]):
            raise ValueError(tr('Action inconnue'))
    payload = {'version': 1, 'changes': changes, 'items': identities(c, changes)}
    c.execute('DELETE FROM action_history WHERE applied=0')
    c.execute('INSERT INTO action_history(description,payload) VALUES(?,?)',
              (CANONICAL.get(description,description), json.dumps(payload, ensure_ascii=False)))
    c.execute('DELETE FROM action_history WHERE id NOT IN (SELECT id FROM action_history ORDER BY id DESC LIMIT ?)', (limit(c),))
    return True


def record_payload(c, description, payload):
    kind = payload['kind']
    if kind == 'storage':
        states = []
        for name in ('before', 'after'):
            state = payload[name]
            links = [dict(row, quantity=row.get('quantity')) for row in state['links']]
            states.append({
                'storage_drawers': {(row['id'],): row for row in state['drawers']},
                'storage_contents': {(row['drawer_id'], row['item_id'], row['color']): row for row in links}})
        changes = differences(*states)
    elif kind in ('color', 'visual'):
        table = 'settings' if kind == 'color' else 'visual'
        row = payload['after'] or payload['before']
        changes = [{'table': table, 'key': [row[key] for key in TABLES[table]],
                    'before': payload['before'], 'after': payload['after']}]
    else:
        raise ValueError(tr('Action inconnue'))
    return record_changes(c, description, changes)


@contextmanager
def change(c, tables, description):
    if not c.in_transaction:
        c.execute('BEGIN IMMEDIATE')
    before = snapshot(c, tables)
    yield
    validate(c)
    record_changes(c, description, differences(before, snapshot(c, tables)))


def validate(c):
    from .storage_quantities import validate as validate_quantities
    from .projects import validate as validate_projects
    validate_quantities(c)
    validate_projects(c)
    from .collection_workflows import validate_picks
    validate_picks(c)


def description(db, redo=False):
    rows = db.rows('SELECT description FROM action_history WHERE applied=? ORDER BY id ' + ('ASC' if redo else 'DESC') + ' LIMIT 1', (0 if redo else 1,))
    return tr(rows[0]['description']) if rows else ''


def rows(db):
    return db.rows('SELECT id,description,created,applied FROM action_history ORDER BY id DESC')


def set_limit(db, value):
    if type(value) is not int or not 1 <= value <= 500:
        raise ValueError(tr('Nombre d’actions invalide.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("INSERT OR REPLACE INTO settings VALUES('undo_limit',?)", (json.dumps(value),))
        excess=max(0,c.execute('SELECT COUNT(*) FROM action_history').fetchone()[0]-value)
        c.execute('DELETE FROM action_history WHERE id IN (SELECT id FROM action_history WHERE applied=1 ORDER BY id ASC LIMIT ?)',(excess,))
        excess=max(0,c.execute('SELECT COUNT(*) FROM action_history').fetchone()[0]-value)
        c.execute('DELETE FROM action_history WHERE id IN (SELECT id FROM action_history WHERE applied=0 ORDER BY id DESC LIMIT ?)',(excess,))


def clear(c):
    c.execute('DELETE FROM action_history')
    c.execute('DELETE FROM action_undo')
    c.execute('DELETE FROM stock_undo')


def restore(db, redo=False):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        action = c.execute('SELECT * FROM action_history WHERE applied=? ORDER BY id ' + ('ASC' if redo else 'DESC') + ' LIMIT 1', (0 if redo else 1,)).fetchone()
        if not action:
            return False
        payload = json.loads(action['payload'])
        if payload.get('version') != 1:
            raise ValueError(tr('Format d’action inconnu.'))
        changes = payload['changes']
        for change in changes:
            if change['table']=='construction_projects':
                for state in ('before','after'):
                    if change[state] is not None:
                        change[state].setdefault('ignore_colors',0)
                        change[state].setdefault('include_set_stock',0)
        source, target = ('before', 'after') if redo else ('after', 'before')
        if identities(c, changes) != payload['items']:
            raise ValueError(tr('Les références ont changé ; cette action ne peut pas être restaurée.'))
        for change in changes:
            table = change['table']
            if table not in TABLES or len(change['key']) != len(TABLES[table]):
                raise ValueError(tr('Action inconnue'))
            row = c.execute('SELECT * FROM ' + table + ' WHERE ' + ' AND '.join(key + '=?' for key in TABLES[table]), change['key']).fetchone()
            if (dict(row) if row else None) != change[source]:
                raise ValueError(tr('Les données ont changé depuis cette action ; restauration impossible.'))
            fields = {row['name'] for row in c.execute('PRAGMA table_info(' + table + ')')}
            if change[target] and set(change[target]) != fields:
                raise ValueError(tr('Format d’action incompatible avec les données actuelles.'))
        children = {'construction_projects': ('project_parts','project_id'),
                    'stock_sets': ('stock_set_components','set_entry_id'),
                    'storage_walls': ('storage_drawers','wall_id'),
                    'storage_drawers': ('storage_contents','drawer_id')}
        changed_settings = {tuple(change['key']) for change in changes if change['table']=='settings'}
        for change in changes:
            if change[target] is not None or change[source] is None:
                continue
            table = change['table']
            if table in children:
                child, foreign_key = children[table]
                actual = [dict(row) for row in c.execute('SELECT * FROM ' + child + ' WHERE ' + foreign_key + '=?',change['key'])]
                expected = [row[source] for row in changes if row['table']==child and row[source] and row[source].get(foreign_key)==change['key'][0]]
                keyed=lambda rows:{tuple(row[key] for key in TABLES[child]):row for row in rows}
                if keyed(actual)!=keyed(expected):
                    raise ValueError(tr('Les données liées ont changé ; cette action ne peut pas être restaurée.'))
            if table in ('stock','stock_sets','queue'):
                key = 'label_layout_' + table + '_' + str(change['key'][0])
                if (key,) not in changed_settings and c.execute('SELECT 1 FROM settings WHERE key=?',(key,)).fetchone():
                    raise ValueError(tr('La disposition d’une étiquette a changé depuis cette action.'))
        # Remove children first, and update surviving parents without cascading.
        for change in sorted(changes, key=lambda row: ORDER[row['table']], reverse=True):
            if change[target] is None:
                c.execute('DELETE FROM ' + change['table'] + ' WHERE ' + ' AND '.join(key + '=?' for key in TABLES[change['table']]), change['key'])
        for change in sorted(changes, key=lambda row: ORDER[row['table']]):
            row, table = change[target], change['table']
            if row is None:
                continue
            fields = list(row)
            if change[source] is None:
                c.execute('INSERT INTO ' + table + '(' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in fields) + ')', [row[key] for key in fields])
            else:
                updates = [key for key in fields if key not in TABLES[table]]
                if updates:
                    c.execute('UPDATE ' + table + ' SET ' + ','.join(key + '=?' for key in updates) + ' WHERE ' + ' AND '.join(key + '=?' for key in TABLES[table]), [row[key] for key in updates] + change['key'])
        validate(c)
        c.execute('UPDATE action_history SET applied=? WHERE id=?', (1 if redo else 0, action['id']))
        c.execute('DELETE FROM action_undo')
        if any(change['table'] in ('stock','stock_sets','stock_set_components','queue','stock_import_applied') for change in changes):
            c.execute('DELETE FROM stock_undo')
    return True
