"""Read-only proposed cabinet, using the application's shared thumbnails."""
from collections import OrderedDict

from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtGui import QColor,QPen,QPainter
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QTabWidget,QTableWidget,QHeaderView,QAbstractItemView,QGraphicsScene

from .i18n import tr,tf
from .storage_panel import CabinetItem,DrawerItem,WallView
from .thumbnails import ThumbnailContext,PartThumbnails,load_thumbnail
from .ui_common import FlowLayout,async_task,pixmap
from .result_tables import fill_table,row_index
from . import storage_wall as walls


def proposal_snapshot(plan,targets):
    """Overlay draft targets; no database access or mutations while repainting."""
    base=plan['preview'];drawers={d['id']:dict(d) for d in base['drawers']}
    quantities={(row['id'],row['color']):row['quantity'] for row in base['stock']}
    totals={}
    for row in base['stock']:totals[row['id']]=totals.get(row['id'],0)+row['quantity']
    def part(identity,color,stored_quantity=None):
        item=dict(base['items'][identity]);item['chosen_color']=color
        item['chosen_quantity']=quantities.get((identity,color),0) if color else totals.get(identity,0)
        item['stored_quantity']=stored_quantity
        return item
    contents={d:[] for d in drawers};replaced={link['drawer_id'] for link in plan['replaced']} if plan['reorganize'] else set()
    for link in base['links']:
        if link['drawer_id'] not in replaced:contents[link['drawer_id']].append(part(link['item_id'],link['color'],link.get('quantity')))
    for identity in replaced:drawers[identity]['name']=''
    assignments={}
    for index,(group,target) in enumerate(zip(plan['groups'],targets)):
        if target in drawers:assignments.setdefault(target,[]).append(index)
    for target,indices in assignments.items():
        groups=[plan['groups'][index] for index in indices]
        drawers[target]['name']=groups[0]['name'] if len(groups)==1 else ' / '.join(dict.fromkeys(g['category'] for g in groups))+' · '+tf('{0} référence(s)',len({identity for g in groups for identity,color in g['entries']}))
        contents[target]=[part(identity,color,plan.get('quantities',{}).get((identity,color))) for group in groups for identity,color in group['entries']]
    conflicts={target for target,indices in assignments.items() if len(indices)>1 and not plan.get('shared_drawers')}
    return {'wall':base['wall'],'drawers':list(drawers.values()),'contents':contents,'assignments':assignments,'conflicts':conflicts,'items':base['items'],'part':part}


class ProposalDrawer(DrawerItem):
    opened=Signal(int)
    def __init__(self,*args,proposed=False,conflict=False,**kwargs):
        super().__init__(*args,**kwargs);self.drop_active=proposed;self.conflict=conflict
    def paint(self,painter,option,widget=None):
        super().paint(painter,option,widget)
        if self.conflict:
            painter.save();painter.setTransform(self.transform_face,True);painter.setPen(QPen(QColor('#ff806d'),3));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPolygon(self.front);painter.restore()
    def mouseDoubleClickEvent(self,event):
        self.opened.emit(self.drawer['id']);event.accept()


