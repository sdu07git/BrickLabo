"""Separate loose stock and owned set components; atomic single-action undo."""
import json
import sqlite3
from contextlib import closing,nullcontext
from .i18n import tr
from .sqlite_file import connect

TABLES={'stock':('id',),'stock_sets':('id',),'stock_set_components':('set_entry_id','item_id','color'),'queue':('id',),'settings':('key',)}

def prepare(db,c):
    legacy=list(c.execute("SELECT s.* FROM stock s JOIN items i ON i.id=s.item_id WHERE i.kind='set'"))
    if legacy and not c.execute("SELECT 1 FROM settings WHERE key='stock_layout_v37'").fetchone():
        folder=db.path.parent/'sauvegardes';folder.mkdir(exist_ok=True);snapshot=folder/'avant_v37.sqlite'
        if not snapshot.exists():
            with closing(connect(db.path)) as source,closing(connect(snapshot)) as target:source.backup(target)
    c.executescript('''CREATE TABLE IF NOT EXISTS stock_sets(id INTEGER PRIMARY KEY,item_id INTEGER,color TEXT DEFAULT '',quantity INTEGER NOT NULL,added TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(item_id,color));
    CREATE TABLE IF NOT EXISTS stock_undo(id INTEGER PRIMARY KEY CHECK(id=1),description TEXT NOT NULL,changes TEXT NOT NULL);
    CREATE VIEW IF NOT EXISTS stock_available AS SELECT s.id,s.item_id,s.color,s.quantity+COALESCE((SELECT SUM(p.quantity) FROM stock_set_components p JOIN stock_sets o ON o.id=p.set_entry_id WHERE p.item_id=s.item_id AND p.color=s.color),0) AS quantity,s.added FROM stock s UNION ALL SELECT -id,item_id,color,quantity,added FROM stock_sets;''')
    c.executescript('CREATE TABLE IF NOT EXISTS stock_revision(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL); INSERT OR IGNORE INTO stock_revision VALUES(1,0);')
    for table in ('stock','stock_sets','stock_set_components'):
        for action in ('INSERT','UPDATE','DELETE'):
            c.execute('CREATE TRIGGER IF NOT EXISTS revision_'+table+'_'+action.lower()+' AFTER '+action+' ON '+table+' BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')
    if c.execute("SELECT 1 FROM settings WHERE key='stock_layout_v37'").fetchone():return
    notes=[]
    for row in legacy:
        c.execute('INSERT INTO stock_sets(id,item_id,color,quantity,added) VALUES(?,?,?,?,?)',tuple(row))
        if not c.execute('SELECT 1 FROM stock_set_components WHERE set_entry_id=?',(row['id'],)).fetchone():notes.append(tr('Set conservé sans inventaire suivi : ')+str(row['item_id']))
        c.execute('DELETE FROM stock WHERE id=?',(row['id'],))
        c.execute('UPDATE settings SET key=? WHERE key=?',('label_layout_stock_sets_'+str(row['id']),'label_layout_stock_'+str(row['id'])))
    if legacy:
        for part in list(c.execute('SELECT item_id,color,SUM(quantity) AS quantity FROM stock_set_components GROUP BY item_id,color')):
            old=c.execute('SELECT * FROM stock WHERE item_id=? AND color=?',(part['item_id'],part['color'])).fetchone();have=max(0,int(old['quantity'])) if old else 0
            if have<part['quantity']:
                remaining=have
                for component in list(c.execute('SELECT * FROM stock_set_components WHERE item_id=? AND color=? ORDER BY set_entry_id',(part['item_id'],part['color']))):
                    amount=min(remaining,component['quantity']);remaining-=amount
                    c.execute('UPDATE stock_set_components SET quantity=? WHERE set_entry_id=? AND item_id=? AND color=?',(amount,component['set_entry_id'],component['item_id'],component['color']))
                notes.append(tr('Inventaire de set incomplet conservé : ')+str(part['item_id'])+' / '+str(part['color']))
            c.execute('INSERT INTO stock(item_id,color,quantity) VALUES(?,?,?) ON CONFLICT(item_id,color) DO UPDATE SET quantity=excluded.quantity',(part['item_id'],part['color'],max(0,have-part['quantity'])))
        excluded=c.execute("SELECT value FROM settings WHERE key='build_excluded_entries'").fetchone()
        if excluded:
            sets={row['id'] for row in legacy};c.execute("UPDATE settings SET value=? WHERE key='build_excluded_entries'",(json.dumps([-x if x in sets else x for x in json.loads(excluded['value'])]),))
    c.execute("INSERT INTO settings VALUES('stock_layout_v37','true')")
    if notes:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('stock_migration_report',json.dumps(notes,ensure_ascii=False)))

