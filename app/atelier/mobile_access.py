"""Opt-in, read-only LAN consultation. No Qt objects enter HTTP worker threads."""
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from io import BytesIO
import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time

from .i18n import tr


def read_request(method):
    def guarded(self,*args,**kwargs):
        with self.query_lock:
            if self.stopping:raise ValueError('Stopped')
            return method(self,*args,**kwargs)
    return guarded


def addresses():
    result={'127.0.0.1'}
    try:
        for _,_,_,_,address in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            ip=ipaddress.ip_address(address[0])
            if ip.is_private and not ip.is_unspecified:result.add(str(ip))
    except OSError:pass
    return sorted(result,key=lambda value:(value.startswith('127.'),value))


class MobileAccess:
    def __init__(self,db):
        self.db=db;self.server=None;self.thread=None;self.code='';self.sessions={};self.failures={};self.lock=threading.Lock();self.urls=[];self.query_lock=threading.RLock();self.stopping=True

    def start(self,host='0.0.0.0',port=0):
        if self.server:return self.urls
        with self.query_lock:self.stopping=False
        self.code=secrets.token_hex(5).upper();self.sessions.clear();self.failures.clear();owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.0'
            def log_message(self,*_):pass
            def setup(self):super().setup();self.connection.settimeout(5)
            def send(self,status,body=b'',kind='application/json; charset=utf-8',cookie=None):
                if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'nonce-"+owner.nonce+"'; style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                if cookie:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(body)
            def host_ok(self):return self.headers.get('Host','') in owner.hosts
            def authenticated(self):
                try:
                    cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''));token=cookies.get('bricklabo_session');value=token.value if token else ''
                except Exception:return False
                with owner.lock:
                    stamp=owner.sessions.get(value)
                    return stamp is not None and time.monotonic()-stamp<24*3600
            def do_GET(self):
                if not self.host_ok():self.send(400,{'error':'Host'});return
                request=urlsplit(self.path)
                if request.path=='/':self.send(200,phone_html(owner.nonce).encode(),'text/html; charset=utf-8');return
                if not self.authenticated():self.send(401,{'error':tr('Saisis le code affiché sur le PC.')});return
                try:
                    args=parse_qs(request.query,keep_blank_values=True,max_num_fields=8)
                    if request.path=='/api/search':result=owner.search(args.get('q',[''])[0],int(args.get('page',['0'])[0]))
                    elif request.path=='/api/cabinets':result=owner.cabinets()
                    elif request.path=='/api/drawer':result=owner.drawer(int(args.get('id',['0'])[0]))
                    elif request.path=='/api/drawers':result=owner.drawers(int(args.get('wall',['0'])[0]))
                    elif request.path=='/api/photo':
                        data=owner.photo(int(args.get('id',['0'])[0]),args.get('color',[''])[0]);self.send(200,data,'image/png') if data else self.send(404,{});return
                    else:self.send(404,{});return
                    self.send(200,result)
                except (ValueError,KeyError):self.send(400,{'error':tr('Recherche invalide.')})
                except Exception:self.send(503,{'error':tr('Consultation momentanément indisponible.')})
            def do_POST(self):
                if not self.host_ok():self.send(400,{});return
                if self.path!='/login':self.send(405,{});return
                if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):self.send(403,{});return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 1<=size<=512:raise ValueError()
                    payload=json.loads(self.rfile.read(size));code=str(payload.get('code','')).strip().upper()
                except (ValueError,TypeError):self.send(400,{});return
                now=time.monotonic();ip=self.client_address[0]
                with owner.lock:
                    failures=owner.failures.setdefault(ip,deque())
                    while failures and now-failures[0]>60:failures.popleft()
                    if len(failures)>=10:self.send(429,{'error':tr('Attends une minute avant de réessayer.')});return
                    if not code.isascii() or not hmac.compare_digest(code,owner.code):failures.append(now);self.send(403,{'error':tr('Code incorrect.')});return
                    if len(owner.sessions)>=1000:owner.sessions={key:stamp for key,stamp in owner.sessions.items() if now-stamp<3600}
                    token=secrets.token_urlsafe(32);owner.sessions[token]=now
                self.send(200,{'ok':True},cookie='bricklabo_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
            def do_PUT(self):self.send(405,{})
            do_DELETE=do_PATCH=do_PUT
        self.nonce=secrets.token_urlsafe(24)
        class Server(ThreadingHTTPServer):daemon_threads=True;block_on_close=False
        self.server=Server((host,port),Handler);actual=self.server.server_address[1]
        ips=addresses() if host=='0.0.0.0' else [host];self.hosts={ip+':'+str(actual) for ip in ips};self.urls=['http://'+ip+':'+str(actual) for ip in ips]
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True);self.thread.start();return self.urls

    def stop(self):
        with self.query_lock:self.stopping=True
        if self.server:
            server,self.server=self.server,None;server.shutdown();server.server_close();self.thread.join(timeout=2)
        self.sessions.clear();self.urls=[];self.code=''

    @read_request
    def search(self,query,page=0):
        from .data import normalize
        if not 0<=page<=100000 or len(query)>200:raise ValueError()
        conditions=[];args=[]
        for word in normalize(query).split():conditions.append("norm(i.ref||' '||i.name||' '||i.category) LIKE ?");args.append('%'+word+'%')
        where=' AND '.join(conditions) or '1'
        with self.db.read() as c:
            c.execute('BEGIN')
            rows=[dict(r) for r in c.execute('''WITH keys AS (SELECT item_id,color FROM stock UNION SELECT item_id,color FROM storage_contents UNION SELECT item_id,color FROM stock_set_components)
                SELECT i.id,i.source,i.kind,i.ref,i.name,i.category,k.color,COALESCE(s.quantity,0) AS quantity,
                COALESCE((SELECT SUM(quantity) FROM storage_contents p WHERE p.item_id=i.id AND p.color=k.color),0) AS located,
                (SELECT COUNT(*) FROM storage_contents p WHERE p.item_id=i.id AND (p.color=k.color OR p.color='')) AS drawer_count,
                COALESCE((SELECT SUM(p.quantity) FROM stock_set_components p JOIN stock_sets o ON o.id=p.set_entry_id WHERE o.quantity>0 AND p.item_id=i.id AND p.color=k.color),0) AS in_sets
                FROM keys k JOIN items i ON i.id=k.item_id LEFT JOIN stock s ON s.item_id=k.item_id AND s.color=k.color WHERE '''+where+''' ORDER BY i.source,i.ref,k.color LIMIT 51 OFFSET ?''',args+[page*50])]
            for row in rows[:50]:
                row['drawers']=[dict(r) for r in c.execute('''SELECT d.id,d.col,d.row,w.name AS cabinet,p.color,p.quantity FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN storage_walls w ON w.id=d.wall_id WHERE p.item_id=? AND (p.color=? OR p.color='') ORDER BY w.y,w.x,d.row,d.col LIMIT 100''',(row['id'],row['color']))]
            self.colour_names(rows[:50])
            return dict(rows=rows[:50],more=len(rows)>50,page=page)

    def colour_names(self,rows):
        from .color_links import rb_palette,bl_palette
        rb=rb_palette();bl=bl_palette(self.db.setting)
        for row in rows:
            source=row['source']
            if source=='ALT':source=(self.db.get_item(row['id']) or {}).get('origin_source','ALT')
            palette=bl if source=='BL' else rb if source=='RB' else {}
            row['color_name']=palette.get(str(row['color']),{}).get('name',str(row['color']))

    @read_request
    def cabinets(self):
        return self.db.rows('SELECT w.*,(SELECT COUNT(*) FROM storage_drawers d WHERE d.wall_id=w.id) AS drawers FROM storage_walls w ORDER BY y,x,id')

    @read_request
    def drawers(self,wall_id):
        if wall_id<=0:raise ValueError()
        return self.db.rows('SELECT d.id,d.col,d.row,w.name AS cabinet,(SELECT SUM(p.quantity) FROM storage_contents p WHERE p.drawer_id=d.id) AS quantity FROM storage_drawers d JOIN storage_walls w ON w.id=d.wall_id WHERE wall_id=? ORDER BY d.row,d.col LIMIT 10000',(wall_id,))

    @read_request
    def drawer(self,identity):
        rows=self.db.rows('SELECT d.*,w.name AS cabinet FROM storage_drawers d JOIN storage_walls w ON w.id=d.wall_id WHERE d.id=?',(identity,))
        if not rows:raise ValueError()
        parts=self.db.rows('''SELECT i.id,i.source,i.ref,i.name,p.color,p.quantity,COALESCE(s.quantity,0) AS owned FROM storage_contents p JOIN items i ON i.id=p.item_id LEFT JOIN stock s ON s.item_id=p.item_id AND s.color=p.color WHERE p.drawer_id=? ORDER BY i.source,i.ref,p.color''',(identity,))
        self.colour_names(parts)
        return dict(drawer=rows[0],parts=parts)

    @read_request
    def photo(self,identity,color=''):
        if len(color)>16:raise ValueError()
        rows=self.db.rows('SELECT image FROM visual WHERE item_id=?',(identity,))
        item=self.db.get_item(identity)
        paths=[]
        if item:
            from .thumbnails import ThumbnailContext
            from .fileio import compact_digest
            import hashlib
            key=ThumbnailContext(self.db).state(dict(item,chosen_color=color))
            paths.append(self.db.path.parent/'cache'/'miniatures'/(str(identity)+'-'+compact_digest(json.dumps(key,ensure_ascii=False,default=str))+'.png'))
            url=self.db.part_image(item,color)
            if url:
                paths.extend(self.db.path.parent/'images'/(name+'.img') for name in (compact_digest(url),hashlib.sha256(url.encode()).hexdigest()))
        for value in ([r['image'] for r in rows]+([item['image']] if item else [])+paths):
            if not value or str(value).startswith(('http:','https:')):continue
            path=Path(value).resolve()
            if not path.is_relative_to(self.db.path.parent.resolve()) or not path.is_file() or path.stat().st_size>16*1024*1024:continue
            try:
                from PIL import Image
                with Image.open(path) as image:
                    image.thumbnail((240,180));out=BytesIO();image.convert('RGBA').save(out,'PNG');return out.getvalue()
            except (OSError,ValueError):continue
        return None


