"""Separate loose stock and owned set components; transactional undo/redo."""
import json
import sqlite3
from contextlib import closing,nullcontext
from .i18n import tr
from .sqlite_file import connect

TABLES={'purchase_lots':('id',),'purchase_lot_entries':('lot_id','scope','item_id','color'),'stock':('id',),'stock_sets':('id',),'stock_set_components':('set_entry_id','item_id','color'),'queue':('id',),'settings':('key',),'stock_import_jobs':('id',),'stock_import_applied':('job_id','ordinal'),'storage_contents':('drawer_id','item_id','color')}

def prepare(db,c):
    legacy=list(c.execute("SELECT s.* FROM stock s JOIN items i ON i.id=s.item_id WHERE i.kind='set'"))
    if legacy and not c.execute("SELECT 1 FROM settings WHERE key='stock_layout_v37'").fetchone():
        folder=db.path.parent/'sauvegardes';folder.mkdir(exist_ok=True);snapshot=folder/'avant_v37.sqlite'
        if not snapshot.exists():
            with closing(connect(db.path)) as source,closing(connect(snapshot)) as target:source.backup(target)
    c.executescript('''CREATE TABLE IF NOT EXISTS stock_sets(id INTEGER PRIMARY KEY,item_id INTEGER,color TEXT DEFAULT '',quantity INTEGER NOT NULL,added TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(item_id,color));
    CREATE TABLE IF NOT EXISTS stock_undo(id INTEGER PRIMARY KEY CHECK(id=1),description TEXT NOT NULL,changes TEXT NOT NULL);
    CREATE VIEW IF NOT EXISTS stock_available AS SELECT s.id,s.item_id,s.color,s.quantity+COALESCE((SELECT SUM(p.quantity) FROM stock_set_components p JOIN stock_sets o ON o.id=p.set_entry_id WHERE p.item_id=s.item_id AND p.color=s.color),0) AS quantity,s.added FROM stock s UNION ALL SELECT -id,item_id,color,quantity,added FROM stock_sets;''')
    for table in ('stock','stock_sets'):
        if 'last_added' not in {r['name'] for r in c.execute('PRAGMA table_info('+table+')')}:
            c.execute('ALTER TABLE '+table+" ADD COLUMN last_added TEXT NOT NULL DEFAULT ''")
            c.execute('UPDATE '+table+' SET last_added=added')
    c.executescript('CREATE TABLE IF NOT EXISTS stock_revision(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL); INSERT OR IGNORE INTO stock_revision VALUES(1,0);')
    for table in ('stock','stock_sets','stock_set_components'):
        for action in ('INSERT','UPDATE','DELETE'):
            c.execute('CREATE TRIGGER IF NOT EXISTS revision_'+table+'_'+action.lower()+' AFTER '+action+' ON '+table+' BEGIN UPDATE stock_revision SET version=version+1 WHERE id=1; END')
    if c.execute("SELECT 1 FROM settings WHERE key='stock_layout_v37'").fetchone():return
    notes=[]
    for row in legacy:
        c.execute('INSERT INTO stock_sets(id,item_id,color,quantity,added,last_added) VALUES(?,?,?,?,?,?)',tuple(row[k] for k in ('id','item_id','color','quantity','added'))+(row['added'],))
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
    c.execute('INSERT INTO stock(item_id,color,quantity,last_added) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(item_id,color) DO UPDATE SET quantity=stock.quantity+excluded.quantity,last_added=excluded.last_added',(iid,str(color),amount))

def _apply(c,action):
    scope=action.get('scope','stock');op=action['op']
    if op=='import_complete':
        job=action['job_id']
        for ordinal in action['ordinals']:
            c.execute('INSERT INTO stock_import_applied(job_id,ordinal) VALUES(?,?)',(job,ordinal))
        if action.get('target_item_id'):
            entry=c.execute('SELECT id FROM stock_sets WHERE item_id=? AND color=\'\'',(action['target_item_id'],)).fetchone()
            c.execute('UPDATE stock_import_jobs SET target_entry=? WHERE id=?',(entry['id'],job))
        return
    if scope not in ('stock','stock_sets','queue'):raise ValueError(tr('Destination inconnue'))
    if op=='add':
        iid=action['item_id'];qty=int(action['quantity']);color=str(action.get('color',''))
        if qty<1:raise ValueError(tr('Quantité positive requise'))
        date_column=',last_added' if scope in ('stock','stock_sets') else ''
        date_value=',CURRENT_TIMESTAMP' if date_column else ''
        date_update=',last_added=excluded.last_added' if date_column else ''
        c.execute('INSERT INTO '+scope+'(item_id,color,quantity'+date_column+') VALUES(?,?,?'+date_value+') ON CONFLICT(item_id,color) DO UPDATE SET quantity='+scope+'.quantity+excluded.quantity'+date_update,(iid,color,qty))
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
                date_update=',last_added=CURRENT_TIMESTAMP' if scope in ('stock','stock_sets') and qty>row['quantity'] else ''
                c.execute('UPDATE '+scope+' SET quantity=?'+date_update+' WHERE id=?',(qty,eid))
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
        actions=list(actions)
        before=_state(c)
        for action in actions:_apply(c,action)
        from .collection_workflows import record_lot_actions
        completion=next((a for a in actions if a['op']=='import_complete'),None)
        if completion:
            job=c.execute('SELECT filename FROM stock_import_jobs WHERE id=?',(completion['job_id'],)).fetchone()
            if job:
                from pathlib import Path
                import uuid
                job_id=completion['job_id']
                active=c.execute('SELECT id FROM purchase_lots WHERE import_job=? AND cancelled=0 ORDER BY rowid DESC LIMIT 1',(job_id,)).fetchone()
                lot_id=active['id'] if active else uuid.uuid4().hex
                record_lot_actions(c,lot_id,actions,Path(job['filename']).name)
                c.execute('UPDATE purchase_lots SET import_job=? WHERE id=?',(job_id,lot_id))
        else:
            for lot_id in dict.fromkeys(a['lot_id'] for a in actions if a.get('lot_id')):
                record_lot_actions(c,lot_id,[a for a in actions if a.get('lot_id')==lot_id])
        from .storage_quantities import follow_stock_additions
        follow_stock_additions(c,before['stock'])
        from .action_history import validate,record_changes
        validate(c)
        after=_state(c);changes=[]
        for table in TABLES:
            for key in before[table].keys()|after[table].keys():
                old=before[table].get(key);new=after[table].get(key)
                if old!=new:changes.append({'table':table,'key':key,'before':old,'after':new})
        if changes:c.execute('INSERT OR REPLACE INTO stock_undo VALUES(1,?,?)',(description,json.dumps(changes,ensure_ascii=False)))
        record_changes(c,description,changes)
    return bool(changes)

def undo(db):
    from .action_history import restore
    return restore(db)
