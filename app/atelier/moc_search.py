"""On-demand public MOC search. The v3 API has no global MOC search endpoint."""
import re
import threading
import time
from html.parser import HTMLParser
from urllib.parse import quote,urljoin,urlsplit,urlunsplit,urlencode,unquote
from .services import request
from .alternates import rb_link
from .data import normalize
from .i18n import tr

class Node:
    def __init__(self,tag='',attrs=(),parent=None):self.tag=tag;self.attrs=dict(attrs);self.parent=parent;self.children=[]
    def has(self,cls):return cls in self.attrs.get('class','').split()
    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child,Node):yield from child.walk()
    def text(self):return ' '.join(c.text() if isinstance(c,Node) else c for c in self.children)

class Tree(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs,self.stack[-1]);self.stack[-1].children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.stack.append(node)
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:del self.stack[i:];break
    def handle_data(self,data):self.stack[-1].children.append(data)

def _tree(html):tree=Tree();tree.feed(html);return tree.root
def _text(node):return re.sub(r'\s+',' ',node.text()).strip()
def _clean_link(value,page):
    url=urljoin(page,value);parsed=urlsplit(url)
    return urlunsplit(parsed._replace(query='',fragment='')) if rb_link(url) else ''

def search_url(keyword='',creator='',free=False,alternates=True,page=1):
    creator=creator.strip()
    if len(creator)>100 or '/' in creator or '\\' in creator:raise ValueError(tr('Indique le nom exact du profil du créateur.'))
    path='/users/'+quote(creator,safe='')+'/mocs/' if creator else '/mocs/'
    values={'q':keyword.strip(),'page':int(page),'inc_free':'on'}
    if not free:values['inc_premium']='on'
    if alternates:values.update(show_alts_only='on',inc_partial_alts='on')
    return 'https://rebrickable.com'+path+'?'+urlencode(values)

def parse_search(html,page_url):
    tree=_tree(html);rows=[];seen=set()
    for card in (n for n in tree.walk() if n.has('set-tn')):
        name=next((n for n in card.walk() if n.has('js-set-name')),None)
        link=next((n for n in name.walk() if n.tag=='a'),None) if name else None
        if link is None:continue
        url=_clean_link(link.attrs.get('href',''),page_url)
        match=re.search(r'/mocs/(MOC-\d+)/',url,re.I)
        if not match or match[1].upper() in seen:continue
        ref=match[1].upper();seen.add(ref)
        creator=next((n for n in card.walk() if n.tag=='a' and '/users/' in n.attrs.get('href','')),None)
        metadata=next((n for n in card.walk() if n.has('js-sort-data')),None)
        amount=metadata.attrs.get('data-num_parts','0') if metadata else '0'
        image=next((n for n in card.walk() if n.tag=='img' and (n.attrs.get('data-src') or n.attrs.get('src'))),None)
        img=urljoin(page_url,image.attrs.get('data-src') or image.attrs.get('src')) if image else ''
        if urlsplit(img).hostname not in ('cdn.rebrickable.com','rebrickable.com'):img=''
        rows.append({'set_num':ref,'name':_text(link),'designer_name':_text(creator) if creator else unquote(urlsplit(url).path.split('/')[3]),'num_parts':int(amount) if amount.isdigit() else 0,'moc_url':url,'moc_img_url':img,'bases':[],'bases_loaded':False})
    next_node=next((n for n in tree.walk() if n.tag=='a' and (n.attrs.get('rel')=='next' or n.attrs.get('aria-label')=='Next page')),None)
    next_page=urljoin(page_url,next_node.attrs.get('href','')) if next_node else None
    if next_page and (not rb_link(next_page) or urlsplit(next_page).path!=urlsplit(page_url).path):raise ValueError(tr('Pagination Rebrickable invalide'))
    if not rows and not any(word in html.lower() for word in ('no results','no mocs','no sets','nothing found','0 results','no matches','no matching')):raise ValueError(tr('La page Rebrickable ne peut pas être lue. Ouvre la recherche dans le navigateur.'))
    return rows,next_page

_web_lock=threading.Lock();_last_call=0
def public_page(url):
    global _last_call
    if not rb_link(url):raise ValueError(tr('Lien Rebrickable invalide'))
    with _web_lock:
        delay=1.1-(time.monotonic()-_last_call)
        if delay>0:time.sleep(delay)
        try:
            raw=request(url,timeout=20)
            if len(raw)>16*1024*1024:raise ValueError(tr('Page trop volumineuse'))
            return raw.decode('utf-8')
        finally:_last_call=time.monotonic()

def fetch_search(url):return parse_search(public_page(url),url)

