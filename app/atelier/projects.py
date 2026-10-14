"""Construction requirements and reservations of loose stock, with undo/redo."""
from collections import Counter

from .i18n import tr

STATES = {'planned': 'À préparer', 'active': 'En cours', 'completed': 'Terminé'}
TABLES = ('construction_projects', 'project_parts')


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
    for table in TABLES:
        for operation in ('INSERT', 'UPDATE', 'DELETE'):
            c.execute('CREATE TRIGGER IF NOT EXISTS revision_' + table + '_' + operation.lower() + ' AFTER ' + operation + ' ON ' + table + ' BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')


def amount(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 1000000000:
        raise ValueError(tr('Quantité entière invalide.'))
    return value


def validate(c):
    bad = c.execute('''SELECT p.item_id,p.color FROM project_parts p
        LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
        GROUP BY p.item_id,p.color
        HAVING SUM(p.reserved)>COALESCE(MAX(s.quantity),0) LIMIT 1''').fetchone()
    if bad:
        raise ValueError(tr('La quantité réservée aux projets dépasse le stock en vrac. Libère d’abord les réservations concernées.'))


def free(c, item_id, color, own_project=None):
    stock = c.execute('SELECT quantity FROM stock WHERE item_id=? AND color=?', (item_id, str(color))).fetchone()
    reserved = c.execute('SELECT COALESCE(SUM(reserved),0) FROM project_parts WHERE item_id=? AND color=? AND project_id<>?', (item_id, str(color), own_project or -1)).fetchone()[0]
    return max(0, int(stock['quantity']) - int(reserved)) if stock else 0


def create(db, name, parts=(), set_id=None, copies=1):
    from .action_history import change
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
        identity = c.execute('INSERT INTO construction_projects(name,set_id,copies) VALUES(?,?,?)', (name, set_id, copies)).lastrowid
        for (item_id, color), quantity in totals.items():
            amount(quantity, 1)
            if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig')", (item_id,)).fetchone():
                raise ValueError(tr('Référence introuvable'))
            c.execute('INSERT INTO project_parts(project_id,item_id,color,required) VALUES(?,?,?,?)', (identity, item_id, color, quantity))
    return identity


def from_set(db, set_id, copies=1, name='', spares=False):
    amount(copies, 1)
    item = db.get_item(set_id)
    if not item or item['kind'] != 'set':
        raise ValueError(tr('Set introuvable.'))
    components = db.components(item, strict=True)
    if not components:
        raise ValueError(tr('Charge d’abord l’inventaire complet de ce set.'))
    parts = [{'item_id': row['id'], 'color': str(row.get('chosen_color', '')),
              'quantity': int(row.get('chosen_quantity', 1)) * copies}
             for row in components if spares or not row.get('is_spare')]
    return create(db, name or item['ref'] + ' · ' + item['name'], parts, set_id, copies)


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
        rows = list(c.execute('SELECT * FROM project_parts WHERE project_id=?', (project_id,)))
        keys = {(row['item_id'], row['color']) for row in rows}
        if wanted is not None and not wanted <= keys:
            raise ValueError(tr('Les pièces du projet ont changé.'))
        for row in rows:
            if wanted is not None and (row['item_id'], row['color']) not in wanted:
                continue
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


def delete(db, project_id):
    from .action_history import change
    with db.connect() as c, change(c, TABLES, tr('Suppression d’un projet')):
        c.execute('DELETE FROM construction_projects WHERE id=?', (project_id,))


def detail(db, project_id):
    return db.rows('''SELECT i.*,p.project_id,p.color AS chosen_color,p.required,p.reserved,
        COALESCE(s.quantity,0) AS chosen_quantity,
        MAX(0,COALESCE(s.quantity,0)-(SELECT COALESCE(SUM(x.reserved),0) FROM project_parts x WHERE x.item_id=p.item_id AND x.color=p.color)) AS free_quantity,
        MAX(0,p.required-p.reserved-MAX(0,COALESCE(s.quantity,0)-(SELECT COALESCE(SUM(x.reserved),0) FROM project_parts x WHERE x.item_id=p.item_id AND x.color=p.color))) AS missing
        FROM project_parts p JOIN items i ON i.id=p.item_id
        LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
        WHERE p.project_id=? ORDER BY i.source,i.ref,p.color''', (project_id,))


def list_projects(db):
    return db.rows('''SELECT p.*,COALESCE(i.ref,'') AS set_ref,
        COALESCE((SELECT SUM(required) FROM project_parts x WHERE x.project_id=p.id),0) AS required,
        COALESCE((SELECT SUM(reserved) FROM project_parts x WHERE x.project_id=p.id),0) AS reserved,
        COALESCE((SELECT SUM(MAX(0,x.required-x.reserved-MAX(0,COALESCE(s.quantity,0)-(SELECT COALESCE(SUM(z.reserved),0) FROM project_parts z WHERE z.item_id=x.item_id AND z.color=x.color))))
        FROM project_parts x LEFT JOIN stock s ON s.item_id=x.item_id AND s.color=x.color WHERE x.project_id=p.id),0) AS missing
        FROM construction_projects p LEFT JOIN items i ON i.id=p.set_id ORDER BY p.id DESC''')
