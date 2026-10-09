"""Drawer geometry and loose-stock links; locations never duplicate stock."""
from .data import normalize
from .i18n import tr
import math

MAX_POSITION=100000


def extent(wall):
    """Standard drawer units, including the cabinet frame and name strip."""
    return wall['columns']+.3,wall['rows']+.5


def coordinate(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>MAX_POSITION:
        raise ValueError(tr('Position du meuble invalide.'))
    return round(float(value),1)


def check_position(c,wall_id,x,y,columns,rows):
    x,y=coordinate(x),coordinate(y);width,height=extent({'columns':columns,'rows':rows})
    for other in c.execute('SELECT * FROM storage_walls WHERE id<>?',(wall_id or -1,)):
        w,h=extent(other)
        if x<other['x']+w-1e-8 and other['x']<x+width-1e-8 and y<other['y']+h-1e-8 and other['y']<y+height-1e-8:
            raise ValueError(tr('Cet emplacement chevauche un autre meuble. Déplace le meuble ou augmente l’écart.'))
    return x,y


def prepare(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS storage_walls(id INTEGER PRIMARY KEY,name TEXT NOT NULL,columns INTEGER NOT NULL,rows INTEGER NOT NULL,
      x REAL NOT NULL DEFAULT 0,y REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS storage_drawers(id INTEGER PRIMARY KEY,wall_id INTEGER NOT NULL REFERENCES storage_walls(id) ON DELETE CASCADE,
      col INTEGER NOT NULL,row INTEGER NOT NULL,width INTEGER NOT NULL DEFAULT 1,height INTEGER NOT NULL DEFAULT 1,name TEXT NOT NULL DEFAULT '',
      UNIQUE(wall_id,col,row));
    CREATE TABLE IF NOT EXISTS storage_contents(drawer_id INTEGER NOT NULL REFERENCES storage_drawers(id) ON DELETE CASCADE,
      item_id INTEGER NOT NULL REFERENCES items(id),color TEXT NOT NULL DEFAULT '',PRIMARY KEY(drawer_id,item_id,color));
    CREATE INDEX IF NOT EXISTS idx_storage_item ON storage_contents(item_id,color);
    ''')
    fields={row['name'] for row in c.execute('PRAGMA table_info(storage_walls)')}
    if 'x' not in fields:c.execute('ALTER TABLE storage_walls ADD COLUMN x REAL NOT NULL DEFAULT 0')
    if 'y' not in fields:c.execute('ALTER TABLE storage_walls ADD COLUMN y REAL NOT NULL DEFAULT 0')
    if 'x' not in fields or 'y' not in fields:
        # Existing independent cabinets gain a usable overview once, retaining
        # drawer identities and every stock/location association.
        position=0.0
        for wall in c.execute('SELECT id,columns FROM storage_walls ORDER BY id').fetchall():
            c.execute('UPDATE storage_walls SET x=?,y=0 WHERE id=?',(position,wall['id']))
            position=round(position+wall['columns']+.5,1)


def create_wall(db,name,columns=4,rows=6,x=None,y=0):
    name=name.strip()
    if not name or not 1<=columns<=100 or not 1<=rows<=100:raise ValueError(tr('Nom et dimensions du meuble invalides.'))
    with db.connect() as c:
        if x is None:x=round(c.execute('SELECT COALESCE(MAX(x+columns+.5),0) FROM storage_walls').fetchone()[0],1)
        x,y=check_position(c,None,x,y,columns,rows)
        wall_id=c.execute('INSERT INTO storage_walls(name,columns,rows,x,y) VALUES(?,?,?,?,?)',(name,columns,rows,x,y)).lastrowid
        c.executemany('INSERT INTO storage_drawers(wall_id,col,row) VALUES(?,?,?)',((wall_id,col,row) for row in range(1,rows+1) for col in range(1,columns+1)))
    return wall_id


def walls(db):return db.rows('SELECT * FROM storage_walls ORDER BY id')


def update_wall(db,wall_id,name,x,y):
    if not name.strip():raise ValueError(tr('Nom du meuble invalide.'))
    with db.connect() as c:
        wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
        if not wall:raise ValueError(tr('Meuble introuvable.'))
        x,y=check_position(c,wall_id,x,y,wall['columns'],wall['rows'])
        if (name.strip(),x,y)!=(wall['name'],wall['x'],wall['y']):
            c.execute('UPDATE storage_walls SET name=?,x=?,y=? WHERE id=?',(name.strip(),x,y,wall_id))


def position_wall(db,wall_id,x,y):
    with db.connect() as c:
        wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
        if not wall:raise ValueError(tr('Meuble introuvable.'))
        x,y=check_position(c,wall_id,x,y,wall['columns'],wall['rows'])
        if (x,y)!=(wall['x'],wall['y']):c.execute('UPDATE storage_walls SET x=?,y=? WHERE id=?',(x,y,wall_id))


def rename_wall(db,wall_id,name):
    name=name.strip()
    if not name:raise ValueError(tr('Nom du meuble invalide.'))
    with db.connect() as c:
        wall=c.execute('SELECT name FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
        if not wall:raise ValueError(tr('Meuble introuvable.'))
        if wall['name']!=name:c.execute('UPDATE storage_walls SET name=? WHERE id=?',(name,wall_id))
    return name


def relative_position(db,wall_id,reference_id,direction,gap=.2):
    gap=coordinate(gap)
    if gap<0 or wall_id==reference_id:raise ValueError(tr('Position relative du meuble invalide.'))
    selected=db.rows('SELECT * FROM storage_walls WHERE id IN (?,?)',(wall_id,reference_id))
    by_id={wall['id']:wall for wall in selected}
    if wall_id not in by_id or reference_id not in by_id:raise ValueError(tr('Meuble introuvable.'))
    wall,reference=by_id[wall_id],by_id[reference_id];w,h=extent(wall);rw,rh=extent(reference)
    x,y=reference['x'],reference['y']
    if direction=='left':x-=w+gap
    elif direction=='right':x+=rw+gap
    elif direction=='above':y-=h+gap
    elif direction=='below':y+=rh+gap
    else:raise ValueError(tr('Position relative du meuble invalide.'))
    return coordinate(x),coordinate(y)


def delete_wall(db,wall_id):
    with db.connect() as c:
        if not c.execute('SELECT 1 FROM storage_walls WHERE id=?',(wall_id,)).fetchone():raise ValueError(tr('Meuble introuvable.'))
        # FK cascades remove drawers and location links; stocks are independent.
        c.execute('DELETE FROM storage_walls WHERE id=?',(wall_id,))


def drawers(db,wall_id):return db.rows('SELECT * FROM storage_drawers WHERE wall_id=? ORDER BY row,col',(wall_id,))


def layout_drawers(db,wall_id=None):
    return db.rows('SELECT * FROM storage_drawers'+(' WHERE wall_id=?' if wall_id is not None else '')+' ORDER BY wall_id,row,col',(wall_id,) if wall_id is not None else ())


def address(drawer):return tr('Colonne')+' '+str(drawer['col'])+' · '+tr('Tiroir')+' '+str(drawer['row'])


def save_drawer(db,wall_id,col,row,width=1,height=1,name='',drawer_id=None):
    if min(col,row,width,height)<1 or max(col,row,width,height)>100:raise ValueError(tr('Position ou taille du tiroir invalide.'))
    with db.connect() as c:
        wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
        if not wall:raise ValueError(tr('Meuble introuvable.'))
        check_position(c,wall_id,wall['x'],wall['y'],max(wall['columns'],col+width-1),max(wall['rows'],row+height-1))
        if drawer_id and not c.execute('SELECT 1 FROM storage_drawers WHERE id=? AND wall_id=?',(drawer_id,wall_id)).fetchone():raise ValueError(tr('Tiroir introuvable.'))
        others=c.execute('SELECT * FROM storage_drawers WHERE wall_id=? AND id<>?',(wall_id,drawer_id or -1)).fetchall()
        overlapping=[d for d in others if col<d['col']+d['width'] and d['col']<col+width and row<d['row']+d['height'] and d['row']<row+height]
        for d in overlapping:
            if c.execute('SELECT 1 FROM storage_contents WHERE drawer_id=? LIMIT 1',(d['id'],)).fetchone():raise ValueError(tr('Un tiroir contenant des références occupe cet emplacement. Déplace-le avant de modifier la taille.'))
        for d in overlapping:c.execute('DELETE FROM storage_drawers WHERE id=?',(d['id'],))
        if drawer_id:c.execute('UPDATE storage_drawers SET col=?,row=?,width=?,height=?,name=? WHERE id=?',(col,row,width,height,name.strip(),drawer_id))
        else:drawer_id=c.execute('INSERT INTO storage_drawers(wall_id,col,row,width,height,name) VALUES(?,?,?,?,?,?)',(wall_id,col,row,width,height,name.strip())).lastrowid
        c.execute('UPDATE storage_walls SET columns=MAX(columns,?),rows=MAX(rows,?) WHERE id=?',(col+width-1,row+height-1,wall_id))
    return drawer_id


def assign(db,drawer_id,entries):
    with db.connect() as c:
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?',(drawer_id,)).fetchone():raise ValueError(tr('Tiroir introuvable.'))
        for item_id,color in entries:
            color=str(color or '')
            if not c.execute("SELECT 1 FROM stock s JOIN items i ON i.id=s.item_id WHERE s.item_id=? AND s.color=? AND s.quantity>0 AND i.kind IN ('part','minifig')",(item_id,color)).fetchone():raise ValueError(tr('Cette référence n’est plus dans le stock en vrac.'))
            c.execute('INSERT OR IGNORE INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',(drawer_id,item_id,color))


def unassign(db,drawer_id,entries=None):
    """Remove location links atomically, leaving every stock quantity intact."""
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?',(drawer_id,)).fetchone():raise ValueError(tr('Tiroir introuvable.'))
        before=c.total_changes
        if entries is None:c.execute('DELETE FROM storage_contents WHERE drawer_id=?',(drawer_id,))
        else:c.executemany('DELETE FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',((drawer_id,item_id,str(color or '')) for item_id,color in entries))
        return c.total_changes-before


def move_drawer(db,drawer_id,wall_id,col,row):
    """Commit a drop atomically; swap equal drawers, or use unnamed empty cells.

    IDs carry their labels and stock links, including transfers between cabinets.
    An invalid drop never deletes or truncates a neighbour. The vacated footprint
    gets standard empty drawers so the cabinet remains usable after a large move.
    """
    if any(isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=100 for v in (col,row)):
        raise ValueError(tr('Position ou taille du tiroir invalide.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        drawer=c.execute('SELECT * FROM storage_drawers WHERE id=?',(drawer_id,)).fetchone()
        wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
        if not drawer:raise ValueError(tr('Tiroir introuvable.'))
        if not wall:raise ValueError(tr('Meuble introuvable.'))
        if col+drawer['width']-1>wall['columns'] or row+drawer['height']-1>wall['rows']:
            raise ValueError(tr('Le tiroir doit rester entièrement dans un meuble.'))
        if (wall_id,col,row)==(drawer['wall_id'],drawer['col'],drawer['row']):return False
        others=c.execute('SELECT * FROM storage_drawers WHERE wall_id=? AND id<>?',(wall_id,drawer_id)).fetchall()
        overlapping=[d for d in others if col<d['col']+d['width'] and d['col']<col+drawer['width'] and row<d['row']+d['height'] and d['row']<row+drawer['height']]
        swap=overlapping[0] if len(overlapping)==1 and (overlapping[0]['col'],overlapping[0]['row'],overlapping[0]['width'],overlapping[0]['height'])==(col,row,drawer['width'],drawer['height']) else None
        if not swap:
            populated={r[0] for r in c.execute('SELECT DISTINCT p.drawer_id FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id WHERE d.wall_id=?',(wall_id,))}
            for other in overlapping:
                inside=col<=other['col'] and row<=other['row'] and other['col']+other['width']<=col+drawer['width'] and other['row']+other['height']<=row+drawer['height']
                if not inside or other['name'] or other['id'] in populated:
                    raise ValueError(tr('Emplacement occupé : échange possible uniquement entre tiroirs de même taille.'))
            for other in overlapping:c.execute('DELETE FROM storage_drawers WHERE id=?',(other['id'],))
        # Reserve an off-grid coordinate inside this transaction to avoid the
        # UNIQUE(wall_id,col,row) collision when two populated drawers exchange.
        c.execute('UPDATE storage_drawers SET col=0,row=0 WHERE id=?',(drawer_id,))
        if swap:
            c.execute('UPDATE storage_drawers SET wall_id=?,col=?,row=? WHERE id=?',(drawer['wall_id'],drawer['col'],drawer['row'],swap['id']))
        c.execute('UPDATE storage_drawers SET wall_id=?,col=?,row=? WHERE id=?',(wall_id,col,row,drawer_id))
        if not swap:
            occupied=c.execute('SELECT col,row,width,height FROM storage_drawers WHERE wall_id=?',(drawer['wall_id'],)).fetchall()
            covered={(x,y) for d in occupied for y in range(max(drawer['row'],d['row']),min(drawer['row']+drawer['height'],d['row']+d['height'])) for x in range(max(drawer['col'],d['col']),min(drawer['col']+drawer['width'],d['col']+d['width']))}
            empty=[(drawer['wall_id'],x,y) for y in range(drawer['row'],drawer['row']+drawer['height']) for x in range(drawer['col'],drawer['col']+drawer['width']) if (x,y) not in covered]
            c.executemany('INSERT INTO storage_drawers(wall_id,col,row) VALUES(?,?,?)',empty)
    return True


def contents(db,drawer_id):
    return db.rows('''SELECT i.*,p.color AS chosen_color,COALESCE(s.quantity,0) AS chosen_quantity
       FROM storage_contents p JOIN items i ON i.id=p.item_id
       LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
       WHERE p.drawer_id=? ORDER BY i.source,i.ref,p.color''',(drawer_id,))


CONTENTS_SQL='''SELECT p.drawer_id,i.*,p.color AS chosen_color,COALESCE(s.quantity,0) AS chosen_quantity
      FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN items i ON i.id=p.item_id
      LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color'''


def wall_contents(db,wall_id=None):
    return db.rows(CONTENTS_SQL+(' WHERE d.wall_id=?' if wall_id is not None else '')+' ORDER BY d.wall_id,d.row,d.col,i.ref',(wall_id,) if wall_id is not None else ())


def print_snapshot(db):
    """One read-only snapshot; later preview paints never query the database."""
    with db.read() as c:
        c.execute('BEGIN')
        return {'walls':[dict(r) for r in c.execute('SELECT * FROM storage_walls ORDER BY id')],
                'drawers':[dict(r) for r in c.execute('SELECT * FROM storage_drawers ORDER BY wall_id,row,col')],
                'parts':[dict(r) for r in c.execute(CONTENTS_SQL+' ORDER BY d.wall_id,d.row,d.col,i.ref')]}


def search(db,query,wall_id=None):
    words=normalize(query).split()
    if not words:return []
    clause=' AND d.wall_id=?' if wall_id is not None else ''
    rows=db.rows('''SELECT d.*,w.name AS wall_name,i.id AS item_id,i.source,i.ref,i.name AS piece_name,
      i.category,i.dimensions,p.color,COALESCE(s.quantity,0) AS stock_quantity,COALESCE(c.name,'') AS color_name
      FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN storage_walls w ON w.id=d.wall_id
      JOIN items i ON i.id=p.item_id LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
      LEFT JOIN colors c ON i.source='RB' AND CAST(c.id AS TEXT)=p.color WHERE 1=1'''+clause+' ORDER BY w.id,d.row,d.col,i.ref',(wall_id,) if wall_id is not None else ())
    palette=db.setting('bl_colors',{})
    for row in rows:
        if row['source']=='BL':row['color_name']=palette.get(row['color'],{}).get('name','')
    return [r for r in rows if all(word in normalize(' '.join(str(r[k]) for k in ('ref','piece_name','category','dimensions','color','color_name','name','wall_name'))) for word in words)]
