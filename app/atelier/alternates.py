"""Read-only Rebrickable alternate builds for one set; never changes stock."""
import json
import re
from urllib.parse import quote,urlsplit
from urllib.error import HTTPError,URLError
from .services import request
from .i18n import tr
from .result_tables import row_index,fill_table


def set_reference(item):
    if item.get('source') not in ('RB','BL'):return ''
    ref=str(item.get('ref','')).strip()
    return ref+'-1' if re.fullmatch(r'\d+',ref) else ref


def rb_link(url):
    p=urlsplit(str(url or ''))
    return p.scheme=='https' and p.hostname in ('rebrickable.com','www.rebrickable.com') and not p.username and not p.password


def fetch_alternates(key,ref,page=None):
    if not key:raise ValueError(tr('Renseigne ta clé Rebrickable dans « API Keys », puis réessaie.'))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',ref):raise ValueError(tr('Référence de set Rebrickable invalide.'))
    endpoint='https://rebrickable.com/api/v3/lego/sets/'+quote(ref,safe='')+'/alternates/'
    url=page or endpoint+'?page_size=100'
    if urlsplit(url)._replace(query='',fragment='').geturl()!=endpoint:
        raise ValueError(tr('Lien de pagination Rebrickable invalide.'))
    try:data=json.loads(request(url,{'Authorization':'key '+key},timeout=20))
    except HTTPError as e:
        messages={401:'Clé Rebrickable invalide.',403:'Accès Rebrickable refusé. Vérifie ta clé API.',404:'Set introuvable sur Rebrickable. Vérifie sa référence, y compris le suffixe -1.',429:'Limite Rebrickable atteinte. Attends un peu puis réessaie.'}
        raise ValueError(tr(messages.get(e.code,'Rebrickable est indisponible. Réessaie plus tard.'))) from None
    except (URLError,TimeoutError):raise ValueError(tr('Connexion à Rebrickable impossible. Vérifie Internet puis réessaie.')) from None
    if not isinstance(data,dict) or not isinstance(data.get('results'),list):raise ValueError(tr('Réponse Rebrickable inattendue.'))
    rows=[]
    for raw in data['results']:
        if not isinstance(raw,dict):continue
        rows.append({k:raw.get(k,'') for k in ('set_num','name','designer_name','num_parts','year','moc_url','set_url','set_img_url','moc_img_url')})
    next_page=data.get('next')
    if next_page and (not isinstance(next_page,str) or urlsplit(next_page)._replace(query='',fragment='').geturl()!=endpoint):
        raise ValueError(tr('Lien de pagination Rebrickable invalide.'))
    return rows,next_page,data.get('count',len(rows))


from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView
from .ui_common import async_task,scalable


