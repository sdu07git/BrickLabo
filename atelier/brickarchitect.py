"""Brick Architect ranking snapshot, explicit external IDs and LDraw choices."""
from __future__ import annotations

from .i18n import tr,tf
import json,re,datetime,concurrent.futures,threading
from pathlib import Path
from html import unescape
from urllib.parse import urlsplit,parse_qs
from .data import normalize
from .services import request

ORIGIN='https://brickarchitect.com/parts/most-common-allyears'
RESOURCE=Path(__file__).resolve().parent.parent/'ressources'

def parse_page(text,page):
    records=[]
    for ref,row in re.findall(r'<a href="https://brickarchitect.com/parts/([^"/?]+)"><div class="tr">(.*?)</div></a>',text,re.S):
        name=re.search(r'<span class="partname">(.*?)</span>',row,re.S)
        if not name:continue
        title=unescape(re.sub('<[^>]*>',' ',name[1])).strip()
        records.append({'ref':ref,'name':title,'rank':(page-1)*250+len(records)+1,'url':'https://brickarchitect.com/parts/'+ref,'models':[],'BL':[],'RB':[]})
    if not records:raise ValueError(tr('Page Brick Architect vide ou format non reconnu : ')+str(page))
    return records

def parse_detail(text,ref):
    out={'ref':ref,'models':[],'BL':[],'RB':[],'checked':True}
    title=re.search(r'<h1>(.*?)</h1>',text,re.S)
    if not title:raise ValueError(tr('Fiche Brick Architect non reconnue : ')+ref)
    breadcrumb=re.findall(r'href="https://brickarchitect.com/parts/category-[^"]+"[^>]*>(.*?)</a>',text,re.S)
    out['category']=unescape(re.sub('<[^>]*>',' ',breadcrumb[-1])).strip() if breadcrumb else 'Autres'
    for match in re.finditer(r'href="([^"]+)"',text):
        href=match[1]
        description=unescape(re.sub('<[^>]*>',' ',text[match.end():].split('</div>',1)[0]))
        if 'Part not found on' in description:continue
        p=urlsplit(unescape(href))
        if p.hostname=='library.ldraw.org' and p.path=='/parts/list':
            model=parse_qs(p.query).get('tableSearch',[''])[0]
            if re.fullmatch(r'[\w.-]+\.dat',model):out['models'].append(model.lower())
        elif p.hostname in ('www.bricklink.com','bricklink.com') and p.path=='/v2/catalog/catalogitem.page':
            value=parse_qs(p.query).get('P',[''])[0]
            if value:out['BL'].append(value)
        elif p.hostname=='rebrickable.com' and p.path.startswith('/parts/'):
            value=p.path[len('/parts/'):].strip('/')
            if value and '/' not in value:out['RB'].append(value)
    for key in ('models','BL','RB'):out[key]=list(dict.fromkeys(out[key]))
    return out

def record_for(db,ref):
    rows=db.rows('SELECT data FROM brickarchitect WHERE ref=?',(ref,))
    return json.loads(rows[0]['data']) if rows else {}

def replace_catalogue(db,data):
    records=data.get('records',[])
    if not records or len({r['ref'] for r in records})!=len(records):raise ValueError(tr('Catalogue BrickArchitect vide ou références dupliquées.'))
    for r in records:
        if not r.get('ref') or not r.get('name') or not isinstance(r.get('models',[]),list):raise ValueError(tr('Référence BrickArchitect invalide.'))
    with db.connect() as c:
        # Keep metadata for removed entries already referenced by stock/history.
        c.execute("DELETE FROM brickarchitect WHERE ref NOT IN (SELECT i.ref FROM items i WHERE i.source='BA' AND (EXISTS(SELECT 1 FROM stock WHERE item_id=i.id) OR EXISTS(SELECT 1 FROM queue WHERE item_id=i.id) OR EXISTS(SELECT 1 FROM history WHERE item_id=i.id)))")
        c.execute("UPDATE items SET catalogue_hidden=1 WHERE source='BA'")
        for r in records:
            category=r.get('category') or 'Autres'
            alternate=', '.join(dict.fromkeys(r.get('BL',[])+r.get('RB',[])))
            search=normalize(' '.join([r['ref'],r['name'],category,alternate,' '.join(r.get('models',[]))]))
            c.execute('INSERT INTO brickarchitect(ref,rank,models,data) VALUES(?,?,?,?) ON CONFLICT(ref) DO UPDATE SET rank=excluded.rank,models=excluded.models,data=excluded.data',(r['ref'],int(r.get('rank',0)),' / '.join(r.get('models',[])),json.dumps(r,ensure_ascii=False)))
            c.execute("INSERT INTO items(source,kind,ref,name,category,alternate,search) VALUES('BA','part',?,?,?,?,?) ON CONFLICT(source,kind,ref) DO UPDATE SET name=excluded.name,category=excluded.category,alternate=excluded.alternate,search=excluded.search,catalogue_hidden=0",(r['ref'],r['name'],category,alternate,search))
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('brickarchitect_info',json.dumps({k:v for k,v in data.items() if k!='records'},ensure_ascii=False)))
    return len(records)

