"""Shared project shortages, purchase tracking and idempotent stock receipts."""
from collections import Counter
import json
import uuid
import xml.etree.ElementTree as ET

from .i18n import tr

TABLES=('shopping_lists','shopping_projects','shopping_rows','shopping_receipts')


def prepare(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS shopping_lists(
        id TEXT PRIMARY KEY,name TEXT NOT NULL,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS shopping_projects(
        list_id TEXT NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
        project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
        priority INTEGER NOT NULL,PRIMARY KEY(list_id,project_id));
        CREATE TABLE IF NOT EXISTS shopping_rows(
        list_id TEXT NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,item_id INTEGER NOT NULL REFERENCES items(id),
        color TEXT NOT NULL,target INTEGER NOT NULL CHECK(target>=0),ordered INTEGER NOT NULL DEFAULT 0 CHECK(ordered>=0),
        received INTEGER NOT NULL DEFAULT 0 CHECK(received>=0),bl_ref TEXT NOT NULL DEFAULT '',bl_color TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(list_id,item_id,color));
        CREATE TABLE IF NOT EXISTS shopping_receipts(
        id TEXT PRIMARY KEY,list_id TEXT NOT NULL REFERENCES shopping_lists(id),item_id INTEGER NOT NULL REFERENCES items(id),
        need_color TEXT NOT NULL,actual_color TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),
        lot_id TEXT NOT NULL REFERENCES purchase_lots(id),created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);''')


def shortages(c,project_ids):
    """Spend each free physical unit once in the displayed project priority order."""
    from .project_stock import owned_sets
    from .set_allocations import pool
    ids=list(dict.fromkeys(project_ids))
    if not ids:raise ValueError(tr('Choisis au moins un projet.'))
    loose=Counter({(r['item_id'],str(r['color'])):int(r['quantity']) for r in c.execute('SELECT item_id,color,quantity FROM stock WHERE quantity>0')})
    for r in c.execute('SELECT item_id,color,SUM(reserved) AS q FROM project_stock_reservations GROUP BY item_id,color'):loose[(r['item_id'],str(r['color']))]-=r['q']
    loose=+loose;sets,warnings=owned_sets(c);result=Counter();details=[]
    def take(stock,identity,color,quantity,ignore):
        keys=sorted((k for k in stock if k[0]==identity),key=lambda k:(k[1]!=color,k[1])) if ignore else [(identity,color)]
        for key in keys:
            used=min(quantity,stock[key]);stock[key]-=used;quantity-=used
            if not quantity:break
        return quantity
    for project_id in ids:
        p=c.execute('SELECT * FROM construction_projects WHERE id=?',(project_id,)).fetchone()
        if not p:raise ValueError(tr('Projet introuvable.'))
        selected=c.execute('SELECT 1 FROM project_set_sources WHERE project_id=?',(project_id,)).fetchone()
        set_pool=pool(c,project_id,sets) if p['include_set_stock'] else Counter()
        if selected:set_pool=set_pool.copy()
        for part in c.execute('SELECT * FROM project_parts WHERE project_id=? ORDER BY item_id,color',(project_id,)):
            need=max(0,part['required']-part['reserved'])
            need=take(loose,part['item_id'],part['color'],need,p['ignore_colors'])
            need=take(set_pool,part['item_id'],part['color'],need,p['ignore_colors'])
            if need:
                color='*' if p['ignore_colors'] else str(part['color']);result[(part['item_id'],color)]+=need
                details.append(dict(project_id=project_id,project_name=p['name'],item_id=part['item_id'],color=color,quantity=need))
    return result,details,warnings


def create(db,name,project_ids):
    from .action_history import change
    if not name.strip():raise ValueError(tr('Nom de la liste obligatoire.'))
    project_ids=list(dict.fromkeys(project_ids));identity=uuid.uuid4().hex
    with db.connect() as c,change(c,TABLES,tr('Création d’une liste d’achats')):
        needs,_,_=shortages(c,project_ids)
        c.execute('INSERT INTO shopping_lists(id,name) VALUES(?,?)',(identity,name.strip()))
        c.executemany('INSERT INTO shopping_projects VALUES(?,?,?)',[(identity,p,index) for index,p in enumerate(project_ids)])
        c.executemany('INSERT INTO shopping_rows(list_id,item_id,color,target) VALUES(?,?,?,?)',[(identity,i,color,q) for (i,color),q in needs.items()])
    return identity


def recalculate(db,list_id):
    from .action_history import change
    with db.connect() as c,change(c,('shopping_rows',),tr('Recalcul d’une liste d’achats')):
        projects=[r[0] for r in c.execute('SELECT project_id FROM shopping_projects WHERE list_id=? ORDER BY priority',(list_id,))]
        needs,details,warnings=shortages(c,projects)
        existing={(r['item_id'],r['color']):dict(r) for r in c.execute('SELECT * FROM shopping_rows WHERE list_id=?',(list_id,))}
        for key in needs.keys()|existing.keys():
            old=existing.get(key,{});target=old.get('received',0)+needs[key]
            c.execute('INSERT INTO shopping_rows(list_id,item_id,color,target) VALUES(?,?,?,?) ON CONFLICT(list_id,item_id,color) DO UPDATE SET target=excluded.target',(list_id,*key,target))
    return details,warnings


def rows(db,list_id):
    result=db.rows('SELECT r.*,i.source,i.kind,i.ref,i.name,i.origin_source,i.origin_ref FROM shopping_rows r JOIN items i ON i.id=r.item_id WHERE list_id=? ORDER BY i.source,i.ref,r.color',(list_id,))
    for row in result:
        row['missing']=max(0,row['target']-row['received']);row['to_order']=max(0,row['missing']-max(0,row['ordered']-row['received']))
    return result


def set_ordered(db,list_id,item_id,color,quantity):
    from .action_history import change
    if type(quantity) is not int or not 0<=quantity<=1000000000:raise ValueError(tr('Quantité entière invalide.'))
    with db.connect() as c,change(c,('shopping_rows',),tr('Suivi d’une commande')):
        row=c.execute('SELECT * FROM shopping_rows WHERE list_id=? AND item_id=? AND color=?',(list_id,item_id,str(color))).fetchone()
        if not row or quantity<row['received']:raise ValueError(tr('La quantité commandée ne peut pas être inférieure à la quantité reçue.'))
        c.execute('UPDATE shopping_rows SET ordered=? WHERE list_id=? AND item_id=? AND color=?',(quantity,list_id,item_id,str(color)))


def receive(db,list_id,item_id,color,quantity,actual_color=None,expected_received=None,receipt_id=None):
    from .action_history import change,snapshot
    from .stock import _apply
    from .collection_workflows import record_lot_actions
    from .storage_quantities import follow_stock_additions
    if type(quantity) is not int or not 1<=quantity<=1000000000:raise ValueError(tr('Quantité entière invalide.'))
    color=str(color);actual_color=color if actual_color is None else str(actual_color)
    if actual_color=='*' or color!='*' and color!=actual_color:raise ValueError(tr('Indique la couleur réellement reçue.'))
    action=db.stock_action('stock',item_id,actual_color,quantity);receipt_id=receipt_id or uuid.uuid4().hex
    tables=TABLES+('stock','storage_contents','purchase_lots','purchase_lot_entries')
    with db.connect() as c,change(c,tables,tr('Réception des pièces commandées')):
        previous=c.execute('SELECT * FROM shopping_receipts WHERE id=?',(receipt_id,)).fetchone()
        if previous:
            if (previous['list_id'],previous['item_id'],previous['need_color'],previous['actual_color'],previous['quantity'])!=(list_id,item_id,color,actual_color,quantity):raise ValueError(tr('Identifiant de réception déjà utilisé.'))
            return receipt_id
        row=c.execute('SELECT * FROM shopping_rows WHERE list_id=? AND item_id=? AND color=?',(list_id,item_id,color)).fetchone()
        if not row or expected_received is not None and row['received']!=expected_received:raise ValueError(tr('Cette ligne a changé. Actualise la liste avant de recevoir les pièces.'))
        if row['received']+quantity>max(row['target'],row['ordered']):raise ValueError(tr('La réception dépasse la quantité prévue ou commandée.'))
        before=snapshot(c,('stock',))['stock'];_apply(c,action)
        lot_id=uuid.uuid4().hex;record_lot_actions(c,lot_id,[action],tr('Réception de commande'))
        c.execute('UPDATE shopping_rows SET received=received+?,ordered=MAX(ordered,received+?) WHERE list_id=? AND item_id=? AND color=?',(quantity,quantity,list_id,item_id,color))
        c.execute('INSERT INTO shopping_receipts(id,list_id,item_id,need_color,actual_color,quantity,lot_id) VALUES(?,?,?,?,?,?,?)',(receipt_id,list_id,item_id,color,actual_color,quantity,lot_id));follow_stock_additions(c,before)
    return receipt_id


def set_mapping(db,list_id,item_id,color,reference,bl_color):
    import re
    from .action_history import change
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',reference) or bl_color and not re.fullmatch(r'[0-9]{1,6}',bl_color):raise ValueError(tr('Correspondance BrickLink invalide.'))
    with db.connect() as c,change(c,('shopping_rows',),tr('Correspondance pour la liste d’achats')):
        c.execute('UPDATE shopping_rows SET bl_ref=?,bl_color=? WHERE list_id=? AND item_id=? AND color=?',(reference,bl_color,list_id,item_id,str(color)))


def bricklink_mapping(db,row):
    source=row['origin_source'] if row['source']=='ALT' else row['source'];ref=row['origin_ref'] if row['source']=='ALT' else row['ref']
    reference=row['bl_ref']
    if not reference and source=='BL':reference=ref
    if not reference and source=='RB':
        value=db.setting('rb_bricklink_refs_'+row['kind']+'_'+ref,[])
        if isinstance(value,list) and len(value)==1 and isinstance(value[0],str):reference=value[0]
    color=row['bl_color']
    if row['color']=='*':color=''
    elif not color and source=='BL':color=row['color']
    elif not color and source=='RB':
        from .color_links import rb_palette
        external=rb_palette().get(str(row['color']),{}).get('external',{}).get('BL',[])
        ids=list(dict.fromkeys(e['id'] for e in external))
        if len(ids)==1:color=str(ids[0])
    issue='' if reference and (color or row['color']=='*' or row['kind']=='minifig') else tr('Correspondance BrickLink à renseigner')
    return reference,color,issue


def wanted_xml(db,list_id,path):
    from .fileio import atomic_output
    root=ET.Element('INVENTORY');missing=[]
    for row in rows(db,list_id):
        if not row['to_order']:continue
        ref,color,issue=bricklink_mapping(db,row)
        if issue:missing.append(row['source']+' '+row['ref']+' / '+row['color']);continue
        item=ET.SubElement(root,'ITEM')
        for key,value in [('ITEMTYPE','M' if row['kind']=='minifig' else 'P'),('ITEMID',ref),('MINQTY',str(row['to_order']))]:ET.SubElement(item,key).text=value
        if color:ET.SubElement(item,'COLOR').text=color
    if missing:raise ValueError(tr('Complète les correspondances avant l’export : ')+', '.join(missing[:20]))
    # BrickLink mass upload expects INVENTORY without an XML declaration:
    # https://www.bricklink.com/help.asp?helpID=207
    with atomic_output(path) as temporary:ET.ElementTree(root).write(temporary,encoding='utf-8',xml_declaration=False)
    return path
