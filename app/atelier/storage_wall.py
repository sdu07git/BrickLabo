"""Drawer geometry and loose-stock links; locations never duplicate stock."""
from .data import normalize
from .i18n import tr


def prepare(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS storage_walls(id INTEGER PRIMARY KEY,name TEXT NOT NULL,columns INTEGER NOT NULL,rows INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS storage_drawers(id INTEGER PRIMARY KEY,wall_id INTEGER NOT NULL REFERENCES storage_walls(id) ON DELETE CASCADE,
      col INTEGER NOT NULL,row INTEGER NOT NULL,width INTEGER NOT NULL DEFAULT 1,height INTEGER NOT NULL DEFAULT 1,name TEXT NOT NULL DEFAULT '',
      UNIQUE(wall_id,col,row));
    CREATE TABLE IF NOT EXISTS storage_contents(drawer_id INTEGER NOT NULL REFERENCES storage_drawers(id) ON DELETE CASCADE,
      item_id INTEGER NOT NULL REFERENCES items(id),color TEXT NOT NULL DEFAULT '',PRIMARY KEY(drawer_id,item_id,color));
    CREATE INDEX IF NOT EXISTS idx_storage_item ON storage_contents(item_id,color);
    ''')


def create_wall(db,name,columns=4,rows=6):
    name=name.strip()
    if not name or not 1<=columns<=100 or not 1<=rows<=100:raise ValueError(tr('Nom et dimensions du meuble invalides.'))
    with db.connect() as c:
        wall_id=c.execute('INSERT INTO storage_walls(name,columns,rows) VALUES(?,?,?)',(name,columns,rows)).lastrowid
        c.executemany('INSERT INTO storage_drawers(wall_id,col,row) VALUES(?,?,?)',((wall_id,col,row) for row in range(1,rows+1) for col in range(1,columns+1)))
    return wall_id


def walls(db):return db.rows('SELECT * FROM storage_walls ORDER BY id')


def drawers(db,wall_id):return db.rows('SELECT * FROM storage_drawers WHERE wall_id=? ORDER BY row,col',(wall_id,))


def address(drawer):return tr('Colonne')+' '+str(drawer['col'])+' · '+tr('Tiroir')+' '+str(drawer['row'])


def save_drawer(db,wall_id,col,row,width=1,height=1,name='',drawer_id=None):
    if min(col,row,width,height)<1 or max(col,row,width,height)>100:raise ValueError(tr('Position ou taille du tiroir invalide.'))
    with db.connect() as c:
        wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
        if not wall:raise ValueError(tr('Meuble introuvable.'))
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


def contents(db,drawer_id):
    return db.rows('''SELECT i.*,p.color AS chosen_color,COALESCE(s.quantity,0) AS chosen_quantity
       FROM storage_contents p JOIN items i ON i.id=p.item_id
       LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color
       WHERE p.drawer_id=? ORDER BY i.source,i.ref,p.color''',(drawer_id,))


def wall_contents(db,wall_id):
    return db.rows('''SELECT p.drawer_id,i.*,p.color AS chosen_color,COALESCE(s.quantity,0) AS chosen_quantity
      FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN items i ON i.id=p.item_id
      LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color WHERE d.wall_id=? ORDER BY d.row,d.col,i.ref''',(wall_id,))


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
