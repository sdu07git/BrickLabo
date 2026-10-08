from __future__ import annotations

from .i18n import tr,tf

import csv
import gzip
import io
import json
import re
import shutil
import sqlite3
import time
import threading
import weakref
import unicodedata
import zipfile
from contextlib import contextmanager
from pathlib import Path


def normalize(text):
    text = unicodedata.normalize('NFKD', str(text or '').lower().replace('×', 'x'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'(?<=\d)\s*x\s*(?=\d)', 'x', text).strip()


def part_has_sticker(ref,name):
    text=normalize(name)
    return int(bool(re.search(r'(?:stk|stkr|sticker)',str(ref),re.I) or re.search(r'\b(?:stickers?|autocollants?)\b',text)))


def part_has_print(ref,name):
    text=normalize(name)
    reference=bool(re.search(r'(?:pat|pb|pr)\d+',str(ref),re.I))
    explicit=bool(re.search(r'\b(?:printed|print|serigraphie|serigraphiee)\b',text))
    pattern=bool(re.search(r'\bpattern\b',text)) and not part_has_sticker(ref,name)
    if re.search(r'\bsticker (?:sheet|for set)\b',text):return 0
    return int(reference or explicit or pattern)


PRINT_EXPRESSION="(i.kind='part' AND (part_has_print(i.ref,i.name)=1 OR (i.source='RB' AND EXISTS (SELECT 1 FROM relationships r WHERE r.child_part_num=i.ref AND r.rel_type='P'))))"
STICKER_EXPRESSION="(i.kind='part' AND part_has_sticker(i.ref,i.name)=1)"


SCHEMA = '''
CREATE TABLE IF NOT EXISTS items (
 id INTEGER PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL,
 name TEXT NOT NULL, category TEXT DEFAULT '', category_id TEXT DEFAULT '',
 image TEXT DEFAULT '', year TEXT DEFAULT '', quantity INTEGER DEFAULT 0,
 alternate TEXT DEFAULT '', weight TEXT DEFAULT '', dimensions TEXT DEFAULT '',
 search TEXT NOT NULL, catalogue_hidden INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL DEFAULT '', UNIQUE(source,kind,ref));
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source,kind,category);
CREATE TABLE IF NOT EXISTS bl_manual_inventory(set_id INTEGER,ordinal INTEGER,item_id INTEGER,color TEXT,quantity INTEGER,extra INTEGER,alternate INTEGER,counterpart INTEGER,match_id INTEGER,PRIMARY KEY(set_id,ordinal));
CREATE INDEX IF NOT EXISTS idx_bl_manual_item ON bl_manual_inventory(item_id,set_id);
CREATE TABLE IF NOT EXISTS inventories(id INTEGER PRIMARY KEY, version INTEGER, set_num TEXT);
CREATE INDEX IF NOT EXISTS idx_inventories_set ON inventories(set_num,version);
CREATE TABLE IF NOT EXISTS inventory_parts (
 inventory_id INTEGER, part_num TEXT, color_id INTEGER, quantity INTEGER, is_spare INTEGER, img_url TEXT);
CREATE INDEX IF NOT EXISTS idx_ip_inventory ON inventory_parts(inventory_id);
CREATE INDEX IF NOT EXISTS idx_ip_part ON inventory_parts(part_num,inventory_id);
CREATE TABLE IF NOT EXISTS inventory_sets(inventory_id INTEGER,set_num TEXT,quantity INTEGER);
CREATE INDEX IF NOT EXISTS idx_is_inventory ON inventory_sets(inventory_id);
CREATE TABLE IF NOT EXISTS inventory_minifigs(inventory_id INTEGER,fig_num TEXT,quantity INTEGER);
CREATE INDEX IF NOT EXISTS idx_im_inventory ON inventory_minifigs(inventory_id);
CREATE INDEX IF NOT EXISTS idx_im_fig ON inventory_minifigs(fig_num,inventory_id);
CREATE TABLE IF NOT EXISTS colors(id INTEGER PRIMARY KEY,name TEXT,rgb TEXT,is_trans INTEGER);
CREATE TABLE IF NOT EXISTS themes(id INTEGER PRIMARY KEY,name TEXT,parent_id INTEGER);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY,name TEXT);
CREATE TABLE IF NOT EXISTS elements(element_id TEXT,part_num TEXT,color_id INTEGER,design_id TEXT);
CREATE INDEX IF NOT EXISTS idx_elements_part ON elements(part_num);
CREATE TABLE IF NOT EXISTS relationships(rel_type TEXT,child_part_num TEXT,parent_part_num TEXT);
CREATE INDEX IF NOT EXISTS idx_relationships_child ON relationships(child_part_num,rel_type);
CREATE TABLE IF NOT EXISTS bl_codes(item_ref TEXT NOT NULL,color_name TEXT NOT NULL,element_code TEXT NOT NULL,
 PRIMARY KEY(item_ref,color_name,element_code));
CREATE INDEX IF NOT EXISTS idx_bl_codes_part ON bl_codes(item_ref);
CREATE TABLE IF NOT EXISTS bl_categories(id TEXT PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bl_itemtypes(id TEXT PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY,item_id INTEGER,color TEXT DEFAULT '',
 quantity INTEGER DEFAULT 1,added TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(item_id,color));
CREATE TABLE IF NOT EXISTS stock_set_components(set_entry_id INTEGER,item_id INTEGER,color TEXT,
 quantity INTEGER NOT NULL,PRIMARY KEY(set_entry_id,item_id,color));
CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY,item_id INTEGER,color TEXT DEFAULT '',
 quantity INTEGER DEFAULT 1,added TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(item_id,color));
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,item_id INTEGER,color TEXT DEFAULT '',
 quantity INTEGER,method TEXT,date TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS visual(item_id INTEGER PRIMARY KEY,mode TEXT DEFAULT '3d',
 color TEXT DEFAULT '',image TEXT DEFAULT '',links TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS brickarchitect(ref TEXT PRIMARY KEY,rank INTEGER,models TEXT,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(file TEXT PRIMARY KEY,path TEXT,date TEXT,rows INTEGER);
'''


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self._reader=None;self._read_lock=threading.RLock();self._reader_finalizer=None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)
            if 'catalogue_hidden' not in {r['name'] for r in c.execute('PRAGMA table_info(items)')}:
                c.execute('ALTER TABLE items ADD COLUMN catalogue_hidden INTEGER NOT NULL DEFAULT 0')
            if 'imported_at' not in {r['name'] for r in c.execute('PRAGMA table_info(items)')}:
                c.execute("ALTER TABLE items ADD COLUMN imported_at TEXT NOT NULL DEFAULT ''")
            c.execute("CREATE TRIGGER IF NOT EXISTS items_import_date AFTER INSERT ON items WHEN NEW.imported_at='' BEGIN UPDATE items SET imported_at=datetime('now','localtime') WHERE id=NEW.id; END")
            c.execute('CREATE INDEX IF NOT EXISTS idx_items_import_date ON items(source,kind,imported_at)')
            from .search_index import prepare_index
            self.search_index_available=prepare_index(c)
            from .stock import prepare
            prepare(self,c)

    @contextmanager
    def connect(self):
        from .sqlite_file import connect
        c = connect(self.path, timeout=90)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA temp_store=MEMORY')
        c.create_function('norm', 1, normalize, deterministic=True)
        c.create_function('part_has_print',2,part_has_print,deterministic=True)
        c.create_function('part_has_sticker',2,part_has_sticker,deterministic=True)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


    @contextmanager
    def read(self):
        """Serialize short reads on one read-only connection; end snapshots promptly."""
        from .sqlite_file import connect
        with self._read_lock:
            if self._reader is None:
                c=connect(self.path,timeout=90,read_only=True,check_same_thread=False)
                try:
                    c.row_factory=sqlite3.Row
                    c.execute('PRAGMA temp_store=MEMORY')
                    c.create_function('norm',1,normalize,deterministic=True)
                    c.create_function('part_has_print',2,part_has_print,deterministic=True)
                    c.create_function('part_has_sticker',2,part_has_sticker,deterministic=True)
                except Exception:c.close();raise
                self._reader=c;self._reader_finalizer=weakref.finalize(self,c.close)
            try:yield self._reader
            finally:self._reader.rollback()

    def close(self):
        with self._read_lock:
            if self._reader is not None:
                self._reader_finalizer();self._reader=None;self._reader_finalizer=None

    def rows(self,sql,args=()):
        with self.read() as c:return [dict(r) for r in c.execute(sql,args)]

    def run(self, sql, args=()):
        with self.connect() as c:
            return c.execute(sql, args).lastrowid

    def setting(self, key, default=None):
        r = self.rows('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(r[0]['value']) if r else default

    def set_setting(self, key, value):
        self.run('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE settings.value<>excluded.value', (key,json.dumps(value,ensure_ascii=False)))

    def get_item(self, item_id):
        r = self.rows('SELECT * FROM items WHERE id=?',(item_id,))
        return r[0] if r else None

    def visual(self, item_id):
        r = self.rows('SELECT * FROM visual WHERE item_id=?',(item_id,))
        v = r[0] if r else {'item_id':item_id,'mode':'3d','color':'','image':'','links':'[]'}
        v['links'] = json.loads(v['links'])
        return v

    def save_visual(self,item_id,**updates):
        v = self.visual(item_id)
        v.update(updates)
        self.run('INSERT INTO visual VALUES(?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET mode=excluded.mode,color=excluded.color,image=excluded.image,links=excluded.links WHERE visual.mode IS NOT excluded.mode OR visual.color IS NOT excluded.color OR visual.image IS NOT excluded.image OR visual.links IS NOT excluded.links',
                 (item_id,v['mode'],v['color'],v['image'],json.dumps(v['links'],ensure_ascii=False)))

    def categories(self,source=None,kind=None):
        clause,args = self.filter_clause(source,kind)
        if source=='ALT':clause+=(' AND ' if clause else 'WHERE ')+'i.catalogue_hidden=0'
        return [r['category'] for r in self.rows('SELECT DISTINCT category FROM items i '+clause+' ORDER BY category COLLATE NOCASE',args)]

    def years(self,source=None,kind='set'):
        clause,args=self.filter_clause(source,kind)
        if source=='ALT':clause+=(' AND ' if clause else 'WHERE ')+'i.catalogue_hidden=0'
        return [r['year'] for r in self.rows("SELECT DISTINCT TRIM(COALESCE(i.year,'')) AS year FROM items i "+clause+' ORDER BY year DESC',args)]

    @staticmethod
    def filter_clause(source=None,kind=None,search='',category=''):
        parts=[]; args=[]
        for col,val in [('source',source),('kind',kind),('category',category)]:
            if val:
                if isinstance(val,(list,tuple)):
                    parts.append('i.'+col+' IN ('+','.join('?' for _ in val)+')');args.extend(val)
                else:parts.append('i.'+col+'=?'); args.append(val)
        for word in normalize(search).split():
            pattern='%'+word.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            parts.append("(i.search LIKE ? ESCAPE '\\' OR norm(COALESCE(i.category,'')) LIKE ? ESCAPE '\\' OR (i.source='RB' AND i.kind='set' AND i.category_id IN (WITH RECURSIVE matching(id) AS (SELECT id FROM themes WHERE norm(name) LIKE ? ESCAPE '\\' UNION SELECT t.id FROM themes t JOIN matching m ON t.parent_id=m.id) SELECT CAST(id AS TEXT) FROM matching)))")
            args.extend([pattern,pattern,pattern])
        return ('WHERE '+' AND '.join(parts) if parts else ''),args

    def query(self,source=None,kind=None,search='',category='',scope='catalogue',page=1,size=100,sort='ref',descending=False,hide_decorated=False,year='',advanced=None):
        clause,args = self.filter_clause(source,kind,search if not self.search_index_available else '',category)
        from .search_index import indexed_clause, advanced_clause
        extra_parts,extra_args=indexed_clause(search) if self.search_index_available else ([],[])
        ap,aa=advanced_clause(advanced or {},scope);extra_parts+=ap;extra_args+=aa
        if extra_parts:clause+=(' AND ' if clause else 'WHERE ')+' AND '.join(extra_parts);args.extend(extra_args)
        if scope=='catalogue':clause+=(' AND ' if clause else 'WHERE ')+'i.catalogue_hidden=0'
        if year:
            clause+=(' AND ' if clause else 'WHERE ')+"TRIM(COALESCE(i.year,''))=?"
            args.append('' if year=='__unknown__' else str(year))
        if hide_decorated:clause+=(' AND ' if clause else 'WHERE ')+f'NOT ({PRINT_EXPRESSION} OR {STICKER_EXPRESSION})'
        join=" LEFT JOIN brickarchitect ba ON i.source='BA' AND ba.ref=i.ref "; extra=',ba.rank AS architect_rank,ba.models AS ldraw_model'; prefix='i.'
        if scope in ('stock','stock_sets','stock_available','queue','history'):
            join+=f' JOIN {scope} s ON s.item_id=i.id '
            if scope!='history':clause+=(' AND ' if clause else 'WHERE ')+'s.quantity>0'
            extra+=",s.id AS entry_id,s.color AS chosen_color,s.quantity AS chosen_quantity,"+('s.date AS date,s.method AS method' if scope=='history' else 's.added AS date')
        allowed={'ref','name','category','year','date','chosen_quantity','chosen_color','source','method','has_print','has_sticker','architect_rank','ldraw_model','imported_at'}
        if sort not in allowed or (sort in {'date','chosen_quantity','chosen_color','method'} and scope not in ('stock','stock_sets','stock_available','queue','history')): sort='ref'
        if sort in {'date','chosen_quantity','chosen_color','method','has_print','has_sticker','architect_rank','ldraw_model'}: prefix=''
        with self.read() as c:
            c.execute('BEGIN')
            total=c.execute('SELECT COUNT(*) FROM items i '+join+clause,args).fetchone()[0]
            pages=max(1,(total+size-1)//size);page=min(max(1,page),pages)
            sql='SELECT i.*,'+PRINT_EXPRESSION+' AS has_print,'+STICKER_EXPRESSION+' AS has_sticker'+extra+' FROM items i '+join+clause+f' ORDER BY {prefix}{sort} COLLATE NOCASE '+('DESC' if descending else 'ASC')+',i.id LIMIT ? OFFSET ?'
            rows=[dict(r) for r in c.execute(sql,args+[size,(page-1)*size])]
        return rows,total,pages,page

    def stock_action(self,scope,item_id,color='',quantity=1):
        item=self.get_item(item_id);quantity=int(quantity)
        if not item:raise ValueError(tr('Référence absente du catalogue'))
        if quantity<1:raise ValueError(tr('Quantité positive requise'))
        if scope=='stock' and item['kind']=='set':scope='stock_sets'
        if scope not in ('stock','stock_sets','queue'):raise ValueError(tr('Destination inconnue'))
        action={'op':'add','scope':scope,'item_id':item_id,'color':str(color),'quantity':quantity}
        if scope=='stock_sets':
            if item['kind']!='set':raise ValueError(tr('Un set est attendu.'))
            parts=self.components(item,strict=True)
            if not parts:raise ValueError(tr('Inventaire indisponible pour ')+item['ref'])
            for part in parts:
                native=self.get_item(part.get('id'))
                if not native or native['kind'] not in ('part','minifig') or int(part.get('chosen_quantity',1))<1:raise ValueError(tr('Inventaire incomplet : ')+item['ref'])
            action['components']=[{'item_id':p['id'],'color':str(p.get('chosen_color','')),'quantity':int(p.get('chosen_quantity',1))} for p in parts if int(p.get('chosen_quantity',1))>0]
        return action

    def add_many(self,entries,description=None):
        from .stock import mutate
        actions=[self.stock_action(*entry) for entry in entries]
        mutate(self,actions,description or tr('Ajout au stock / aux étiquettes'))
        return sum(1+len(action.get('components',[])) for action in actions)

    def add(self,scope,item_id,color='',quantity=1):return self.add_many([(scope,item_id,color,quantity)])

    def remove(self,scope,ids,remove_set_parts=False):
        ids=list(ids)
        if not ids:return
        if scope=='history':
            with self.connect() as c:
                for eid in ids:c.execute('DELETE FROM history WHERE id=?',(eid,));c.execute('DELETE FROM settings WHERE key=?',('label_layout_history_'+str(eid),))
            return
        from .stock import mutate
        mutate(self,[{'op':'remove','scope':scope,'ids':ids,'keep_parts':not remove_set_parts}],tr('Retrait du stock / des étiquettes'))

    def change_entries(self,scope,ids,operation,value):
        from .stock import mutate
        return mutate(self,[{'op':operation,'scope':scope,'ids':list(ids),'value':value}],tr('Modification du stock / des étiquettes'))

    def undo_description(self):
        rows=self.rows('SELECT description FROM stock_undo WHERE id=1');return rows[0]['description'] if rows else ''

    def undo_last_action(self):
        from .stock import undo
        return undo(self)

    def owned_components(self,entry_id):
        return self.rows('SELECT i.*,p.color AS chosen_color,p.quantity AS chosen_quantity,0 AS is_spare FROM stock_set_components p JOIN items i ON i.id=p.item_id WHERE p.set_entry_id=? AND p.quantity>0 ORDER BY i.source,i.ref,p.color',(abs(int(entry_id)),))

    def delete_alternatives(self,ids):
        ids=list(dict.fromkeys(ids))
        if not ids:return
        with self.connect() as c:
            rows=c.execute('SELECT id,source FROM items WHERE id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()
            if len(rows)!=len(ids) or any(row['source']!='ALT' for row in rows):raise ValueError(tr('Seules les références du catalogue alternatif peuvent être supprimées.'))
            # Keep identity and inventory so personal stock/history are preserved.
            c.executemany('UPDATE items SET catalogue_hidden=1 WHERE id=?',[(iid,) for iid in ids])

    def copy_alternative(self,item):
        ref=item['source']+'-'+item['ref']
        self.run('INSERT INTO items(source,kind,ref,name,category,image,search) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,kind,ref) DO UPDATE SET catalogue_hidden=0',
                 ('ALT',item['kind'],ref,item['name'],item['category'],item['image'],normalize(ref+' '+item['name'])))
        if item['kind']=='set':
            target=self.rows("SELECT id FROM items WHERE source='ALT' AND kind='set' AND ref=?",(ref,))[0]['id']
            parts=self.components(item)
            self.set_setting('alt_components_'+str(target),[{'item_id':p['id'],'color':str(p.get('chosen_color','')),'quantity':p.get('chosen_quantity',1)} for p in parts])

    def alternative(self,kind,ref,name,category,image='',item_id=None):
        if not ref.strip() or not name.strip(): raise ValueError(tr('Référence et nom obligatoires'))
        if not item_id:
            hidden=self.rows("SELECT id FROM items WHERE source='ALT' AND kind=? AND ref=? AND catalogue_hidden=1",(kind,ref.strip()))
            if hidden:
                item_id=hidden[0]['id'];self.run('UPDATE items SET catalogue_hidden=0 WHERE id=?',(item_id,))
        args=('ALT',kind,ref.strip(),name.strip(),category,image,normalize(ref+' '+name))
        if item_id:
            self.run('UPDATE items SET source=?,kind=?,ref=?,name=?,category=?,image=?,search=? WHERE id=?',args+(item_id,))
        else:
            self.run('INSERT INTO items(source,kind,ref,name,category,image,search) VALUES(?,?,?,?,?,?,?)',args)

    def add_alt_component(self,set_id,part_id,color,quantity):
        components=self.setting('alt_components_'+str(set_id),[])
        components.append({'item_id':part_id,'color':str(color),'quantity':int(quantity)})
        self.set_setting('alt_components_'+str(set_id),components)

    def components(self,item,visited=None,strict=False):
        visited=set(visited or [])
        key=(item['source'],item['ref'])
        if key in visited:
            if strict:raise ValueError(tr('Inventaire incomplet ou récursif : ')+item['ref'])
            return []
        visited.add(key)
        if item['source']=='ALT':
            out=[]
            for x in self.setting('alt_components_'+str(item['id']),[]):
                part=self.get_item(x['item_id'])
                if strict and not part:raise ValueError(tr('Inventaire incomplet : ')+item['ref'])
                if part and part['kind']=='set':
                    children=self.components(part,visited,strict)
                    if strict and not children:raise ValueError(tr('Inventaire incomplet : ')+part['ref'])
                    out.extend(dict(child,chosen_quantity=int(child['chosen_quantity'])*int(x['quantity'])) for child in children)
                elif part:out.append(dict(part,chosen_color=x['color'],chosen_quantity=x['quantity'],is_spare=0))
            return out
        ref=item['ref']
        if item['source']=='BL':
            if item['kind']=='set' and self.setting('bl_manual_inventory_'+str(item['id'])):
                from .set_inventory import components
                return components(self,item)
            cached=self.setting(('bl_minifig_components_' if item['kind']=='minifig' else 'bl_components_')+item['ref'],[])
            if cached:return cached
            match=self.rows("SELECT * FROM items WHERE source='RB' AND kind='set' AND ref IN (?,?) ORDER BY ref",(ref,ref+'-1'))
            if not match:return []
            ref=match[0]['ref']
        inv=self.rows('SELECT id FROM inventories WHERE set_num=? ORDER BY version DESC LIMIT 1',(ref,))
        if not inv:
            if strict:raise ValueError(tr('Inventaire indisponible pour ')+ref)
            return []
        iid=inv[0]['id']
        if strict:
            for table,column,kind in [('inventory_parts','part_num','part'),('inventory_minifigs','fig_num','minifig'),('inventory_sets','set_num','set')]:
                missing=self.rows('SELECT 1 FROM '+table+" p WHERE p.inventory_id=? AND NOT EXISTS(SELECT 1 FROM items i WHERE i.source='RB' AND i.kind=? AND i.ref=p."+column+') LIMIT 1',(iid,kind))
                if missing:raise ValueError(tr('Inventaire incomplet : ')+ref)
        parts=self.rows("SELECT i.*,p.color_id AS chosen_color,p.quantity AS chosen_quantity,p.is_spare,p.img_url AS inventory_image FROM inventory_parts p JOIN items i ON i.source='RB' AND i.kind='part' AND i.ref=p.part_num WHERE p.inventory_id=?",(iid,))
        figs=self.rows("SELECT i.*, '' AS chosen_color,p.quantity AS chosen_quantity,0 AS is_spare FROM inventory_minifigs p JOIN items i ON i.source='RB' AND i.kind='minifig' AND i.ref=p.fig_num WHERE p.inventory_id=?",(iid,))
        out=parts+figs
        for child in self.rows("SELECT i.*,p.quantity AS multiplier FROM inventory_sets p JOIN items i ON i.source='RB' AND i.kind='set' AND i.ref=p.set_num WHERE p.inventory_id=?",(iid,)):
            for p in self.components(child,visited,strict):
                p['chosen_quantity']*=child['multiplier'];out.append(p)
        return out

    def containing_sets(self,item):
        if item['source']=='ALT':
            out=[]
            for s in self.rows("SELECT * FROM items WHERE source='ALT' AND kind='set'"):
                if any(p['item_id']==item['id'] for p in self.setting('alt_components_'+str(s['id']),[])):out.append(s)
            return out
        if item['source']=='BA':
            from .brickarchitect import native_item
            native=native_item(self,item,'RB')
            return self.containing_sets(native) if native else []
        if item['source']=='BL':
            return self.rows("SELECT DISTINCT s.* FROM bl_manual_inventory p JOIN items s ON s.id=p.set_id WHERE p.item_id=? AND p.alternate=0 AND p.counterpart=0 ORDER BY s.ref",(item['id'],))
        if item['kind']=='minifig':
            join='inventory_minifigs';col='fig_num'
        else:join='inventory_parts';col='part_num'
        return self.rows(f"SELECT DISTINCT s.* FROM {join} p JOIN inventories v ON v.id=p.inventory_id JOIN items s ON s.source='RB' AND s.kind='set' AND s.ref=v.set_num WHERE p.{col}=? AND v.version=(SELECT MAX(v2.version) FROM inventories v2 WHERE v2.set_num=v.set_num) ORDER BY s.ref",(item['ref'],))

    def available_colors(self,item):
        if item['source']=='BL':
            from .color_links import bl_palette
            palette=bl_palette(self.setting)
            ids={str(key) for key in self.setting('bl_available_colors_'+item['kind']+'_'+item['ref'],[])}
            ids.update(row['color'] for row in self.rows("SELECT DISTINCT p.color FROM bl_manual_inventory p JOIN items i ON i.id=p.item_id WHERE i.source='BL' AND i.kind=? AND i.ref=?",(item['kind'],item['ref'])))
            codes={}
            if item['kind']=='part':
                names={c.get('name'):key for key,c in palette.items()}
                for row in self.rows('SELECT color_name,element_code FROM bl_codes WHERE item_ref=?',(item['ref'],)):
                    key=names.get(row['color_name'])
                    if key is not None:
                        ids.add(str(key));codes.setdefault(str(key),[]).append(row['element_code'])
            return sorted([{'id':key,'name':palette.get(key,{}).get('name',tr('Couleur ')+key),'rgb':palette.get(key,{}).get('rgb',''),**({'element_codes':sorted(set(codes[key]))} if key in codes else {})} for key in ids],key=lambda c:c['name'])
        if item['source']!='RB':return []
        return self.rows('SELECT DISTINCT c.* FROM inventory_parts p JOIN colors c ON c.id=p.color_id WHERE p.part_num=? ORDER BY c.name',(item['ref'],))

    def part_image(self,item,color=None):
        if item.get('inventory_image'):return item['inventory_image']
        if item.get('image'):return item['image']
        if item['source']=='RB':
            sql='SELECT img_url FROM inventory_parts WHERE part_num=? AND img_url<>\'\'';args=[item['ref']]
            if color not in ('',None):sql+=' AND color_id=?';args.append(color)
            rows=self.rows(sql+' LIMIT 1',args)
            return rows[0]['img_url'] if rows else ''
        return ''

    def import_file(self,path,progress=lambda *_:None):
        path=Path(path)
        if path.suffix.lower()=='.txt' and re.fullmatch(r'S-(.+)\.txt',path.name,re.I):
            ref=re.fullmatch(r'S-(.+)\.txt',path.name,re.I).group(1)
            selected=self.rows("SELECT * FROM items WHERE source='BL' AND kind='set' AND ref=?",(ref,))
            if not selected:raise ValueError(tr('Importer d’abord le catalogue BrickLink Sets pour trouver le set ')+ref+'.')
            from .set_inventory import import_inventory
            return import_inventory(self,selected[0],path,progress)['rows']
        if path.name.lower()=='complete.zip':
            with zipfile.ZipFile(path) as z:
                if 'ldraw/LDConfig.ldr' not in z.namelist(): raise ValueError(tr('Archive LDraw non reconnue'))
            from .disk_space import reuse_ldraw
            target=reuse_ldraw(self,path)
            self.set_setting('ldraw',str(target))
            self.run('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',('LDraw',str(target),time.strftime('%Y-%m-%d %H:%M'),0))
            return 0
        if path.suffix.lower()=='.zip':
            with zipfile.ZipFile(path) as z:
                names=[n for n in z.namelist() if n.lower().endswith('.csv') and not n.startswith('__MACOSX/')]
                if len(names)!=1:raise ValueError(tr('Le ZIP doit contenir un CSV Rebrickable'))
                with z.open(names[0]) as f:
                    return self._import_rb(Path(names[0]).stem,csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',newline='')),path,progress)
        if path.suffix.lower()=='.gz':
            with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
                return self._import_rb(Path(path.stem).stem,csv.DictReader(f),path,progress)
        with path.open(encoding='utf-8-sig',newline='',errors='strict') as f:
            if path.suffix.lower()=='.csv':return self._import_rb(path.stem,csv.DictReader(f),path,progress)
            return self._import_bl(path.stem,csv.DictReader((line for line in f if line.strip()),delimiter='\t'),path,progress)

    def _insert_items(self,c,records,keep_category=False):
        fields=['name','category','category_id','image','year','quantity','alternate','weight','dimensions','search']
        if keep_category:fields.remove('category')
        updates=','.join(f'{field}=excluded.{field}' for field in fields)
        differences=' OR '.join(f'items.{field} IS NOT excluded.{field}' for field in fields)
        c.executemany('INSERT INTO items(source,kind,ref,name,category,category_id,image,year,quantity,alternate,weight,dimensions,search) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,kind,ref) DO UPDATE SET '+updates+' WHERE '+differences,records)

    def _import_bl(self,stem,reader,path,progress):
        auxiliary={
            'codes':('bl_codes',('Item No','Color','Code')),
            'categories':('bl_categories',('Category ID','Category Name')),
            'itemtypes':('bl_itemtypes',('Item Type ID','Item Type Name'))}
        if stem.lower() in auxiliary:
            table,columns=auxiliary[stem.lower()]
            if not set(columns).issubset(reader.fieldnames or []):raise ValueError(tr('Colonnes BrickLink manquantes : ')+stem)
            count=0;batch=[]
            with self.connect() as c:
                c.execute('DELETE FROM '+table)
                sql='INSERT OR IGNORE INTO '+table+' VALUES('+','.join('?' for _ in columns)+')'
                for row in reader:
                    values=tuple(str(row.get(k) or '').strip() for k in columns)
                    if any(not v for v in values):raise ValueError(tr('Ligne incomplète dans ')+path.name)
                    batch.append(values);count+=1
                    if len(batch)>=5000:c.executemany(sql,batch);batch=[];progress(stem,count)
                c.executemany(sql,batch)
                if table=='bl_categories':
                    c.execute("UPDATE items SET category=(SELECT name FROM bl_categories WHERE id=items.category_id) WHERE source='BL' AND EXISTS(SELECT 1 FROM bl_categories WHERE id=items.category_id) AND category IS NOT (SELECT name FROM bl_categories WHERE id=items.category_id)")
                c.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',(path.name,str(path),time.strftime('%Y-%m-%d %H:%M'),count))
            return count
        # A palette is separate from the item catalog and from per-item availability.
        fields={str(k).strip().lower():k for k in (reader.fieldnames or [])}
        id_field=next((fields[k] for k in ('color id','colorid','id') if k in fields),None)
        name_field=next((fields[k] for k in ('color name','colorname','name') if k in fields),None)
        if stem.lower() in ('colors','colours'):
            if not id_field or not name_field:raise ValueError(tr('Colors.txt doit contenir Color ID et Color Name.'))
            rgb_field=next((fields[k] for k in ('rgb','color code','colorcode','hex','hex code') if k in fields),None)
            palette=dict(self.setting('bl_colors',{}));count=0
            for row in reader:
                key=str(row[id_field]).strip();name=str(row[name_field]).strip()
                if not key.isdigit() or not name:raise ValueError(tr('Identifiant ou nom de couleur BrickLink invalide.'))
                rgb=str(row.get(rgb_field,'') or '').strip().lstrip('#') if rgb_field else ''
                if rgb and not re.fullmatch('[0-9a-fA-F]{6}',rgb):raise ValueError(tr('Code RGB invalide pour ')+name)
                palette[key]={'name':name,'rgb':rgb or palette.get(key,{}).get('rgb',''),'type':row.get(fields.get('type'),''),'year_from':row.get(fields.get('year from'),''),'year_to':row.get(fields.get('year to'),'')};count+=1
            self.set_setting('bl_colors',palette)
            self.run('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',(path.name,str(path),time.strftime('%Y-%m-%d %H:%M'),count))
            return count
        kinds={'Parts':'part','Sets':'set','Minifigures':'minifig','Instructions':'instructions','Original Boxes':'box','Books':'book','Gear':'gear','Catalogs':'catalog'}
        if stem not in kinds:raise ValueError(tr('Type de catalogue BrickLink inconnu : ')+stem)
        if not {'Number','Name','Category Name'}.issubset(reader.fieldnames or []):raise ValueError(tr('Colonnes BrickLink manquantes'))
        count=0;batch=[]
        with self.connect() as c:
            for r in reader:
                batch.append(('BL',kinds[stem],r['Number'],r['Name'],r['Category Name'],r['Category ID'],'',r.get('Year Released',''),0,r.get('Alternate Item Number',''),r.get('Weight (in Grams)',''),r.get('Dimensions',''),normalize(r['Number']+' '+r['Name'])))
                count+=1
                if len(batch)>=5000:self._insert_items(c,batch);batch=[];progress(stem,count)
            self._insert_items(c,batch)
            c.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',(stem+'.txt',str(path),time.strftime('%Y-%m-%d %H:%M'),count))
        return count

    def _import_rb(self,stem,reader,path,progress):
        configs={
            'part_categories':('categories',['id','name']),
            'themes':('themes',['id','name','parent_id']),
            'colors':('colors',['id','name','rgb','is_trans']),
            'inventories':('inventories',['id','version','set_num']),
            'inventory_parts':('inventory_parts',['inventory_id','part_num','color_id','quantity','is_spare','img_url']),
            'inventory_sets':('inventory_sets',['inventory_id','set_num','quantity']),
            'inventory_minifigs':('inventory_minifigs',['inventory_id','fig_num','quantity']),
            'elements':('elements',['element_id','part_num','color_id','design_id']),
            'part_relationships':('relationships',['rel_type','child_part_num','parent_part_num'])}
        if stem not in configs and stem not in ('parts','sets','minifigs'):raise ValueError(tr('CSV Rebrickable inconnu : ')+stem)
        required={'parts':['part_num','name','part_cat_id'],'sets':['set_num','name','theme_id'],'minifigs':['fig_num','name']}.get(stem,configs.get(stem,(None,[]))[1])
        # Les anciennes éditions peuvent ne pas inclure img_url dans inventory_parts.
        if not set(x for x in required if x not in ('img_url','design_id')).issubset(reader.fieldnames or []):raise ValueError(tr('Colonnes Rebrickable manquantes : ')+stem)
        count=0;batch=[]
        with self.connect() as c:
            categories={str(r['id']):r['name'] for r in c.execute('SELECT * FROM '+('categories' if stem=='parts' else 'themes'))} if stem in ('parts','sets') else {}
            if stem in configs:
                table,fields=configs[stem];c.execute('DELETE FROM '+table)
                sql='INSERT INTO '+table+' VALUES('+','.join('?' for _ in fields)+')'
            for r in reader:
                if stem in configs:
                    values=[]
                    for f in fields:
                        v=r.get(f,'')
                        if f in ('is_spare','is_trans'):v=int(str(v).lower() in ('true','1'))
                        if f=='parent_id' and not v:v=None
                        values.append(v)
                    batch.append(values)
                else:
                    kind={'parts':'part','sets':'set','minifigs':'minifig'}[stem]
                    ref=r[{'parts':'part_num','sets':'set_num','minifigs':'fig_num'}[stem]]
                    cid=r.get('part_cat_id',r.get('theme_id',''))
                    batch.append(('RB',kind,ref,r['name'],categories.get(str(cid),''),cid,r.get('img_url',''),r.get('year',''),int(r.get('num_parts',0)), '', '', '',normalize(ref+' '+r['name'])))
                count+=1
                if len(batch)>=10000:
                    if stem in configs:c.executemany(sql,batch)
                    else:self._insert_items(c,batch,keep_category=stem=='minifigs')
                    batch=[];progress(stem,count)
            if stem in configs:c.executemany(sql,batch)
            else:self._insert_items(c,batch,keep_category=stem=='minifigs')
            if stem=='part_categories':c.execute("UPDATE items SET category=COALESCE((SELECT name FROM categories WHERE id=items.category_id),'') WHERE source='RB' AND kind='part' AND category IS NOT COALESCE((SELECT name FROM categories WHERE id=items.category_id),'')")
            if stem=='themes':c.execute("UPDATE items SET category=COALESCE((SELECT name FROM themes WHERE id=items.category_id),'') WHERE source='RB' AND kind='set' AND category IS NOT COALESCE((SELECT name FROM themes WHERE id=items.category_id),'')")
            c.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',(stem+'.csv',str(path),time.strftime('%Y-%m-%d %H:%M'),count))
        return count

    def categorize_minifigs(self):
        value="COALESCE((SELECT group_concat(category,' / ') FROM (SELECT DISTINCT s.category FROM inventory_minifigs m JOIN inventories v ON v.id=m.inventory_id JOIN items s ON s.source='RB' AND s.kind='set' AND s.ref=v.set_num WHERE m.fig_num=items.ref AND s.category<>'' ORDER BY s.category)), 'Non classée')"
        with self.connect() as c:c.execute("UPDATE items SET category="+value+" WHERE source='RB' AND kind='minifig' AND category IS NOT "+value)
