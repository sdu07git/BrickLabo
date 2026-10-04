from __future__ import annotations

from .i18n import tr,tf

import hashlib
import hmac
import io
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
import uuid
import threading
from pathlib import Path

from PIL import Image
from .version import VERSION
from .fileio import compact_digest,atomic_output


def rebrickable_set_photo(html,ref,page_url):
    """Read the set's published sharing image, never a recommended set image."""
    from html.parser import HTMLParser
    import re
    class Metadata(HTMLParser):
        def __init__(self):super().__init__();self.values={};self.in_title=False;self.title=''
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='title':self.in_title=True
            if tag=='meta':self.values[str(attrs.get('property') or attrs.get('name') or '').lower()]=attrs.get('content') or ''
        def handle_endtag(self,tag):
            if tag=='title':self.in_title=False
        def handle_data(self,data):
            if self.in_title:self.title+=data
    parser=Metadata();parser.feed(html)
    title=parser.values.get('og:title','')+' '+parser.title
    if not re.search(r'(?<![\w-])'+re.escape(ref)+r'(?![\w-])',title,re.I):return ''
    image=parser.values.get('og:image') or parser.values.get('twitter:image') or ''
    url=urllib.parse.urljoin(page_url,image) if image else ''
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http','https') or parsed.hostname not in ('cdn.rebrickable.com','rebrickable.com'):return ''
    return url


def request(url,headers=None,destination=None,timeout=45):
    if urllib.parse.urlsplit(url).scheme not in ('http','https'):raise ValueError(tr('Lien HTTP ou HTTPS requis'))
    req=urllib.request.Request(url,headers={'User-Agent':'BrickLabo/'+VERSION,**(headers or {})})
    if destination:
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        with atomic_output(destination) as temp:
            with urllib.request.urlopen(req,timeout=timeout) as r,temp.open('wb') as f:
                shutil.copyfileobj(r,f,length=1024*1024)
        return destination
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()


def oauth_header(url,credentials):
    import base64
    quote=lambda x:urllib.parse.quote(str(x),safe='~-._')
    values={'oauth_consumer_key':credentials['consumer_key'],'oauth_token':credentials['token'],
            'oauth_nonce':uuid.uuid4().hex,'oauth_timestamp':str(int(time.time())),
            'oauth_signature_method':'HMAC-SHA1','oauth_version':'1.0'}
    parsed=urllib.parse.urlsplit(url)
    params=sorted(urllib.parse.parse_qsl(parsed.query)+list(values.items()))
    base='GET&'+quote(urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'','')))+'&'+quote('&'.join(quote(k)+'='+quote(v) for k,v in params))
    key=quote(credentials['consumer_secret'])+'&'+quote(credentials['token_secret'])
    values['oauth_signature']=base64.b64encode(hmac.new(key.encode(),base.encode(),hashlib.sha1).digest()).decode()
    return 'OAuth '+', '.join(quote(k)+'="'+quote(v)+'"' for k,v in sorted(values.items()))


