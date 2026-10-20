"""Physical counts per drawer, separate from possession and project reservations."""
from .i18n import tr


ALLOCATED = '(COALESCE((SELECT SUM(p.quantity) FROM storage_contents p WHERE p.item_id=s.item_id AND p.color=s.color),0)+COALESCE((SELECT SUM(p.quantity) FROM project_pick_rows p WHERE p.item_id=s.item_id AND p.color=s.color),0))'


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


def put_entry(db,drawer_id,item_id,color,quantity=None,previous=None):
    """Replace a captured drawer row atomically, without changing possession."""
    from .action_undo import storage_change
    if quantity is not None:integer(quantity)
    color=str(color or '')
    with db.connect() as c,storage_change(c,[drawer_id],tr('Modification du contenu d’un tiroir')):
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?',(drawer_id,)).fetchone():raise ValueError(tr('Tiroir introuvable.'))
        if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig')",(item_id,)).fetchone():raise ValueError(tr('Référence introuvable'))
        target=c.execute('SELECT 1 FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer_id,item_id,color)).fetchone()
        if previous is not None:
            old_id=previous['id'];old_color=str(previous.get('chosen_color') or '')
            current=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer_id,old_id,old_color)).fetchone()
            if current is None or current['quantity']!=previous.get('stored_quantity'):raise ValueError(tr('Cette ligne a changé. Actualise l’inventaire du tiroir.'))
            if (old_id,old_color)!=(item_id,color) and target:raise ValueError(tr('Cette référence et cette couleur sont déjà dans le tiroir.'))
            c.execute('UPDATE storage_contents SET item_id=?,color=?,quantity=? WHERE drawer_id=? AND item_id=? AND color=?',(item_id,color,quantity,drawer_id,old_id,old_color))
        else:
            if target:raise ValueError(tr('Cette référence et cette couleur sont déjà dans le tiroir.'))
            c.execute('INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)',(drawer_id,item_id,color,quantity))
        validate(c)
    return True


def available(c, item_id, color):
    row = c.execute('SELECT s.quantity-' + ALLOCATED + ' AS remaining FROM stock s WHERE s.item_id=? AND s.color=?', (item_id, str(color))).fetchone()
    return int(row['remaining']) if row else 0


def follow_stock_additions(c, previous):
    """A single fully counted location follows additions; split counts stay put."""
    old={(row['item_id'],str(row['color'])):int(row['quantity']) for row in previous.values()}
    for row in c.execute('SELECT item_id,color,quantity FROM stock WHERE quantity>0'):
        before=old.get((row['item_id'],str(row['color'])),0)
        if row['quantity']<=before:continue
        locations=c.execute('SELECT drawer_id,quantity FROM storage_contents WHERE item_id=? AND color=?',(row['item_id'],row['color'])).fetchall()
        picked=c.execute('SELECT COALESCE(SUM(quantity),0) FROM project_pick_rows WHERE item_id=? AND color=?',(row['item_id'],row['color'])).fetchone()[0]
        if len(locations)==1 and locations[0]['quantity']==before-picked:
            c.execute('UPDATE storage_contents SET quantity=? WHERE drawer_id=? AND item_id=? AND color=?',(row['quantity']-picked,locations[0]['drawer_id'],row['item_id'],row['color']))


def transfer_entries(db, source_drawer, target_drawer, entries):
    """Move chosen counts atomically, checking the quantities shown by the dialog."""
    from .action_undo import storage_change
    entries=list(entries)
    if not entries or source_drawer==target_drawer:return False
    if len({(identity,str(color or '')) for identity,color,amount,expected in entries})!=len(entries):
        raise ValueError(tr('Cette référence et cette couleur sont déjà dans le tiroir.'))
    with db.connect() as c,storage_change(c,[source_drawer,target_drawer],tr('Transfert d’une quantité entre tiroirs')):
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?',(target_drawer,)).fetchone():raise ValueError(tr('Tiroir introuvable.'))
        for identity,color,amount,expected in entries:
            color=str(color or '')
            source=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(source_drawer,identity,color)).fetchone()
            if source is None or source['quantity']!=expected:raise ValueError(tr('Le contenu du tiroir a changé. Recommence le glissement.'))
            if source['quantity'] is None:
                if amount is not None:raise ValueError(tr('Renseigne la quantité du tiroir avant un transfert partiel.'))
            else:
                integer(amount)
                if amount>source['quantity'] or amount==0 and source['quantity']>0:raise ValueError(tr('La quantité à transférer n’est plus disponible dans ce tiroir.'))
            target=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(target_drawer,identity,color)).fetchone()
            target_quantity=target['quantity'] if target is not None else None
            total=(amount or 0)+(target_quantity or 0) if amount is not None or target_quantity is not None else None
            c.execute('INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?) ON CONFLICT(drawer_id,item_id,color) DO UPDATE SET quantity=excluded.quantity',(target_drawer,identity,color,total))
            if amount is None or amount==source['quantity']:
                c.execute('DELETE FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(source_drawer,identity,color))
            else:c.execute('UPDATE storage_contents SET quantity=quantity-? WHERE drawer_id=? AND item_id=? AND color=?',(amount,source_drawer,identity,color))
        validate(c)
    return True


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
