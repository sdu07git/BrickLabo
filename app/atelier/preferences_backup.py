"""Portable, selective JSON backups; database identifiers never cross machines."""
import copy
import json
import re
from pathlib import Path
from .data import normalize
from .fileio import atomic_output
from .i18n import tr

FAMILIES={'labels':tr('Modèles d’étiquette'),'colors':tr('Couleurs des catégories'),'views':tr('Vues et rendus 3D'),'loose':tr('Pièces en vrac'),'sets':tr('Sets et leurs pièces'),'queue':tr('Étiquettes à imprimer'),'storage':tr('Meubles et emplacements'),'preferences':tr('Autres préférences'),'api':tr('Clés API (privées)')}
ITEM_KEYS=('camera_item_','architect_model_','architect_photo_choice_','photo_choices_','label_layout_item_')
ENTRY_RE=re.compile(r'^label_layout_(stock_sets|stock|queue|history)_([0-9]+)$')

def identity(item):
    return {k:item.get(k,'') for k in ('source','kind','ref','name','category','image')}

def _portable_key(db,key):
    match=ENTRY_RE.match(key)
    if match:
        scope,eid=match.groups();rows=db.rows('SELECT i.*,s.color FROM '+scope+' s JOIN items i ON i.id=s.item_id WHERE s.id=?',(int(eid),))
        return {'entry':identity(rows[0]),'scope':scope,'color':rows[0]['color']} if rows else None
    for prefix in ITEM_KEYS:
        if key.startswith(prefix) and key[len(prefix):].isdigit():
            item=db.get_item(int(key[len(prefix):]));return {'item':identity(item),'prefix':prefix} if item else None
    return {'key':key}

def _view_key(key):return key.startswith(('camera_','architect_model_','architect_photo_choice_','photo_choices_','edge_')) or key=='default_color'
def _label_key(key):return key in ('template','templates') or key.startswith('label_layout_')
def _private_or_cache(key):return key.startswith(('api_','stock_mocs_','moc_search_','rb_','bl_','alt_components_','export_rb_','stock_layout_','stock_migration_','downloads')) or key in ('build_excluded_entries','ldraw','output')

def _settings(db,predicate,strip_colors=False):
    result=[]
    for row in db.rows('SELECT key,value FROM settings ORDER BY key'):
        if not predicate(row['key']):continue
        target=_portable_key(db,row['key'])
        if target is None:continue
        value=json.loads(row['value'])
        if strip_colors and isinstance(value,dict):
            value=copy.deepcopy(value);value.pop('category_colors',None)
            if row['key']=='templates':
                for template in value.values():
                    if isinstance(template,dict):template.pop('category_colors',None)
        result.append({'target':target,'value':value})
    return result

def collect_family(db,family):
    if family not in FAMILIES:raise ValueError(tr('Famille de sauvegarde inconnue'))
    if family=='storage':
        from .storage_wall import walls,drawers,contents
        return {'walls':[{'name':w['name'],'columns':w['columns'],'rows':w['rows'],'x':w['x'],'y':w['y'],'drawers':[dict({k:d[k] for k in ('col','row','width','height','name')},parts=[{'item':identity(p),'color':p['chosen_color']} for p in contents(db,d['id'])]) for d in drawers(db,w['id'])]} for w in walls(db)]}
    if family in ('loose','sets','queue'):
        table={'loose':'stock','sets':'stock_sets','queue':'queue'}[family];entries=[]
        for row in db.rows('SELECT i.*,s.id AS entry_id,s.color,s.quantity AS stock_quantity FROM '+table+' s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 ORDER BY i.source,i.ref,s.color'):
            entry={'item':identity(row),'color':str(row['color']),'quantity':int(row['stock_quantity'])}
            if family=='sets':entry['components']=[{'item':identity(p),'color':str(p['chosen_color']),'quantity':int(p['chosen_quantity'])} for p in db.owned_components(row['entry_id'])]
            entries.append(entry)
        return {'entries':entries}
    if family=='labels':return {'settings':_settings(db,_label_key,True)}
    if family=='colors':
        templates=_settings(db,lambda key:key=='template' or key.startswith('label_layout_'))
        colors=[{'target':r['target'],'value':r['value'].get('category_colors',{})} for r in templates if isinstance(r['value'],dict)]
        named=db.setting('templates',{})
        if isinstance(named,dict):colors.append({'target':{'key':'templates'},'named':True,'value':{name:t.get('category_colors',{}) for name,t in named.items() if isinstance(t,dict)}})
        return {'automatic':db.setting('automatic_category_colors',{}),'templates':colors}
    if family=='views':
        visuals=db.rows('SELECT i.*,v.mode,v.color FROM visual v JOIN items i ON i.id=v.item_id')
        return {'settings':_settings(db,_view_key),'visuals':[{'item':identity(r),'mode':r['mode'],'color':r['color']} for r in visuals]}
    if family=='api':return {'settings':_settings(db,lambda key:key.startswith('api_'))}
    return {'settings':_settings(db,lambda k:not (_label_key(k) or _view_key(k) or _private_or_cache(k) or k=='automatic_category_colors'))}