HTML=r'''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BrickLabo · Consultation</title>
<style>body{font:16px system-ui;background:#101923;color:#ecf1f6;margin:0;padding:18px;max-width:900px;margin:auto}h1{font-size:23px}input,button,select{font:inherit;border:1px solid #62798d;border-radius:8px;padding:10px;background:#1d3042;color:inherit}button{cursor:pointer}input{max-width:90%}.bar{display:flex;gap:8px;flex-wrap:wrap}.card{background:#1c2c3b;border-radius:10px;padding:14px;margin:12px 0}.muted{color:#b5c6d5}img{width:90px;height:70px;object-fit:contain;float:right}.tag{margin:5px;padding:6px}a{color:#8dc9ff}#content[hidden],#login[hidden]{display:none}</style>
<h1>BrickLabo · Consultation locale</h1><p class="muted">Stock et tiroirs · lecture seule</p><section id="login"><p>Recopiez le code affiché dans BrickLabo sur le PC.</p><input id="code" autocomplete="one-time-code" placeholder="Code d’accès"><button id="connect">Connexion</button></section><p id="status" role="status"></p>
<section id="content" hidden><div class="bar"><input id="query" placeholder="Référence, nom ou catégorie"><button id="search">Rechercher</button><button id="cabinets">Meubles</button></div><div id="results"></div><button id="next" hidden>Page suivante</button></section>
<script nonce="__NONCE__">const $=id=>document.getElementById(id);let page=0,last='';function text(tag,value,parent,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;parent.append(e);return e}function clear(){$('results').replaceChildren();$('next').hidden=true}async function api(path,options){let r=await fetch(path,options);let v=await r.json();if(!r.ok){if(r.status===401){$('login').hidden=false;$('content').hidden=true}throw Error(v.error||'Connexion impossible')}return v}function card(title){const e=text('article','',$('results'),'card');text('strong',title,e);return e}function img(p,e){let i=document.createElement('img');i.src='/api/photo?id='+p.id+'&color='+encodeURIComponent(p.color||'');i.alt=p.ref;i.onerror=()=>i.remove();e.prepend(i)}function link(d,e){let b=text('button',d.cabinet+' · '+d.col+'/'+d.row+(d.quantity==null?' · quantité à renseigner':' · '+d.quantity),e,'tag');b.onclick=()=>drawer(d.id)}async function search(more=false){try{if(!more){page=0;last=$('query').value;clear()}let v=await api('/api/search?q='+encodeURIComponent(last)+'&page='+page);v.rows.forEach(p=>{let e=card(p.source+' '+p.ref+' · '+p.name);img(p,e);text('p',(p.color_name||p.color)+' · Vrac : '+p.quantity+' · Localisées : '+p.located+' · Dans les sets : '+p.in_sets,e);if(!p.drawers.length)text('p','Aucun tiroir défini',e,'muted');p.drawers.forEach(d=>link(d,e))});$('next').hidden=!v.more;$('status').textContent=v.rows.length?'':'Aucun résultat';}catch(e){$('status').textContent=e.message}}async function cabinets(){try{clear();let v=await api('/api/cabinets');v.forEach(w=>{let e=card(w.name);text('p',w.columns+' colonnes × '+w.rows+' rangées · '+w.drawers+' tiroirs',e);let b=text('button','Afficher les tiroirs',e);b.onclick=async()=>{let ds=await api('/api/drawers?wall='+w.id);ds.forEach(d=>link(d,e));b.remove()}})}catch(e){$('status').textContent=e.message}}async function drawer(id){try{let v=await api('/api/drawer?id='+id);clear();let e=card(v.drawer.cabinet+' · '+v.drawer.col+'/'+v.drawer.row);v.parts.forEach(p=>{let c=text('div','',e,'card');img(p,c);text('strong',p.source+' '+p.ref+' · '+p.name,c);text('p','Couleur : '+(p.color_name||p.color)+' · '+(p.quantity==null?'Quantité non renseignée':p.quantity+' pièce(s)')+' · Vrac total : '+p.owned,c)});if(!v.parts.length)text('p','Tiroir vide',e)}catch(e){$('status').textContent=e.message}}$('connect').onclick=async()=>{try{await api('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('code').value})});$('login').hidden=true;$('content').hidden=false;$('status').textContent='';await search()}catch(e){$('status').textContent=e.message}};$('search').onclick=()=>search();$('query').onkeydown=e=>{if(e.key==='Enter')search()};$('next').onclick=()=>{page++;search(true)};$('cabinets').onclick=cabinets;api('/api/cabinets').then(()=>{$('login').hidden=true;$('content').hidden=false}).catch(()=>{});</script></html>'''


