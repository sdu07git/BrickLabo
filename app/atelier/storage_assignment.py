"""Atomic placement of loose-stock references and read-only drawer proposals."""
import hashlib
import json
import re
from fractions import Fraction

from .data import normalize
from .i18n import tr,tf
from .action_undo import storage_change


def stock_rows(db,query='',category='',unlocated=False,limit=None,remaining_only=False):
    conditions=["i.kind IN ('part','minifig')","s.quantity>0"];args=[]
    if category:conditions.append('i.category=?');args.append(category)
    if unlocated:conditions.append('NOT EXISTS (SELECT 1 FROM storage_contents p WHERE p.item_id=i.id AND p.color=s.color)')
    allocated='COALESCE((SELECT SUM(p.quantity) FROM storage_contents p WHERE p.item_id=i.id AND p.color=s.color),0)'
    if remaining_only:conditions.append('s.quantity>'+allocated)
    for word in normalize(query).split():
        conditions.append("norm(i.ref||' '||i.name||' '||i.category) LIKE ?");args.append('%'+word+'%')
    sql='SELECT i.*,s.color AS chosen_color,s.quantity AS chosen_quantity,'+allocated+' AS allocated_quantity,MAX(0,s.quantity-'+allocated+') AS remaining_quantity FROM stock s JOIN items i ON i.id=s.item_id WHERE '+' AND '.join(conditions)+' ORDER BY i.category,i.source,i.ref,s.color'
    if limit is not None:sql+=' LIMIT ?';args.append(limit)
    return db.rows(sql,args)


def catalogue_rows(db,query='',category='',unlocated=False,source=None,kind=None,limit=None):
    conditions=["i.kind IN ('part','minifig')","i.catalogue_hidden=0"];args=[]
    if source:conditions.append('i.source=?');args.append(source)
    if kind:conditions.append('i.kind=?');args.append(kind)
    if category:conditions.append('i.category=?');args.append(category)
    if unlocated:conditions.append('NOT EXISTS (SELECT 1 FROM storage_contents p WHERE p.item_id=i.id)')
    for word in normalize(query).split():
        conditions.append("norm(i.ref||' '||i.name||' '||i.category) LIKE ?");args.append('%'+word+'%')
    sql="SELECT i.*,'' AS chosen_color FROM items i WHERE "+' AND '.join(conditions)+' ORDER BY i.source,i.ref,i.id'
    if limit is not None:sql+=' LIMIT ?';args.append(limit)
    return db.rows(sql,args)


def place_entries(db,drawer_id,entries,source_drawer=None,from_catalogue=False):
    """Move location links from a drawer, or add stock references; never quantities."""
    entries=list(dict.fromkeys((identity,str(color or '')) for identity,color in entries))
    if type(from_catalogue) is not bool or from_catalogue and (source_drawer is not None or any(color for identity,color in entries)):
        raise ValueError(tr('Sélection de pièces invalide.'))
    if type(drawer_id) is not int or drawer_id<=0 or source_drawer is not None and (type(source_drawer) is not int or source_drawer<=0) or not entries or len(entries)>5000 or any(type(identity) is not int or identity<=0 for identity,color in entries):
        raise ValueError(tr('Sélection de pièces invalide.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM storage_drawers WHERE id=?',(drawer_id,)).fetchone():raise ValueError(tr('Tiroir introuvable.'))
        for identity,color in entries:
            if source_drawer is not None:
                valid=c.execute('SELECT 1 FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(source_drawer,identity,color)).fetchone()
                if not valid:raise ValueError(tr('Le contenu du tiroir a changé. Recommence le glissement.'))
            elif from_catalogue:
                if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig') AND catalogue_hidden=0",(identity,)).fetchone():
                    raise ValueError(tr('Cette référence n’est plus disponible dans le catalogue.'))
            elif not c.execute("SELECT 1 FROM stock s JOIN items i ON i.id=s.item_id WHERE s.item_id=? AND s.color=? AND s.quantity>0 AND i.kind IN ('part','minifig')",(identity,color)).fetchone():
                raise ValueError(tr('Cette référence n’est plus dans le stock en vrac.'))
        if source_drawer==drawer_id:return 0
        with storage_change(c,[drawer_id]+([source_drawer] if source_drawer is not None else []),tr('Placement de pièces dans les tiroirs')):
            before=c.total_changes
            if source_drawer is None:
                c.executemany('INSERT OR IGNORE INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',[(drawer_id,identity,color) for identity,color in entries])
            else:
                for identity,color in entries:
                    source=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(source_drawer,identity,color)).fetchone()
                    target=c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer_id,identity,color)).fetchone()
                    quantity=(source['quantity'] or 0)+(target['quantity'] or 0) if source['quantity'] is not None or target is not None and target['quantity'] is not None else None
                    c.execute('INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?) ON CONFLICT(drawer_id,item_id,color) DO UPDATE SET quantity=excluded.quantity',(drawer_id,identity,color,quantity))
            if source_drawer is not None:
                c.executemany('DELETE FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',[(source_drawer,identity,color) for identity,color in entries])
            changed=c.total_changes-before
    return changed


