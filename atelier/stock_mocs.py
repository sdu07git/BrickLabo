"""Discover alternate builds through sets covered by the selected stock.
The API exposes no general MOC inventory search: results are suggestions,
not an independently verified MOC bill of materials.
"""
import threading,time
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
from .i18n import tr
from .result_tables import row_index,fill_table
from .ui_common import async_task,scalable
from .build_stock import find_builds
from .alternates import fetch_alternates,rb_link

class StockMocsDialog(QDialog):
    def __init__(self,db,engine,excluded,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.excluded=list(excluded);self.closed=False;self.busy=False;self.cancel=threading.Event();self.sets=[];self.cursor=0;self.rows=[];self.photos=0
        self.setWindowTitle(tr('MOC avec les pièces disponibles'));self.resize(1050,750)
        layout=QVBoxLayout(self)
        note=QLabel(tr('Les pièces en vrac et les pièces des sets autorisés sont combinées, en couleurs exactes. BrickLabo recherche les alternatives des sets Rebrickable reconstituables à 100 %. Ce n’est pas une recherche exhaustive de MOC. Les inventaires des MOC ne sont pas vérifiés : contrôler les pièces, pièces supplémentaires et notices sur Rebrickable. Chaque proposition utilise le même stock indépendamment.'));note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel(tr('Clique sur Rechercher pour analyser le stock sélectionné.'));self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels([tr('Référence'),tr('Construction'),tr('Créateur'),tr('Pièces'),tr('Sets de départ')]);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        self.photo=QLabel();self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter);self.photo.setMinimumHeight(160);layout.addWidget(self.photo)
        buttons=QHBoxLayout();self.run=QPushButton(tr('Rechercher'));self.more=QPushButton(tr('Analyser les 20 sets suivants'));self.more.setEnabled(False);self.stop=QPushButton(tr('Arrêter'));self.stop.setEnabled(False);self.open=QPushButton(tr('Voir la construction / les notices'));self.open.setEnabled(False)
        for b in (self.run,self.more,self.stop,self.open):buttons.addWidget(b)
        self.run.clicked.connect(self.start);self.more.clicked.connect(self.next_batch);self.stop.clicked.connect(self.cancel.set);self.open.clicked.connect(self.open_selected)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);buttons.addWidget(close);layout.addLayout(buttons)
        self.table.itemSelectionChanged.connect(self.select);self.table.itemDoubleClicked.connect(lambda _:self.open_selected())
    def controls(self,busy):
        self.busy=busy;self.run.setEnabled(not busy);self.more.setEnabled(not busy and self.cursor<len(self.sets));self.stop.setEnabled(busy)
    def start(self):
        if self.busy:return
        if not self.db.setting('api_rb',''):
            self.status.setText(tr('Renseigne ta clé Rebrickable dans « API Keys », puis réessaie.'));return
        self.cancel.clear();self.rows=[];self.table.setRowCount(0);self.sets=[];self.cursor=0;self.photo.clear();self.photos+=1;self.controls(True)
        def done(result):
            if self.closed:return
            self.sets,warnings,excluded,cancelled=result;self.controls(False)
            self.status.setText(str(len(self.sets))+tr(' sets reconstituables avec le stock sélectionné.')+'\n'+'\n'.join(warnings))
            if self.sets and not cancelled:self.next_batch()
        async_task(self,lambda progress:find_builds(self.db,'RB','',False,1,100,self.cancel,progress,self.excluded),done,self.fail,self.progress)
    def progress(self,message):
        if not self.closed:self.status.setText(str(message))
    def fail(self,error):
        if not self.closed:self.controls(False);self.status.setText(str(error))
    def next_batch(self):
        if self.busy:return
        self.cancel.clear();self.controls(True);start=self.cursor;end=min(start+20,len(self.sets));key=self.db.setting('api_rb','')
        def work(progress):
            found=[];cursor=start;errors=[]
            for index in range(start,end):
                if self.cancel.is_set():break
                item=self.sets[index];ref=item['ref'];progress(str(index+1)+' / '+str(len(self.sets))+' — '+ref)
                cache=self.db.setting('stock_mocs_'+ref,{})
                if time.time()-cache.get('time',0)<86400:
                    found.extend((row,ref) for row in cache.get('rows',[]));cursor=index+1;continue
                rows=[];page=None
                try:
                    while True:
                        if self.cancel.wait(1.1):break
                        result,page,_=fetch_alternates(key,ref,page);rows.extend(result)
                        if not page:break
                    if self.cancel.is_set():break
                    self.db.set_setting('stock_mocs_'+ref,{'time':time.time(),'rows':rows})
                    found.extend((row,ref) for row in rows);cursor=index+1
                except Exception as error:
                    errors.append(ref+' : '+str(error));break
            return found,cursor,errors
        def done(result):
            if self.closed:return
            found,self.cursor,errors=result
            lookup={r['set_num']:r for r in self.rows}
            for row,ref in found:
                num=row.get('set_num','')
                if not num:continue
                if num not in lookup:
                    data=dict(row,bases=[]);lookup[num]=data;self.rows.append(data)
                if ref not in lookup[num]['bases']:lookup[num]['bases'].append(ref)
            fill_table(self.table,[(row['set_num'],row['name'],row['designer_name'],row['num_parts'],', '.join(row['bases'])) for row in self.rows])
            self.select()
            self.controls(False);self.status.setText(str(len(self.rows))+tr(' MOC proposés ; sets analysés : ')+str(self.cursor)+' / '+str(len(self.sets))+('\n'+'\n'.join(errors) if errors else ''))
        async_task(self,work,done,self.fail,self.progress)
    def select(self):
        self.photos+=1;token=self.photos;index=row_index(self.table);self.photo.clear();self.open.setEnabled(0<=index<len(self.rows))
        if not self.engine or not 0<=index<len(self.rows):return
        row=self.rows[index];url=row.get('moc_img_url') or row.get('set_img_url')
        if not url:return
        def done(image):
            if not self.closed and token==self.photos and image is not None:scalable(self.photo,image,550,210)
        async_task(self,lambda _:self.engine.images.get(url,True),done,lambda _:None)
    def open_selected(self):
        index=row_index(self.table)
        if not 0<=index<len(self.rows):return
        row=self.rows[index];url=row.get('moc_url') or row.get('set_url')
        if rb_link(url):QDesktopServices.openUrl(QUrl(url))
    def done(self,result):
        self.closed=True;self.photos+=1;self.cancel.set();super().done(result)
