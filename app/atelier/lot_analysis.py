"""Explainable local-inventory suggestions and bounded combinations for a lot."""
from collections import Counter
import heapq
import threading

from .i18n import tr


def analyze(db,lot_id,ignore_colors=False,exclude_minifigs=False,minimum=25,max_sets=6,cap_to_free=True,cancel=None,progress=lambda _:None):
    from .build_stock import InventoryReader,compare
    if type(ignore_colors) is not bool or type(exclude_minifigs) is not bool or type(cap_to_free) is not bool or not 1<=minimum<=100 or type(max_sets) is not int or not 1<=max_sets<=20:raise ValueError(tr('Réglages d’analyse du lot invalides.'))
    cancel=cancel or threading.Event()
    with db.read() as c:
        c.execute('BEGIN');lot=c.execute('SELECT * FROM purchase_lots WHERE id=? AND cancelled=0',(lot_id,)).fetchone()
        if not lot:raise ValueError(tr('Lot introuvable ou déjà annulé.'))
        reader=InventoryReader(c,ignore_colors=ignore_colors,exclude_minifigs=exclude_minifigs,include_set_stock=False)
        available=Counter();warnings=[]
        for row in c.execute("SELECT e.*,i.source,i.kind,i.ref,COALESCE(s.quantity,0) AS owned FROM purchase_lot_entries e JOIN items i ON i.id=e.item_id LEFT JOIN stock s ON s.item_id=e.item_id AND s.color=e.color WHERE e.lot_id=? AND e.scope='stock'",(lot_id,)):
            quantity=int(row['quantity'])
            if cap_to_free:
                reserved=c.execute('SELECT COALESCE(SUM(reserved),0) FROM project_stock_reservations WHERE item_id=? AND color=?',(row['item_id'],row['color'])).fetchone()[0]
                quantity=min(quantity,max(0,int(row['owned'])-reserved))
            if quantity<=0 or exclude_minifigs and row['kind']=='minifig':continue
            if row['kind']=='part':counts,unknown=reader.part(row['source'],row['ref'],row['color'],quantity)
            else:
                counts,complete=reader.inventory(row['source'],'minifig',row['ref'],spares=True);counts=Counter({k:v*quantity for k,v in counts.items()})
                if not complete:warnings.append(tr('Certaines minifigurines du lot ont un inventaire incomplet.'))
            available.update(counts)
        if not available:raise ValueError(tr('Ce lot ne contient aucune pièce en vrac utilisable avec ces réglages.'))
        sets=c.execute("SELECT * FROM items WHERE kind='set' AND catalogue_hidden=0 ORDER BY source,ref").fetchall()
        frequency=Counter();candidates=[];excluded=0
        for index,item in enumerate(sets):
            if cancel.is_set():return None
            if index%50==0:progress(str(index)+' / '+str(len(sets))+tr(' sets analysés…'))
            required,complete=reader.inventory(item['source'],'set',item['ref'])
            if not complete or not required:excluded+=1;continue
            shared=required.keys()&available.keys();frequency.update(shared)
            if not shared:continue
            total,missing,percent=compare(required,available)
            if percent+1e-9<minimum:continue
            row=dict(item,required=required,total=total,missing=missing,percent=percent,matched=total-missing,copies=1)
            priority=(percent,total-missing,len(shared),-index)
            if len(candidates)<256:heapq.heappush(candidates,(priority,index,row))
            elif priority>candidates[0][0]:heapq.heapreplace(candidates,(priority,index,row))
        choices=[r for _,_,r in candidates]
        for row in choices:
            shared=row['required'].keys()&available.keys()
            row['distinctive']=sorted(shared,key=lambda key:(frequency[key],key))[:5]
            row['rarity']=sum(1/max(1,frequency[key]) for key in shared)
        choices.sort(key=lambda r:(-r['percent'],-r['rarity'],-r['matched'],r['source'],r['ref']))
        # A bounded beam is deliberately labelled a suggestion, not a global optimum.
        shortlist=choices[:48];beam=[(0.,(),available,0,0)];best=beam[0]
        for depth in range(max_sets):
            expanded=[]
            for score,path,remaining,used,missing_total in beam:
                for index,row in enumerate(shortlist):
                    if cancel.is_set():return None
                    if path and index<path[-1] or path.count(index)>=3:continue
                    required=row['required'];total,missing,percent=compare(required,remaining)
                    if percent+1e-9<minimum or total==missing:continue
                    consumed=required&remaining;units=sum(consumed.values())
                    rarity=sum(1/max(1,frequency[k]) for k in consumed)
                    new_score=score+units-2*missing+rarity
                    state=(new_score,path+(index,),remaining-consumed,used+units,missing_total+missing)
                    expanded.append(state)
                    if (new_score,state[3],-state[4])>(best[0],best[3],-best[4]):best=state
            if not expanded:break
            expanded.sort(key=lambda state:(-state[0],-state[3],state[4],state[1]));beam=expanded[:32]
        if not best[1] and choices:
            # Retain a useful single-set lead even if its missing parts dominate.
            row=choices[0];consumed=row['required']&available
            best=(0.,(0,),available-consumed,sum(consumed.values()),row['missing'])
        multiplicities=Counter(best[1]);selected=[];combination=[];remaining=available.copy()
        for index,copies in sorted(multiplicities.items()):
            row=dict(shortlist[index],copies=copies);row['required']=Counter({k:v*copies for k,v in row['required'].items()})
            total,missing,percent=compare(row['required'],remaining);taken=row['required']&remaining;remaining-=taken
            row.update(allocated=sum(taken.values()),combination_missing=missing);combination.append(row);selected.append(len(combination)-1)
        return dict(lot_id=lot_id,lot_name=lot['name'],suggestions=choices,choices=combination,selected=selected,available=available,remaining=remaining,
            stock_revision=c.execute('SELECT version FROM stock_revision WHERE id=1').fetchone()[0],warnings=sorted(set(warnings)|reader.warnings),excluded=excluded,
            ignore_colors=ignore_colors,exclude_minifigs=exclude_minifigs,include_set_stock=False,cap_to_free=cap_to_free)


def create_projects(db,result):
    from .collection_workflows import create_comparison_projects
    if db.stock_revision()!=result['stock_revision']:raise ValueError(tr('Le stock a changé. Relance l’analyse du lot avant de créer les projets.'))
    return create_comparison_projects(db,result,exclude_minifigs=result['exclude_minifigs'])