def export_family(db,family,path):
    payload={'format':'BrickLabo-selective-1','version':1,'family':family,'data':collect_family(db,family)}
    with atomic_output(path) as temp:temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return Path(path)

def read_family(path):
    path=Path(path)
    if path.stat().st_size>50*1024*1024:raise ValueError(tr('Sauvegarde trop volumineuse'))
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload.get('format')!='BrickLabo-selective-1' or payload.get('version')!=1 or payload.get('family') not in FAMILIES or not isinstance(payload.get('data'),dict):raise ValueError(tr('Sauvegarde sélective invalide'))
    return payload

def _item(c,value):
    if value.get('source') not in ('RB','BL','BA','ALT') or value.get('kind') not in ('part','minifig','set','instructions','box','book','gear','catalog') or not isinstance(value.get('ref'),str) or not value['ref']:raise ValueError(tr('Identité de référence invalide'))
    row=c.execute('SELECT id FROM items WHERE source=? AND kind=? AND ref=?',(value['source'],value['kind'],value['ref'])).fetchone()
    if row:return row['id']
    image=value.get('image','');image=image if image.startswith(('https://','http://')) else ''
    c.execute('INSERT INTO items(source,kind,ref,name,category,image,search) VALUES(?,?,?,?,?,?,?)',(value['source'],value['kind'],value['ref'],value.get('name') or value['ref'],value.get('category',''),image,normalize(value['ref']+' '+value.get('name',''))))
    return c.execute('SELECT last_insert_rowid()').fetchone()[0]

def _key(c,target):
    if 'item' in target:
        prefix=target.get('prefix')
        if prefix not in ITEM_KEYS:raise ValueError(tr('Réglage de référence invalide'))
        return prefix+str(_item(c,target['item']))
    if 'entry' in target:
        scope=target.get('scope')
        if scope not in ('stock','stock_sets','queue','history'):raise ValueError(tr('Destination invalide'))
        iid=_item(c,target['entry']);row=c.execute('SELECT id FROM '+scope+' WHERE item_id=? AND color=? ORDER BY id LIMIT 1',(iid,str(target.get('color','')))).fetchone()
        return 'label_layout_'+scope+'_'+str(row['id']) if row else None
    key=target.get('key')
    if not isinstance(key,str) or len(key)>250 or ENTRY_RE.match(key) or any(key.startswith(p) for p in ITEM_KEYS):raise ValueError(tr('Nom de réglage invalide'))
    return key

def _write(c,key,value):c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,ensure_ascii=False)))
def _quantity(value):
    if type(value) is not int or not 1<=value<=100_000_000:raise ValueError(tr('Quantité de sauvegarde invalide'))
    return value

def _entry_layouts(c,table):
    result=[]
    for row in c.execute('SELECT key,value FROM settings WHERE key LIKE ?',('label_layout_'+table+'_%',)):
        match=ENTRY_RE.match(row['key'])
        if not match:continue
        entry=c.execute('SELECT i.*,s.color FROM '+table+' s JOIN items i ON i.id=s.item_id WHERE s.id=?',(int(match[2]),)).fetchone()
        if entry:result.append(({'entry':identity(dict(entry)),'scope':table,'color':entry['color']},json.loads(row['value'])))
    return result

def _preserve_colors(value,old):
    if not isinstance(value,dict):return value
    value=copy.deepcopy(value)
    if 'layers' in value:value['category_colors']=old.get('category_colors',{}) if isinstance(old,dict) else {}
    elif isinstance(old,dict):
        for name,template in value.items():
            if isinstance(template,dict) and 'layers' in template:value[name]=_preserve_colors(template,old.get(name,{}))
    return value