def _state(c):
    result={}
    for table,keys in TABLES.items():
        sql='SELECT * FROM '+table
        if table=='settings':sql+=" WHERE key LIKE 'label_layout_%' OR key='build_excluded_entries'"
        result[table]={tuple(row[k] for k in keys):dict(row) for row in c.execute(sql)}
    return result

def _loose(c,iid,color,amount):
    if amount==0:
        c.execute('INSERT INTO stock(item_id,color,quantity) VALUES(?,?,0) ON CONFLICT(item_id,color) DO NOTHING',(iid,str(color)));return
    c.execute('INSERT INTO stock(item_id,color,quantity) VALUES(?,?,?) ON CONFLICT(item_id,color) DO UPDATE SET quantity=stock.quantity+excluded.quantity',(iid,str(color),amount))

def _apply(c,action):
    scope=action.get('scope','stock');op=action['op']
    if scope not in ('stock','stock_sets','queue'):raise ValueError(tr('Destination inconnue'))
    if op=='add':
        iid=action['item_id'];qty=int(action['quantity']);color=str(action.get('color',''))
        if qty<1:raise ValueError(tr('Quantité positive requise'))
        c.execute('INSERT INTO '+scope+'(item_id,color,quantity) VALUES(?,?,?) ON CONFLICT(item_id,color) DO UPDATE SET quantity='+scope+'.quantity+excluded.quantity',(iid,color,qty))
        if scope=='stock_sets':
            eid=c.execute('SELECT id FROM stock_sets WHERE item_id=? AND color=?',(iid,color)).fetchone()['id']
            for p in action.get('components',[]):
                amount=int(p['quantity'])*qty
                if amount<1:raise ValueError(tr('Quantité positive requise'))
                c.execute('INSERT INTO stock_set_components VALUES(?,?,?,?) ON CONFLICT(set_entry_id,item_id,color) DO UPDATE SET quantity=stock_set_components.quantity+excluded.quantity',(eid,p['item_id'],str(p['color']),amount));_loose(c,p['item_id'],p['color'],0)
    elif op=='attach':
        eid=int(action['entry_id'])
        if not c.execute('SELECT 1 FROM stock_sets WHERE id=?',(eid,)).fetchone():raise ValueError(tr('Set absent du stock'))
        for p in action['components']:
            amount=int(p['quantity'])
            if amount<1:raise ValueError(tr('Quantité positive requise'))
            c.execute('INSERT INTO stock_set_components VALUES(?,?,?,?) ON CONFLICT(set_entry_id,item_id,color) DO UPDATE SET quantity=stock_set_components.quantity+excluded.quantity',(eid,p['item_id'],str(p['color']),amount));_loose(c,p['item_id'],p['color'],0)
    elif op=='remove':
        for eid in action['ids']:
            if scope=='stock_sets':
                if action.get('keep_parts'):
                    for p in list(c.execute('SELECT * FROM stock_set_components WHERE set_entry_id=?',(eid,))):_loose(c,p['item_id'],p['color'],p['quantity'])
                c.execute('DELETE FROM stock_set_components WHERE set_entry_id=?',(eid,));c.execute('DELETE FROM stock_sets WHERE id=?',(eid,))
            elif scope=='stock':c.execute('UPDATE stock SET quantity=0 WHERE id=?',(eid,))
            else:c.execute('DELETE FROM queue WHERE id=?',(eid,))
            c.execute('DELETE FROM settings WHERE key=?',('label_layout_'+scope+'_'+str(eid),))
    elif op in ('quantity','color'):
        for eid in action['ids']:
            row=c.execute('SELECT * FROM '+scope+' WHERE id=?',(eid,)).fetchone()
            if not row:continue
            if op=='quantity':
                qty=int(action['value'])
                if qty<1:raise ValueError(tr('Quantité positive requise'))
                if scope=='stock_sets':
                    for p in list(c.execute('SELECT * FROM stock_set_components WHERE set_entry_id=?',(eid,))):
                        amount=p['quantity']*qty
                        if amount%row['quantity']:raise ValueError(tr('Ce set contient des quantités personnalisées. Modifie son inventaire avant de changer le nombre de sets.'))
                        c.execute('UPDATE stock_set_components SET quantity=? WHERE set_entry_id=? AND item_id=? AND color=?',(amount//row['quantity'],eid,p['item_id'],p['color']))
                c.execute('UPDATE '+scope+' SET quantity=? WHERE id=?',(qty,eid))
            else:
                color=str(action['value'])
                if color==row['color']:continue
                if scope=='stock':
                    _loose(c,row['item_id'],color,row['quantity']);c.execute('UPDATE stock SET quantity=0 WHERE id=?',(eid,))
                    new_id=c.execute('SELECT id FROM stock WHERE item_id=? AND color=?',(row['item_id'],color)).fetchone()['id']
                    old_key='label_layout_stock_'+str(eid);new_key='label_layout_stock_'+str(new_id)
                    if c.execute('SELECT 1 FROM settings WHERE key=?',(new_key,)).fetchone():c.execute('DELETE FROM settings WHERE key=?',(old_key,))
                    else:c.execute('UPDATE settings SET key=? WHERE key=?',(new_key,old_key))
                    continue
                target=c.execute('SELECT * FROM '+scope+' WHERE item_id=? AND color=?',(row['item_id'],color)).fetchone()
                if target:
                    c.execute('UPDATE '+scope+' SET quantity=quantity+? WHERE id=?',(row['quantity'],target['id']))
                    if scope=='stock_sets':
                        for p in list(c.execute('SELECT * FROM stock_set_components WHERE set_entry_id=?',(eid,))):c.execute('INSERT INTO stock_set_components VALUES(?,?,?,?) ON CONFLICT(set_entry_id,item_id,color) DO UPDATE SET quantity=stock_set_components.quantity+excluded.quantity',(target['id'],p['item_id'],p['color'],p['quantity']))
                        c.execute('DELETE FROM stock_set_components WHERE set_entry_id=?',(eid,))
                    c.execute('DELETE FROM '+scope+' WHERE id=?',(eid,));c.execute('DELETE FROM settings WHERE key=?',('label_layout_'+scope+'_'+str(eid),))
                else:
                    if scope=='stock':
                        _loose(c,row['item_id'],color,row['quantity']);c.execute('UPDATE stock SET quantity=0 WHERE id=?',(eid,))
                        target_id=c.execute('SELECT id FROM stock WHERE item_id=? AND color=?',(row['item_id'],color)).fetchone()['id']
                        c.execute('UPDATE settings SET key=? WHERE key=?',('label_layout_stock_'+str(target_id),'label_layout_stock_'+str(eid)))
                    else:c.execute('UPDATE '+scope+' SET color=? WHERE id=?',(color,eid))
    else:raise ValueError(tr('Action inconnue'))

def mutate(db,actions,description,connection=None):
    with (db.connect() if connection is None else nullcontext(connection)) as c:
        if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
        before=_state(c)
        for action in actions:_apply(c,action)
        after=_state(c);changes=[]
        for table in TABLES:
            for key in before[table].keys()|after[table].keys():
                old=before[table].get(key);new=after[table].get(key)
                if old!=new:changes.append({'table':table,'key':key,'before':old,'after':new})
        if changes:c.execute('INSERT OR REPLACE INTO stock_undo VALUES(1,?,?)',(description,json.dumps(changes,ensure_ascii=False)))
    return bool(changes)

def undo(db):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');journal=c.execute('SELECT * FROM stock_undo WHERE id=1').fetchone()
        if not journal:return False
        changes=json.loads(journal['changes']);state=_state(c)
        if any(state[x['table']].get(tuple(x['key']))!=x['after'] for x in changes):raise ValueError(tr('Le stock a changé depuis cette action ; annulation impossible.'))
        changed_settings={tuple(x['key']) for x in changes if x['table']=='settings'}
        for change in changes:
            if change['table'] in ('stock','stock_sets','queue') and change['before'] is None and change['after']:
                key=('label_layout_'+change['table']+'_'+str(change['after']['id']),)
                if key in state['settings'] and key not in changed_settings:raise ValueError(tr('Le stock a changé depuis cette action ; annulation impossible.'))
        for x in changes:
            table=x['table'];keys=TABLES[table];c.execute('DELETE FROM '+table+' WHERE '+' AND '.join(k+'=?' for k in keys),x['key'])
        for x in changes:
            row=x['before']
            if row:
                keys=list(row);c.execute('INSERT INTO '+x['table']+'('+','.join(keys)+') VALUES('+','.join('?' for k in keys)+')',[row[k] for k in keys])
        c.execute('DELETE FROM stock_undo')
    return True
