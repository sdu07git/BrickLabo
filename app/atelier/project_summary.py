"""Compute project totals from one shared snapshot, spending each pool per project."""
from collections import Counter,defaultdict


def summarize(c,rows):
    if not rows:return rows
    needs=defaultdict(list)
    for r in c.execute('SELECT project_id,item_id,color,required,reserved FROM project_parts'):
        needs[r['project_id']].append(r)
    reserved=Counter({(r['item_id'],str(r['color'])):r['quantity'] for r in c.execute(
        'SELECT item_id,color,SUM(reserved) AS quantity FROM project_stock_reservations GROUP BY item_id,color')})
    free={};free_colors=Counter()
    for r in c.execute('''SELECT item_id,color,quantity FROM stock
            WHERE item_id IN (SELECT item_id FROM project_parts)'''):
        k=r['item_id'],str(r['color']);free[k]=max(0,r['quantity']-reserved[k]);free_colors[r['item_id']]+=free[k]
    counts=Counter();claims=defaultdict(Counter);explicit=set();warnings=[]
    if any(r['include_set_stock'] for r in rows):
        from .project_stock import owned_sets
        from .set_allocations import unpack
        counts,warnings=owned_sets(c,include_allocated=True)
        for r in c.execute('SELECT project_id,components FROM project_set_allocations'):
            values=unpack(r['components']);claims[r['project_id']].update(values);counts.subtract(values)
        counts=Counter({k:max(0,v) for k,v in counts.items()})
        explicit={r[0] for r in c.execute('SELECT project_id FROM project_set_sources')}
    for row in rows:
        parts=needs[row['id']];required=Counter();own=Counter()
        for p in parts:
            k=(p['item_id'],'*' if row['ignore_colors'] else str(p['color']))
            required[k]+=p['required'];own[k]+=p['reserved']
        row.update(required=sum(required.values()),reserved=sum(own.values()),missing=0,
                   set_stock_warnings=warnings if row['include_set_stock'] else [])
        set_counts=claims[row['id']] if row['id'] in explicit else counts
        sets=Counter()
        if row['include_set_stock']:
            for (identity,color),quantity in set_counts.items():sets[(identity,'*' if row['ignore_colors'] else color)]+=quantity
        for k,quantity in required.items():
            available=free_colors[k[0]] if row['ignore_colors'] else free.get(k,0)
            row['missing']+=max(0,quantity-own[k]-available-sets[k])
    return rows