def enrich_record(db,item):
    info=record_for(db,item['ref'])
    if info.get('checked'):return info
    detail=parse_detail(request(info.get('url','https://brickarchitect.com/parts/'+item['ref']),timeout=15).decode('utf-8','replace'),item['ref'])
    info.update(detail)
    from .architect_models import ensure_models
    ensure_models(db,info)
    with db.connect() as c:
        c.execute('UPDATE brickarchitect SET models=?,data=? WHERE ref=?',(' / '.join(info.get('models',[])),json.dumps(info,ensure_ascii=False),item['ref']))
        alternate=', '.join(dict.fromkeys(info.get('BL',[])+info.get('RB',[])))
        category=info.get('category') or item['category']
        search=normalize(' '.join([item['ref'],item['name'],category,alternate,' '.join(info.get('models',[]))]))
        c.execute('UPDATE items SET category=?,alternate=?,search=? WHERE id=?',(category,alternate,search,item['id']))
    return info

def model_ref(db,item):
    if item['source']!='BA':
        if item['source']=='RB' and item['kind']=='part':
            from .model_links import rebrickable_model
            return rebrickable_model(item['ref']) or item['ref']
        return item['ref']
    models=record_for(db,item['ref']).get('models',[])
    chosen=db.setting('architect_model_'+str(item['id']),'')
    available=[m for m in models if record_for(db,item['ref']).get('model_status',{}).get(m)!='unavailable']
    return chosen if chosen in models else available[0] if available else models[0] if models else item['ref']

def native_item(db,item,source='RB',preview=False):
    if item['source']!='BA':return item
    info=record_for(db,item['ref']);refs=info.get(source,[])
    if not refs:return None
    selected=model_ref(db,item).removesuffix('.dat')
    choice=db.setting('architect_photo_choice_'+str(item['id']),'').partition(':')[2]
    preferred=[choice] if choice in refs else [r for r in refs if r in (item['ref'],selected)]
    # Named photo previews may represent a variant; inventories remain ambiguous.
    refs=preferred or (refs[:1] if preview else refs if len(refs)==1 else [])
    for ref in refs:
        rows=db.rows('SELECT * FROM items WHERE source=? AND kind=? AND ref=?',(source,'part',ref))
        if rows:return rows[0]
    if refs:return {**item,'source':source,'ref':refs[0],'image':''}
    return None

