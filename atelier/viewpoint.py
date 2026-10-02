"""Camera settings: independent item overrides, global defaults and named presets."""
import json
import math

DEFAULT_CAMERA={'yaw':180.0,'pitch':-23.0,'roll':-3.0}

def normalize_camera(value):
    value=value if isinstance(value,dict) else {}
    result={}
    for key,limit in (('yaw',180),('pitch',89),('roll',180)):
        try:number=float(value.get(key,0))
        except (TypeError,ValueError):number=0.0
        if not math.isfinite(number):number=0.0
        result[key]=max(-limit,min(limit,number))
    return result

def camera_for_item(db,item):
    local=db.setting('camera_item_'+str(item['id']))
    return normalize_camera(local if local is not None else db.setting('camera_default',DEFAULT_CAMERA))

def save_camera(db,item,camera,all_models=False):
    camera=normalize_camera(camera)
    with db.connect() as c:
        if all_models:
            # An explicit all-model application also replaces earlier item overrides.
            c.execute("DELETE FROM settings WHERE substr(key,1,12)='camera_item_'")
            key='camera_default'
        else:key='camera_item_'+str(item['id'])
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(camera)))
    return camera
