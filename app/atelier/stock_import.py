"""Read collection lists and apply validated rows as one undoable action."""
import csv
import io
import json
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from .i18n import tr

def _header(value):
    return re.sub(r'[^a-z0-9]','',str(value).lower())


def list_kind(path):
    """Recognise collection CSVs without confusing them with catalogue dumps."""
    path=Path(path)
    if path.suffix.lower()!='.csv':return None
    try:
        with path.open('rb') as stream:raw=stream.read(8192)
    except OSError:return None
    try:content=raw.decode('utf-8-sig')
    except UnicodeDecodeError:content=raw.decode('cp1252')
    try:dialect=csv.Sniffer().sniff(content,delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    fields={_header(value) for value in next(csv.reader(io.StringIO(content),dialect=dialect),[])}
    if 'inventoryid' in fields or not fields.intersection(('quantity','qty','minqty')):return None
    if fields.intersection(('setnumber','setnum','set','setid')):return 'set'
    if fields.intersection(('partnumber','partnum','part')):return 'part'
    if fields.intersection(('minifignumber','fignum','fignumber','fig')):return 'minifig'
    return None

def _row(raw, source, strict=True):
    values={_header(k):str(v or '').strip() for k,v in raw.items() if k is not None}
    def get(*keys,default=''):
        return next((values[k] for k in keys if values.get(k)),default)
    if get('alternate','alternateitem','alternateflag').upper() in ('Y','YES','TRUE','1') or get('counterpart','counterpartitem').upper() in ('Y','YES','TRUE','1'):return None
    src=source if source!='auto' else ('BL' if any(k in values for k in ('itemno','itemid','itemtype')) else 'RB')
    typ=get('itemtype','type').upper()
    kind={'S':'set','SET':'set','P':'part','PART':'part','M':'minifig','MINIFIG':'minifig','MINIFIGURE':'minifig'}.get(typ)
    if typ and kind is None and strict:raise ValueError(tr('Type de référence non pris en charge : ')+typ)
    kind=kind or (typ.lower() if typ else 'set' if get('set','setnum','setnumber','setid') else 'minifig' if get('fig','fignum','fignumber','minifignumber') else 'part')
    ref=get('itemno','itemid','part','partnum','partnumber','set','setnum','setnumber','setid','fig','fignum','fignumber','minifignumber')
    if strict and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',ref):raise ValueError(tr('Référence invalide : ')+ref)
    amount=get('quantity','qty','minqty',default='1')
    valid_amount=bool(re.fullmatch(r'[0-9]{1,10}',amount)) and 1<=int(amount)<=10_000_000
    if strict and not valid_amount:raise ValueError(tr('Quantité invalide : ')+amount)
    color='' if kind!='part' else get('color','colorid',default='')
    if strict and kind=='part' and (not re.fullmatch(r'[0-9]{1,6}',color) or int(color)>100000):raise ValueError(tr('Code couleur numérique requis pour ')+ref)
    result={'source':src,'kind':kind,'ref':ref,'color':color,'quantity':int(amount) if valid_amount else amount}
    version=get('inventoryver','inventoryversion','invversion') if kind=='set' else ''
    if version:
        if strict and not re.fullmatch(r'[1-9][0-9]{0,5}',version):raise ValueError(tr('Version d’inventaire invalide : ')+version)
        result['inventory_version']=version
    return result

def read_list(path,source='auto',strict=True):
    if source not in ('auto','RB','BL'):raise ValueError(tr('Source inconnue'))
    path=Path(path)
    if path.stat().st_size>50*1024*1024:raise ValueError(tr('Fichier trop volumineux (50 Mo maximum).'))
    raw=path.read_bytes()
    try:content=raw.decode('utf-8-sig')
    except UnicodeDecodeError:content=raw.decode('cp1252')
    if content.lstrip().startswith('<'):
        root=ET.fromstring(content)
        records=[{child.tag:child.text or '' for child in node} for node in root.iter() if node.tag.upper()=='ITEM']
        source='BL' if source=='auto' else source
    else:
        try:dialect=csv.Sniffer().sniff(content[:8192],delimiters=',;\t')
        except csv.Error:dialect=csv.excel_tab if '\t' in content.partition('\n')[0] else csv.excel
        records=csv.DictReader(io.StringIO(content),dialect=dialect)
    rows=[]
    for index,record in enumerate(records,1):
        if not any(str(v or '').strip() for v in record.values()):continue
        try:row=_row(record,source,strict)
        except ValueError as error:raise ValueError(tr('Ligne ')+str(index)+' : '+str(error)) from error
        if row:
            if not strict:row.update(line_number=index,original=record)
            rows.append(row)
    if not rows:raise ValueError(tr('Aucune pièce ou aucun set à importer.'))
    return rows

def resolve_rows(db,rows):
    from .color_links import rb_palette,bl_palette
    palettes={'BL':set(bl_palette(db.setting)),'RB':set(rb_palette())|{str(r['id']) for r in db.rows('SELECT id FROM colors')}}
    result=[];items={};inventories={}
    for row in rows:
        item=None;issue='';source=row.get('source','');kind=row.get('kind','');ref=str(row.get('ref',''));color=str(row.get('color',''));amount=str(row.get('quantity',''))
        if source not in ('RB','BL','ALT','BA'):issue=tr('Source inconnue')
        elif kind not in ('part','set','minifig'):issue=tr('Type de référence non pris en charge : ')+kind
        elif not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',ref):issue=tr('Référence invalide : ')+ref
        elif not re.fullmatch(r'[0-9]{1,10}',amount) or not 1<=int(amount)<=10_000_000:issue=tr('Quantité invalide : ')+amount
        elif kind=='set' and row.get('inventory_version') not in (None,'') and not re.fullmatch(r'[1-9][0-9]{0,5}',str(row['inventory_version'])):issue=tr('Version d’inventaire invalide : ')+str(row['inventory_version'])
        if not issue:
            key=(source,kind,ref)
            if key not in items:
                found=db.rows('SELECT * FROM items WHERE source=? AND kind=? AND ref=? AND catalogue_hidden=0',key)
                if not found and source=='RB' and kind=='set' and '-' not in ref:
                    found=db.rows("SELECT * FROM items WHERE source='RB' AND kind='set' AND ref=? AND catalogue_hidden=0",(ref+'-1',))
                items[key]=found[0] if found else None
            item=items[key]
            if not item:issue=tr('Référence absente du catalogue local')
            elif kind=='part' and (not re.fullmatch(r'[0-9]{1,6}',color) or int(color)>100000 or color not in palettes['BL' if source=='BL' else 'RB']):issue=tr('Couleur absente de la palette de la source : ')+color
            elif kind=='set':
                key=(item['id'],row.get('inventory_version') or None)
                if key not in inventories:
                    try:db.stock_action('stock_sets',item['id'],inventory_version=key[1]);inventories[key]=''
                    except ValueError as error:inventories[key]=str(error)
                issue=inventories[key]
        valid_amount=bool(re.fullmatch(r'[0-9]{1,10}',amount)) and 1<=int(amount)<=10_000_000
        result.append(dict(row,item=item,issue=issue,quantity=int(amount) if valid_amount else row.get('quantity','')))
    return result

def import_rows(db,rows,destination='stock',target_entry=None,name='',connection=None,completion=None):
    from contextlib import nullcontext
    from .stock import mutate
    if destination not in ('stock','stock_sets'):raise ValueError(tr('Destination inconnue'))
    resolved=resolve_rows(db,rows)
    missing=[r['ref']+' : '+r['issue'] for r in resolved if r['issue']]
    if missing:raise ValueError(tr('Aucun ajout. Lignes à corriger : ')+', '.join(missing[:20]))
    if not resolved:return 0
    actions=[];parts=[]
    for row in resolved:
        item=row['item']
        if item['kind']=='set':
            action=db.stock_action('stock_sets',item['id'],'',row['quantity'],inventory_version=row.get('inventory_version') or None)
            if destination=='stock_sets':actions.append(action)
            else:
                actions.extend({'op':'add','scope':'stock','item_id':p['item_id'],'color':p['color'],'quantity':p['quantity']*row['quantity']} for p in action['components'])
        elif destination=='stock':actions.append(db.stock_action('stock',item['id'],row['color'],row['quantity']))
        else:parts.append({'item_id':item['id'],'color':row['color'],'quantity':row['quantity']})

    if parts and not target_entry and not name.strip():raise ValueError(tr('Donne un nom à cet inventaire de pièces.'))
    with (db.connect() if connection is None else nullcontext(connection)) as c:
        if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
        target_item=None
        if parts:
            if target_entry:
                if not c.execute('SELECT 1 FROM stock_sets WHERE id=?',(int(target_entry),)).fetchone():raise ValueError(tr('Set absent du stock'))
                actions.append({'op':'attach','scope':'stock_sets','entry_id':int(target_entry),'components':parts})
            else:
                from .data import normalize
                ref='INV-'+uuid.uuid4().hex[:12]
                iid=c.execute("INSERT INTO items(source,kind,ref,name,category,search) VALUES('ALT','set',?,?,?,?)",(ref,name.strip(),tr('Inventaires personnels'),normalize(ref+' '+name.strip()))).lastrowid
                c.execute('INSERT INTO settings VALUES(?,?)',('alt_components_'+str(iid),json.dumps(parts,ensure_ascii=False)))
                actions.append({'op':'add','scope':'stock_sets','item_id':iid,'color':'','quantity':1,'components':parts})
                target_item=iid
        if completion:actions.append(dict(completion,target_item_id=target_item))
        mutate(db,actions,tr('Import de collection'),connection=c)

    return len(resolved)
