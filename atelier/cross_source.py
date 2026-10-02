"""Photo cross-references require explicit source metadata, never equal IDs alone."""
import json
from pathlib import Path
from .services import API

def bricklink_reference(db,item,download=False):
    if item.get('source')=='BL':return item['ref']
    if item.get('source')!='RB' or item.get('kind') not in ('part','minifig'):return None
    key='rb_bricklink_refs_'+item['kind']+'_'+item['ref']
    refs=db.setting(key)
    if refs is None:
        path=Path(__file__).resolve().parent.parent/'ressources'/'verified_photo_refs.json'
        known=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        refs=known.get(item['kind']+':'+item['ref'],{}).get('BrickLink')
    if refs is None and download and db.setting('api_rb',''):
        import urllib.parse
        typ={'part':'parts','minifig':'minifigs'}[item['kind']]
        data=API(db).rb(typ+'/'+urllib.parse.quote(item['ref'],safe='')+'/')
        refs=data.get('external_ids',{}).get('BrickLink',[])
        db.set_setting(key,refs)
    if isinstance(refs,str):refs=[refs]
    refs=list(dict.fromkeys(str(x) for x in refs or [] if x))
    return refs[0] if len(refs)==1 else None