def phone_html(nonce):
    from .i18n import language
    page=HTML.replace('__NONCE__',nonce)
    # Labels in HTML and JS text nodes; all user values still use textContent.
    if language()=='en':
        translations={'lang="fr"':'lang="en"','Consultation locale':'Local consultation','Stock et tiroirs · lecture seule':'Stock and drawers · read only',
            'Recopiez le code affiché dans BrickLabo sur le PC.':'Enter the code displayed in BrickLabo on the PC.',
            'Code d’accès':'Access code','Connexion impossible':'Connection failed','Connexion':'Connect',
            'Référence, nom ou catégorie':'Reference, name or category','Rechercher':'Search','Meubles':'Cabinets',
            'Page suivante':'Next page','Afficher les tiroirs':'Show drawers','quantité à renseigner':'quantity unknown',
            'Aucun tiroir défini':'No drawer defined','Aucun résultat':'No results','Quantité non renseignée':'Quantity unknown',
            'Tiroir vide':'Empty drawer','Couleur : ':'Colour: ','pièce(s)':'unit(s)','Vrac total : ':'Total loose: ',
            'Vrac : ':'Loose: ','Localisées : ':'Located: ','Dans les sets : ':'In owned sets: ',
            'colonnes':'columns','rangées':'rows','tiroirs':'drawers'}
        for source,target in sorted(translations.items(),key=lambda pair:-len(pair[0])):page=page.replace(source,target)
    return page