class API:
    def __init__(self,db):self.db=db

    def rb(self,path):
        key=self.db.setting('api_rb','')
        if not key:raise ValueError(tr('Clé Rebrickable manquante'))
        url=path if path.startswith('https://rebrickable.com/api/') else 'https://rebrickable.com/api/v3/lego/'+path
        return json.loads(request(url,{'Authorization':'key '+key}))

    def bl(self,path):
        credentials=self.db.setting('api_bl',{})
        if not all(credentials.get(k) for k in ['consumer_key','consumer_secret','token','token_secret']):
            raise ValueError(tr('BrickLink nécessite Consumer Key, Consumer Secret, Token et Token Secret'))
        url='https://api.bricklink.com/api/store/v1/'+path
        result=json.loads(request(url,{'Authorization':oauth_header(url,credentials)}))
        if result.get('meta',{}).get('code')!=200:raise ValueError(result.get('meta',{}).get('description',tr('Erreur BrickLink')))
        return result['data']

    def bl_components(self,item):
        typ='MINIFIG' if item['kind']=='minifig' else 'SET'
        data=self.bl('items/'+typ+'/'+urllib.parse.quote(item['ref'],safe='')+'/subsets?break_minifigs=false&break_subsets=true')
        out=[]
        for group in data:
            for entry in group.get('entries',[]):
                obj=entry['item'];kind='minifig' if obj['type']=='MINIFIG' else 'part'
                found=self.db.rows('SELECT * FROM items WHERE source=\'BL\' AND kind=? AND ref=?',(kind,obj['no']))
                if not found:
                    self.db.run('INSERT INTO items(source,kind,ref,name,category,category_id,search) VALUES(?,?,?,?,?,?,?)',
                                ('BL',kind,obj['no'],obj['name'],'',str(obj.get('category_id','')),obj['no'].lower()+' '+obj['name'].lower()))
                    found=self.db.rows('SELECT * FROM items WHERE source=\'BL\' AND kind=? AND ref=?',(kind,obj['no']))
                out.append(dict(found[0],chosen_color=str(entry.get('color_id','')),chosen_quantity=entry.get('quantity',1),is_spare=0))
        self.db.set_setting(('bl_minifig_components_' if item['kind']=='minifig' else 'bl_components_')+item['ref'],out)
        return out

    def rb_minifig_components(self,item):
        out=[];path='minifigs/'+urllib.parse.quote(item['ref'],safe='')+'/parts/?page_size=1000'
        while path:
            data=self.rb(path)
            for entry in data['results']:
                obj=entry['part'];ref=obj['part_num']
                found=self.db.rows("SELECT * FROM items WHERE source='RB' AND kind='part' AND ref=?",(ref,))
                if not found:
                    from .data import normalize
                    self.db.run('INSERT INTO items(source,kind,ref,name,category_id,image,search) VALUES(?,?,?,?,?,?,?)',('RB','part',ref,obj['name'],str(obj.get('part_cat_id','')),obj.get('part_img_url') or '',normalize(ref+' '+obj['name'])))
                    found=self.db.rows("SELECT * FROM items WHERE source='RB' AND kind='part' AND ref=?",(ref,))
                out.append(dict(found[0],chosen_color=str(entry['color']['id']),chosen_quantity=entry['quantity'],is_spare=entry.get('is_spare',False),inventory_image=entry.get('part_img_url') or obj.get('part_img_url') or ''))
            path=data.get('next')
        self.db.set_setting('rb_minifig_components_'+item['ref'],out)
        return out

    def bl_available_colors(self,item):
        if item['source']!='BL':raise ValueError(tr('Référence BrickLink requise'))
        typ={'part':'PART','minifig':'MINIFIG','set':'SET'}.get(item['kind'])
        if not typ:raise ValueError(tr('Couleurs indisponibles pour ce type de document'))
        # Keep native BrickLink identifiers; never treat an RB ID as a BL ID.
        known=self.bl('items/'+typ+'/'+urllib.parse.quote(item['ref'],safe='')+'/colors')
        palette=self.db.setting('bl_colors',{})
        if not palette:
            colors=self.bl('colors')
            palette={str(c['color_id']):{'name':c['color_name'],'rgb':c.get('color_code') or ''} for c in colors}
            self.db.set_setting('bl_colors',palette)
        ids=[]
        for entry in known:
            key=str(entry['color_id'] if isinstance(entry,dict) else entry)
            if key not in ids:ids.append(key)
        self.db.set_setting('bl_available_colors_'+item['kind']+'_'+item['ref'],ids)
        return self.db.available_colors(item)

    def bl_image(self,item):
        typ={'set':'SET','minifig':'MINIFIG','part':'PART'}.get(item['kind'],'PART')
        data=self.bl('items/'+typ+'/'+urllib.parse.quote(item['ref'],safe=''))
        return data.get('image_url','')

    def rb_download(self,stem,folder):
        # Exports publics complets, l'API enrichit une référence sélectionnée.
        return request('https://cdn.rebrickable.com/media/downloads/'+stem+'.csv.gz',destination=Path(folder)/(stem+'.csv.gz'))

    def enrich(self,item):
        if item['source']=='RB':
            typ={'part':'parts','set':'sets','minifig':'minifigs'}[item['kind']]
            data=self.rb(typ+'/'+urllib.parse.quote(item['ref'],safe='')+'/')
            image=data.get('part_img_url',data.get('set_img_url','')) or ''
            if item['kind'] in ('part','minifig') and 'external_ids' in data:self.db.set_setting('rb_bricklink_refs_'+item['kind']+'_'+item['ref'],data['external_ids'].get('BrickLink',[]))
        elif item['source']=='BL':
            image=self.bl_image(item)
            if not self.db.setting('bl_colors',{}):
                colors=self.bl('colors')
                self.db.set_setting('bl_colors',{str(c['color_id']):{'name':c['color_name'],'rgb':c['color_code']} for c in colors})
        else:raise ValueError(tr('Cette source ne possède pas d’API configurée'))
        if image:self.db.run('UPDATE items SET image=? WHERE id=?',(image,item['id']))
        return image


def rebrickable_photo_links(content,item):
    """Only published image URLs identifying this exact Rebrickable part."""
    import html,re
    content=html.unescape(content.replace('\\/','/'))
    ref=str(item['ref'])
    urls=re.findall(r"(?:https?://|//|/media/)[^\s<>\"'\\]+\.(?:png|gif|jpe?g|webp|bmp)(?:\?[^\s<>\"'\\]*)?",content,re.I)
    out=[]
    for url in urls:
        url=urllib.parse.urljoin('https://rebrickable.com/',url)
        parsed=urllib.parse.urlsplit(url);path=urllib.parse.unquote(parsed.path)
        if parsed.hostname not in ('cdn.rebrickable.com','rebrickable.com'):continue
        if '/parts/' not in path.lower():continue
        if not re.search(r'(?:/|^)'+re.escape(ref)+r'(?:[._-]|/|$)',path,re.I):continue
        if url not in out:out.append(url)
    return out


