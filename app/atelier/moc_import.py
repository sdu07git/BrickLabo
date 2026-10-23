"""Import a build requirement, never a declaration of ownership."""
from pathlib import Path
from .i18n import tr


def preview(db,path,source='auto'):
    from .stock_import import read_list,resolve_rows
    path=Path(path)
    if path.stat().st_size>50*1024*1024:raise ValueError(tr('Fichier trop volumineux (50 Mo maximum).'))
    raw=path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError(tr('Les déclarations XML externes ne sont pas acceptées.'))
    return resolve(db,read_list(path,source,strict=False))


def resolve(db,rows):
    from .stock_import import resolve_rows
    result=resolve_rows(db,rows)
    for row in result:
        if row.get('kind') not in ('part','minifig'):row['issue']=tr('Un inventaire de MOC doit contenir des pièces ou des minifigurines, pas des sets.')
    return result


def create_project(db,name,rows,ignore_colors=False):
    from .projects import create
    resolved=resolve(db,rows)
    if not resolved or any(row['issue'] for row in resolved):raise ValueError(tr('Corrige toutes les lignes avant de créer le projet.'))
    return create(db,name,[dict(item_id=r['item']['id'],color=str(r['color']),quantity=r['quantity']) for r in resolved],ignore_colors=ignore_colors)
