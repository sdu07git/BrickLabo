"""Resolution of general and per-label edge styles, with legacy migration."""
def normalize_style(value):
    value=value or {}
    return {'black':round(max(0,min(100,float(value.get('black',100)))),1),
            'width':round(max(.5,min(10,float(value.get('width',1)))),1)}

def general_style(db):
    saved=db.setting('edge_settings')
    if saved is not None:return normalize_style(saved)
    level=max(0,min(2,int(db.setting('edge_strength',0))))
    return {'black':86.3 if level==0 else 100.,'width':(1.,1.5,2.)[level],'legacy':level}

def style_for_item(db,item,template=None):
    if template is None:
        from .labels import individual_template_key
        template=db.setting(individual_template_key(item)) or db.setting('label_layout_item_'+str(item['id'])) or {}
    if not template.get('use_general') and isinstance(template.get('edge_settings'),dict):return normalize_style(template['edge_settings'])
    return general_style(db)