def rebrickable_photos(db,item):
    """Known inventory photos, optional authenticated API and public part page."""
    ref=str(item['ref']);urls=[];errors=[]
    def add(url):
        if url and urllib.parse.urlsplit(url).scheme in ('http','https') and url not in urls:urls.append(url)
    add(item.get('image',''))
    for row in db.rows("SELECT DISTINCT img_url FROM inventory_parts WHERE part_num=? AND img_url<>''",(ref,)):add(row['img_url'])
    if db.setting('api_rb',''):
        api=API(db)
        try:add(api.rb('parts/'+urllib.parse.quote(ref,safe='')+'/').get('part_img_url') or '')
        except Exception as e:errors.append(tr('API Rebrickable : ')+str(e))
        try:
            path='parts/'+urllib.parse.quote(ref,safe='')+'/colors/?page_size=100';seen=set()
            while path and path not in seen:
                seen.add(path);data=api.rb(path)
                for row in data.get('results',[]):add(row.get('part_img_url') or '')
                path=data.get('next') or ''
                if path and not path.startswith('https://rebrickable.com/api/v3/lego/'):raise ValueError(tr('Pagination Rebrickable invalide'))
        except Exception as e:errors.append(tr('Couleurs Rebrickable : ')+str(e))
    page='https://rebrickable.com/parts/'+urllib.parse.quote(ref,safe='')+'/'
    try:
        for url in rebrickable_photo_links(request(page,timeout=15).decode('utf-8','replace'),item):add(url)
    except Exception as e:errors.append(tr('Page Rebrickable : ')+str(e))
    return urls,errors


def bricklink_photo_links(content,item):
    import html,re
    content=html.unescape(content.replace('\\/','/'))
    urls=re.findall(r"(?:https?://|//)[^\s<>\"'\\]+\.(?:png|gif|jpe?g|webp|bmp)(?:\?[^\s<>\"'\\]*)?",content,re.I)
    ref=item['ref'].lower();out=[]
    for url in urls:
        url=urllib.parse.urljoin('https://www.bricklink.com/',url)
        parsed=urllib.parse.urlsplit(url);stem=Path(urllib.parse.unquote(parsed.path)).stem.lower()
        if parsed.hostname not in ('img.bricklink.com','www.bricklink.com','static.bricklink.com'):continue
        if '/itemimage/' not in parsed.path.lower():continue
        if not re.match(re.escape(ref)+r'(?:$|[_\-.])',stem):continue
        if url not in out:out.append(url)
    return out


import weakref

class Images:
    _locks=weakref.WeakValueDictionary()
    _guard=threading.Lock()
    _missing={}
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)

    def get(self,url,download=True):
        if not url:return None
        if url.startswith('//'):url='https:'+url
        if not url.startswith(('http://','https://')):
            path=Path(url)
            if not path.is_file():return None
        else:
            path=self.folder/(compact_digest(url)+'.img')
            legacy=self.folder/(hashlib.sha256(url.encode()).hexdigest()+'.img')
            if not path.exists() and legacy.is_file():path=legacy
            with self._guard:lock=self._locks.setdefault(str(path),threading.Lock())
            with lock:
                if download and self._missing.get(str(path),0)>time.monotonic():
                    import urllib.error
                    raise urllib.error.HTTPError(url,404,tr('Photo absente (cache temporaire)'),None,None)
                if not path.exists():
                    if not download:return None
                    try:request(url,destination=path,timeout=10)
                    except Exception as e:
                        import urllib.error
                        if isinstance(e,urllib.error.HTTPError) and e.code in (404,410):self._missing[str(path)]=time.monotonic()+300
                        if len(self._missing)>512:
                            for expired in list(self._missing)[:len(self._missing)-512]:self._missing.pop(expired,None)
                        raise
        with Image.open(path) as im:
            im.seek(0);result=im.convert('RGBA')
        if url.startswith(('http://','https://')):
            with self._guard:
                ledger=self.folder/'SOURCES_IMAGES.json'
                try:entries=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
                except (ValueError,OSError):entries={}
                entries[path.name]={'url':url,'date':time.strftime('%Y-%m-%d'),'rights':tr('Droits du fournisseur et des auteurs ; aucune licence libre présumée.')}
                try:
                    with atomic_output(ledger) as temp:temp.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
                except OSError:
                    import logging
                    logging.getLogger('bricklabo').warning('Impossible de mettre à jour le registre des images',exc_info=True)
        return result

    def preserve(self,path):
        path=Path(path)
        with Image.open(path) as im:im.verify()
        dest=self.folder/(uuid.uuid4().hex+path.suffix.lower());shutil.copy2(path,dest)
        return str(dest)