class AlternatesDialog(QDialog):
    def __init__(self,db,engine,item,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.rows=[];self.next_page=None;self.closed=False;self.token=0;self.photo_token=0;self.busy=False
        self.setWindowTitle(tr('Constructions alternatives — ')+str(item['ref']));self.resize(1000,700)
        self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowMinimizeButtonHint)
        layout=QVBoxLayout(self)
        caption=QLabel(str(item['ref'])+' — '+str(item.get('name','')));caption.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(caption)
        note=QLabel(tr('Constructions alternatives répertoriées par Rebrickable pour les pièces de ce set. Certaines notices sont payantes. Cette liste ne compare pas ton stock complet.'));note.setWordWrap(True);layout.addWidget(note)
        bar=QHBoxLayout();bar.addWidget(QLabel(tr('Référence Rebrickable')));self.reference=QLineEdit(set_reference(item));bar.addWidget(self.reference)
        self.refresh=QPushButton(tr('Rechercher / actualiser'));bar.addWidget(self.refresh);self.refresh.clicked.connect(lambda:self.load(True));self.reference.returnPressed.connect(lambda:self.load(True));layout.addLayout(bar)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels([tr('Référence'),tr('Construction'),tr('Créateur'),tr('Pièces')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        self.photo=QLabel(tr('Sélectionne une construction pour voir sa photo.'));self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter);self.photo.setMinimumHeight(180);layout.addWidget(self.photo)
        buttons=QHBoxLayout();self.more=QPushButton(tr('Charger la suite'));self.more.setEnabled(False);self.more.clicked.connect(lambda:self.load(False));buttons.addWidget(self.more)
        self.open=QPushButton(tr('Voir la construction / les notices'));self.open.setEnabled(False);self.open.clicked.connect(self.open_selected);buttons.addWidget(self.open)
        website=QPushButton(tr('Voir le set sur Rebrickable'));website.clicked.connect(self.open_set);buttons.addWidget(website)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);buttons.addWidget(close);layout.addLayout(buttons)
        self.table.itemSelectionChanged.connect(self.select);self.table.itemDoubleClicked.connect(lambda _:self.open_selected())
        if self.reference.text():self.load(True)
        else:self.status.setText(tr('Indique la référence du set LEGO de départ sur Rebrickable.'))
    def load(self,reset):
        if self.busy:return
        ref=self.reference.text().strip()
        if not reset and ref!=getattr(self,'loaded_ref',''):reset=True
        if not reset and not self.next_page:return
        self.busy=True;self.token+=1;token=self.token;self.refresh.setEnabled(False);self.more.setEnabled(False);self.reference.setEnabled(False)
        if reset:
            self.rows=[];self.table.setRowCount(0);self.next_page=None;self.loaded_ref=ref;self.photo_token+=1;self.photo.clear();self.open.setEnabled(False)
        self.status.setText(tr('Chargement des constructions alternatives…'));key=self.db.setting('api_rb','');page=None if reset else self.next_page
        def finish():
            self.busy=False;self.refresh.setEnabled(True);self.reference.setEnabled(True);self.more.setEnabled(bool(self.next_page))
        def done(result):
            if self.closed or token!=self.token:return
            rows,self.next_page,total=result
            from .moc_search import remember
            remember(self.db,[dict(row,bases=[ref],bases_loaded=True) for row in rows])
            known={r['set_num'] for r in self.rows}
            self.rows.extend(r for r in rows if not r['set_num'] or r['set_num'] not in known)
            fill_table(self.table,[[row.get(k) or '' for k in ('set_num','name','designer_name','num_parts')] for row in self.rows])
            self.status.setText(str(len(self.rows))+' / '+str(total)+tr(' construction(s) chargée(s).') if self.rows else tr('Aucune construction alternative répertoriée pour ce set.'))
            finish()
            if self.rows and self.table.currentRow()<0:self.table.selectRow(0)
            else:self.select()
        def fail(error):
            if self.closed or token!=self.token:return
            self.status.setText(error);finish()
        async_task(self,lambda progress:fetch_alternates(key,ref,page),done,fail)
    def selected(self):
        i=row_index(self.table);return self.rows[i] if 0<=i<len(self.rows) else None
    def select(self):
        row=self.selected();self.photo_token+=1;token=self.photo_token
        self.photo.clear();self.open.setEnabled(bool(row and rb_link(row.get('moc_url') or row.get('set_url'))))
        if not row:return
        url=str(row.get('set_img_url') or row.get('moc_img_url') or '')
        if not url or not self.engine:self.photo.setText(tr('Photo indisponible.'));return
        self.photo.setText(tr('Chargement de la photo…'))
        def done(image):
            if self.closed or token!=self.photo_token:return
            if image is None:self.photo.setText(tr('Photo indisponible.'))
            else:scalable(self.photo,image,600,220)
        def fail(error):
            if not self.closed and token==self.photo_token:self.photo.setText(tr('Photo indisponible.'))
        async_task(self,lambda progress:self.engine.images.get(url),done,fail)
    def open_selected(self):
        row=self.selected();url=(row.get('moc_url') or row.get('set_url')) if row else ''
        if rb_link(url):QDesktopServices.openUrl(QUrl(url))
    def open_set(self):
        ref=self.reference.text().strip()
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',ref):QDesktopServices.openUrl(QUrl('https://rebrickable.com/sets/'+quote(ref,safe='')+'/#alt_builds'))
    def done(self,result):
        self.closed=True;self.token+=1;self.photo_token+=1;super().done(result)
