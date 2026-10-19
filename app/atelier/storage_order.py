"""Portable category priorities; the footprint sort remains within each family."""
from .data import normalize
from .i18n import tr

SETTING='storage_category_order'


def validate(values):
    if not isinstance(values,(list,tuple)) or any(not isinstance(value,str) for value in values) or len(values)!=len(set(values)):
        raise ValueError(tr('Ordre des catégories invalide.'))
    return list(values)


def saved(db):
    try:return validate(db.setting(SETTING,[]))
    except ValueError:return []


def arranged(categories,preferred):
    categories=set(categories);preferred=validate(preferred)
    return [category for category in preferred if category in categories]+sorted(categories-set(preferred),key=lambda category:(normalize(category),category))


def remember(db,order):
    order=validate(order);db.set_setting(SETTING,order+[category for category in saved(db) if category not in order])


def category_rows(plan):
    """Counts from the proposal's actual scope, without double-counting colours."""
    rows={}
    for group in plan['groups']:
        for category in group['categories']:
            row=rows.setdefault(category,{'category':category,'references':set(),'drawers':0,'unknown':set()});row['drawers']+=1
        for identity,color in group['entries']:
            category=plan['preview']['items'][identity]['category'];rows[category]['references'].add(identity)
    for item in plan['unknown']:
        row=rows.setdefault(item['category'],{'category':item['category'],'references':set(),'drawers':0,'unknown':set()});row['references'].add(item['id']);row['unknown'].add(item['id'])
    return [dict(row,references=len(row['references']),unknown=len(row['unknown'])) for row in rows.values()]
