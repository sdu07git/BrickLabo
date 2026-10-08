"""Validated, all-or-nothing collection imports from Rebrickable and BrickLink."""
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

def _row(raw, source):
    values={_header(k):str(v or '').strip() for k,v in raw.items() if k is not None}
    def get(*keys,default=''):
        return next((values[k] for k in keys if values.get(k)),default)
    if get('alternate','alternateitem','alternateflag').upper() in ('Y','YES','TRUE','1') or get('counterpart','counterpartitem').upper() in ('Y','YES','TRUE','1'):return None
    src=source if source!='auto' else ('BL' if any(k in values for k in ('itemno','itemid','itemtype','colorid')) else 'RB')
    typ=get('itemtype','type').upper()
    kind={'S':'set','SET':'set','P':'part','PART':'part','M':'minifig','MINIFIG':'minifig','MINIFIGURE':'minifig'}.get(typ)
    if typ and kind is None:raise ValueError(tr('Type de référence non pris en charge : ')+typ)
    kind=kind or ('set' if get('set','setnum') else 'part')
    ref=get('itemno','itemid','part','partnum','set','setnum','fig','fignum')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',ref):raise ValueError(tr('Référence invalide : ')+ref)
    amount=get('quantity','qty','minqty',default='1')
    if not re.fullmatch(r'[0-9]+',amount) or not 1<=int(amount)<=10_000_000:raise ValueError(tr('Quantité invalide : ')+amount)
    color='' if kind!='part' else get('color','colorid',default='')
    if kind=='part' and (not color.isdigit() or int(color)>100000):raise ValueError(tr('Code couleur numérique requis pour ')+ref)
    return {'source':src,'kind':kind,'ref':ref,'color':color,'quantity':int(amount)}

def read_list(path,source='auto'):
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
        try:row=_row(record,source)
        except ValueError as error:raise ValueError(tr('Ligne ')+str(index)+' : '+str(error)) from error
        if row:rows.append(row)
    if not rows:raise ValueError(tr('Aucune pièce ou aucun set à importer.'))
    return rows

def resolve_rows(db,rows):
    result=[]
    for row in rows:
        found=db.rows('SELECT * FROM items WHERE source=? AND kind=? AND ref=?',(row['source'],row['kind'],row['ref']))
        if not found and row['source']=='RB' and row['kind']=='set' and '-' not in row['ref']:
            found=db.rows("SELECT * FROM items WHERE source='RB' AND kind='set' AND ref=?",(row['ref']+'-1',))
        item=found[0] if found else None
        result.append(dict(row,item=item,issue='' if item else tr('Référence absente du catalogue local')))
    return result

def import_rows(db,rows,destination='stock',target_entry=None,name=''):
    from .stock import mutate
    if destination not in ('stock','stock_sets'):raise ValueError(tr('Destination inconnue'))
    resolved=resolve_rows(db,rows)
    missing=[r['ref'] for r in resolved if r['issue']]
    if missing:raise ValueError(tr('Aucun ajout. Références absentes : ')+', '.join(missing[:20]))
    actions=[];parts=[]
    for row in resolved:
        item=row['item']
        if item['kind']=='set':
            action=db.stock_action('stock_sets',item['id'],'',row['quantity'])
            if destination=='stock_sets':actions.append(action)
            else:
                actions.extend({'op':'add','scope':'stock','item_id':p['item_id'],'color':p['color'],'quantity':p['quantity']*row['quantity']} for p in action['components'])
        elif destination=='stock':actions.append(db.stock_action('stock',item['id'],row['color'],row['quantity']))
        else:parts.append({'item_id':item['id'],'color':row['color'],'quantity':row['quantity']})

    if parts and not target_entry and not name.strip():raise ValueError(tr('Donne un nom à cet inventaire de pièces.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
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
        mutate(db,actions,tr('Import de collection'),connection=c)

    return len(resolved)