def restore_families(db,paths):
    payloads=[read_family(p) for p in paths]
    if len({p['family'] for p in payloads})!=len(payloads):raise ValueError(tr('Choisis un seul fichier par famille.'))
    order={'loose':0,'sets':1,'queue':2,'labels':3,'colors':4,'views':5,'storage':6,'preferences':7,'api':8}
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for payload in sorted(payloads,key=lambda p:order[p['family']]):
            family=payload['family'];data=payload['data']
            previous_labels={}
            if family=='storage':
                from .storage_wall import check_position
                c.execute('DELETE FROM storage_walls')
                for wall in data.get('walls',[]):
                    columns,rows=int(wall['columns']),int(wall['rows'])
                    if not wall['name'].strip() or not 1<=columns<=100 or not 1<=rows<=100:raise ValueError(tr('Meuble invalide'))
                    if ('x' in wall)!=('y' in wall):raise ValueError(tr('Position du meuble invalide.'))
                    default_x=round(c.execute('SELECT COALESCE(MAX(x+columns+.5),0) FROM storage_walls').fetchone()[0],1)
                    x,y=check_position(c,None,wall.get('x',default_x),wall.get('y',0),columns,rows)
                    wid=c.execute('INSERT INTO storage_walls(name,columns,rows,x,y) VALUES(?,?,?,?,?)',(wall['name'],columns,rows,x,y)).lastrowid;rects=[]
                    for drawer in wall['drawers']:
                        col,row,width,height=(int(drawer[k]) for k in ('col','row','width','height'))
                        if min(col,row,width,height)<1 or col+width-1>columns or row+height-1>rows or any(col<x+w and x<col+width and row<y+h and y<row+height for x,y,w,h in rects):raise ValueError(tr('Tiroir invalide'))
                        rects.append((col,row,width,height));did=c.execute('INSERT INTO storage_drawers(wall_id,col,row,width,height,name) VALUES(?,?,?,?,?,?)',(wid,col,row,width,height,drawer['name'])).lastrowid
                        for part in drawer['parts']:c.execute('INSERT INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',(did,_item(c,part['item']),str(part['color'])))
            elif family in ('loose','sets','queue'):
                table={'loose':'stock','sets':'stock_sets','queue':'queue'}[family]
                layouts=_entry_layouts(c,table)
                c.execute('DELETE FROM settings WHERE key LIKE ?',('label_layout_'+table+'_%',))
                if family=='loose':c.execute('UPDATE stock SET quantity=0')
                else:
                    if family=='sets':c.execute('DELETE FROM stock_set_components')
                    c.execute('DELETE FROM '+table)
                for entry in data.get('entries',[]):
                    iid=_item(c,entry['item']);color=str(entry.get('color',''));qty=_quantity(entry['quantity'])
                    if family=='sets' and entry['item']['kind']!='set':raise ValueError(tr('Un set est attendu.'))
                    if family=='loose' and entry['item']['kind'] not in ('part','minifig'):raise ValueError(tr('Une pièce est attendue.'))
                    c.execute('INSERT INTO '+table+'(item_id,color,quantity) VALUES(?,?,?) ON CONFLICT(item_id,color) DO UPDATE SET quantity='+table+'.quantity+excluded.quantity',(iid,color,qty))
                    if family=='sets':
                        eid=c.execute('SELECT id FROM stock_sets WHERE item_id=? AND color=?',(iid,color)).fetchone()['id']
                        for p in entry.get('components',[]):
                            pid=_item(c,p['item']);pcolor=str(p.get('color',''));amount=_quantity(p['quantity'])
                            if p['item']['kind'] not in ('part','minifig'):raise ValueError(tr('Composant de set invalide'))
                            c.execute('INSERT INTO stock_set_components VALUES(?,?,?,?) ON CONFLICT(set_entry_id,item_id,color) DO UPDATE SET quantity=stock_set_components.quantity+excluded.quantity',(eid,pid,pcolor,amount))
                            c.execute('INSERT INTO stock(item_id,color,quantity) VALUES(?,?,0) ON CONFLICT(item_id,color) DO NOTHING',(pid,pcolor))
                for target,value in layouts:
                    key=_key(c,target)
                    if key:_write(c,key,value)
                c.execute('DELETE FROM stock_undo');c.execute("DELETE FROM settings WHERE key='build_excluded_entries'")
            elif family=='labels':
                previous_labels={r['key']:json.loads(r['value']) for r in c.execute('SELECT key,value FROM settings') if _label_key(r['key'])}
                c.execute("DELETE FROM settings WHERE key LIKE 'label_layout_%'")
            elif family=='colors':
                from .labels import default_template
                _write(c,'automatic_category_colors',data.get('automatic',{}))
                for record in data.get('templates',[]):
                    key=_key(c,record['target'])
                    if not key or not _label_key(key):continue
                    row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
                    if record.get('named') and key=='templates':
                        template=json.loads(row['value']) if row else {}
                        for name,colors in record['value'].items():
                            if name not in template:template[name]=default_template()
                            template[name]['category_colors']=colors
                    else:
                        template=json.loads(row['value']) if row else default_template()
                        template['category_colors']=record['value']
                    _write(c,key,template)
            elif family=='views':
                for row in list(c.execute('SELECT key FROM settings')):
                    if _view_key(row['key']):c.execute('DELETE FROM settings WHERE key=?',(row['key'],))
                for visual in data.get('visuals',[]):
                    if visual.get('mode') not in ('3d','photo','photo_rb','photo_bl','local'):raise ValueError(tr('Mode de visuel invalide'))
                    c.execute('INSERT INTO visual(item_id,mode,color) VALUES(?,?,?) ON CONFLICT(item_id) DO UPDATE SET mode=excluded.mode,color=excluded.color',(_item(c,visual['item']),visual['mode'],str(visual.get('color',''))))
            for record in data.get('settings',[]):
                key=_key(c,record['target'])
                if not key:continue
                allowed=_label_key(key) if family=='labels' else _view_key(key) if family=='views' else key.startswith('api_') if family=='api' else key.startswith('label_layout_'+{'loose':'stock','sets':'stock_sets','queue':'queue'}[family]+'_') if family in ('loose','sets','queue') else not (_label_key(key) or _view_key(key) or _private_or_cache(key) or key=='automatic_category_colors') if family=='preferences' else False
                if not allowed:raise ValueError(tr('Réglage incompatible avec sa famille : ')+key)
                value=record['value']
                if family=='labels':value=_preserve_colors(value,previous_labels.get(key,{}))
                _write(c,key,value)
    return [p['family'] for p in payloads]
