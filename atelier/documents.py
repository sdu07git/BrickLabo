from __future__ import annotations
import html
import os
import uuid
from datetime import datetime,timezone
from html.parser import HTMLParser
import re
import shutil
import time
import urllib.parse
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QFileDialog,QLineEdit,QMenu,QAbstractItemView
from .services import request
from .ui_common import async_task


def enable_header_menu(table,db,key):
    header=table.horizontalHeader();header.setSectionsMovable(True)
    hidden=db.setting('header_hidden_'+key,[])
    for col in hidden:
        if col<table.columnCount():table.setColumnHidden(col,True)
    header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def show(pos):
        menu=QMenu(table)
        for col in range(table.columnCount()):
            item=table.horizontalHeaderItem(col);action=menu.addAction(item.text() if item else str(col+1));action.setCheckable(True);action.setChecked(not table.isColumnHidden(col))
            def toggle(checked,c=col):
                if not checked and sum(not table.isColumnHidden(x) for x in range(table.columnCount()))<=1:return
                table.setColumnHidden(c,not checked);db.set_setting('header_hidden_'+key,[x for x in range(table.columnCount()) if table.isColumnHidden(x)])
            action.toggled.connect(toggle)
        menu.exec(header.mapToGlobal(pos))
    header.customContextMenuRequested.connect(show)


def pdf_links(content,base):
    # Only publish actual PDF URLs present in the public page; do not guess document IDs.
    content=html.unescape(content.replace('\\/','/'))
    values=re.findall(r'''(?:https?://|//)[^\s<>"'\\]+?\.pdf(?=\?|[\s<>"'\\]|$)(?:\?[^\s<>"'\\]*)?''',content,re.I)
    values+=re.findall(r'''href\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']''',content,re.I)
    return sorted({urllib.parse.urljoin(base,v) for v in values})


class NoticeHTML(HTMLParser):
    def __init__(self,content):
        super().__init__(convert_charrefs=True);self.links=[];self.anchor=None;self.feed(content)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('href'):
            self.anchor={'url':attrs['href'],'text':attrs.get('title') or ''};self.links.append(self.anchor)
        if tag=='img' and self.anchor:self.anchor['text']+=' '+(attrs.get('alt') or '')+' '+(attrs.get('title') or '')
        for key in ('src','data','data-pdf-url','data-download-url'):
            if attrs.get(key) and (tag in ('iframe','embed','object') or key.startswith('data-')):self.links.append({'url':attrs[key],'text':'PDF' if tag in ('embed','object') else (attrs.get('title') or '')})
    def handle_data(self,data):
        if self.anchor:self.anchor['text']+=' '+data
    def handle_endtag(self,tag):
        if tag=='a':self.anchor=None


def notice_targets(content,base):
    content=html.unescape(content.replace('\\/','/'))
    links=NoticeHTML(content).links;pdfs=set(pdf_links(content,base))
    for link in links:
        url=urllib.parse.urljoin(base,link['url']);parsed=urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http','https'):continue
        query=urllib.parse.parse_qs(parsed.query)
        download=('download' in query and query['download'] not in (['0'],['false'])) or '/download' in parsed.path.lower()
        text=link['text'].lower()
        if parsed.path.lower().endswith('.pdf') or rebrickable_document_id(url) or (download and any(word in text for word in ('pdf','download','télécharger','telecharger','mode d’emploi','manual'))):pdfs.add(url)
    return sorted(pdfs),links


