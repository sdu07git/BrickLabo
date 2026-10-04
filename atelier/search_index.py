"""Rebuildable local substring index; inventory/stock remain relational data."""
import logging
import re
import sqlite3
from datetime import date
from .i18n import tr

DOCUMENT="norm(COALESCE({p}search,'') || ' ' || {p}ref || ' ' || {p}name || ' ' || COALESCE({p}category,''))"

def prepare_index(c):
    """Build once for existing catalogues. Triggers keep later imports in sync.

    FTS5 trigram is optional in SQLite distributions. A missing tokenizer retains
    the legacy search rather than preventing the portable application from opening.
    """
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='items_search'").fetchone():
        return True
    try:
        c.execute("CREATE VIRTUAL TABLE items_search USING fts5(text, tokenize='trigram', detail='none')")
    except sqlite3.OperationalError:
        logging.getLogger(__name__).warning('FTS5 trigram unavailable; using compatible catalogue search',exc_info=True)
        return False
    c.execute('INSERT INTO items_search(rowid,text) SELECT id,'+DOCUMENT.format(p='')+' FROM items')
    # execute(), not executescript(), preserves the migration transaction.
    c.execute('CREATE TRIGGER items_search_insert AFTER INSERT ON items BEGIN INSERT OR REPLACE INTO items_search(rowid,text) VALUES(new.id,'+DOCUMENT.format(p='new.')+'); END')
    c.execute('CREATE TRIGGER items_search_delete AFTER DELETE ON items BEGIN DELETE FROM items_search WHERE rowid=old.id; END')
    c.execute('CREATE TRIGGER items_search_update AFTER UPDATE OF search,ref,name,category ON items BEGIN DELETE FROM items_search WHERE rowid=old.id; INSERT INTO items_search(rowid,text) VALUES(new.id,'+DOCUMENT.format(p='new.')+'); END')
    return True

def indexed_clause(search):
    from .data import normalize
    parts=[];args=[]
    for word in normalize(search).split():
        pattern='%'+word.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        # ESCAPE disables FTS5's LIKE optimization. Plain words take the indexed
        # route; wildcard characters remain literal with a safe escaped fallback.
        if any(ch in word for ch in ('\\','%','_')):
            condition="text LIKE ? ESCAPE '\\'"
        else:condition='text LIKE ?'
        parts.append("(i.id IN (SELECT rowid FROM items_search WHERE "+condition+") OR (i.source='RB' AND i.kind='set' AND i.category_id IN (WITH RECURSIVE matching(id) AS (SELECT id FROM themes WHERE norm(name) LIKE ? ESCAPE '\\' UNION SELECT t.id FROM themes t JOIN matching m ON t.parent_id=m.id) SELECT CAST(id AS TEXT) FROM matching)))")
        args.extend((pattern,pattern))
    return parts,args

def advanced_clause(filters,scope):
    parts=[];args=[]
    # All field names and SQL fragments are controlled here; values stay bound.
    categories=filters.get('categories',[])
    if isinstance(categories,(list,tuple)):
        values=list(dict.fromkeys(v for v in categories if isinstance(v,str) and v))
        if values:parts.append('i.category IN ('+','.join('?' for _ in values)+')');args.extend(values)
    sources=filters.get('sources')
    if sources:
        values=[s for s in sources if s in ('RB','BL','BA','ALT')]
        if values:parts.append('i.source IN ('+','.join('?' for _ in values)+')');args.extend(values)
    from .data import PRINT_EXPRESSION,STICKER_EXPRESSION
    expressions={'printed':PRINT_EXPRESSION,'sticker':STICKER_EXPRESSION,
                 'photo':"(TRIM(COALESCE(i.image,''))<>'' OR EXISTS(SELECT 1 FROM visual v WHERE v.item_id=i.id AND TRIM(COALESCE(v.image,''))<>''))",
                 'stock':'EXISTS(SELECT 1 FROM stock st WHERE st.item_id=i.id AND st.quantity>0)'}
    for key,expression in expressions.items():
        if filters.get(key) in ('yes','no'):parts.append(('' if filters[key]=='yes' else 'NOT ')+expression)
    for key,operator in [('year_min','>='),('year_max','<=')]:
        value=str(filters.get(key,'')).strip()
        if re.fullmatch(r'\d{4}',value):
            parts.append("(TRIM(COALESCE(i.year,'')) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(i.year AS INTEGER) "+operator+' ?)');args.append(int(value))
    for key,operator in [('import_from','>='),('import_to','<=')]:
        value=filters.get(key,'')
        if value:
            try:date.fromisoformat(value)
            except (ValueError,TypeError):raise ValueError(tr('Saisis les dates au format AAAA-MM-JJ.'))
            parts.append('substr(i.imported_at,1,10) '+operator+' ?');args.append(value)
    if scope in ('stock','queue','history') and filters.get('color','')!='':
        parts.append('s.color=?');args.append(str(filters['color']))
    return parts,args
