"""Keep reviewed draft destinations and prefer neighbouring drawers for splits."""
from collections import OrderedDict


def series_key(group):return tuple(sorted(group['entries']))


def group_key(group):return series_key(group),group.get('split_index',0)


def neighbours(left,right):
    if left['wall_id']!=right['wall_id']:return False
    horizontal=(left['col']+left['width']==right['col'] or right['col']+right['width']==left['col']) and max(left['row'],right['row'])<min(left['row']+left['height'],right['row']+right['height'])
    vertical=(left['row']+left['height']==right['row'] or right['row']+right['height']==left['row']) and max(left['col'],right['col'])<min(left['col']+left['width'],right['col']+right['width'])
    return horizontal or vertical


def connected(drawers):
    if not drawers:return False
    found={drawers[0]['id']}
    while True:
        extra={drawer['id'] for drawer in drawers if drawer['id'] not in found and any(neighbours(drawer,other) for other in drawers if other['id'] in found)}
        if not extra:return len(found)==len(drawers)
        found.update(extra)


def block(free,count,required=()):
    """A horizontal run first, then a connected block in the same cabinet."""
    by_id={drawer['id']:drawer for drawer in free};required=list(dict.fromkeys(required))
    if len(free)<count or any(identity not in by_id for identity in required):return None
    anchors=[by_id[required[0]]] if required else free
    for horizontal in (True,False):
        for anchor in anchors:
            chosen=[anchor];seen={anchor['id']}
            while len(chosen)<count:
                candidates=[drawer for drawer in free if drawer['id'] not in seen and drawer['wall_id']==anchor['wall_id'] and (not horizontal or drawer['row']==anchor['row']) and any(neighbours(drawer,other) for other in chosen)]
                if not candidates:break
                candidates.sort(key=lambda drawer:(drawer['id'] not in required,drawer['row']!=anchor['row'],abs(drawer['col']-anchor['col'])+abs(drawer['row']-anchor['row']),drawer['row'],drawer['col'],drawer['id']))
                chosen.append(candidates[0]);seen.add(chosen[-1]['id'])
            if len(chosen)==count and set(required)<=seen:return [drawer['id'] for drawer in chosen]
    return None


def arrange_targets(plan,previous=None,previous_targets=(),overrides=None,changed=()):
    """Only explicit destination choices are fixed; automatic rows can make room."""
    groups=plan['groups'];available=plan['available'];allowed={drawer['id'] for drawer in available};overrides=overrides or {};changed=set(changed)
    keys=[group_key(group) for group in groups];fixed={index:overrides[key] for index,key in enumerate(keys) if key in overrides and (overrides[key] is None or overrides[key] in allowed)}
    if plan.get('shared_drawers'):return [fixed.get(index,group['drawer_id']) for index,group in enumerate(groups)]
    old={group_key(group):target for group,target in zip(previous['groups'],previous_targets)} if previous else {}
    series=OrderedDict()
    for index,group in enumerate(groups):series.setdefault(series_key(group),[]).append(index)
    ordered=sorted(series.items(),key=lambda pair:not any(identity in changed for identity,color in pair[0]))
    reserved={target for target in fixed.values() if target is not None};used=set();result=[None]*len(groups)
    for entries,indices in ordered:
        pins=[fixed[index] for index in indices if index in fixed and fixed[index] is not None]
        free=[drawer for drawer in available if drawer['id'] not in used and (drawer['id'] not in reserved or drawer['id'] in pins)]
        free_ids={drawer['id'] for drawer in free};preferred=[old.get(keys[index]) for index in indices]
        anchor=next((target for target in preferred if target in free_ids),None)
        slots=[index for index in indices if index not in fixed or fixed[index] is not None]
        chosen=None
        if len(slots)==len(indices):
            required=pins or ([anchor] if anchor is not None else [])
            chosen=block(free,len(indices),required)
            if chosen is None and not pins and anchor is not None:chosen=block(free,len(indices))
        if chosen is None:
            # Keep every explicit choice, including a deliberately unassigned row.
            chosen=list(dict.fromkeys(pins+[target for target in preferred if target in free_ids]+[drawer['id'] for drawer in free]))[:len(slots)]
        remaining=[target for target in chosen if target not in pins]
        for index in indices:
            result[index]=fixed[index] if index in fixed else remaining.pop(0) if remaining else None
            if result[index] is not None:used.add(result[index])
    return result


def spaced_references(plan,targets):
    drawers={drawer['id']:drawer for drawer in plan['available']};series={}
    for group,target in zip(plan['groups'],targets):
        if group.get('split_count',1)>1 and target in drawers:series.setdefault(series_key(group),[]).append(drawers[target])
    return list(dict.fromkeys(plan['preview']['items'][entries[0][0]]['source']+' '+plan['preview']['items'][entries[0][0]]['ref'] for entries,selected in series.items() if len(selected)>1 and not connected(selected)))
