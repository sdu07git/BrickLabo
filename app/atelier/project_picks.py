"""Keep picked quantities after their physical cabinet or drawer is removed."""
from collections import Counter

TABLES=('project_pick_rows','project_color_pick_rows','project_unlocated_picks')


def prepare(c):
    c.execute('''CREATE TABLE IF NOT EXISTS project_unlocated_picks(
        project_id INTEGER NOT NULL,item_id INTEGER NOT NULL,color TEXT NOT NULL,
        stock_color TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),
        PRIMARY KEY(project_id,item_id,color,stock_color),
        FOREIGN KEY(project_id,item_id,color) REFERENCES project_parts(project_id,item_id,color) ON DELETE RESTRICT)''')
    view=c.execute("SELECT sql FROM sqlite_master WHERE type='view' AND name='project_physical_picks'").fetchone()
    if not view or 'project_unlocated_picks' not in view['sql']:
        c.executescript('''DROP VIEW IF EXISTS project_physical_picks;
          CREATE VIEW project_physical_picks AS
          SELECT project_id,item_id,color,drawer_id,quantity,color AS need_color FROM project_pick_rows
          UNION ALL SELECT project_id,item_id,stock_color AS color,drawer_id,quantity,color AS need_color FROM project_color_pick_rows
          UNION ALL SELECT project_id,item_id,stock_color AS color,NULL AS drawer_id,quantity,color AS need_color FROM project_unlocated_picks;''')
    for operation in ('INSERT','UPDATE','DELETE'):
        c.execute('CREATE TRIGGER IF NOT EXISTS revision_project_unlocated_picks_'+operation.lower()+' AFTER '+operation+' ON project_unlocated_picks BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')


def detach_drawers(c,identities):
    """Move picks to an unlocated ledger without changing ownership or colours."""
    identities=list(identities)
    for start in range(0,len(identities),800):
        chunk=identities[start:start+800];marks=','.join('?' for _ in chunk)
        counts=Counter()
        for row in c.execute('SELECT * FROM project_physical_picks WHERE drawer_id IN ('+marks+')',chunk):
            counts[(row['project_id'],row['item_id'],row['need_color'],row['color'])]+=row['quantity']
        c.executemany('''INSERT INTO project_unlocated_picks VALUES(?,?,?,?,?)
          ON CONFLICT(project_id,item_id,color,stock_color) DO UPDATE SET quantity=project_unlocated_picks.quantity+excluded.quantity''',
          [key+(value,) for key,value in counts.items()])
        for table in TABLES[:2]:c.execute('DELETE FROM '+table+' WHERE drawer_id IN ('+marks+')',chunk)
