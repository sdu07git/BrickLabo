"""Persistent correction jobs; stock changes and applied markers commit together."""
import json
import uuid
from pathlib import Path

from .i18n import tr
from .stock_import import read_list,resolve_rows,import_rows

FIELDS=('source','kind','ref','color','quantity')


def create_job(db,path,source='auto',destination='stock'):
    if destination not in ('stock','stock_sets'):raise ValueError(tr('Destination inconnue'))
    rows=read_list(path,source,strict=False)
    job=uuid.uuid4().hex
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO stock_import_jobs(id,filename,source,destination) VALUES(?,?,?,?)',(job,str(Path(path)),source,destination))
        c.executemany('INSERT INTO stock_import_rows VALUES(?,?,?,?)',[(job,row['line_number'],json.dumps({k:row[k] for k in FIELDS},ensure_ascii=False),json.dumps(row['original'],ensure_ascii=False)) for row in rows])
    return job


def jobs(db):
    return db.rows('''SELECT j.*,COUNT(r.ordinal) AS total,COUNT(a.ordinal) AS imported,
        COUNT(r.ordinal)-COUNT(a.ordinal) AS pending FROM stock_import_jobs j
        JOIN stock_import_rows r ON r.job_id=j.id LEFT JOIN stock_import_applied a
        ON a.job_id=r.job_id AND a.ordinal=r.ordinal GROUP BY j.id
        HAVING pending>0 ORDER BY j.created DESC,j.rowid DESC''')


def job_rows(db,job):
    rows=db.rows('''SELECT r.*,a.ordinal IS NOT NULL AS imported FROM stock_import_rows r
        LEFT JOIN stock_import_applied a ON a.job_id=r.job_id AND a.ordinal=r.ordinal
        WHERE r.job_id=? ORDER BY r.ordinal''',(job,))
    return [dict(json.loads(r['payload']),ordinal=r['ordinal'],original=json.loads(r['original']),imported=bool(r['imported'])) for r in rows]


def update_row(db,job,ordinal,payload):
    data={key:payload.get(key,'') for key in FIELDS}
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM stock_import_applied WHERE job_id=? AND ordinal=?',(job,ordinal)).fetchone():raise ValueError(tr('Cette ligne a déjà été importée.'))
        if not c.execute('UPDATE stock_import_rows SET payload=? WHERE job_id=? AND ordinal=?',(json.dumps(data,ensure_ascii=False),job,ordinal)).rowcount:raise ValueError(tr('Ligne d’import introuvable.'))


def update_destination(db,job,destination,target_entry=None,name=''):
    if destination not in ('stock','stock_sets'):raise ValueError(tr('Destination inconnue'))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM stock_import_jobs WHERE id=?',(job,)).fetchone()
        if not old:raise ValueError(tr('Import introuvable.'))
        new=(destination,target_entry,name.strip())
        applied=list(c.execute('SELECT r.payload FROM stock_import_rows r JOIN stock_import_applied a ON a.job_id=r.job_id AND a.ordinal=r.ordinal WHERE r.job_id=?',(job,)))
        if applied:
            target_exists=old['target_entry'] is not None and c.execute('SELECT 1 FROM stock_sets WHERE id=? AND quantity>0',(old['target_entry'],)).fetchone()
            attached=any(json.loads(row['payload'])['kind']!='set' for row in applied)
            if destination!=old['destination'] or attached and target_exists and new[1:]!=(old['target_entry'],old['name']):
                raise ValueError(tr('La destination reste celle des lignes déjà importées.'))
        c.execute('UPDATE stock_import_jobs SET destination=?,target_entry=?,name=? WHERE id=?',new+(job,))


def import_ready(db,job):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        details=c.execute('SELECT * FROM stock_import_jobs WHERE id=?',(job,)).fetchone()
        if not details:raise ValueError(tr('Import introuvable.'))
        pending=list(c.execute('''SELECT r.* FROM stock_import_rows r WHERE r.job_id=?
            AND NOT EXISTS(SELECT 1 FROM stock_import_applied a WHERE a.job_id=r.job_id AND a.ordinal=r.ordinal)
            ORDER BY r.ordinal''',(job,)))
        resolved=resolve_rows(db,[dict(json.loads(r['payload']),ordinal=r['ordinal']) for r in pending])
        ready=[r for r in resolved if not r['issue']]
        count=import_rows(db,ready,details['destination'],details['target_entry'],details['name'],connection=c,
                          completion={'op':'import_complete','job_id':job,'ordinals':[r['ordinal'] for r in ready]})
    return {'imported':count,'pending':len(pending)-count}
