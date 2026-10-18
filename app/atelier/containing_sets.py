"""Reverse local inventories through minifigures and nested sets, without network."""
from collections import defaultdict


def find(db, item, color=None):
    source = item['source']
    if source not in ('RB', 'BL', 'ALT') or item['kind'] not in ('part', 'minifig'):
        return []
    color=None if color in (None,'') else str(color)
    pending = {(item['kind'], item['ref'])}
    seen = set()
    found = set()
    with db.read() as c:
        c.execute('BEGIN')
        # Reuse the same precedence as the forward inventory readers.
        latest = """v.id=(SELECT x.id FROM inventories x WHERE x.set_num=v.set_num
            ORDER BY x.version DESC,x.id DESC LIMIT 1)
            AND NOT EXISTS(SELECT 1 FROM catalogue_inventory ci WHERE ci.source='RB' AND ci.ref=v.set_num)"""
        parent_kind = """CASE WHEN EXISTS(SELECT 1 FROM items i WHERE i.source='RB'
            AND i.kind='minifig' AND i.ref=v.set_num) OR EXISTS(SELECT 1 FROM inventory_minifigs f
            WHERE f.fig_num=v.set_num) THEN 'minifig' ELSE 'set' END"""
        while pending:
            current = pending - seen
            if not current:
                break
            seen.update(current)
            parents = set()
            grouped = defaultdict(list)
            for kind, ref in current:
                grouped[kind].append(ref)
            for kind, refs in grouped.items():
                for offset in range(0, len(refs), 400):
                    chunk = refs[offset:offset + 400]
                    marks = ','.join('?' for _ in chunk)
                    exact=color is not None and kind==item['kind'] and item['ref'] in chunk
                    color_args=[color] if exact else []
                    if source=='ALT':
                        parents.update((r['kind'],r['ref']) for r in c.execute("""
                            SELECT DISTINCT parent.kind,parent.ref FROM items parent JOIN settings s
                            ON s.key='alt_components_'||parent.id JOIN json_each(CASE WHEN json_valid(s.value) THEN s.value ELSE '[]' END) p
                            JOIN items child ON child.id=json_extract(p.value,'$.item_id')
                            WHERE parent.source='ALT' AND child.source='ALT' AND child.kind=? AND child.ref IN ("""+marks+") AND json_extract(p.value,'$.quantity')>0"+
                            (" AND CAST(json_extract(p.value,'$.color') AS TEXT)=?" if exact else ''),[kind]+chunk+color_args))
                        continue
                    if source == 'RB':
                        table, column = {'part': ('inventory_parts', 'part_num'),
                                         'minifig': ('inventory_minifigs', 'fig_num'),
                                         'set': ('inventory_sets', 'set_num')}[kind]
                        parents.update((r['kind'], r['ref']) for r in c.execute(
                            'SELECT DISTINCT ' + parent_kind + ' AS kind,v.set_num AS ref FROM ' + table +
                            ' p JOIN inventories v ON v.id=p.inventory_id WHERE p.' + column +
                            ' IN (' + marks + ') AND p.quantity>0 AND ' + latest+(' AND CAST(p.color_id AS TEXT)=?' if exact and kind=='part' else ''), chunk+(color_args if kind=='part' else [])))
                    # Cached inventories loaded by batches already contain minifig parts.
                    parents.update(('set', r['ref']) for r in c.execute("""
                        SELECT ci.ref FROM catalogue_inventory ci
                        WHERE ci.source=? AND NOT EXISTS(SELECT 1 FROM items i JOIN settings s
                            ON s.key='bl_manual_inventory_'||i.id WHERE i.source='BL'
                            AND i.kind='set' AND i.ref=ci.ref AND ci.source='BL')
                        AND EXISTS(SELECT 1 FROM json_each(CASE WHEN json_valid(ci.parts)
                            THEN ci.parts ELSE '[]' END) p WHERE json_extract(p.value,'$.source')=?
                            AND COALESCE(json_extract(p.value,'$.kind'),'part')=?
                            AND json_extract(p.value,'$.ref') IN (""" + marks + ") AND json_extract(p.value,'$.quantity')>0"+(" AND CAST(json_extract(p.value,'$.color') AS TEXT)=?" if exact else '')+")", [source, source, kind] + chunk+color_args))
                    # Legacy API caches store complete item dictionaries in settings.
                    prefixes = [('rb_minifig_components_', 'minifig')] if source == 'RB' else [('bl_minifig_components_', 'minifig'), ('bl_components_', 'set')]
                    for prefix, parent_type in prefixes:
                        parents.update((parent_type, r['ref']) for r in c.execute("""
                            SELECT substr(s.key,?) AS ref FROM settings s WHERE s.key GLOB ?
                            AND NOT EXISTS(SELECT 1 FROM catalogue_inventory ci WHERE ci.source=? AND ci.ref=substr(s.key,?))
                            AND NOT (?='RB' AND EXISTS(SELECT 1 FROM inventories v WHERE v.set_num=substr(s.key,?)))
                            AND NOT EXISTS(SELECT 1 FROM items i JOIN settings m ON m.key='bl_manual_inventory_'||i.id
                                WHERE i.source='BL' AND i.kind='set' AND i.ref=substr(s.key,?) AND ?='set')
                            AND EXISTS(SELECT 1 FROM json_each(CASE WHEN json_valid(s.value)
                                THEN s.value ELSE '[]' END) p WHERE json_extract(p.value,'$.source')=?
                                AND COALESCE(json_extract(p.value,'$.kind'),'part')=?
                                AND json_extract(p.value,'$.ref') IN (""" + marks + ") AND json_extract(p.value,'$.chosen_quantity')>0"+(" AND CAST(json_extract(p.value,'$.chosen_color') AS TEXT)=?" if exact else '')+")",
                            [len(prefix) + 1, prefix + '*', source, len(prefix) + 1, source, len(prefix) + 1,
                             len(prefix) + 1, parent_type, source, kind] + chunk+color_args))
                    if source == 'BL':
                        parents.update(('set', r['ref']) for r in c.execute("""
                            SELECT DISTINCT parent.ref FROM bl_manual_inventory p JOIN items child ON child.id=p.item_id
                            JOIN items parent ON parent.id=p.set_id WHERE child.source='BL' AND child.kind=?
                            AND child.ref IN (""" + marks + ") AND p.quantity>0 AND p.alternate=0 AND p.counterpart=0"+(" AND CAST(p.color AS TEXT)=?" if exact else ''), [kind] + chunk+color_args))
            found.update(ref for kind, ref in parents if kind == 'set')
            pending = parents - seen
        result = []
        refs = sorted(found)
        for offset in range(0, len(refs), 400):
            chunk = refs[offset:offset + 400]
            result.extend(dict(r) for r in c.execute("SELECT * FROM items WHERE source=? AND kind='set' AND ref IN (" + ','.join('?' for _ in chunk) + ')', [source] + chunk))
    return sorted(result, key=lambda r: r['ref'])


def matching(db, criteria):
    """Intersection: every chosen reference/colour must occur in the same set."""
    result = None
    for item, color in criteria:
        matches = {row['id']: row for row in db.containing_sets(item, color)}
        result = matches if result is None else {key: row for key, row in result.items() if key in matches}
        if not result:
            break
    return sorted((result or {}).values(), key=lambda row: (row['source'], row['ref']))