_NUMBER=r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)'
_SIZE=re.compile(r'(?<![\w.,/])('+_NUMBER+r')\s*[x×]\s*('+_NUMBER+r')(?:\s*[x×]\s*('+_NUMBER+r'))?',re.I)


def stud_dimensions(name):
    """Dimensions explicitly written in a catalogue name; do not guess from IDs."""
    match=_SIZE.search(name)
    if not match:return None
    values=[]
    for number in match.groups():
        if number is None:continue
        try:
            values.append(sum(float(Fraction(part.replace(',','.'))) for part in number.split()))
        except (ValueError,ZeroDivisionError):return None
    if any(value<=0 or value>1000 for value in values):return None
    return tuple(sorted(values[:2]))+tuple(values[2:])


def dimensions_text(dimensions):
    return ' × '.join(format(value,'g').replace('.',',') for value in dimensions)


def _state(c,wall_id,entries=None,from_catalogue=False):
    selected=[dict(r) for r in c.execute('SELECT * FROM storage_walls'+(' WHERE id=?' if wall_id is not None else '')+' ORDER BY y,x,id',(wall_id,) if wall_id is not None else ())]
    if not selected:raise ValueError(tr('Meuble introuvable.'))
    order={wall['id']:index for index,wall in enumerate(selected)}
    drawers=[dict(r) for r in c.execute('SELECT * FROM storage_drawers'+(' WHERE wall_id=?' if wall_id is not None else ''),(wall_id,) if wall_id is not None else ())]
    drawers.sort(key=lambda drawer:(order[drawer['wall_id']],drawer['row'],drawer['col'],drawer['id']))
    state={'wall':selected[0],'walls':selected,
            'drawers':drawers,
            'links':[dict(r) for r in c.execute('SELECT p.*,i.category,i.source,i.ref,i.name FROM storage_contents p JOIN items i ON i.id=p.item_id ORDER BY p.drawer_id,p.item_id,p.color')],
            'stock':[dict(r) for r in c.execute("SELECT i.id,i.source,i.ref,i.name,i.category,s.color,s.quantity FROM stock s JOIN items i ON i.id=s.item_id WHERE i.kind IN ('part','minifig') AND s.quantity>0 ORDER BY i.id,s.color")]}
    state['picked']=[dict(r) for r in c.execute('SELECT project_id,item_id,color,drawer_id,quantity FROM project_pick_rows ORDER BY project_id,item_id,color,drawer_id')]
    if from_catalogue:
        identities=sorted({identity for identity,color in entries or []});items=[]
        for start in range(0,len(identities),900):
            chunk=identities[start:start+900]
            items.extend(dict(row,color='',quantity=0) for row in c.execute("SELECT id,source,kind,ref,name,category,catalogue_hidden FROM items WHERE id IN ("+','.join('?' for _ in chunk)+') ORDER BY id',chunk))
        if len(items)!=len(identities) or any(item['kind'] not in ('part','minifig') or item['catalogue_hidden'] for item in items):raise ValueError(tr('Une référence de catalogue a changé ou n’est plus disponible. Prépare une nouvelle proposition.'))
        state['catalogue']=sorted(items,key=lambda item:item['id'])
    return state


