"""Construction availability and reservations of loose stock, with undo/redo."""
from collections import Counter

from .i18n import tr

STATES = {'planned': 'À préparer', 'active': 'En cours', 'completed': 'Terminé'}
TABLES = ('construction_projects', 'project_parts', 'project_color_reservations','project_set_sources','project_set_allocations')


def prepare(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS construction_projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'planned',set_id INTEGER REFERENCES items(id),
        copies INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        CREATE TABLE IF NOT EXISTS project_parts(
        project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL REFERENCES items(id),color TEXT NOT NULL DEFAULT '',
        required INTEGER NOT NULL CHECK(required>0),reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0 AND reserved<=required),
        PRIMARY KEY(project_id,item_id,color));
        CREATE INDEX IF NOT EXISTS idx_project_parts_stock ON project_parts(item_id,color);''')
    from .project_colors import prepare as prepare_colors
    prepare_colors(c)
    from .project_stock import prepare as prepare_stock
    prepare_stock(c)
    from .set_allocations import prepare as prepare_allocations
    prepare_allocations(c)
    from .project_picks import prepare as prepare_picks
    prepare_picks(c)
    for table in TABLES:
        for operation in ('INSERT', 'UPDATE', 'DELETE'):
            c.execute('CREATE TRIGGER IF NOT EXISTS revision_' + table + '_' + operation.lower() + ' AFTER ' + operation + ' ON ' + table + ' BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')


def amount(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 1000000000:
        raise ValueError(tr('Quantité entière invalide.'))
    return value


def validate(c):
    from .set_allocations import validate as validate_allocations
    validate_allocations(c)
    from .project_colors import validate as validate_colors
    validate_colors(c)
    bad = c.execute('''SELECT p.item_id,p.color FROM project_stock_reservations p
        LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
        GROUP BY p.item_id,p.color
        HAVING SUM(p.reserved)>COALESCE(MAX(s.quantity),0) LIMIT 1''').fetchone()
    if bad:
        raise ValueError(tr('La quantité réservée aux projets dépasse le stock en vrac. Libère d’abord les réservations concernées.'))


def free(c, item_id, color, own_project=None):
    stock = c.execute('SELECT quantity FROM stock WHERE item_id=? AND color=?', (item_id, str(color))).fetchone()
    reserved = c.execute('SELECT COALESCE(SUM(reserved),0) FROM project_stock_reservations WHERE item_id=? AND color=? AND project_id<>?', (item_id, str(color), own_project or -1)).fetchone()[0]
    return max(0, int(stock['quantity']) - int(reserved)) if stock else 0


def create(db, name, parts=(), set_id=None, copies=1, ignore_colors=False, include_set_stock=False):
    from .action_history import change
    if type(ignore_colors) is not bool:raise ValueError(tr('Réglage des couleurs du projet invalide.'))
    if type(include_set_stock) is not bool:raise ValueError(tr('Réglage du stock du projet invalide.'))
    name = name.strip()
    if not name:
        raise ValueError(tr('Nom du projet obligatoire.'))
    amount(copies, 1)
    totals = Counter()
    for row in parts:
        totals[(int(row['item_id']), str(row.get('color', '')))] += amount(row['quantity'], 1)
    with db.connect() as c, change(c, TABLES, tr('Création d’un projet')):
        if set_id is not None and not c.execute("SELECT 1 FROM items WHERE id=? AND kind='set'", (set_id,)).fetchone():
            raise ValueError(tr('Set introuvable.'))
        identity = c.execute('INSERT INTO construction_projects(name,set_id,copies,ignore_colors,include_set_stock) VALUES(?,?,?,?,?)', (name, set_id, copies, int(ignore_colors), int(include_set_stock))).lastrowid
        for (item_id, color), quantity in totals.items():
            amount(quantity, 1)
            if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig')", (item_id,)).fetchone():
                raise ValueError(tr('Référence introuvable'))
            c.execute('INSERT INTO project_parts(project_id,item_id,color,required) VALUES(?,?,?,?)', (identity, item_id, color, quantity))
    return identity


def from_set(db, set_id, copies=1, name='', spares=False, exclude_minifigs=False, allow_alternatives=False, ignore_colors=False, include_set_stock=False):
    amount(copies, 1)
    item = db.get_item(set_id)
    if not item or item['kind'] != 'set':
        raise ValueError(tr('Set introuvable.'))
    components = db.components(item, strict=True, exclude_minifigs=exclude_minifigs)
    if not components:
        raise ValueError(tr('Charge d’abord l’inventaire complet de ce set.'))
    parts = [{'item_id': row['id'], 'color': str(row.get('chosen_color', '')),
              'quantity': int(row.get('chosen_quantity', 1)) * copies}
             for row in components if spares or not row.get('is_spare')]
    if allow_alternatives:parts=equivalent_parts(db,parts,ignore_colors=ignore_colors)
    return create(db, name or item['ref'] + ' · ' + item['name'], parts, set_id, copies, ignore_colors, include_set_stock)


def equivalent_parts(db, parts, ignore_colors=False):
    """Allocate free physical identities without reserving or changing ownership."""
    from .build_stock import InventoryReader
    from .alternative_catalogue import original
    needs=Counter()
    for row in parts:needs[(row['item_id'],str(row['color']))]+=row['quantity']
    assigned=Counter()
    with db.read() as c:
        c.execute('BEGIN');reader=InventoryReader(c,ignore_colors=ignore_colors,allow_alternatives=True)
        rows=[dict(row) for row in c.execute('SELECT i.*,s.color,s.quantity AS stock_quantity FROM stock s JOIN items i ON i.id=s.item_id WHERE s.quantity>0')]
        available={(row['id'],str(row['color'])):free(c,row['id'],row['color']) for row in rows}
        def family(item,color):
            if item['kind']=='part':
                key=reader.canonical(item['source'],item['ref'],color)
                return ('part',)+key if key[2] else None
            native=original(item)
            return native['source'],native['kind'],native['ref'],'*' if ignore_colors else str(color)
        # Keep each exact reference's free stock before assigning equivalents.
        remaining={}
        for key,quantity in needs.items():
            candidates=sorted((k for k in available if k[0]==key[0]),key=lambda k:(k!=key,k[1])) if ignore_colors else [key]
            for candidate in candidates:
                take=min(quantity,available.get(candidate,0));available[candidate]=available.get(candidate,0)-take
                assigned[key]+=take;quantity-=take
            remaining[key]=quantity
        for (identity,color),quantity in remaining.items():
            item=dict(c.execute('SELECT * FROM items WHERE id=?',(identity,)).fetchone());wanted=family(item,color)
            for row in rows:
                key=(row['id'],str(row['color']))
                if not quantity:break
                if key==(identity,color) or not wanted or row['kind']!=item['kind'] or 'ALT' not in (item['source'],row['source']) or family(row,row['color'])!=wanted:continue
                take=min(quantity,available[key]);assigned[key]+=take;available[key]-=take;quantity-=take
            assigned[(identity,color)]+=quantity
    return [{'item_id':identity,'color':color,'quantity':quantity} for (identity,color),quantity in assigned.items() if quantity]


def edit(db, project_id, name=None, status=None):
    from .action_history import change
    if name is not None and not name.strip():
        raise ValueError(tr('Nom du projet obligatoire.'))
    if status is not None and status not in STATES:
        raise ValueError(tr('État du projet invalide.'))
    with db.connect() as c, change(c, TABLES, tr('Modification d’un projet')):
        if not c.execute('SELECT 1 FROM construction_projects WHERE id=?', (project_id,)).fetchone():
            raise ValueError(tr('Projet introuvable.'))
        if name is not None:
            c.execute('UPDATE construction_projects SET name=? WHERE id=? AND name<>?', (name.strip(), project_id, name.strip()))
        if status is not None:
            c.execute('UPDATE construction_projects SET status=? WHERE id=? AND status<>?', (status, project_id, status))


def put_part(db, project_id, item_id, color, quantity):
    from .action_history import change
    amount(quantity, 1)
    with db.connect() as c, change(c, TABLES, tr('Modification des pièces d’un projet')):
        if not c.execute('SELECT 1 FROM construction_projects WHERE id=?', (project_id,)).fetchone():
            raise ValueError(tr('Projet introuvable.'))
        if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig')", (item_id,)).fetchone():
            raise ValueError(tr('Référence introuvable'))
        old = c.execute('SELECT reserved FROM project_parts WHERE project_id=? AND item_id=? AND color=?', (project_id, item_id, str(color))).fetchone()
        if old and quantity < old['reserved']:
            raise ValueError(tr('Libère les réservations avant de réduire la quantité nécessaire.'))
        c.execute('''INSERT INTO project_parts(project_id,item_id,color,required) VALUES(?,?,?,?)
            ON CONFLICT(project_id,item_id,color) DO UPDATE SET required=excluded.required WHERE project_parts.required<>excluded.required''', (project_id, item_id, str(color), quantity))


def remove_parts(db, project_id, entries):
    from .action_history import change
    with db.connect() as c, change(c, TABLES, tr('Retrait de pièces d’un projet')):
        c.executemany('DELETE FROM project_parts WHERE project_id=? AND item_id=? AND color=?', [(project_id, identity, str(color)) for identity, color in entries])


def reserve(db, project_id, entries=None, quantity=None):
    from .action_history import change
    if quantity is not None:
        amount(quantity)
    wanted = set((identity, str(color)) for identity, color in entries) if entries is not None else None
    with db.connect() as c, change(c, TABLES, tr('Réservation de pièces pour un projet')):
        if not c.execute('SELECT 1 FROM construction_projects WHERE id=?', (project_id,)).fetchone():
            raise ValueError(tr('Projet introuvable.'))
        from .project_colors import enabled,reserve as reserve_colors
        ignore_colors=enabled(c,project_id)
        rows = list(c.execute('SELECT * FROM project_parts WHERE project_id=? ORDER BY item_id,color', (project_id,)))
        keys = {(row['item_id'], row['color']) for row in rows}
        if wanted is not None and not wanted <= keys:
            raise ValueError(tr('Les pièces du projet ont changé.'))
        for row in rows:
            if wanted is not None and (row['item_id'], row['color']) not in wanted:
                continue
            if ignore_colors:
                reserve_colors(c,project_id,row,quantity);continue
            available = free(c, row['item_id'], row['color'], project_id)
            value = min(row['required'], available) if quantity is None else quantity
            if value > row['required'] or value > available:
                raise ValueError(tr('Réservation supérieure au besoin ou au stock libre.'))
            if value != row['reserved']:
                c.execute('UPDATE project_parts SET reserved=? WHERE project_id=? AND item_id=? AND color=?', (value, project_id, row['item_id'], row['color']))


def release(db, project_id):
    from .action_history import change
    with db.connect() as c, change(c, TABLES, tr('Libération des pièces d’un projet')):
        c.execute('UPDATE project_parts SET reserved=0 WHERE project_id=? AND reserved<>0', (project_id,))
        c.execute('DELETE FROM project_color_reservations WHERE project_id=?',(project_id,))


def delete(db, project_id):
    from .action_history import change
    from .project_picks import TABLES as PICK_TABLES
    with db.connect() as c, change(c, TABLES+PICK_TABLES+('shopping_projects',), tr('Suppression d’un projet')):
        # Picked pieces remain owned, free and without a counted drawer. Do not
        # pretend they were physically put back into their original drawers.
        for table in PICK_TABLES:c.execute('DELETE FROM '+table+' WHERE project_id=?',(project_id,))
        c.execute('DELETE FROM construction_projects WHERE id=?', (project_id,))


def detail(db, project_id):
    with db.read() as c:
        c.execute('BEGIN')
        return _detail(c, project_id)


def _detail(c, project_id, set_stock=None):
    rows=[dict(r) for r in c.execute('''WITH reservations AS (
        SELECT item_id,color,SUM(reserved) AS reserved FROM project_stock_reservations
        WHERE item_id IN (SELECT item_id FROM project_parts WHERE project_id=?) GROUP BY item_id,color)
        SELECT i.*,p.project_id,p.color AS chosen_color,p.required,p.reserved,
        COALESCE(s.quantity,0) AS chosen_quantity,
        MAX(0,COALESCE(s.quantity,0)-COALESCE(r.reserved,0)) AS free_quantity,
        MAX(0,p.required-p.reserved-MAX(0,COALESCE(s.quantity,0)-COALESCE(r.reserved,0))) AS missing
        FROM project_parts p JOIN items i ON i.id=p.item_id
        LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
        LEFT JOIN reservations r ON r.item_id=p.item_id AND r.color=p.color
        WHERE p.project_id=? ORDER BY i.source,i.ref,p.color''', (project_id,project_id))]
    from .project_colors import enabled,decorate_detail
    if not rows:return rows
    ignore_colors=enabled(c,project_id)
    if ignore_colors:decorate_detail(c,project_id,rows)
    else:
        for row in rows:row.update(ignore_colors=False,reserved_colors={row['chosen_color']:row['reserved']} if row['reserved'] else {})
    for row in rows:
        row.update(set_quantity=0,owned_set_quantity=0)
        row.setdefault('reservable_quantity',min(row['required'],row['reserved']+row['free_quantity']))
    if c.execute('SELECT include_set_stock FROM construction_projects WHERE id=?',(project_id,)).fetchone()[0]:
        from .project_stock import owned_sets,decorate
        from .set_allocations import pool
        decorate(rows,pool(c,project_id,set_stock),ignore_colors)
    return rows


def list_projects(db):
    from .i18n import language
    return db.cached_read(('project-summary',language()),lambda c:_list_projects(c))


def _list_projects(c):
    from .project_summary import summarize
    if not c.in_transaction:c.execute('BEGIN')
    rows=[dict(r) for r in c.execute("SELECT p.*,COALESCE(i.ref,'') AS set_ref FROM construction_projects p LEFT JOIN items i ON i.id=p.set_id ORDER BY p.id DESC")]
    return summarize(c,rows)


def set_include_set_stock(db,project_id,value):
    from .action_history import change
    if type(value) is not bool:raise ValueError(tr('Réglage du stock du projet invalide.'))
    with db.connect() as c,change(c,('construction_projects','project_set_sources','project_set_allocations'),tr('Réglage du stock d’un projet')):
        row=c.execute('SELECT include_set_stock FROM construction_projects WHERE id=?',(project_id,)).fetchone()
        if not row:raise ValueError(tr('Projet introuvable.'))
        if not value:
            c.execute('DELETE FROM project_set_allocations WHERE project_id=?',(project_id,))
            c.execute('DELETE FROM project_set_sources WHERE project_id=?',(project_id,))
        if bool(row['include_set_stock'])!=value:
            c.execute('UPDATE construction_projects SET include_set_stock=? WHERE id=?',(int(value),project_id))


def set_ignore_colors(db,project_id,value):
    from .action_history import change
    from .project_colors import enabled
    if type(value) is not bool:raise ValueError(tr('Réglage des couleurs du projet invalide.'))
    with db.connect() as c,change(c,TABLES,tr('Réglage des couleurs d’un projet')):
        old=enabled(c,project_id)
        if old==value:return
        if value:
            c.execute('''INSERT INTO project_color_reservations(project_id,item_id,color,stock_color,quantity)
              SELECT project_id,item_id,color,color,reserved FROM project_parts WHERE project_id=? AND reserved>0''',(project_id,))
        else:
            if c.execute('SELECT 1 FROM project_color_reservations WHERE project_id=? AND color<>stock_color LIMIT 1',(project_id,)).fetchone():
                raise ValueError(tr('Libère les réservations dans d’autres couleurs avant de rétablir les couleurs prévues.'))
            c.execute('DELETE FROM project_color_reservations WHERE project_id=?',(project_id,))
        c.execute('UPDATE construction_projects SET ignore_colors=? WHERE id=?',(int(value),project_id))
