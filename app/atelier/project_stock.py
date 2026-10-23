"""Owned-set availability, excluding other projects' exclusive set assignments.

Components remain in their ownership ledger. Drawer picking uses loose stock;
set_allocations handles the separate, exclusive claims on owned set copies.
"""
from collections import Counter

from .i18n import tr


def prepare(c):
    fields = {row['name'] for row in c.execute('PRAGMA table_info(construction_projects)')}
    if 'include_set_stock' not in fields:
        c.execute('ALTER TABLE construction_projects ADD COLUMN include_set_stock INTEGER NOT NULL DEFAULT 0 CHECK(include_set_stock IN (0,1))')


def owned_sets(c, include_allocated=False):
    """Use actual tracked quantities, including zeroes, before catalogue fallback.

    Tracked components already include the number of owned copies. Re-expanding
    their catalogue inventory would hide missing parts or count copies twice.
    """
    counts = Counter()
    for row in c.execute('''SELECT p.item_id,p.color,SUM(p.quantity) AS quantity
        FROM stock_set_components p JOIN stock_sets s ON s.id=p.set_entry_id
        JOIN items i ON i.id=p.item_id WHERE s.quantity>0 AND i.kind IN ('part','minifig')
        GROUP BY p.item_id,p.color'''):
        counts[(row['item_id'], str(row['color']))] += max(0, int(row['quantity']))

    legacy = c.execute('''SELECT i.source,i.ref,s.quantity FROM stock_sets s
        JOIN items i ON i.id=s.item_id WHERE s.quantity>0 AND NOT EXISTS
        (SELECT 1 FROM stock_set_components p WHERE p.set_entry_id=s.id)''').fetchall()
    warnings = []
    if legacy:
        from .build_stock import InventoryReader
        reader = InventoryReader(c)
        identities = {}

        def expand(source, ref, trail=()):
            key = source, ref
            if key in trail:
                return Counter(), False
            children, complete = reader.children(source, 'set', ref)
            result = Counter()
            for src, kind, num, color, quantity, spare in children:
                if quantity <= 0:
                    continue
                if kind == 'set':
                    nested, ok = expand(src, num, trail + (key,))
                    complete = complete and ok
                    result.update({identity: value * quantity for identity, value in nested.items()})
                elif kind in ('part', 'minifig'):
                    identity = src, kind, num
                    if identity not in identities:
                        row = c.execute('SELECT id FROM items WHERE source=? AND kind=? AND ref=?', identity).fetchone()
                        identities[identity] = row['id'] if row else None
                    if identities[identity] is None:
                        complete = False
                    else:
                        result[(identities[identity], str(color))] += quantity
                else:
                    complete = False
            return result, complete and bool(result)

        for row in legacy:
            inventory, complete = expand(row['source'], row['ref'])
            if complete:
                counts.update({key: value * int(row['quantity']) for key, value in inventory.items()})
                warnings.append(tr('Inventaire du catalogue utilisé pour un set sans suivi de pièces : ') + row['ref'])
            else:
                warnings.append(tr('Inventaire de set indisponible ou incomplet : ') + row['ref'])
    if not include_allocated:
        from .set_allocations import allocated_counts
        for key,quantity in allocated_counts(c).items():counts[key]=max(0,counts[key]-quantity)
    return counts, sorted(set(warnings))


def decorate(rows, counts, ignore_colors=False):
    """Allocate set availability once, after loose stock and own reservations."""
    pools = Counter()
    for (identity, color), quantity in counts.items():
        pools[(identity, '*' if ignore_colors else color)] += quantity
    remaining = pools.copy()
    for row in rows:
        key = row['id'], '*' if ignore_colors else row['chosen_color']
        take = min(row['missing'], remaining[key])
        remaining[key] -= take
        row.update(set_quantity=take, owned_set_quantity=pools[key], missing=row['missing'] - take)
    return rows
