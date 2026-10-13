"""Atomic placement of loose-stock references and read-only drawer proposals."""
import hashlib
import json
import re
from fractions import Fraction

from .data import normalize
from .i18n import tr


def stock_rows(db,query='',category='',unlocated=False,limit=None):
    conditions=["i.kind IN ('part','minifig')","s.quantity>0"];args=[]
    if category:conditions.append('i.category=?');args.append(category)
    if unlocated:conditions.append('NOT EXISTS (SELECT 1 FROM storage_contents p WHERE p.item_id=i.id AND p.color=s.color)')
    for word in normalize(query).split():
        conditions.append("norm(i.ref||' '||i.name||' '||i.category) LIKE ?");args.append('%'+word+'%')
    sql='SELECT i.*,s.color AS chosen_color,s.quantity AS chosen_quantity FROM stock s JOIN items i ON i.id=s.item_id WHERE '+' AND '.join(conditions)+' ORDER BY i.category,i.source,i.ref,s.color'
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
        before=c.total_changes
        c.executemany('INSERT OR IGNORE INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',[(drawer_id,identity,color) for identity,color in entries])
        if source_drawer is not None:
            c.executemany('DELETE FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',[(source_drawer,identity,color) for identity,color in entries])
        return c.total_changes-before


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
    wall=c.execute('SELECT * FROM storage_walls WHERE id=?',(wall_id,)).fetchone()
    if not wall:raise ValueError(tr('Meuble introuvable.'))
    state={'wall':dict(wall),
            'drawers':[dict(r) for r in c.execute('SELECT * FROM storage_drawers WHERE wall_id=? ORDER BY row,col',(wall_id,))],
            'links':[dict(r) for r in c.execute('SELECT p.*,i.category,i.source,i.ref,i.name FROM storage_contents p JOIN items i ON i.id=p.item_id ORDER BY p.drawer_id,p.item_id,p.color')],
            'stock':[dict(r) for r in c.execute("SELECT i.id,i.source,i.ref,i.name,i.category,s.color,s.quantity FROM stock s JOIN items i ON i.id=s.item_id WHERE i.kind IN ('part','minifig') AND s.quantity>0 ORDER BY i.id,s.color")]}
    if from_catalogue:
        identities=sorted({identity for identity,color in entries or []});items=[]
        for start in range(0,len(identities),900):
            chunk=identities[start:start+900]
            items.extend(dict(row,color='',quantity=0) for row in c.execute("SELECT id,source,kind,ref,name,category,catalogue_hidden FROM items WHERE id IN ("+','.join('?' for _ in chunk)+') ORDER BY id',chunk))
        if len(items)!=len(identities) or any(item['kind'] not in ('part','minifig') or item['catalogue_hidden'] for item in items):raise ValueError(tr('Une référence de catalogue a changé ou n’est plus disponible. Prépare une nouvelle proposition.'))
        state['catalogue']=sorted(items,key=lambda item:item['id'])
    return state


def _fingerprint(state):return hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def propose(db,wall_id,category='',split_colors=False,reorganize=False,entries=None,from_catalogue=False):
    """One group per category and footprint, ordered from few to many studs."""
    if reorganize and not category:raise ValueError(tr('Choisis une catégorie pour réorganiser ses tiroirs.'))
    with db.read() as c:
        c.execute('BEGIN');state=_state(c,wall_id,entries,from_catalogue)
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
    groups={};unknown=[];candidates=list(state['catalogue'] if from_catalogue else state['stock'])
    if entries is not None and not from_catalogue:
        wanted={(identity,str(color)) for identity,color in entries};candidates=[item for item in candidates if (item['id'],item['color']) in wanted]
        if wanted-{(item['id'],item['color']) for item in candidates}:raise ValueError(tr('Le stock ou le rangement a changé. Prépare une nouvelle proposition.'))
    known={(item['id'],item['color']) for item in candidates};existing={(link['item_id'],link['color']) for link in replaced}
    for link in replaced:
        if (link['item_id'],link['color']) not in known:
            candidates.append(dict(link,id=link['item_id'],quantity=0));known.add((link['item_id'],link['color']))
    for item in candidates:
        if category and item['category']!=category:continue
        if (item['id'],item['color']) in located and (item['id'],item['color']) not in existing:continue
        dimensions=stud_dimensions(item['name'])
        if not dimensions:unknown.append(item);continue
        key=(item['category'],dimensions,item['source'] if split_colors else '',item['color'] if split_colors else '')
        group=groups.setdefault(key,{'category':item['category'],'dimensions':dimensions,'color':(item['source']+' '+item['color']) if split_colors else '', 'entries':[],'references':[]})
        group['entries'].append((item['id'],item['color']));group['references'].append(item['source']+' '+item['ref'])
    ordered=sorted(groups.values(),key=lambda g:(normalize(g['category']),g['dimensions'][0]*g['dimensions'][1],g['dimensions'][1],g['dimensions'][0],g['dimensions'][2:],g['color']))
    for index,group in enumerate(ordered):
        group['drawer_id']=available[index]['id'] if index<len(available) else None
        group['name']=' · '.join(v for v in (group['category'],dimensions_text(group['dimensions']),group['color']) if v)
    return {'wall_id':wall_id,'fingerprint':_fingerprint(state),'available':available,'replaced':replaced,'groups':ordered,'unknown':unknown,'reorganize':reorganize,'entries':list(entries) if entries is not None else None,'from_catalogue':from_catalogue}


def apply_proposal(db,plan,targets=None):
    """Validate a preview and commit all chosen associations in one transaction."""
    groups=plan['groups'];targets=list(targets if targets is not None else [g['drawer_id'] for g in groups])
    if len(targets)!=len(groups):raise ValueError(tr('Proposition de rangement invalide.'))
    chosen=[target for target in targets if target is not None];allowed={d['id'] for d in plan['available']}
    if any(type(target) is not int or target not in allowed for target in chosen) or len(chosen)!=len(set(chosen)):
        raise ValueError(tr('Choisis un tiroir disponible différent pour chaque groupe.'))
    if not chosen:raise ValueError(tr('Aucun tiroir choisi.'))
    placed={tuple(entry) for group,target in zip(groups,targets) if target is not None for entry in group['entries']}
    if plan['reorganize'] and any((link['item_id'],link['color']) not in placed for link in plan['replaced']):
        raise ValueError(tr('Tous les contenus existants doivent avoir un tiroir proposé avant la réorganisation.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if _fingerprint(_state(c,plan['wall_id'],plan.get('entries'),plan.get('from_catalogue',False)))!=plan['fingerprint']:
            raise ValueError(tr('Le stock ou le rangement a changé. Prépare une nouvelle proposition.'))
        if plan['reorganize']:
            ids=sorted({link['drawer_id'] for link in plan['replaced']})
            for identity in ids:
                c.execute('DELETE FROM storage_contents WHERE drawer_id=?',(identity,))
                c.execute("UPDATE storage_drawers SET name='' WHERE id=?",(identity,))
        for group,target in zip(groups,targets):
            if target is None:continue
            c.execute('UPDATE storage_drawers SET name=? WHERE id=?',(group['name'],target))
            c.executemany('INSERT OR IGNORE INTO storage_contents(drawer_id,item_id,color) VALUES(?,?,?)',[(target,identity,color) for identity,color in group['entries']])
    return len(chosen),len(placed)
