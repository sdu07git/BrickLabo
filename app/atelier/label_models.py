"""Reusable label layouts and atomic application to a captured selection."""
import copy
import json
import math

from .i18n import tr
from .labels import default_template,independent_category,individual_template_key,template_for_item

CATEGORY_MODELS='label_layout_categories'
LAYOUT_FIELDS=('layers','layout_schema','preset_id','model_name','border','margin','background','transparent_background','outline')


def validate_template(template):
    if not isinstance(template,dict):raise ValueError(tr('Modèle invalide'))
    for key in ('width','height'):
        value=template.get(key)
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not .1<=value<=300:raise ValueError(tr('Modèle invalide'))
    if not isinstance(template.get('layers'),list) or len(template['layers'])>500:raise ValueError(tr('Modèle invalide'))
    for layer in template['layers']:
        if not isinstance(layer,dict) or not isinstance(layer.get('type'),str):raise ValueError(tr('Modèle invalide'))
        for key in ('x','y','w','h'):
            value=layer.get(key)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>10000 or (key in ('w','h') and value<=0):raise ValueError(tr('Modèle invalide'))
    return independent_category({**default_template(),**copy.deepcopy(template)})


def merge_layout(base,model):
    """Use the current sheet format, retaining each label's colours and edges."""
    model=validate_template(model);result=independent_category(base)
    for key in LAYOUT_FIELDS:
        result.pop(key,None)
        if key in model:result[key]=copy.deepcopy(model[key])
    sx=result['width']/model['width'];sy=result['height']/model['height']
    for layer in result['layers']:
        for key in ('x','w'):layer[key]*=sx
        for key in ('y','h'):layer[key]*=sy
    result.pop('use_general',None)
    return result


def save_named_model(db,name,template):
    name=name.strip()
    if not name or len(name)>100:raise ValueError(tr('Nom de modèle invalide'))
    model=validate_template(template);model.pop('use_general',None);model.pop('preset_id',None);model['model_name']=name
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');models=_setting(c,'templates',{})
        models[name]=model;_write(c,'templates',models)
    return name


def delete_named_model(db,name):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');models=_setting(c,'templates',{});models.pop(name,None);_write(c,'templates',models)


def _setting(c,key,default=None):
    row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return json.loads(row['value']) if row else copy.deepcopy(default)


def _write(c,key,value):
    c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,ensure_ascii=False)))


def set_category_model(db,category,template=None):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');models=_setting(c,CATEGORY_MODELS,{})
        if template is None:models.pop(category,None)
        else:
            model=validate_template(template)
            models[category]={key:copy.deepcopy(model[key]) for key in ('width','height',*LAYOUT_FIELDS) if key in model}
        _write(c,CATEGORY_MODELS,models)


def apply_selection(db,items,template):
    """Reject stale identities and commit all labels together; never alter stock."""
    template=validate_template(template);targets={individual_template_key(item):dict(item) for item in items}
    if not targets:raise ValueError(tr('Sélectionne une ou plusieurs lignes.'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');base=_setting(c,'template',default_template())
        layouts=[]
        for key,item in targets.items():
            scope=item.get('_scope')
            if scope in ('queue','stock','stock_sets','history') and item.get('entry_id'):
                row=c.execute('SELECT i.* FROM '+scope+' s JOIN items i ON i.id=s.item_id WHERE s.id=? AND i.id=?',(item['entry_id'],item['id'])).fetchone()
            else:row=c.execute('SELECT * FROM items WHERE id=?',(item['id'],)).fetchone()
            if not row or any(row[field]!=item[field] for field in ('source','kind','ref')):raise ValueError(tr('La sélection a changé. Rouvre l’éditeur avant d’appliquer.'))
            current=template_for_item(dict(item,category=row['category']),db,base,read_setting=lambda name,default=None:_setting(c,name,default))
            layouts.append((key,merge_layout(current,template)))
        for key,model in layouts:_write(c,key,model)
    return len(layouts)