def dialog(parent):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QSpinBox
    from .windows import show_window
    from .collection_dialogs import safe
    if not hasattr(parent,'mobile_access'):parent.mobile_access=MobileAccess(parent.db)
    service=parent.mobile_access;window=QDialog(parent);window.setWindowTitle(tr('Consultation sur téléphone'));window.resize(670,410);layout=QVBoxLayout(window)
    note=QLabel(tr('Connecte le téléphone et le PC au même Wi-Fi. Démarre l’accès, ouvre une des adresses dans le navigateur du téléphone, puis saisis le code. Le PC et BrickLabo doivent rester ouverts. Aucune modification du stock n’est possible depuis le téléphone.'));note.setWordWrap(True);layout.addWidget(note)
    status=QLabel();status.setWordWrap(True);status.setTextInteractionFlags(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(status)
    def refresh():status.setText(('\n'.join(service.urls)+'\n'+tr('Code d’accès : ')+service.code) if service.server else tr('Accès téléphone arrêté.'))
    port=QSpinBox();port.setRange(1024,65535);port.setValue(parent.db.setting('mobile_port',8765));layout.addWidget(QLabel(tr('Port local pour le téléphone')));layout.addWidget(port)
    def start():
        def run():service.start(port=port.value());parent.db.set_setting('mobile_port',port.value());refresh()
        safe(window,run)
    def stop():service.stop();refresh()
    for title,callback in [(tr('Démarrer l’accès téléphone'),start),(tr('Arrêter l’accès téléphone'),stop)]:
        button=QPushButton(title);button.clicked.connect(callback);layout.addWidget(button)
    hint=QLabel(tr('Utilise uniquement un réseau local de confiance. Si Windows demande une autorisation réseau, choisis le réseau privé. Aucune ouverture de port sur le routeur n’est nécessaire. Les adresses peuvent changer au prochain démarrage.'));hint.setWordWrap(True);layout.addWidget(hint);refresh();show_window(window,parent);return window