def update_from_site(db,progress=lambda *_:None,pages=22,cancelled=None):
    def check():
        if cancelled and cancelled.is_set():raise ValueError(tr('Mise à jour annulée ; catalogue précédent conservé.'))
    records=[]
    for page in range(1,pages+1):
        check();progress(tr('BrickArchitect : page ')+str(page)+' / '+str(pages))
        records.extend(parse_page(request(ORIGIN+(('?page='+str(page)) if page>1 else '')).decode('utf-8','replace'),page))
    if len({r['ref'] for r in records})!=len(records):raise ValueError(tr('Pagination incohérente : références dupliquées.'))
    def detail(record):
        check()
        try:return parse_detail(request(record['url'],timeout=25).decode('utf-8','replace'),record['ref'])
        except Exception as error:
            import urllib.error
            if isinstance(error,urllib.error.HTTPError) and error.code!=404:raise
            if not isinstance(error,urllib.error.URLError):raise
            previous=record_for(db,record['ref'])
            return {**previous,'ref':record['ref'],'checked':False,'detail_error':str(error),'models':previous.get('models',[]),'BL':previous.get('BL',[]),'RB':previous.get('RB',[])}
    # Limited concurrency; no retry loop or workaround on server refusal.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for index,(record,result) in enumerate(zip(records,pool.map(detail,records))):
            check();record.update(result);progress(tr('Correspondances : ')+str(index+1)+' / '+str(len(records)))
    if pages==22:
        from .architect_models import URLS,build_pack
        folder=db.path.parent/'temporaires'/'brickarchitect';folder.mkdir(parents=True,exist_ok=True)
        archives=[]
        for status,url in URLS.items():
            check();progress(tr('Téléchargement LDraw ')+status+'…');path=folder/(status+'.zip')
            request(url,destination=path,timeout=90);archives.append((status,path))
        check();progress(tr('Vérification des dépendances LDraw…'))
        existing=db.setting('ldraw','')
        build_pack(records,archives,folder/'supplement.pending.zip',existing if existing and Path(existing).is_file() else None)
    check();data={'origin':ORIGIN,'date':datetime.date.today().isoformat(),'records':records,'warnings':[{'ref':r['ref'],'error':r['detail_error']} for r in records if r.get('detail_error')]}
    replace_catalogue(db,data)
    if pages==22:
        import os
        os.replace(folder/'supplement.pending.zip',db.path.parent/'brickarchitect_ldraw.zip')
    return len(records)

from PySide6.QtWidgets import QPushButton,QLabel,QMessageBox
from .catalogue import Catalogue
from .ui_common import async_task
class BrickArchitectCatalogue(Catalogue):
    def __init__(self,db,parent=None):
        bundled=RESOURCE/'brickarchitect.json'
        if bundled.exists() and not db.rows('SELECT 1 FROM brickarchitect LIMIT 1'):
            replace_catalogue(db,json.loads(bundled.read_text(encoding='utf-8')))
        if not db.setting('columns_BA_part_catalogue'):
            db.set_setting('columns_BA_part_catalogue',['ref','name','category','architect_rank','ldraw_model','image'])
        super().__init__(db,'BA','part','catalogue',parent)
        self.button=QPushButton(tr('Mettre à jour BrickArchitect depuis le site…'));self.button.clicked.connect(self.update_site);self.layout().insertWidget(0,self.button)
        self.cancel_button=QPushButton(tr('Annuler la mise à jour'));self.cancel_button.hide();self.cancel_button.clicked.connect(lambda:self.cancelled.set());self.layout().insertWidget(1,self.cancel_button)
        self.info=QLabel();self.info.setWordWrap(True);self.layout().insertWidget(1,self.info);self.update_info()
    def update_info(self):
        info=self.db.setting('brickarchitect_info',{})
        self.info.setText(tr('Classement toutes années · ')+str(self.db.query('BA','part')[1])+tr(' références · ')+str(info.get('date',''))+(' · '+str(len(info.get('warnings',[])))+tr(' fiches non vérifiées') if info.get('warnings') else ''))
    def update_site(self):
        self.button.setEnabled(False);self.cancelled=threading.Event();self.cancel_button.show()
        def done(count):
            self.button.setEnabled(True);self.cancel_button.hide();self.ids.clear();self.reload_categories();self.reload();self.update_info();self.changed.emit();self.selected.emit(None)
            if self.engine:self.engine.ldraw=None;self.engine.ldraw_path=''
            self.load_thumbnails()
            QMessageBox.information(self,'BrickArchitect',str(count)+tr(' références mises à jour. Les éléments du stock et les réglages individuels sont conservés.'))
        def failed(error):self.button.setEnabled(True);self.cancel_button.hide();self.update_info();QMessageBox.warning(self,'BrickArchitect',error)
        async_task(self,lambda progress:update_from_site(self.db,progress,cancelled=self.cancelled),done,failed,progress_callback=self.info.setText)
