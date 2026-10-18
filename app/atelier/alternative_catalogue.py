"""Alternative catalogue copies retain their explicit origin and visual choices."""
import json
from collections import Counter
from .i18n import tr

FIELDS = ('name', 'category', 'category_id', 'image', 'year', 'quantity', 'alternate', 'weight', 'dimensions')
ITEM_SETTINGS = ('camera_item_', 'label_layout_item_', 'architect_model_', 'architect_photo_choice_', 'photo_choices_')


def original(item):
    """Use the original source namespace while keeping personal identity/settings."""
    if item and item['source'] == 'ALT' and item.get('origin_source') and item.get('origin_ref'):
        return dict(item, source=item['origin_source'], ref=item['origin_ref'])
    return item


def _copy_visuals(c, source, target):
    c.execute('INSERT OR IGNORE INTO visual(item_id,mode,color,image,links) SELECT ?,mode,color,image,links FROM visual WHERE item_id=?', (target, source))
    for prefix in ITEM_SETTINGS:
        c.execute('INSERT OR IGNORE INTO settings(key,value) SELECT ?,value FROM settings WHERE key=?', (prefix + str(target), prefix + str(source)))


def prepare(c):
    columns = {r['name'] for r in c.execute('PRAGMA table_info(items)')}
    for name in ('origin_source', 'origin_ref', 'comment'):
        if name not in columns:
            c.execute('ALTER TABLE items ADD COLUMN ' + name + " TEXT NOT NULL DEFAULT ''")
    if c.execute("SELECT 1 FROM settings WHERE key='alternative_origins_v61'").fetchone():
        return
    # Only the old application's exact copy convention establishes lineage.
    for row in list(c.execute("SELECT a.id AS target,n.* FROM items a JOIN items n ON a.ref=n.source||'-'||n.ref AND a.kind=n.kind AND a.name=n.name WHERE a.source='ALT' AND a.origin_source='' AND n.source IN ('RB','BL','BA')")):
        c.execute('UPDATE items SET origin_source=?,origin_ref=? WHERE id=?', (row['source'], row['ref'], row['target']))
        for field in FIELDS:
            if field in columns:
                c.execute('UPDATE items SET ' + field + '=? WHERE id=? AND (' + field + " IS NULL OR " + field + "='' OR " + field + '=0)', (row[field], row['target']))
        _copy_visuals(c, row['id'], row['target'])
    c.execute("INSERT INTO settings VALUES('alternative_origins_v61','true')")


def copy_items(db, items, include_parts=False, comment=None):
    from .data import normalize
    from .build_stock import InventoryReader
    selected = [db.get_item(item['id']) for item in items]
    if not selected or any(item is None for item in selected):
        raise ValueError(tr('Référence introuvable'))
    if include_parts and any(item['kind'] != 'set' for item in selected):
        raise ValueError(tr('Sélectionne uniquement des sets.'))
    inventories = {}
    figures = {}
    for item in selected:
        if item['kind'] == 'set':
            parts = db.components(item, strict=include_parts)
            if include_parts and not parts:
                raise ValueError(tr('Inventaire indisponible pour ') + item['ref'])
            for part in parts:
                if part['kind'] not in ('part', 'minifig') or type(part.get('chosen_quantity', 1)) is not int or part.get('chosen_quantity', 1) < 1:
                    raise ValueError(tr('Inventaire incomplet : ') + item['ref'])
            inventories[item['id']] = parts
    if include_parts:
        with db.read() as c:
            c.execute('BEGIN')
            reader = InventoryReader(c)
            for item in [p for parts in inventories.values() for p in parts if p['kind'] == 'minifig']:
                children, complete = reader.children(item['source'], 'minifig', item['ref'])
                parts = []
                for source, kind, ref, color, quantity, spare in children:
                    row = c.execute('SELECT * FROM items WHERE source=? AND kind=? AND ref=?', (source, kind, ref)).fetchone()
                    if row is None or kind != 'part' or quantity < 1:
                        complete = False
                        break
                    parts.append(dict(row, chosen_color=color, chosen_quantity=quantity, is_spare=int(spare)))
                if complete and parts:
                    figures[item['id']] = parts
    comment = str(comment or '').strip()
    copied = {}
    part_ids = set()
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')

        def copy_one(item):
            if item['id'] in copied:
                return copied[item['id']]
            if item['source'] == 'ALT':
                target = item['id']
                c.execute('UPDATE items SET catalogue_hidden=0 WHERE id=?', (target,))
            else:
                ref = item['source'] + '-' + item['ref']
                names = ('source', 'kind', 'ref') + FIELDS + ('search', 'origin_source', 'origin_ref', 'comment')
                values = ('ALT', item['kind'], ref) + tuple(item.get(field, '') for field in FIELDS) + (normalize(ref + ' ' + item['name'] + ' ' + comment), item['source'], item['ref'], comment)
                c.execute('INSERT INTO items(' + ','.join(names) + ') VALUES(' + ','.join('?' for _ in names) + ') ON CONFLICT(source,kind,ref) DO UPDATE SET catalogue_hidden=0', values)
                row = c.execute("SELECT * FROM items WHERE source='ALT' AND kind=? AND ref=?", (item['kind'], ref)).fetchone()
                if row['origin_source'] and (row['origin_source'], row['origin_ref']) != (item['source'], item['ref']) or not row['origin_source'] and row['name'] != item['name']:
                    raise ValueError(tr('Cette référence alternative existe déjà avec une autre origine : ') + ref)
                target = row['id']
                c.execute('UPDATE items SET origin_source=?,origin_ref=? WHERE id=?', (item['source'], item['ref'], target))
                _copy_visuals(c, item['id'], target)
            if comment:
                row = c.execute('SELECT ref,name FROM items WHERE id=?', (target,)).fetchone()
                c.execute('UPDATE items SET comment=?,search=? WHERE id=?', (comment, normalize(row['ref'] + ' ' + row['name'] + ' ' + comment), target))
            copied[item['id']] = target
            if include_parts and item['kind'] in ('part', 'minifig'):
                part_ids.add(target)
            if item['id'] in figures and not c.execute('SELECT 1 FROM settings WHERE key=?', ('alt_components_' + str(target),)).fetchone():
                save_inventory(target, figures[item['id']], True)
            return target

        def save_inventory(target, parts, clone):
            totals = Counter()
            for part in parts:
                identity = copy_one(part) if clone else part['id']
                totals[(identity, str(part.get('chosen_color', '')), int(bool(part.get('is_spare', 0))))] += part.get('chosen_quantity', 1)
            values = [{'item_id': identity, 'color': color, 'quantity': quantity, 'is_spare': spare} for (identity, color, spare), quantity in totals.items()]
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('alt_components_' + str(target), json.dumps(values)))

        targets = []
        for item in selected:
            target = copy_one(item)
            targets.append(target)
            parts = inventories.get(item['id'], [])
            if parts and (include_parts or not c.execute('SELECT 1 FROM settings WHERE key=?', ('alt_components_' + str(target),)).fetchone()):
                save_inventory(target, parts, include_parts)
    return {'target_ids': targets, 'part_count': len(part_ids)}