class StorageProposalPreview(QWidget):
    drawer_selected=Signal(int)
    def __init__(self,db,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.plan=None;self.snapshot=None;self.selected_id=None;self.items={};self.rows=[]
        self.icons=OrderedDict();self.context=ThumbnailContext(db);self.token=0;self.running=False;self.closed=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        board=QWidget();body=QVBoxLayout(board);body.setContentsMargins(6,6,6,6)
        self.caption=QLabel(tr('Aperçu du meuble proposé'));self.caption.setWordWrap(True);body.addWidget(self.caption)
        controls=FlowLayout()
        for label,factor in [('−',1/1.25),('+',1.25)]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,f=factor:self.view.zoom(f));controls.addWidget(button)
        fit=QPushButton(tr('Vue complète'));fit.clicked.connect(self.fit);controls.addWidget(fit);body.addLayout(controls)
        self.scene=QGraphicsScene(self);self.view=WallView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setAcceptDrops(False);body.addWidget(self.view,1)
        hint=QLabel(tr('Vert : placement proposé. Rouge : conflit d’affectation. Clique sur un tiroir pour son contenu ; double-clique pour ouvrir les détails.'));hint.setWordWrap(True);body.addWidget(hint)
        self.tabs.addTab(board,tr('Meuble proposé'))
        details=QWidget();detail_layout=QVBoxLayout(details);detail_layout.setContentsMargins(6,6,6,6)
        self.detail_title=QLabel(tr('Sélectionne un tiroir dans l’aperçu.'));self.detail_title.setWordWrap(True);detail_layout.addWidget(self.detail_title)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Catégorie'),tr('Couleur'),tr('Stock global en vrac'),tr('Aperçu'),tr('Quantité dans ce tiroir')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column,width in enumerate((65,95,220,160,120,150,125)):self.table.setColumnWidth(column,width)
        self.table.setColumnWidth(7,180)
        self.table.horizontalHeader().moveSection(7,2)
        detail_layout.addWidget(self.table,1)
        note=QLabel(tr('Le stock global reste distinct de la quantité proposée dans ce tiroir. Une quantité non renseignée n’est pas un comptage.'));note.setWordWrap(True);detail_layout.addWidget(note)
        self.tabs.addTab(details,tr('Contenu du tiroir'))
        self.thumbs=PartThumbnails(self.table,db,engine,self.visible_rows,6,self) if engine else None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(80);self.timer.timeout.connect(self.load_icons)
        self.view.view_changed.connect(self.schedule_icons);self.tabs.currentChanged.connect(self.schedule_icons)

    def visible_rows(self):return [self.rows[row_index(self.table,index)] for index in range(self.table.rowCount())]

    def set_proposal(self,plan,targets,reset=False):
        self.plan=plan;self.token+=1;self.scene.clear();self.items={};self.snapshot=None
        if plan is None:self.rows=[];self.table.setRowCount(0);self.caption.setText(tr('Aucune proposition disponible.'));return
        self.snapshot=proposal_snapshot(plan,targets);snap=self.snapshot
        cabinet=CabinetItem(dict(snap['wall']),0,0,False,False);self.scene.addItem(cabinet)
        for drawer in snap['drawers']:
            entries=snap['contents'][drawer['id']]
            item=ProposalDrawer(drawer,entries,self.icons,0,0,cabinet,proposed=drawer['id'] in snap['assignments'],conflict=drawer['id'] in snap['conflicts'])
            item.chosen.connect(self.choose_drawer);item.opened.connect(self.open_drawer);self.items[drawer['id']]=item
            item.setToolTip(walls.address(drawer)+'\n'+drawer['name']+'\n'+'\n'.join(p['source']+' '+p['ref']+' · '+(p['chosen_color'] or tr('Non précisée'))+' · '+str(p['chosen_quantity']) for p in entries))
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-12,-12,12,12))
        self.caption.setText(snap['wall']['name']+' — '+tf('{0} tiroir(s) proposé(s)',len(snap['assignments'])))
        if reset or self.view.transform().m11()==1:self.fit()
        if self.selected_id in self.items:self.choose_drawer(self.selected_id,emit=False)
        else:self.rows=[];self.table.setRowCount(0);self.detail_title.setText(tr('Sélectionne un tiroir dans l’aperçu.'))
        self.schedule_icons()

    def fit(self):
        if self.snapshot:self.view.fit_rect(self.scene.sceneRect())

    def show_parts(self,parts,title):
        self.rows=parts;self.detail_title.setText(title)
        palette={str(row['id']):row['name'] for row in self.db.rows('SELECT id,name FROM colors')}
        bl=self.db.setting('bl_colors',{})
        def color(part):
            code=part['chosen_color']
            if not code:return tr('Non précisée')
            name=bl.get(code,{}).get('name','') if part['source']=='BL' else palette.get(code,'')
            return name+' ('+code+')' if name else code
        fill_table(self.table,[(p['source'],p['ref'],p['name'],p['category'],color(p),p['chosen_quantity'],tr('3D / photo à charger'),p['stored_quantity'] if p.get('stored_quantity') is not None else tr('À renseigner')) for p in self.rows])
        if self.thumbs:self.thumbs.reset()

    def choose_drawer(self,identity,emit=True):
        if not self.snapshot or identity not in self.items:return
        self.selected_id=identity
        for key,item in self.items.items():item.selected=key==identity;item.update()
        drawer=self.items[identity].drawer
        self.show_parts(self.snapshot['contents'][identity],walls.address(drawer)+' — '+(drawer['name'] or tr('Vide')))
        if emit:self.drawer_selected.emit(identity)

    def open_drawer(self,identity):
        self.choose_drawer(identity);self.tabs.setCurrentIndex(1)

    def show_group(self,index,targets):
        if not self.plan or not 0<=index<len(targets):return
        target=targets[index]
        if target in self.items:self.choose_drawer(target,emit=False)
        else:
            group=self.plan['groups'][index]
            self.show_parts([self.snapshot['part'](identity,color) for identity,color in group['entries']],group['name']+' — '+tr('Laisser sans emplacement'))
            self.tabs.setCurrentIndex(1)

    def invalidate(self):
        self.icons.clear();self.token+=1
        if self.thumbs:self.thumbs.reset()
        for item in self.items.values():item.update()
        self.schedule_icons()

    def schedule_icons(self,*_):
        if not self.closed and self.isVisible():self.timer.start()

    def load_icons(self):
        if self.closed or self.running or not self.engine or self.tabs.currentIndex()!=0:return
        visible=self.view.mapToScene(self.view.viewport().rect()).boundingRect();wanted={}
        candidates=[item for item in self.items.values() if visible.intersects(item.sceneBoundingRect()) and item.w*self.view.transform().m11()>=28]
        candidates.sort(key=lambda item:item.drawer['id']!=self.selected_id)
        for item in candidates[:80]:
            for part in item.parts[:3]:
                key=(part['id'],str(part['chosen_color']))
                if key not in self.icons:wanted.setdefault(key,(part,self.context.state(part)))
            if len(wanted)>=32:break
        if not wanted:return
        self.running=True;token=self.token;generation=self.engine.thumbnail_cache.generation
        def work(progress):
            for key,(part,state) in list(wanted.items())[:32]:
                if self.closed or token!=self.token:break
                try:image,_=load_thumbnail(self.engine,part,state,generation)
                except Exception:image=None
                progress((key,image))
        def delivered(result):
            if self.closed or token!=self.token:return
            key,image=result;self.icons[key]=pixmap(image)
            while len(self.icons)>256:self.icons.popitem(last=False)
            for item in self.items.values():item.update()
        def finished(*_):self.running=False;self.schedule_icons()
        async_task(self,work,finished,finished,delivered)

    def stop(self):
        self.closed=True;self.token+=1;self.timer.stop()
        if self.thumbs:self.thumbs.suspend()

    def showEvent(self,event):super().showEvent(event);self.schedule_icons()
    def hideEvent(self,event):
        self.token+=1;self.timer.stop()
        if self.thumbs:self.thumbs.suspend()
        super().hideEvent(event)
