"""Physical counts per drawer, separate from possession and project reservations."""
from .i18n import tr


ALLOCATED = 'COALESCE((SELECT SUM(p.quantity) FROM storage_contents p WHERE p.item_id=s.item_id AND p.color=s.color),0)'


def integer(value):
    if type(value) is not int or not 0 <= value <= 1000000000:
        raise ValueError(tr('Quantité entière positive ou nulle requise.'))
    return value


def validate(c):
    bad = c.execute('''SELECT p.item_id,p.color FROM storage_contents p
        LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
        GROUP BY p.item_id,p.color
        HAVING SUM(COALESCE(p.quantity,0))>COALESCE(MAX(s.quantity),0)
        OR MIN(COALESCE(p.quantity,0))<0 LIMIT 1''').fetchone()
    if bad:
        raise ValueError(tr('La quantité répartie dans les tiroirs dépasse le stock en vrac. Réduis d’abord la répartition concernée.'))


def available(c, item_id, color):
    row = c.execute('SELECT s.quantity-' + ALLOCATED + ' AS remaining FROM stock s WHERE s.item_id=? AND s.color=?', (item_id, str(color))).fetchone()
    return int(row['remaining']) if row else 0


def set_quantity(db, drawer_id, item_id, color, quantity, target_color=None):
    from .action_undo import storage_change
    integer(quantity)
    color = str(color or '')
    target_color = color if target_color is None else str(target_color)
    with db.connect() as c, storage_change(c, [drawer_id], tr('Quantité dans un tiroir')):
        old = c.execute('SELECT * FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?', (drawer_id, item_id, color)).fetchone()
        if not old:
            raise ValueError(tr('Cette référence n’est plus dans le tiroir.'))
        if target_color != color:
            if color or old['quantity'] not in (None, 0):
                raise ValueError(tr('Choisis la couleur uniquement pour une association sans quantité renseignée.'))
            c.execute('DELETE FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?', (drawer_id, item_id, color))
        c.execute('''INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)
            ON CONFLICT(drawer_id,item_id,color) DO UPDATE SET quantity=excluded.quantity''', (drawer_id, item_id, target_color, quantity))
        validate(c)
    return True


def transfer(db, source_drawer, target_drawer, item_id, color, quantity):
    from .action_undo import storage_change
    integer(quantity)
    if quantity == 0 or source_drawer == target_drawer:
        return False
    color = str(color or '')
    with db.connect() as c, storage_change(c, [source_drawer, target_drawer], tr('Transfert d’une quantité entre tiroirs')):
        source = c.execute('SELECT * FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?', (source_drawer, item_id, color)).fetchone()
        if not source or source['quantity'] is None or quantity > source['quantity']:
            raise ValueError(tr('La quantité à transférer n’est plus disponible dans ce tiroir.'))
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?', (target_drawer,)).fetchone():
            raise ValueError(tr('Tiroir introuvable.'))
        c.execute('UPDATE storage_contents SET quantity=quantity-? WHERE drawer_id=? AND item_id=? AND color=?', (quantity, source_drawer, item_id, color))
        c.execute('''INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)
            ON CONFLICT(drawer_id,item_id,color) DO UPDATE SET quantity=COALESCE(storage_contents.quantity,0)+excluded.quantity''', (target_drawer, item_id, color, quantity))
        validate(c)
    return True


def place_remaining(db, drawer_id, entries):
    """Allocate the loose quantity still unplaced, using the current transaction."""
    from .action_undo import storage_change
    entries = list(dict.fromkeys((identity, str(color or '')) for identity, color in entries))
    with db.connect() as c, storage_change(c, [drawer_id], tr('Répartition du stock restant dans un tiroir')):
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?', (drawer_id,)).fetchone():
            raise ValueError(tr('Tiroir introuvable.'))
        for identity,color in entries:
            if not c.execute("SELECT 1 FROM stock s JOIN items i ON i.id=s.item_id WHERE s.item_id=? AND s.color=? AND s.quantity>0 AND i.kind IN ('part','minifig')",(identity,color)).fetchone():
                raise ValueError(tr('Cette référence n’est plus dans le stock en vrac.'))
        changed = 0
        for identity, color in entries:
            remaining = available(c, identity, color)
            if remaining <= 0:
                continue
            c.execute('''INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)
                ON CONFLICT(drawer_id,item_id,color) DO UPDATE SET quantity=COALESCE(storage_contents.quantity,0)+excluded.quantity''', (drawer_id, identity, color, remaining))
            changed += remaining
        validate(c)
    return changed