def parse_bases(html,url):
    tree=_tree(html);nodes=list(tree.walk());result=[]
    for node in nodes:
        if node.tag not in ('p','h3','h4','h5') or 'alternate build of the following' not in _text(node).lower():continue
        siblings=node.parent.children if node.parent else []
        start=siblings.index(node)+1
        for sibling in siblings[start:]:
            if isinstance(sibling,Node) and sibling.tag in ('p','h3','h4','h5'):break
            if not isinstance(sibling,Node):continue
            for link in sibling.walk():
                if link.tag!='a':continue
                target=_clean_link(link.attrs.get('href',''),url)
                match=re.search(r'/sets/([A-Za-z0-9_.-]+)/',target)
                if match and match[1] not in result:result.append(match[1])
            if result:break
    return result

def fetch_bases(row):
    url=row.get('moc_url') or row.get('set_url')
    if not url:return []
    return parse_bases(public_page(url),url)

def remember(db,rows):
    saved={r['set_num']:r for r in db.setting('moc_search_records',[]) if r.get('set_num')}
    for row in rows:
        if not row.get('set_num'):continue
        old=saved.pop(row['set_num'],{})
        data=dict(old,**row);data['bases']=sorted(set(old.get('bases',[]))|set(row.get('bases',[])));data['bases_loaded']=bool(old.get('bases_loaded') or row.get('bases_loaded'));saved[row['set_num']]=data
    db.set_setting('moc_search_records',list(saved.values())[-2000:])

def local_rows(db,keyword='',creator='',alternates=True):
    records={r['set_num']:dict(r) for r in db.setting('moc_search_records',[]) if r.get('set_num')}
    import json
    for value in db.rows("SELECT key,value FROM settings WHERE key LIKE 'stock_mocs_%'"):
        base=value['key'][len('stock_mocs_'):]
        for row in json.loads(value['value']).get('rows',[]):
            if not row.get('set_num'):continue
            data=records.setdefault(row['set_num'],dict(row,bases=[],bases_loaded=True));data['bases']=sorted(set(data.get('bases',[]))|{base})
    words=normalize(keyword).split();author=normalize(creator)
    return [r for r in records.values() if (not alternates or r.get('bases') or not r.get('bases_loaded')) and all(w in normalize(r.get('name','')+' '+r['set_num']) for w in words) and author in normalize(r.get('designer_name',''))]

from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QCheckBox,QPushButton,QTableWidget,QAbstractItemView,QHeaderView
from .ui_common import async_task,scalable
from .result_tables import fill_table,row_index

