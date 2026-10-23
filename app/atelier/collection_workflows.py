"""Persistent collection work: drafts, counts, purchase lots and physical picks.

Stock is possession. Picking moves counted locations to a reserved project; it
never subtracts possession. Counting is a separate observation until reviewed.
"""
from collections import Counter
import json
import uuid
from .i18n import tr


def prepare(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS collection_sessions(
      id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,body TEXT NOT NULL,
      created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS purchase_lots(
      id TEXT PRIMARY KEY,name TEXT NOT NULL,provenance TEXT NOT NULL DEFAULT '',
      price_cents INTEGER NOT NULL DEFAULT 0,comment TEXT NOT NULL DEFAULT '',import_job TEXT NOT NULL DEFAULT '',
      cancelled INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS purchase_lot_entries(
      lot_id TEXT NOT NULL REFERENCES purchase_lots(id),scope TEXT NOT NULL,
      item_id INTEGER NOT NULL REFERENCES items(id),color TEXT NOT NULL,
      quantity INTEGER NOT NULL CHECK(quantity>=0),components TEXT NOT NULL DEFAULT '[]',
      PRIMARY KEY(lot_id,scope,item_id,color));
    CREATE TABLE IF NOT EXISTS project_pick_rows(
      project_id INTEGER NOT NULL,item_id INTEGER NOT NULL,color TEXT NOT NULL,
      drawer_id INTEGER NOT NULL REFERENCES storage_drawers(id),quantity INTEGER NOT NULL CHECK(quantity>0),
      PRIMARY KEY(project_id,item_id,color,drawer_id),
      FOREIGN KEY(project_id,item_id,color) REFERENCES project_parts(project_id,item_id,color) ON DELETE RESTRICT);
    ''')

    if 'import_job' not in {r['name'] for r in c.execute('PRAGMA table_info(purchase_lots)')}:
        c.execute("ALTER TABLE purchase_lots ADD COLUMN import_job TEXT NOT NULL DEFAULT ''")


def number(value,minimum=0):
    if type(value) is not int or not minimum<=value<=1000000000:
        raise ValueError(tr('Quantité entière invalide.'))
    return value


def save_session(db,kind,name,body,identity=None,expected=None):
    if kind not in ('storage_draft','count') or not name.strip():
        raise ValueError(tr('Nom de la session obligatoire.'))
    identity=identity or uuid.uuid4().hex
    payload=json.dumps(body,ensure_ascii=False,allow_nan=False)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT * FROM collection_sessions WHERE id=?',(identity,)).fetchone()
        if current and (current['kind']!=kind or expected is not None and current['body']!=expected):
            raise ValueError(tr('Cette session a changé dans une autre fenêtre. Rouvre-la.'))
        c.execute('''INSERT INTO collection_sessions(id,kind,name,body) VALUES(?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET name=excluded.name,body=excluded.body,updated=CURRENT_TIMESTAMP''',
          (identity,kind,name.strip(),payload))
    return identity


def sessions(db,kind):
    return db.rows('SELECT * FROM collection_sessions WHERE kind=? ORDER BY updated DESC,rowid DESC',(kind,))


def session(db,identity,kind):
    rows=db.rows('SELECT * FROM collection_sessions WHERE id=? AND kind=?',(identity,kind))
    if not rows:raise ValueError(tr('Session introuvable.'))
    result=rows[0];result['data']=json.loads(result['body']);return result


def start_count(db,kind,identity,name=None):
    with db.read() as c:
        c.execute('BEGIN')
        if kind=='cabinet':
            wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(identity,)).fetchone()
            if not wall:raise ValueError(tr('Meuble introuvable.'))
            rows=[dict(row) for row in c.execute('''SELECT i.id AS item_id,i.source,i.kind,i.ref,i.name,p.color,
              p.quantity AS expected,d.id AS drawer_id,d.col,d.row,d.name AS drawer_name
              FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN items i ON i.id=p.item_id
              WHERE d.wall_id=? ORDER BY d.row,d.col,i.ref,p.color''',(identity,))]
            title=wall['name']
        elif kind=='set':
            item=db.get_item(identity)
            if not item or item['kind']!='set':raise ValueError(tr('Choisis un set.'))
            parts=db.components(item,strict=True)
            rows=[dict(item_id=p['id'],source=p['source'],kind=p['kind'],ref=p['ref'],name=p['name'],color=str(p.get('chosen_color','')),expected=int(p.get('chosen_quantity',1)),drawer_id=None) for p in parts if not p.get('is_spare')]
            title=item['ref']+' · '+item['name']
        else:raise ValueError(tr('Source d’inventaire inconnue.'))
        if not rows:raise ValueError(tr('Aucune pièce à compter.'))
        for row in rows:row['counted']=None
    return save_session(db,'count',name or title,{'version':1,'source':kind,'source_id':identity,'rows':rows})


def count_totals(body):
    rows=body['rows'];known=[r for r in rows if r['counted'] is not None and r['expected'] is not None]
    return dict(remaining=sum(r['counted'] is None for r in rows),
                missing=sum(max(0,r['expected']-r['counted']) for r in known),
                surplus=sum(max(0,r['counted']-r['expected']) for r in known),
                counted=sum(r['counted'] or 0 for r in rows))


def save_count(db,identity,counts,expected_body):
    old=session(db,identity,'count');body=old['data']
    if len(counts)!=len(body['rows']):raise ValueError(tr('Inventaire incompatible.'))
    for row,value in zip(body['rows'],counts):row['counted']=None if value is None else number(value)
    save_session(db,'count',old['name'],body,identity,expected_body)
    return session(db,identity,'count')


def create_lot(db,name,provenance='',price_cents=0,comment=''):
    if not name.strip():raise ValueError(tr('Nom du lot obligatoire.'))
    number(price_cents);identity=uuid.uuid4().hex
    with db.connect() as c:
        c.execute('INSERT INTO purchase_lots(id,name,provenance,price_cents,comment) VALUES(?,?,?,?,?)',
                  (identity,name.strip(),provenance.strip(),price_cents,comment.strip()))
    return identity


def record_lot_actions(c,identity,actions,name=None):
    """Called in the stock transaction, before its single undo record is made."""
    if name is not None:c.execute('INSERT OR IGNORE INTO purchase_lots(id,name) VALUES(?,?)',(identity,name))
    lot=c.execute('SELECT cancelled FROM purchase_lots WHERE id=?',(identity,)).fetchone()
    if not lot:raise ValueError(tr('Lot introuvable ou déjà annulé.'))
    if lot['cancelled']:raise ValueError(tr('Ce lot a été annulé.'))
    for action in actions:
        if action['op'] not in ('add','attach') or action.get('scope','stock') not in ('stock','stock_sets'):continue
        scope=action.get('scope','stock');qty=action.get('quantity',0) if action['op']=='add' else 0
        if action['op']=='attach':
            target=c.execute('SELECT item_id,color FROM stock_sets WHERE id=?',(action['entry_id'],)).fetchone()
            if not target:raise ValueError(tr('Set absent du stock'))
            iid,color=target['item_id'],target['color']
        else:iid,color=action['item_id'],str(action.get('color',''))
        previous=c.execute('SELECT * FROM purchase_lot_entries WHERE lot_id=? AND scope=? AND item_id=? AND color=?',(identity,scope,iid,color)).fetchone()
        parts=Counter()
        for part in json.loads(previous['components']) if previous else []:parts[(part['item_id'],str(part['color']))]+=part['quantity']
        for part in action.get('components',[]):parts[(part['item_id'],str(part['color']))]+=part['quantity']*(qty if action['op']=='add' else 1)
        payload=json.dumps([dict(item_id=k[0],color=k[1],quantity=v) for k,v in sorted(parts.items())])
        c.execute('''INSERT INTO purchase_lot_entries VALUES(?,?,?,?,?,?) ON CONFLICT(lot_id,scope,item_id,color)
           DO UPDATE SET quantity=excluded.quantity,components=excluded.components''',
           (identity,scope,iid,color,qty+(previous['quantity'] if previous else 0),payload))


def add_to_lot(db,identity,item_id,color,quantity,scope='stock'):
    from .stock import mutate
    action=db.stock_action(scope,item_id,str(color),number(quantity,1));action['lot_id']=identity
    return mutate(db,[action],tr('Ajout de pièces à un lot'))


def cancel_lot(db,identity):
    """Subtract only this lot, refusing consumed, located or reserved quantities."""
    from .action_history import change
    tables=('stock','stock_sets','stock_set_components','purchase_lots')
    with db.connect() as c,change(c,tables,tr('Annulation d’un lot d’achat')):
        lot=c.execute('SELECT * FROM purchase_lots WHERE id=?',(identity,)).fetchone()
        if not lot or lot['cancelled']:raise ValueError(tr('Lot introuvable ou déjà annulé.'))
        for entry in c.execute('SELECT * FROM purchase_lot_entries WHERE lot_id=?',(identity,)).fetchall():
            scope=entry['scope']
            if scope not in ('stock','stock_sets'):raise ValueError(tr('Destination inconnue'))
            current=c.execute('SELECT * FROM '+scope+' WHERE item_id=? AND color=?',(entry['item_id'],entry['color'])).fetchone()
            if not current or current['quantity']<entry['quantity']:raise ValueError(tr('Ce lot n’est plus entièrement disponible dans le stock.'))
            c.execute('UPDATE '+scope+' SET quantity=quantity-? WHERE id=?',(entry['quantity'],current['id']))
            for part in json.loads(entry['components']):
                key=(current['id'],part['item_id'],part['color'])
                available=c.execute('SELECT quantity FROM stock_set_components WHERE set_entry_id=? AND item_id=? AND color=?',key).fetchone()
                if not available or available['quantity']<part['quantity']:raise ValueError(tr('L’inventaire du lot a changé. Annulation impossible.'))
                c.execute('UPDATE stock_set_components SET quantity=quantity-? WHERE set_entry_id=? AND item_id=? AND color=?',(part['quantity'],)+key)
            c.execute('DELETE FROM stock_set_components WHERE quantity=0')
        c.execute('UPDATE purchase_lots SET cancelled=1 WHERE id=?',(identity,))


def validate_picks(c):
    bad=c.execute('''SELECT p.project_id FROM project_physical_picks p JOIN project_parts r
      ON r.project_id=p.project_id AND r.item_id=p.item_id AND r.color=p.need_color
      GROUP BY p.project_id,p.item_id,p.need_color HAVING SUM(p.quantity)>MAX(r.reserved) LIMIT 1''').fetchone()
    if not bad:
        bad=c.execute('''SELECT k.project_id FROM project_physical_picks k JOIN construction_projects p ON p.id=k.project_id
          WHERE (p.ignore_colors=0 AND k.color<>k.need_color) OR (p.ignore_colors=1 AND
          (SELECT COALESCE(SUM(x.quantity),0) FROM project_physical_picks x WHERE x.project_id=k.project_id
          AND x.item_id=k.item_id AND x.need_color=k.need_color AND x.color=k.color)>
          (SELECT COALESCE(SUM(a.quantity),0) FROM project_color_reservations a WHERE a.project_id=k.project_id
          AND a.item_id=k.item_id AND a.color=k.need_color AND a.stock_color=k.color)) LIMIT 1''').fetchone()
    if bad:raise ValueError(tr('Remets les pièces prélevées dans leurs tiroirs avant de libérer ou réduire la réservation.'))
    bad=c.execute('''WITH allocated AS (
      SELECT item_id,color,COALESCE(quantity,0) AS quantity FROM storage_contents
      UNION ALL SELECT item_id,color,quantity FROM project_physical_picks)
      SELECT a.item_id FROM allocated a LEFT JOIN stock s ON s.item_id=a.item_id AND s.color=a.color
      GROUP BY a.item_id,a.color HAVING SUM(a.quantity)>COALESCE(MAX(s.quantity),0) LIMIT 1''').fetchone()
    if bad:raise ValueError(tr('Les quantités dans les tiroirs et prélevées pour les projets dépassent le stock.'))


def pick_list(db,project_id):
    """Suggest only counted physical locations, after accounting for prior picks."""
    rows=[]
    with db.read() as c:
        c.execute('BEGIN')
        from .project_colors import enabled,pick_list as color_pick_list
        if not c.execute('SELECT 1 FROM construction_projects WHERE id=?',(project_id,)).fetchone():return []
        if enabled(c,project_id):return color_pick_list(c,project_id)
        for part in c.execute('''SELECT p.*,i.ref,i.name,i.source FROM project_parts p JOIN items i ON i.id=p.item_id
          WHERE p.project_id=? ORDER BY i.ref,p.color''',(project_id,)).fetchall():
            taken=c.execute('SELECT COALESCE(SUM(quantity),0) FROM project_physical_picks WHERE project_id=? AND item_id=? AND need_color=?',(project_id,part['item_id'],part['color'])).fetchone()[0]
            needed=part['required']-taken
            for location in c.execute('''SELECT d.id AS drawer_id,d.col,d.row,w.name AS cabinet,p.quantity
              FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN storage_walls w ON w.id=d.wall_id
              WHERE p.item_id=? AND p.color=? AND p.quantity>0 ORDER BY w.y,w.x,w.id,d.row,d.col''',(part['item_id'],part['color'])):
                quantity=min(needed,location['quantity'])
                if quantity:rows.append(dict(part,**dict(location),suggested=quantity,taken=taken));needed-=quantity
            if needed:rows.append(dict(part,drawer_id=None,cabinet=tr('Sans emplacement compté'),suggested=needed,taken=taken,col=None,row=None))
    return rows


def picked_list(db,project_id):
    """Keep completed picks, grouped by their actual reference, colour and drawer."""
    return db.rows('''SELECT COALESCE(w.name,?) AS cabinet,d.col,d.row,p.drawer_id,p.item_id,
      i.source,i.ref,p.color,SUM(p.quantity) AS quantity
      FROM project_physical_picks p LEFT JOIN storage_drawers d ON d.id=p.drawer_id
      LEFT JOIN storage_walls w ON w.id=d.wall_id JOIN items i ON i.id=p.item_id
      WHERE p.project_id=? GROUP BY p.drawer_id,p.item_id,p.color
      ORDER BY w.y,w.x,w.id,d.row,d.col,i.source,i.ref,p.color''',(tr('Aucun tiroir défini'),project_id))


def pick(db,project_id,item_id,color,drawer_id,quantity,expected=None,need_color=None):
    from .action_history import change
    from .project_colors import enabled,reserve as reserve_colors
    number(quantity,1);color=str(color);need_color=color if need_color is None else str(need_color)
    with db.connect() as c,change(c,('project_parts','project_color_reservations','storage_contents','project_pick_rows','project_color_pick_rows'),tr('Prélèvement de pièces pour un projet')):
        ignore=enabled(c,project_id)
        part=c.execute('SELECT * FROM project_parts WHERE project_id=? AND item_id=? AND color=?',(project_id,item_id,need_color)).fetchone()
        location=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer_id,item_id,color)).fetchone()
        if not part or not location or location['quantity'] is None or location['quantity']<quantity or expected is not None and expected!=location['quantity']:
            raise ValueError(tr('Le contenu du tiroir a changé. Actualise la liste.'))
        taken=c.execute('SELECT COALESCE(SUM(quantity),0) FROM project_physical_picks WHERE project_id=? AND item_id=? AND need_color=?',(project_id,item_id,need_color)).fetchone()[0]
        if taken+quantity>part['required']:raise ValueError(tr('La quantité prélevée dépasse les besoins du projet.'))
        reserve=max(part['reserved'],taken+quantity)
        if ignore:
            taken_color=c.execute('SELECT COALESCE(SUM(quantity),0) FROM project_physical_picks WHERE project_id=? AND item_id=? AND need_color=? AND color=?',(project_id,item_id,need_color,color)).fetchone()[0]
            reserve_colors(c,project_id,part,reserve,{color:taken_color+quantity})
        else:
            from .projects import free
            if color!=need_color or reserve>free(c,item_id,color,project_id):raise ValueError(tr('Ces pièces sont réservées à un autre projet.'))
            c.execute('UPDATE project_parts SET reserved=? WHERE project_id=? AND item_id=? AND color=?',(reserve,project_id,item_id,need_color))
        c.execute('UPDATE storage_contents SET quantity=quantity-? WHERE drawer_id=? AND item_id=? AND color=?',(quantity,drawer_id,item_id,color))
        if ignore:
            c.execute('''INSERT INTO project_color_pick_rows VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,item_id,color,stock_color,drawer_id)
              DO UPDATE SET quantity=project_color_pick_rows.quantity+excluded.quantity''',(project_id,item_id,need_color,color,drawer_id,quantity))
        else:
            c.execute('''INSERT INTO project_pick_rows VALUES(?,?,?,?,?) ON CONFLICT(project_id,item_id,color,drawer_id)
              DO UPDATE SET quantity=project_pick_rows.quantity+excluded.quantity''',(project_id,item_id,color,drawer_id,quantity))


def return_picks(db,project_id):
    from .action_history import change
    from .project_picks import TABLES as PICK_TABLES
    with db.connect() as c,change(c,('storage_contents',)+PICK_TABLES,tr('Retour des prélèvements dans les tiroirs')):
        for row in c.execute('SELECT * FROM project_physical_picks WHERE project_id=?',(project_id,)).fetchall():
            if row['drawer_id'] is None:continue
            existing=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(row['drawer_id'],row['item_id'],row['color'])).fetchone()
            if existing and existing['quantity'] is None:raise ValueError(tr('Renseigne la quantité du tiroir avant de retourner les pièces.'))
            c.execute('''INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)
              ON CONFLICT(drawer_id,item_id,color) DO UPDATE SET quantity=storage_contents.quantity+excluded.quantity''',
              (row['drawer_id'],row['item_id'],row['color'],row['quantity']))
        for table in PICK_TABLES:c.execute('DELETE FROM '+table+' WHERE project_id=?',(project_id,))


def compare_builds(db,candidates,ignore_colors=False,exclude_minifigs=False,include_set_stock=True,allow_alternatives=False,excluded_entries=None):
    """Exact maximum count among at most 16 user-chosen construction bundles."""
    from .build_stock import InventoryReader
    candidates=list(candidates)
    if not 1<=len(candidates)<=16:raise ValueError(tr('Choisis entre 1 et 16 sets à comparer.'))
    if len({identity for identity,copies in candidates})!=len(candidates):raise ValueError(tr('Un set est déjà dans la comparaison.'))
    with db.connect() as c:
        c.execute('BEGIN')
        reader=InventoryReader(c,ignore_colors,excluded_entries,exclude_minifigs,include_set_stock,allow_alternatives)
        available=reader.stock();choices=[]
        for identity,copies in candidates:
            number(copies,1)
            item=c.execute("SELECT * FROM items WHERE id=? AND kind='set'",(identity,)).fetchone()
            if not item:raise ValueError(tr('Choisis un set.'))
            required,complete=reader.inventory(item['source'],item['kind'],item['ref'])
            if not complete or not required:raise ValueError(tr('Inventaire incomplet : ')+item['ref'])
            choices.append(dict(item,required=Counter({k:v*copies for k,v in required.items()}),copies=copies))
        best=[];best_score=(0,0)
        def explore(index,remaining,selected,copies=0):
            nonlocal best,best_score
            score=(copies,len(selected))
            if score>best_score:best=list(selected);best_score=score
            bound=(copies+sum(row['copies'] for row in choices[index:]),len(selected)+len(choices)-index)
            if bound<=best_score:return
            for n in range(index,len(choices)):
                required=choices[n]['required']
                if all(remaining[k]>=v for k,v in required.items()):explore(n+1,remaining-required,selected+[n],copies+choices[n]['copies'])
        explore(0,available,[])
        used=Counter()
        for index in best:used.update(choices[index]['required'])
        return dict(choices=choices,selected=best,available=available,remaining=available-used,stock_revision=c.execute('SELECT version FROM stock_revision WHERE id=1').fetchone()[0],
                    warnings=list(reader.warnings) if hasattr(reader,'warnings') else [],ignore_colors=bool(ignore_colors),include_set_stock=bool(include_set_stock))


def correct_lot_quantity(db,lot_id,scope,item_id,color,quantity):
    """Correct one tracked contribution, without altering another lot."""
    from .action_history import change,snapshot
    from .storage_quantities import follow_stock_additions
    number(quantity);color=str(color)
    if scope not in ('stock','stock_sets'):raise ValueError(tr('Destination inconnue'))
    with db.connect() as c,change(c,('stock','stock_sets','stock_set_components','storage_contents','purchase_lot_entries'),tr('Correction d’une quantité de lot')):
        lot=c.execute('SELECT * FROM purchase_lots WHERE id=? AND cancelled=0',(lot_id,)).fetchone()
        entry=c.execute('SELECT * FROM purchase_lot_entries WHERE lot_id=? AND scope=? AND item_id=? AND color=?',(lot_id,scope,item_id,color)).fetchone()
        if not lot or not entry:raise ValueError(tr('Lot introuvable ou déjà annulé.'))
        old=entry['quantity'];delta=quantity-old
        if not delta:return
        parts=json.loads(entry['components'])
        if parts and (not old or any(p['quantity']%old for p in parts)):
            raise ValueError(tr('Ce lot contient un inventaire attaché. Annule ses apports puis importe l’inventaire corrigé.'))
        current=c.execute('SELECT * FROM '+scope+' WHERE item_id=? AND color=?',(item_id,color)).fetchone()
        if not current or current['quantity']+delta<0:raise ValueError(tr('Ce lot n’est plus entièrement disponible dans le stock.'))
        before=snapshot(c,('stock',))['stock']
        c.execute('UPDATE '+scope+' SET quantity=quantity+?'+(',last_added=CURRENT_TIMESTAMP' if delta>0 else '')+' WHERE id=?',(delta,current['id']))
        for part in parts:
            unit=part['quantity']//old;difference=unit*delta;key=(current['id'],part['item_id'],part['color'])
            found=c.execute('SELECT quantity FROM stock_set_components WHERE set_entry_id=? AND item_id=? AND color=?',key).fetchone()
            if (found['quantity'] if found else 0)+difference<0:raise ValueError(tr('L’inventaire du lot a changé. Annulation impossible.'))
            c.execute('''INSERT INTO stock_set_components VALUES(?,?,?,?) ON CONFLICT(set_entry_id,item_id,color)
              DO UPDATE SET quantity=stock_set_components.quantity+excluded.quantity''',key+(difference,))
            part['quantity']=unit*quantity
        c.execute('DELETE FROM stock_set_components WHERE quantity=0')
        c.execute('UPDATE purchase_lot_entries SET quantity=?,components=? WHERE lot_id=? AND scope=? AND item_id=? AND color=?',(quantity,json.dumps(parts),lot_id,scope,item_id,color))
        follow_stock_additions(c,before)


def create_comparison_projects(db,result,exclude_minifigs=False,allow_alternatives=False,ignore_colors=None):
    """Prepare all requirements first; publish the selected projects atomically."""
    from .action_history import change
    from .projects import equivalent_parts
    if ignore_colors is None:ignore_colors=result.get('ignore_colors',False)
    if type(ignore_colors) is not bool:raise ValueError(tr('Réglage des couleurs du projet invalide.'))
    include_set_stock=result.get('include_set_stock',False)
    if type(include_set_stock) is not bool:raise ValueError(tr('Réglage du stock du projet invalide.'))
    prepared=[]
    for index in result['selected']:
        choice=result['choices'][index];item=db.get_item(choice['id'])
        if not item or item['source']!=choice['source'] or item['ref']!=choice['ref']:raise ValueError(tr('Les références des sets ont changé. Relance la comparaison.'))
        components=db.components(item,strict=True,exclude_minifigs=exclude_minifigs)
        parts=[dict(item_id=p['id'],color=str(p.get('chosen_color','')),quantity=int(p.get('chosen_quantity',1))*choice['copies']) for p in components if not p.get('is_spare')]
        if not parts:raise ValueError(tr('Charge d’abord l’inventaire complet de ce set.'))
        if allow_alternatives:parts=equivalent_parts(db,parts,ignore_colors=ignore_colors)
        prepared.append((item,choice['copies'],parts))
    identities=[]
    with db.connect() as c,change(c,('construction_projects','project_parts'),tr('Création des projets comparés')):
        if result.get('stock_revision') is not None and c.execute('SELECT version FROM stock_revision WHERE id=1').fetchone()[0]!=result['stock_revision']:raise ValueError(tr('Le stock a changé. Relance la comparaison avant de créer les projets.'))
        for item,copies,parts in prepared:
            current=c.execute('SELECT source,ref FROM items WHERE id=?',(item['id'],)).fetchone()
            if not current or (current['source'],current['ref'])!=(item['source'],item['ref']):raise ValueError(tr('Les références des sets ont changé. Relance la comparaison.'))
            identity=c.execute('INSERT INTO construction_projects(name,set_id,copies,ignore_colors,include_set_stock) VALUES(?,?,?,?,?)',(item['ref']+' · '+item['name'],item['id'],copies,int(ignore_colors),int(include_set_stock))).lastrowid
            totals=Counter()
            for part in parts:totals[(part['item_id'],part['color'])]+=number(part['quantity'],1)
            c.executemany('INSERT INTO project_parts(project_id,item_id,color,required) VALUES(?,?,?,?)',[(identity,k[0],k[1],number(v,1)) for k,v in totals.items()]);identities.append(identity)
    return identities
