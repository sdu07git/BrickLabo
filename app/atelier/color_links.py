"""Official color links bundled with the application; IDs retain their namespace."""

from .paths import resources_directory
import json
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def table():
    return json.loads((resources_directory()/'color_links.json').read_text(encoding='utf-8'))['colors']

def rb_palette():
    return {r['id']:r for r in table()}

def candidates(setting, color):
    color=str(color)
    bundled=[r['id'] for r in table() if any(e['id']==color for e in r['external']['BL'])]
    # The verified snapshot takes precedence over old cached conversions.
    return bundled or sorted(set(str(v) for v in setting('export_rb_bl_colors',{}).get(color,[])))

def choice_key(ref,color):
    return json.dumps([str(ref),str(color)],ensure_ascii=False,separators=(',',':'))

def resolve(setting,ref,color):
    options=candidates(setting,color)
    selected=setting('color_choices',{}).get(choice_key(ref,color),'')
    if selected in options:return selected
    return options[0] if len(options)==1 else ''

def save_choice(db,ref,color,selected):
    if selected and selected not in candidates(db.setting,color):raise ValueError('Correspondance de couleur inconnue')
    values=dict(db.setting('color_choices',{}));key=choice_key(ref,color)
    if selected:values[key]=str(selected)
    else:values.pop(key,None)
    db.set_setting('color_choices',values)

def bl_palette(setting):
    result={}
    for r in table():
        for e in r['external']['BL']:
            entry=result.setdefault(e['id'],{'name':' / '.join(e['names']),'rgb':r['rgb']})
            if entry['rgb']!=r['rgb']:entry['rgb']=''
    for key,value in setting('bl_colors',{}).items():result.setdefault(str(key),{}).update(value)
    return result

def describe(rb):
    r=rb_palette().get(str(rb))
    if not r:return 'Rebrickable '+str(rb)
    parts=['Rebrickable '+r['id']+' — '+r['name']]
    for ns in ('BL','LEGO','LDraw'):
        parts.append(('BrickLink' if ns=='BL' else ns)+': '+(', '.join(e['id'] for e in r['external'][ns]) or '—'))
    return ' | '.join(parts)
