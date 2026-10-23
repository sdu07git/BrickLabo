"""Portable storage families/capacities and exclusive owned-set selections."""
from .i18n import tr


def storage_export(db,record):
    from .preferences_backup import identity
    record['shape_overrides']=[dict(item=identity(db.get_item(r['item_id'])),family=r['family']) for r in db.rows('SELECT * FROM storage_shape_overrides')]
    record['formats']=[]
    for row in db.rows('SELECT * FROM storage_formats ORDER BY name'):
        record['formats'].append(dict(name=row['name'],rules=[dict(item=identity(db.get_item(r['item_id'])),width=r['width'],height=r['height'],capacity=r['capacity']) for r in db.rows('SELECT * FROM storage_capacities WHERE format_id=?',(row['id'],))]))
    walls=db.rows('SELECT * FROM storage_walls ORDER BY id')
    for source,target in zip(walls,record['walls']):
        values=db.rows('SELECT f.name FROM storage_wall_formats w JOIN storage_formats f ON f.id=w.format_id WHERE w.wall_id=?',(source['id'],));target['format']=values[0]['name'] if values else None
    return record


def storage_restore(c,data):
    import uuid
    from .preferences_backup import _item
    c.execute('DELETE FROM storage_capacities');c.execute('DELETE FROM storage_formats');c.execute('DELETE FROM storage_shape_overrides')
    for row in data.get('shape_overrides',[]):
        label=row.get('family','')
        if not isinstance(label,str) or not label.strip() or len(label)>120:raise ValueError(tr('Famille de rangement invalide.'))
        c.execute('INSERT INTO storage_shape_overrides VALUES(?,?)',(_item(c,row['item']),label))
    for row in data.get('formats',[]):
        name=row.get('name','')
        if not isinstance(name,str) or not name.strip() or len(name)>120:raise ValueError(tr('Nom de format invalide.'))
        identity=uuid.uuid4().hex;c.execute('INSERT INTO storage_formats VALUES(?,?)',(identity,name))
        for rule in row.get('rules',[]):
            width,height,capacity=(rule.get(key) for key in ('width','height','capacity'))
            if any(type(n) is not int for n in (width,height,capacity)) or not 1<=width<=100 or not 1<=height<=100 or not 1<=capacity<=1000000000:raise ValueError(tr('Capacité de tiroir invalide.'))
            c.execute('INSERT INTO storage_capacities VALUES(?,?,?,?,?)',(identity,_item(c,rule['item']),width,height,capacity))


def wall_format_restore(c,wall_id,name):
    if name is None:return
    row=c.execute('SELECT id FROM storage_formats WHERE name=?',(name,)).fetchone()
    if not row:raise ValueError(tr('Format de meuble absent de la sauvegarde.'))
    c.execute('INSERT INTO storage_wall_formats VALUES(?,?)',(wall_id,row['id']))


def project_export(db,project_id):
    from .preferences_backup import identity
    from .set_allocations import unpack
    if not db.rows('SELECT 1 FROM project_set_sources WHERE project_id=?',(project_id,)):return None
    result=[]
    for row in db.rows('SELECT a.*,s.item_id,s.color FROM project_set_allocations a JOIN stock_sets s ON s.id=a.set_entry_id WHERE project_id=?',(project_id,)):
        result.append(dict(set=identity(db.get_item(row['item_id'])),color=row['color'],copies=row['copies'],components=[dict(item=identity(db.get_item(i)),color=color,quantity=q) for (i,color),q in unpack(row['components']).items()]))
    return result


def project_restore(c,project_id,selection):
    if selection is None:return
    if not isinstance(selection,list):raise ValueError(tr('Sélection de sets invalide.'))
    from .preferences_backup import _item
    from .projects import amount
    from .set_allocations import pack
    from collections import Counter
    c.execute('INSERT INTO project_set_sources VALUES(?)',(project_id,))
    for row in selection:
        identity=_item(c,row['set']);entry=c.execute('SELECT id FROM stock_sets WHERE item_id=? AND color=?',(identity,str(row['color']))).fetchone()
        if not entry:raise ValueError(tr('Restaure aussi les sets possédés avant leurs affectations aux projets.'))
        counts=Counter()
        for part in row['components']:counts[(_item(c,part['item']),str(part['color']))]+=amount(part['quantity'],1)
        c.execute('INSERT INTO project_set_allocations VALUES(?,?,?,?)',(project_id,entry['id'],amount(row['copies'],1),pack(counts)))