def _fingerprint(state):return hashlib.sha256(json.dumps({k:v for k,v in state.items() if k!='preview'},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _preview_state(c,state,entries,category,from_catalogue):
    drawers=state['drawers'];drawer_ids={d['id'] for d in drawers}
    links=[link for link in state['links'] if link['drawer_id'] in drawer_ids]
    candidates=state['catalogue'] if from_catalogue else state['stock']
    wanted={(identity,str(color)) for identity,color in entries} if entries is not None else None
    ids={item['id'] for item in candidates if (not category or item['category']==category) and (wanted is None or from_catalogue or (item['id'],item['color']) in wanted)}
    ids|={link['item_id'] for link in links};items={};ordered=sorted(ids)
    for start in range(0,len(ordered),800):
        chunk=ordered[start:start+800]
        items.update((row['id'],dict(row)) for row in c.execute('SELECT * FROM items WHERE id IN ('+','.join('?' for _ in chunk)+')',chunk))
    return {'wall':state['wall'],'walls':state['walls'],'drawers':drawers,'links':links,'items':items,'stock':[row for row in state['stock'] if row['id'] in ids]}


def propose(db,wall_id,category='',split_colors=False,reorganize=False,entries=None,from_catalogue=False,grouping='size',allocate_quantities=False,criteria=None,drawer_counts=None,category_order=None,share_drawers=False):
    """One group per category and footprint, ordered from few to many studs."""
    if reorganize and not category:raise ValueError(tr('Choisis une catégorie pour réorganiser ses tiroirs.'))
    if grouping not in ('size','reference','manual'):raise ValueError(tr('Mode de rangement invalide.'))
    if type(share_drawers) is not bool:raise ValueError(tr('Mode de rangement invalide.'))
    if grouping=='manual':criteria={'reference'}
    elif criteria is None:criteria={'category','size'}|({'reference'} if grouping=='reference' else set())
    elif not isinstance(criteria,(list,tuple,set,frozenset)) or not criteria or any(value not in ('category','size','reference') for value in criteria):raise ValueError(tr('Coche au moins un critère : catégorie, taille ou référence.'))
    criteria=set(criteria)
    from .storage_order import saved,validate
    category_order=saved(db) if category_order is None else validate(category_order)
    priorities={category:index for index,category in enumerate(category_order)}
    drawer_counts=dict(drawer_counts or {})
    if any(type(identity) is not int or identity<=0 or type(count) is not int or not 1<=count<=1000 for identity,count in drawer_counts.items()):raise ValueError(tr('Nombre de tiroirs invalide.'))
    if drawer_counts and ('reference' not in criteria or grouping=='manual'):raise ValueError(tr('Coche Référence pour répartir une pièce dans plusieurs tiroirs.'))
    if type(allocate_quantities) is not bool or allocate_quantities and from_catalogue:raise ValueError(tr('Les quantités se répartissent depuis le stock en vrac.'))
    with db.read() as c:
        c.execute('BEGIN');state=_state(c,wall_id,entries,from_catalogue)
        state['preview']=_preview_state(c,state,entries,category,from_catalogue)
    occupied={}
    for link in state['links']:occupied.setdefault(link['drawer_id'],[]).append(link)
    available=[];replaced=[]
    for drawer in state['drawers']:
        links=occupied.get(drawer['id'],[])
        if not links and not drawer['name']:available.append(drawer)
        elif reorganize and links and all(link['category']==category for link in links):
            available.append(drawer);replaced.extend(links)
    eligible={d['id'] for d in available}
    located={ (link['item_id'],link['color']) for link in state['links'] if link['drawer_id'] not in eligible }
    if not reorganize:located|={(link['item_id'],link['color']) for link in state['links']}
    groups={};unknown=[];quantities={};candidates=list(state['catalogue'] if from_catalogue else state['stock'])
    allocated={};replaced_quantities={};replaced_known=set()
    for picked in state['picked']:
        key=(picked['item_id'],picked['color']);allocated[key]=allocated.get(key,0)+picked['quantity']
    for link in state['links']:
        key=(link['item_id'],link['color']);allocated[key]=allocated.get(key,0)+(link['quantity'] or 0)
    for link in replaced:
        key=(link['item_id'],link['color']);replaced_quantities[key]=replaced_quantities.get(key,0)+(link['quantity'] or 0)
        if link['quantity'] is not None:replaced_known.add(key)
    if entries is not None and not from_catalogue:
        wanted={(identity,str(color)) for identity,color in entries};candidates=[item for item in candidates if (item['id'],item['color']) in wanted]
        if wanted-{(item['id'],item['color']) for item in candidates}:raise ValueError(tr('Le stock ou le rangement a changé. Prépare une nouvelle proposition.'))
    known={(item['id'],item['color']) for item in candidates};existing={(link['item_id'],link['color']) for link in replaced}
    for link in replaced:
        if (link['item_id'],link['color']) not in known:
            candidates.append(dict(link,id=link['item_id'],quantity=0));known.add((link['item_id'],link['color']))
    for item in candidates:
        if category and item['category']!=category:continue
        entry_key=(item['id'],item['color'])
        if not allocate_quantities and entry_key in located and entry_key not in existing:continue
        physical=replaced_quantities.get(entry_key,0)+max(0,item['quantity']-allocated.get(entry_key,0)) if allocate_quantities else replaced_quantities.get(entry_key,0) if entry_key in replaced_known else None
        if allocate_quantities and not physical and entry_key not in existing:continue
        dimensions=stud_dimensions(item['name']) if 'size' in criteria else ()
        if not dimensions and 'size' in criteria and 'reference' not in criteria:unknown.append(item);continue
        dimensions=dimensions or ()
        key=(item['category'] if 'category' in criteria else '',dimensions,item['id'] if 'reference' in criteria else None,item['source'] if split_colors else '',item['color'] if split_colors else '')
        group=groups.setdefault(key,{'category':item['category'],'categories':[],'dimensions':dimensions,'color':(item['source']+' '+item['color']) if split_colors else '', 'entries':[],'references':[]})
        if item['category'] not in group['categories']:group['categories'].append(item['category'])
        group['entries'].append((item['id'],item['color']));group['references'].append(item['source']+' '+item['ref'])
        quantities[entry_key]=physical
    for group in groups.values():group['category']=' / '.join(sorted(group['categories'],key=normalize))
    ordered=sorted(groups.values(),key=lambda g:((priorities.get(g['category'],len(priorities)),normalize(g['category'])) if 'category' in criteria else (0,''),not bool(g['dimensions']),g['dimensions'][0]*g['dimensions'][1] if g['dimensions'] else 0,g['dimensions'][1:] if g['dimensions'] else (),g['dimensions'][:1],g['references'][0] if 'reference' in criteria else '',g['color']))
    expanded=[]
    for group in ordered:
        identities={identity for identity,color in group['entries']}
        count=drawer_counts.get(next(iter(identities)),1) if len(identities)==1 else 1
        if len(expanded)+count>20000:raise ValueError(tr('La proposition dépasse 20 000 tiroirs. Réduis la sélection ou le nombre de tiroirs par référence.'))
        offsets={};offset=0
        for entry in group['entries']:
            offsets[entry]=offset
            if quantities[entry] is not None:offset=(offset+quantities[entry]%count)%count
        for slot in range(count):
            row=dict(group,split_index=slot,split_count=count)
            row['quantities']={}
            for entry in group['entries']:
                quantity=quantities[entry]
                row['quantities'][entry]=None if quantity is None else quantity//count+((slot-offsets[entry])%count<quantity%count)
            expanded.append(row)
    ordered=expanded
    for index,group in enumerate(ordered):
        group['drawer_id']=available[index]['id'] if grouping!='manual' and index<len(available) else None
        group['name']=' · '.join(v for v in ((group['references'][0] if 'reference' in criteria else ''),(group['category'] if 'category' in criteria else ''),dimensions_text(group['dimensions']),group['color']) if v)
        if group['split_count']>1:group['name']+=' ('+str(group['split_index']+1)+'/'+str(group['split_count'])+')'
    plan={'wall_id':wall_id,'fingerprint':_fingerprint(state),'available':available,'replaced':replaced,'groups':ordered,'unknown':unknown,'reorganize':reorganize,'entries':list(entries) if entries is not None else None,'from_catalogue':from_catalogue,'grouping':grouping,'shared_drawers':grouping=='manual' or share_drawers,'criteria':sorted(criteria),'category_order':category_order,'preview':state['preview'],'quantities':quantities,'allocate_quantities':allocate_quantities}
    if drawer_counts:
        from .storage_draft import arrange_targets
        for group,target in zip(ordered,arrange_targets(plan)):group['drawer_id']=target
    return plan


def group_quantities(plan,group):return group.get('quantities',plan.get('quantities',{}))


def validate_targets(plan,targets):
    groups=plan['groups']
    if len(targets)!=len(groups):raise ValueError(tr('Proposition de rangement invalide.'))
    chosen=[target for target in targets if target is not None];allowed={d['id'] for d in plan['available']}
    if any(type(target) is not int or target not in allowed for target in chosen) or not plan.get('shared_drawers') and len(chosen)!=len(set(chosen)):
        raise ValueError(tr('Choisis un tiroir disponible différent pour chaque groupe.'))
    series={};seen=set()
    for group,target in zip(groups,targets):
        if target is not None:
            for identity,color in group['entries']:
                key=(target,identity,color)
                if key in seen:raise ValueError(tr('Les différents tiroirs d’une même référence doivent rester distincts.'))
                seen.add(key)
        if group.get('split_count',1)>1:series.setdefault(tuple(group['entries']),[]).append(target)
    if any(any(target is not None for target in values) and any(target is None for target in values) for values in series.values()):
        raise ValueError(tr('Choisis tous les tiroirs demandés pour une référence, ou laisse-les tous sans emplacement.'))
    if not chosen:raise ValueError(tr('Aucun tiroir choisi.'))
    return chosen


def drawer_label(plan,drawer):
    from .storage_wall import address
    if plan['wall_id'] is not None:return address(drawer)
    selected=plan['preview']['walls'];names=[wall['name'] for wall in selected]
    labels={wall['id']:wall['name']+(' ('+str(index+1)+')' if names.count(wall['name'])>1 else '') for index,wall in enumerate(selected)}
    return labels[drawer['wall_id']]+' — '+address(drawer)


def apply_proposal(db,plan,targets=None):
    """Validate a preview and commit all chosen associations in one transaction."""
    groups=plan['groups'];targets=list(targets if targets is not None else [g['drawer_id'] for g in groups])
    chosen=validate_targets(plan,targets)
    placed={tuple(entry) for group,target in zip(groups,targets) if target is not None for entry in group['entries']}
    if plan['reorganize'] and any((link['item_id'],link['color']) not in placed for link in plan['replaced']):
        raise ValueError(tr('Tous les contenus existants doivent avoir un tiroir proposé avant la réorganisation.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if _fingerprint(_state(c,plan['wall_id'],plan.get('entries'),plan.get('from_catalogue',False)))!=plan['fingerprint']:
            raise ValueError(tr('Le stock ou le rangement a changé. Prépare une nouvelle proposition.'))
        ids=sorted({link['drawer_id'] for link in plan['replaced']})
        with storage_change(c,set(chosen)|set(ids),tr('Application d’une proposition de rangement')):
            if plan['reorganize']:
                for identity in ids:
                    c.execute('DELETE FROM storage_contents WHERE drawer_id=?',(identity,))
                    c.execute("UPDATE storage_drawers SET name='' WHERE id=?",(identity,))
            buckets={}
            for group,target in zip(groups,targets):
                if target is not None:buckets.setdefault(target,[]).append(group)
            for target,bucket in buckets.items():
                name=bucket[0]['name'] if len(bucket)==1 else ' / '.join(dict.fromkeys(g['category'] for g in bucket))+' · '+tf('{0} référence(s)',len({identity for g in bucket for identity,color in g['entries']}))
                c.execute('UPDATE storage_drawers SET name=? WHERE id=?',(name,target))
                c.executemany('INSERT OR IGNORE INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)',[(target,identity,color,group_quantities(plan,group).get((identity,color))) for group in bucket for identity,color in group['entries']])
    return len(set(chosen)),len(placed)