class MocSearchDialog(QDialog):
    def __init__(self,db,engine,parent=None,keyword='',creator=''):
        super().__init__(parent);self.db=db;self.engine=engine;self.rows=[];self.next_page=None;self.busy=False;self.closed=False;self.photo_token=0
        self.setWindowTitle(tr('Recherche de MOC et constructions alternatives'));self.resize(1100,780);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        layout=QVBoxLayout(self);bar=QHBoxLayout();layout.addLayout(bar);self.keyword=QLineEdit();self.keyword.setPlaceholderText(tr('Mot clé, par exemple falcon'));bar.addWidget(self.keyword,1);self.creator=QLineEdit();self.creator.setPlaceholderText(tr('Nom exact du profil du créateur'));bar.addWidget(self.creator,1)
        self.keyword.setText(keyword);self.creator.setText(creator)
        self.mode=QComboBox();self.mode.addItem(tr('Recherche publique en ligne'),'online');self.mode.addItem(tr('Résultats déjà consultés (non exhaustifs)'),'local');bar.addWidget(self.mode)
        options=QHBoxLayout();layout.addLayout(options);self.alternates=QCheckBox(tr('Constructions alternatives uniquement'));options.addWidget(self.alternates);self.free=QCheckBox(tr('Notices gratuites uniquement'));options.addWidget(self.free);self.run=QPushButton(tr('Rechercher'));self.run.clicked.connect(lambda:self.load(True));options.addWidget(self.run);self.keyword.returnPressed.connect(lambda:self.load(True));self.creator.returnPressed.connect(lambda:self.load(True))
        note=QLabel(tr('Recherche dans tous les MOC et alternatives publiés sur Rebrickable, indépendamment de ton stock. Sélectionne un résultat pour voir sa photo et les sets de départ indiqués, avec leurs liens pour consulter le set à acheter. Charger la suite affiche les pages suivantes.'));note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels([tr('Référence'),tr('Construction'),tr('Créateur'),tr('Pièces'),tr('Sets de départ')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.horizontalHeader().setStretchLastSection(False);layout.addWidget(self.table,1)
        for column,width in enumerate((110,350,170,75,280)):self.table.setColumnWidth(column,width)
        self.photo=QLabel();self.photo.setMinimumHeight(150);self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.photo);self.origins=QLabel();self.origins.setWordWrap(True);self.origins.setTextFormat(Qt.TextFormat.RichText);self.origins.setOpenExternalLinks(True);layout.addWidget(self.origins)
        buttons=QHBoxLayout();layout.addLayout(buttons);self.more=QPushButton(tr('Charger la suite'));self.more.setEnabled(False);self.more.clicked.connect(lambda:self.load(False));buttons.addWidget(self.more);self.open=QPushButton(tr('Voir la construction / les notices'));self.open.clicked.connect(self.open_selected);self.open.setEnabled(False);buttons.addWidget(self.open);web=QPushButton(tr('Ouvrir la recherche sur Rebrickable'));web.clicked.connect(self.open_search);buttons.addWidget(web);close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);buttons.addWidget(close);self.table.itemSelectionChanged.connect(self.select);self.table.itemDoubleClicked.connect(lambda _:self.open_selected())
    def controls(self,busy):
        self.busy=busy
        for widget in (self.run,self.keyword,self.creator,self.mode,self.free,self.alternates):widget.setEnabled(not busy)
        self.more.setEnabled(not busy and bool(self.next_page))
    def fill(self):fill_table(self.table,[(r['set_num'],r.get('name',''),r.get('designer_name',''),r.get('num_parts',0),', '.join(r.get('bases',[])) or tr('À vérifier')) for r in self.rows])
    def load(self,reset):
        if self.busy:return
        if reset and not (self.keyword.text().strip() or self.creator.text().strip()):self.status.setText(tr('Indique un mot clé ou un créateur.'));return
        if self.mode.currentData()=='local':
            if self.free.isChecked():self.status.setText(tr('Le prix des notices n’est pas connu dans les résultats mémorisés. Utilise la recherche en ligne pour ce filtre.'));return
            self.rows=local_rows(self.db,self.keyword.text(),self.creator.text(),self.alternates.isChecked());self.next_page=None;self.fill();self.status.setText(str(len(self.rows))+tr(' résultats mémorisés, liste non exhaustive.'));self.controls(False);self.select();return
        try:url=search_url(self.keyword.text(),self.creator.text(),self.free.isChecked(),self.alternates.isChecked()) if reset else self.next_page
        except ValueError as error:self.status.setText(str(error));return
        if not url:return
        if reset:self.rows=[];self.fill();self.photo_token+=1;self.photo.clear();self.origins.clear();self.open.setEnabled(False)
        self.controls(True);self.status.setText(tr('Recherche sur Rebrickable…'))
        def done(result):
            if self.closed:return
            rows,self.next_page=result;known={r['set_num'] for r in self.rows};self.rows.extend(r for r in rows if r['set_num'] not in known);remember(self.db,rows);self.fill();self.status.setText(str(len(self.rows))+tr(' résultats chargés.'));self.controls(False)
            if self.rows:self.table.selectRow(0)
        def failed(error):
            if not self.closed:self.status.setText(str(error)+tr('\nLa recherche reste disponible avec le bouton Rebrickable.'));self.controls(False)
        async_task(self,lambda progress:fetch_search(url),done,failed)
    def selected(self):
        index=row_index(self.table);return self.rows[index] if 0<=index<len(self.rows) else None
    def select(self):
        row=self.selected();self.photo_token+=1;token=self.photo_token;self.photo.clear();self.origins.clear();self.open.setEnabled(bool(row))
        if not row:return
        self.show_origins(row)
        def work(progress):
            image=None;errors=[];bases=None
            try:
                url=row.get('moc_img_url') or row.get('set_img_url')
                if url and self.engine:image=self.engine.images.get(url)
            except Exception as error:errors.append(str(error))
            if not row.get('bases_loaded'):
                try:bases=fetch_bases(row)
                except Exception as error:errors.append(str(error))
            return image,bases,errors
        def done(result):
            if self.closed or token!=self.photo_token:return
            image,bases,errors=result
            if image is not None:scalable(self.photo,image,700,180)
            else:self.photo.setText(tr('Photo indisponible.'))
            if bases is not None:
                row['bases']=sorted(set(row.get('bases',[]))|set(bases));row['bases_loaded']=True;remember(self.db,[row])
                for position in range(self.table.rowCount()):
                    index=row_index(self.table,position)
                    if 0<=index<len(self.rows) and self.rows[index] is row:
                        self.table.item(position,4).setText(', '.join(row['bases']) or tr('Origine non indiquée sur la page.'));break
                self.show_origins(row)
            if errors:self.origins.setToolTip('\n'.join(errors))
        async_task(self,work,done,lambda error:self.status.setText(str(error)) if not self.closed else None)
    def show_origins(self,row):
        bases=row.get('bases',[])
        self.origins.setText(tr('Sets de départ : ')+', '.join('<a href="https://rebrickable.com/sets/'+quote(ref,safe='')+'/">'+__import__('html').escape(ref)+'</a>' for ref in bases) if bases else tr('Origine non indiquée sur la page.') if row.get('bases_loaded') else tr('Recherche du set de départ…'))
    def open_selected(self):
        row=self.selected();url=(row.get('moc_url') or row.get('set_url')) if row else ''
        if rb_link(url):QDesktopServices.openUrl(QUrl(url))
    def open_search(self):
        try:QDesktopServices.openUrl(QUrl(search_url(self.keyword.text(),self.creator.text(),self.free.isChecked(),self.alternates.isChecked())))
        except ValueError as error:self.status.setText(str(error))
    def done(self,result):self.closed=True;self.photo_token+=1;super().done(result)
