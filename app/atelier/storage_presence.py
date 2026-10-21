"""Read drawer associations without confusing an address with a printed label."""
from .i18n import tr,tf
from .storage_wall import address


def locations(db,item_ids):
    ids=list(dict.fromkeys(item_ids));result={}
    # Bound parameters even if a caller supplies a larger catalogue page.
    for start in range(0,len(ids),500):
        batch=ids[start:start+500]
        rows=db.rows('''SELECT p.item_id,p.color,p.quantity,d.col,d.row,d.name,w.name AS wall_name
            FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id
            JOIN storage_walls w ON w.id=d.wall_id WHERE p.item_id IN ('''+','.join('?' for _ in batch)+') ORDER BY w.id,d.row,d.col,p.color',batch)
        for row in rows:result.setdefault(row['item_id'],[]).append(row)
    return result


def describe(item,entries,scope):
    if item.get('kind')=='set':return ''
    if not entries:return tr('Aucun tiroir')
    chosen='' if item.get('chosen_color') is None else str(item['chosen_color'])
    matching=[e for e in entries if not chosen or not e['color'] or str(e['color'])==chosen]
    label=tr('Déjà rangée') if scope not in ('stock','queue') or matching else tr('Tiroir dans une autre couleur')
    details=[]
    for entry in entries:
        location=entry['wall_name']+' · '+address(entry)
        if entry['name']:location+=' · '+entry['name']
        location+=' · '+(tf('Couleur : {}',entry['color']) if entry['color'] else tr('Toutes couleurs / non précisée'))
        if entry['quantity'] is not None:location+=' · '+tf('{} pièce(s)',entry['quantity'])
        if location not in details:details.append(location)
    return label+' — '+' ; '.join(details)
