"""Read only explicit, unambiguous model links extracted from LDraw headers."""
import json
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def links():
    path=Path(__file__).resolve().parent.parent/'ressources'/'rebrickable_ldraw_refs.json'
    return json.loads(path.read_text(encoding='utf-8')).get('models',{}) if path.exists() else {}

def rebrickable_model(ref):return links().get(ref)