def rebrickable_document_id(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.hostname not in ('rebrickable.com','www.rebrickable.com'):return None
    match=re.fullmatch(r'/instructions/(\d+)/[^/]+/download/?',parsed.path)
    return match.group(1) if match else None


def expired_notice_url(url,now=None):
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    now=time.time() if now is None else now
    try:
        if 'expire' in query:return float(query['expire'][0])<=now+30
        if 'X-Amz-Date' in query and 'X-Amz-Expires' in query:
            start=datetime.strptime(query['X-Amz-Date'][0],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()
            return start+float(query['X-Amz-Expires'][0])<=now+30
    except (ValueError,OverflowError):return False
    return False


def lego_instruction_pdf(url):
    parsed=urllib.parse.urlsplit(url)
    return bool(re.search(r'/(?:biassets/bi|product\.bi\.core\.pdf)/\d+\.pdf$',parsed.path,re.I))


def notice_identity(url):
    document=rebrickable_document_id(url)
    if document:return ('Rebrickable',document)
    parsed=urllib.parse.urlsplit(url)
    if parsed.hostname=='rebrickable-set-bi-files.eu-central-1.linodeobjects.com':return (parsed.hostname,parsed.path)
    return url


def discover_notices(content,url,ref,fetch=None,max_pages=5):
    """Follow published set-specific notice pages; return published download URLs."""
    if fetch is None:fetch=lambda u:request(u,timeout=15).decode('utf-8','replace')
    found,links=notice_targets(content,url);seen={url};number=ref.split('-')[0]
    host=urllib.parse.urlsplit(url).hostname or ''
    candidates=[]
    for link in links:
        candidate=urllib.parse.urljoin(url,link['url']);parsed=urllib.parse.urlsplit(candidate)
        if parsed.scheme not in ('http','https') or parsed.hostname!=host or candidate in seen or candidate in found:continue
        relevant=(('manuall.' in host and re.search(r'/lego-set-'+re.escape(number)+r'(?:-|/)',parsed.path,re.I)) or
                  (host.endswith('rebrickable.com') and parsed.path.startswith('/instructions/'+ref+'/')))
        if relevant and candidate not in candidates:candidates.append(candidate)
    errors=[]
    for candidate in candidates[:max_pages]:
        seen.add(candidate)
        try:
            extra,_=notice_targets(fetch(candidate),candidate);found.extend(extra)
        except Exception as error:errors.append(str(error))
    return sorted(set(found)),errors


class DocumentsPanel(QWidget):
    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db;self.item=None;self.token=0;self.entries=[]
        layout=QVBoxLayout(self);layout.addWidget(QLabel('Notices disponibles pour le set sélectionné'))
        row=QHBoxLayout()
        for label,func in [('Rechercher en ligne',self.search),('Ajouter des PDF locaux',self.local),('Ouvrir',self.open_selected),('Télécharger',self.download_selected)]:
            button=QPushButton(label);button.clicked.connect(func);row.addWidget(button)
            if label=='Télécharger':self.download_button=button
            if label=='Ouvrir':self.open_button=button
        layout.addLayout(row)
        self.rb_page_button=QPushButton('Ouvrir les notices Rebrickable dans le navigateur');self.rb_page_button.clicked.connect(self.open_rebrickable_page);layout.addWidget(self.rb_page_button)
        row=QHBoxLayout();self.url=QLineEdit();self.url.setPlaceholderText('Lien PDF ou page de notice Manuall / Rebrickable…');row.addWidget(self.url,1);b=QPushButton('Ajouter le lien');b.clicked.connect(self.add_url);row.addWidget(b);self.remove_button=QPushButton('Supprimer le lien ajouté');self.remove_button.clicked.connect(self.remove_manual);self.remove_button.setEnabled(False);row.addWidget(self.remove_button);layout.addLayout(row)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Notice / document','Source','Disponibilité']);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.itemSelectionChanged.connect(self.update_remove_button);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setStretchLastSection(True);self.table.itemDoubleClicked.connect(lambda _:self.open_selected());layout.addWidget(self.table,1);enable_header_menu(self.table,db,'documents');self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.table.customContextMenuRequested.connect(self.context_menu)
        self.progress_label=QLabel('Sélectionne un set.');self.progress_label.setWordWrap(True);layout.addWidget(self.progress_label)
    def folder(self,item=None):
        item=item or self.item;p=self.db.path.parent/'Notices'/item['ref'];p.mkdir(parents=True,exist_ok=True);return p
    def sources(self,item):
        ref=urllib.parse.quote(item['ref'],safe='');number=ref.split('-')[0]
        return [('LEGO','https://www.lego.com/fr-fr/service/buildinginstructions/'+number),('Rebrickable','https://rebrickable.com/instructions/'+ref+'/'),('Manuall','https://manuall.fr/?s='+urllib.parse.quote('LEGO '+number))]
    def set_item(self,item):
        self.item=dict(item) if item else None;self.token+=1
        if not self.item:
            self.entries=[];self.table.setRowCount(0);self.update_remove_button();self.progress_label.setText('Sélectionne un set.');return
        self.reload();self.progress_label.setText('Les PDF enregistrés sont listés ici. « Rechercher en ligne » recherche les liens PDF publiés par les sources.')
    def open_rebrickable_page(self):
        if self.item:QDesktopServices.openUrl(QUrl('https://rebrickable.com/instructions/'+urllib.parse.quote(self.item['ref'],safe='')+'/'))
    def reload(self):
        if not self.item:return
        self.entries=[{'name':p.name,'source':'Local','url':str(p),'state':'Téléchargé'} for p in sorted(self.folder().glob('*.pdf'))]
        self.entries+=[e for e in self.db.setting('notice_links_'+self.item['ref'],[]) if e.get('manual') or e.get('source')!='LEGO' or lego_instruction_pdf(e['url'])]
        # BrickLink instruction catalog entries are documents, not necessarily downloadable PDFs.
        number=self.item['ref'].split('-')[0]
        for obj in self.db.rows("SELECT * FROM items WHERE source='BL' AND kind='instructions' AND (ref=? OR ref LIKE ?)",(self.item['ref'],number+'-%')):
            self.entries.append({'name':obj['ref']+' — '+obj['name'],'source':'BrickLink','url':'https://www.bricklink.com/v2/catalog/catalogitem.page?I='+urllib.parse.quote(obj['ref'],safe=''),'state':'Fiche de notice'})
        self.table.setRowCount(len(self.entries))
        for r,obj in enumerate(self.entries):
            for c,k in enumerate(['name','source','state']):self.table.setItem(r,c,QTableWidgetItem(obj[k]))
        self.table.setColumnWidth(0,350);self.table.setColumnWidth(1,110);self.update_remove_button()
    def selected(self):
        r=self.table.currentRow();return self.entries[r] if 0<=r<len(self.entries) else None
    def open_selected(self):
        obj=self.selected()
        if obj:QDesktopServices.openUrl(QUrl(obj['url']) if obj['url'].startswith(('https:','http:')) else QUrl.fromLocalFile(obj['url']))
    def local(self):
        if not self.item:return
        paths,_=QFileDialog.getOpenFileNames(self,'Ajouter des notices','','PDF (*.pdf)')
        for p in paths:
            target=self.folder()/Path(p).name
            if Path(p).resolve()!=target.resolve():shutil.copy2(p,target)
        self.reload()
    def add_url(self):
        if not self.item:return
        url=self.url.text().strip()
        if not url.startswith(('http://','https://')):return
        key='notice_links_'+self.item['ref'];entries=self.db.setting(key,[])
        if not any(e['url']==url for e in entries):entries.append({'name':Path(urllib.parse.urlsplit(url).path).name or 'Notice PDF','url':url,'source':'Lien ajouté','state':'À télécharger','manual':True});self.db.set_setting(key,entries)
        self.url.clear();self.reload()
    def selected_manual(self):
        return [self.entries[r.row()] for r in self.table.selectionModel().selectedRows() if r.row()<len(self.entries) and (self.entries[r.row()].get('manual') or self.entries[r.row()].get('source')=='Lien ajouté')]
    def update_remove_button(self):
        self.remove_button.setEnabled(bool(self.selected_manual()))
        obj=self.selected();fiche=bool(obj and obj.get('state')=='Fiche de notice')
        self.open_button.setText('Ouvrir la fiche BrickLink' if fiche else 'Ouvrir')
        self.download_button.setEnabled(bool(obj and obj['url'].startswith(('http:','https:')) and not fiche))
        self.download_button.setToolTip('Cette fiche BrickLink ne contient pas de lien PDF.' if fiche else 'Télécharger le document sélectionné')
    def remove_manual(self):
        if not self.item:return
        urls={entry['url'] for entry in self.selected_manual()}
        if not urls:return
        key='notice_links_'+self.item['ref']
        self.db.set_setting(key,[e for e in self.db.setting(key,[]) if not (e['url'] in urls and (e.get('manual') or e.get('source')=='Lien ajouté'))])
        self.reload();self.progress_label.setText(str(len(urls))+' lien(s) ajouté(s) supprimé(s).')
    def context_menu(self,pos):
        menu=QMenu(self);menu.addAction('Ouvrir',self.open_selected);download=menu.addAction('Télécharger',self.download_selected);obj=self.selected();download.setEnabled(bool(obj and obj.get('state')!='Fiche de notice' and obj['url'].startswith(('http:','https:'))))
        action=menu.addAction('Supprimer le lien ajouté',self.remove_manual);action.setEnabled(bool(self.selected_manual()));menu.exec(self.table.viewport().mapToGlobal(pos))
    def save_discovered(self,item,entries):
        key='notice_links_'+item['ref'];old=self.db.setting(key,[])
        for e in entries:
            existing=next((o for o in old if notice_identity(o['url'])==notice_identity(e['url'])),None)
            if existing:
                manual=existing.get('manual');existing.update(e)
                if manual:existing['manual']=True
            else:old.append(e)
        self.db.set_setting(key,old)
    def search(self):
        if not self.item:return
        item=dict(self.item);token=self.token;self.progress_label.setText('Recherche des notices en ligne…')
        def work(progress):
            entries=[];errors=[]
            for source,url in self.sources(item):
                progress('Recherche des notices : '+source+'…')
                try:
                    links,failures=discover_notices(request(url,timeout=15).decode('utf-8','replace'),url,item['ref'])
                    errors.extend(source+' : '+e for e in failures)
                    for link in links:
                        if source=='LEGO' and not lego_instruction_pdf(link):continue
                        doc=rebrickable_document_id(link)
                        entries.append({'name':'Notice Rebrickable '+doc if doc else Path(urllib.parse.urlsplit(link).path).name or 'Notice PDF','source':source,'url':link,'state':'À télécharger'})
                except Exception as e:
                    message=str(e)
                    if source=='Rebrickable' and getattr(e,'code',None) in (403,429):message+=' — recherche automatique refusée ; ouvre les notices Rebrickable dans le navigateur et ajoute le lien de téléchargement.'
                    errors.append(source+' : '+message)
            return entries,errors
        def done(result):
            entries,errors=result;self.save_discovered(item,entries)
            if token!=self.token:return
            self.reload();self.progress_label.setText(str(len(entries))+' lien(s) PDF trouvé(s). '+('Sources inaccessibles : '+' ; '.join(errors) if errors else 'Tu peux aussi ajouter un lien PDF ou une page de notice.'))
        async_task(self,work,done,lambda e:self.progress_label.setText(e) if token==self.token else None,lambda message:self.progress_label.setText(message) if token==self.token else None)
    def download_selected(self):
        obj=self.selected()
        if not obj or not obj['url'].startswith(('http:','https:')):return
        if obj['state']=='Fiche de notice':self.progress_label.setText('Fiche BrickLink : utilise « Rechercher en ligne » pour trouver un PDF du set.');return
        token=self.token;item=dict(self.item);folder=self.folder(item);url=obj['url']
        name=Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
        if not name.lower().endswith('.pdf'):
            doc=rebrickable_document_id(url)
            name='notice-'+item['ref']+'-'+('rebrickable-'+doc if doc else str(time.time_ns()))+'.pdf'
        dest=folder/name;temp=folder/('.notice-'+uuid.uuid4().hex+'.tmp');self.progress_label.setText('Récupération de la notice, sans limite de 200 Mo…')
        def work(progress):
            target=url
            if expired_notice_url(target):
                host=urllib.parse.urlsplit(target).hostname or ''
                if rebrickable_document_id(target) or host=='rebrickable-set-bi-files.eu-central-1.linodeobjects.com':
                    progress('Actualisation du lien temporaire Rebrickable…')
                    page='https://rebrickable.com/instructions/'+urllib.parse.quote(item['ref'],safe='')+'/'
                    try:
                        content=request(page,timeout=15).decode('utf-8','replace')
                        links,_=discover_notices(content,page,item['ref'])
                    except Exception as error:raise ValueError('Lien Rebrickable expiré. Ouvre les notices dans le navigateur et ajoute un nouveau lien de téléchargement. '+str(error)) from error
                    candidates=[link for link in links if notice_identity(link)==notice_identity(target)]
                    if not candidates and host=='rebrickable-set-bi-files.eu-central-1.linodeobjects.com':
                        filename=Path(urllib.parse.urlsplit(target).path).stem
                        _,anchors=notice_targets(content,page)
                        candidates=[urllib.parse.urljoin(page,a['url']) for a in anchors if rebrickable_document_id(urllib.parse.urljoin(page,a['url'])) and re.search(r'(?<!\d)'+re.escape(filename)+r'(?!\d)',a['text'])]
                        candidates=list(dict.fromkeys(candidates))
                    if len(candidates)>1:raise ValueError('Plusieurs notices correspondent : relance la recherche et sélectionne le document à télécharger.')
                    if not candidates:raise ValueError('Lien Rebrickable expiré : relance la recherche ou ajoute un nouveau lien depuis la page des notices.')
                    target=candidates[0]
            def download(link):
                request(link,headers={'Referer':url},destination=temp,timeout=90)
                with temp.open('rb') as f:return f.read(5)==b'%PDF-'
            try:
                if download(target):os.replace(temp,dest);return dest,[]
                with temp.open('rb') as f:content=f.read(5_000_000).decode('utf-8','replace')
                links,errors=discover_notices(content,target,item['ref'])
                if not links:raise ValueError('Aucun lien PDF téléchargeable trouvé sur cette page. Ajoute le lien PDF direct de la notice.')
                if len(links)>1:
                    source='Manuall' if 'manuall.' in urllib.parse.urlsplit(url).netloc else 'Rebrickable' if 'rebrickable.com' in urllib.parse.urlsplit(url).netloc else 'Source du lien'
                    return None,[{'name':Path(urllib.parse.urlsplit(link).path).name or 'Notice PDF','source':source,'url':link,'state':'À télécharger'} for link in links]
                if not download(links[0]):raise ValueError('Le lien trouvé ne renvoie pas un PDF téléchargeable.')
                os.replace(temp,dest);return dest,[]
            finally:
                if temp.exists():temp.unlink()
        def done(result):
            path,entries=result
            if entries:self.save_discovered(item,entries)
            if token!=self.token:return
            self.reload();self.progress_label.setText('Notice téléchargée : '+path.name if path else str(len(entries))+' notices trouvées : sélectionne le PDF à télécharger.')
        async_task(self,work,done,lambda e:self.progress_label.setText(e) if token==self.token else None)
