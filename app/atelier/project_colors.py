"""Colour-independent project needs with reservations of actual stock colours."""
from collections import Counter
from .i18n import tr

RESERVATIONS='project_color_reservations'
PICKS='project_color_pick_rows'


def prepare(c):
    if 'ignore_colors' not in {r['name'] for r in c.execute('PRAGMA table_info(construction_projects)')}:
        c.execute('ALTER TABLE construction_projects ADD COLUMN ignore_colors INTEGER NOT NULL DEFAULT 0 CHECK(ignore_colors IN (0,1))')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS project_color_reservations(
        project_id INTEGER NOT NULL,item_id INTEGER NOT NULL,color TEXT NOT NULL,
        stock_color TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),
        PRIMARY KEY(project_id,item_id,color,stock_color),
        FOREIGN KEY(project_id,item_id,color) REFERENCES project_parts(project_id,item_id,color) ON DELETE CASCADE);
      CREATE INDEX IF NOT EXISTS idx_project_color_stock ON project_color_reservations(item_id,stock_color);
      CREATE TABLE IF NOT EXISTS project_color_pick_rows(
        project_id INTEGER NOT NULL,item_id INTEGER NOT NULL,color TEXT NOT NULL,stock_color TEXT NOT NULL,
        drawer_id INTEGER NOT NULL REFERENCES storage_drawers(id),quantity INTEGER NOT NULL CHECK(quantity>0),
        PRIMARY KEY(project_id,item_id,color,stock_color,drawer_id),
        FOREIGN KEY(project_id,item_id,color) REFERENCES project_parts(project_id,item_id,color) ON DELETE RESTRICT);
      CREATE VIEW IF NOT EXISTS project_stock_reservations AS
        SELECT r.project_id,r.item_id,r.color,r.reserved FROM project_parts r
          JOIN construction_projects p ON p.id=r.project_id WHERE p.ignore_colors=0
        UNION ALL SELECT r.project_id,r.item_id,r.stock_color AS color,r.quantity AS reserved
          FROM project_color_reservations r;
      CREATE VIEW IF NOT EXISTS project_physical_picks AS
        SELECT project_id,item_id,color,drawer_id,quantity,color AS need_color FROM project_pick_rows
        UNION ALL SELECT project_id,item_id,stock_color AS color,drawer_id,quantity,color AS need_color
          FROM project_color_pick_rows;
    ''')
    for table in (RESERVATIONS,PICKS):
        for operation in ('INSERT','UPDATE','DELETE'):
            c.execute('CREATE TRIGGER IF NOT EXISTS revision_'+table+'_'+operation.lower()+' AFTER '+operation+' ON '+table+' BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')


def enabled(c,project_id):
    row=c.execute('SELECT ignore_colors FROM construction_projects WHERE id=?',(project_id,)).fetchone()
    if not row:raise ValueError(tr('Projet introuvable.'))
    return bool(row['ignore_colors'])


def validate(c):
    bad=c.execute('''SELECT r.project_id FROM project_color_reservations r
      JOIN construction_projects p ON p.id=r.project_id WHERE p.ignore_colors=0 LIMIT 1''').fetchone()
    if not bad:
        bad=c.execute('''SELECT r.project_id FROM project_parts r JOIN construction_projects p ON p.id=r.project_id
          WHERE p.ignore_colors=1 AND r.reserved<>(SELECT COALESCE(SUM(a.quantity),0) FROM project_color_reservations a
          WHERE a.project_id=r.project_id AND a.item_id=r.item_id AND a.color=r.color) LIMIT 1''').fetchone()
    if bad:raise ValueError(tr('Réservations de couleurs incohérentes pour ce projet.'))


def allocations(c,project_id):
    result={}
    for r in c.execute('SELECT * FROM project_color_reservations WHERE project_id=?',(project_id,)):
        result.setdefault((r['item_id'],r['color']),{})[r['stock_color']]=r['quantity']
    return result


def stock_pools(c,project_id):
    rows=c.execute('''SELECT s.item_id,SUM(s.quantity) AS quantity,
      SUM(MAX(0,s.quantity-COALESCE(r.reserved,0))) AS free FROM stock s
      LEFT JOIN (SELECT item_id,color,SUM(reserved) AS reserved FROM project_stock_reservations WHERE item_id IN (SELECT item_id FROM project_parts WHERE project_id=?) GROUP BY item_id,color) r
      ON r.item_id=s.item_id AND r.color=s.color
      WHERE EXISTS(SELECT 1 FROM project_parts p WHERE p.project_id=? AND p.item_id=s.item_id)
      GROUP BY s.item_id''',(project_id,project_id))
    return {r['item_id']:dict(r) for r in rows}


def missing(c,project_id):
    pools=stock_pools(c,project_id)
    return sum(max(0,r['required']-r['reserved']-pools.get(r['item_id'],{}).get('free',0)) for r in c.execute(
      'SELECT item_id,SUM(required) AS required,SUM(reserved) AS reserved FROM project_parts WHERE project_id=? GROUP BY item_id',(project_id,)))


def decorate_detail(c,project_id,rows):
    pools=stock_pools(c,project_id);reserved=allocations(c,project_id)
    remaining={identity:r['free'] for identity,r in pools.items()}
    for row in rows:
        identity=row['id'];take=min(row['required']-row['reserved'],remaining.get(identity,0));remaining[identity]=remaining.get(identity,0)-take
        row.update(ignore_colors=True,chosen_quantity=pools.get(identity,{}).get('quantity',0),free_quantity=take,
          missing=row['required']-row['reserved']-take,reservable_quantity=min(row['required'],row['reserved']+pools.get(identity,{}).get('free',0)),reserved_colors=reserved.get((identity,row['chosen_color']),{}))
    return rows


def reserve(c,project_id,part,quantity=None,minimums=None):
    """Keep taken colours and existing choices, then use free physical colours."""
    from .projects import free
    identity=part['item_id'];need_color=part['color'];old={r['stock_color']:r['quantity'] for r in c.execute('SELECT stock_color,quantity FROM project_color_reservations WHERE project_id=? AND item_id=? AND color=?',(project_id,identity,need_color))}
    stocks={r['color']:r['quantity'] for r in c.execute('SELECT color,quantity FROM stock WHERE item_id=? AND quantity>0',(identity,))}
    capacity={color:free(c,identity,color)+old.get(color,0) for color in stocks}
    floors=Counter({r['color']:r['quantity'] for r in c.execute('''SELECT color,SUM(quantity) AS quantity FROM project_physical_picks
      WHERE project_id=? AND item_id=? AND need_color=? GROUP BY color''',(project_id,identity,need_color))})
    for color,value in (minimums or {}).items():floors[color]=max(floors[color],value)
    target=min(part['required'],sum(capacity.values())) if quantity is None else quantity
    if target>part['required'] or target>sum(capacity.values()):raise ValueError(tr('Réservation supérieure au besoin ou au stock libre.'))
    if target<sum(floors.values()) or any(value>capacity.get(color,0) for color,value in floors.items()):
        raise ValueError(tr('Remets les pièces prélevées dans leurs tiroirs avant de libérer ou réduire la réservation.'))
    result=Counter(floors);remaining=target-sum(result.values())
    for color in list(old)+[color for color in sorted(stocks,key=lambda color:(color!=need_color,color)) if color not in old]:
        take=min(remaining,max(0,capacity.get(color,0)-result[color]),max(0,old[color]-result[color]) if color in old else remaining)
        result[color]+=take;remaining-=take
    # Existing colours can also supply additional free units after retaining old choices.
    for color in sorted(stocks,key=lambda color:(color!=need_color,color)):
        take=min(remaining,max(0,capacity[color]-result[color]));result[color]+=take;remaining-=take
    c.execute('DELETE FROM project_color_reservations WHERE project_id=? AND item_id=? AND color=?',(project_id,identity,need_color))
    c.executemany('INSERT INTO project_color_reservations VALUES(?,?,?,?,?)',[(project_id,identity,need_color,color,value) for color,value in result.items() if value])
    c.execute('UPDATE project_parts SET reserved=? WHERE project_id=? AND item_id=? AND color=?',(target,project_id,identity,need_color))


def pick_list(c,project_id):
    """Spend each counted drawer and each free stock unit at most once."""
    from .projects import free
    rows=[];free_left={};locations_left={}
    reservations=allocations(c,project_id)
    parts=c.execute('''SELECT p.*,i.ref,i.name,i.source FROM project_parts p JOIN items i ON i.id=p.item_id
      WHERE p.project_id=? ORDER BY i.ref,p.color''',(project_id,)).fetchall()
    for part in parts:
        identity=part['item_id'];need_color=part['color']
        taken_colors={r['color']:r['quantity'] for r in c.execute('''SELECT color,SUM(quantity) AS quantity FROM project_physical_picks
          WHERE project_id=? AND item_id=? AND need_color=? GROUP BY color''',(project_id,identity,need_color))}
        taken=sum(taken_colors.values());needed=part['required']-taken
        own={color:max(0,value-taken_colors.get(color,0)) for color,value in reservations.get((identity,need_color),{}).items()}
        for location in c.execute('''SELECT d.id AS drawer_id,d.col,d.row,w.name AS cabinet,p.quantity,p.color
          FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN storage_walls w ON w.id=d.wall_id
          WHERE p.item_id=? AND p.quantity>0 ORDER BY p.color<>?,w.y,w.x,w.id,d.row,d.col,p.color''',(identity,need_color)).fetchall():
            color=location['color'];key=(identity,color);drawer_key=(location['drawer_id'],identity,color)
            if key not in free_left:free_left[key]=free(c,identity,color)
            if drawer_key not in locations_left:locations_left[drawer_key]=location['quantity']
            quantity=min(needed,locations_left[drawer_key],free_left[key]+own.get(color,0))
            if not quantity:continue
            from_own=min(quantity,own.get(color,0));own[color]=own.get(color,0)-from_own;free_left[key]-=quantity-from_own
            locations_left[drawer_key]-=quantity;needed-=quantity
            row=dict(part);row.update(dict(location));row.update(need_color=need_color,suggested=quantity,taken=taken,ignore_colors=True);rows.append(row)
        if needed:rows.append(dict(part,need_color=need_color,drawer_id=None,cabinet=tr('Sans emplacement compté'),suggested=needed,taken=taken,col=None,row=None,ignore_colors=True))
    return rows
