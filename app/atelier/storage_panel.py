"""Native drawer-wall view. Scene transforms do not render or write files."""
from collections import OrderedDict
import math
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QPolygonF,QTransform,QFont
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,
    QLineEdit,QSpinBox,QCheckBox,QTableWidget,QHeaderView,QAbstractItemView,QSplitter,QSlider,
    QGraphicsObject,QGraphicsScene,QGraphicsView,QMessageBox,QDialogButtonBox,QMenu)
from .i18n import tr
from . import storage_wall as store
from .ui_common import async_task,pixmap
from .windows import show_window,notify_changed
from .result_tables import fill_table,row_index
from .thumbnails import PartThumbnails


class DrawerItem(QGraphicsObject):
    chosen=Signal(int)
    def __init__(self,drawer,parts,icons,yaw,pitch):
        super().__init__()
        self.drawer=drawer;self.parts=parts;self.icons=icons;self.selected=False;self.match=False
        self.w=drawer['width']*112-6;self.h=drawer['height']*70-6
        a,b=math.radians(yaw),math.radians(pitch)
        self.transform_face=QTransform(math.cos(a),math.sin(a)*math.sin(b),0,math.cos(b),28*math.sin(a),-28*math.cos(a)*math.sin(b))
        self.back=QTransform(math.cos(a),math.sin(a)*math.sin(b),0,math.cos(b),0,0)
        x=(drawer['col']-1)*112;y=(drawer['row']-1)*70
        self.setPos(self.back.map(QPointF(x,y)))
        corners=[QPointF(0,0),QPointF(self.w,0),QPointF(self.w,self.h),QPointF(0,self.h)]
        self.front=QPolygonF([self.transform_face.map(p) for p in corners]);rear=[self.back.map(p) for p in corners]
        self.top=QPolygonF([rear[0],rear[1],self.front[1],self.front[0]])
        self.side=QPolygonF([rear[1],rear[2],self.front[2],self.front[1]])
        self.bounds=self.front.boundingRect().united(self.top.boundingRect()).united(self.side.boundingRect()).adjusted(-3,-3,3,3)
        self.setToolTip(store.address(drawer)+'\n'+drawer['name']+'\n'+'\n'.join(p['ref']+' — '+p['name'] for p in parts))
        self.setAcceptHoverEvents(True)
    def boundingRect(self):return self.bounds
    def paint(self,painter,option,widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#172231'),1));painter.setBrush(QColor('#34475c'));painter.drawPolygon(self.top)
        painter.setBrush(QColor('#223449'));painter.drawPolygon(self.side)
        painter.save();painter.setTransform(self.transform_face,True)
        painter.setBrush(QColor('#284e73' if self.match else '#344359'))
        painter.setPen(QPen(QColor('#7dc8ff' if self.match or self.selected else '#54677e'),2 if self.match or self.selected else 1))
        painter.drawRoundedRect(QRectF(0,0,self.w,self.h),3,3)
        painter.setFont(QFont('Segoe UI',8));painter.setPen(QColor('#e8edf5'))
        label=self.drawer['name'] or (self.parts[0]['ref'] if self.parts else tr('Vide'))
        if len(self.parts)>1 and not self.drawer['name']:label+=' +'+str(len(self.parts)-1)
        painter.drawText(QRectF(5,3,self.w-10,16),Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,int(self.w-10)))
        shown=self.parts[:min(3,max(1,int(self.w/35)))];left=(self.w-len(shown)*32)/2
        for index,part in enumerate(shown):
            image=self.icons.get((part['id'],str(part['chosen_color'])))
            if image and not image.isNull():
                image=image.scaled(30,25,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(QPointF(left+index*32+(30-image.width())/2,22),image)
            else:
                painter.setPen(QColor('#bdc9d7'));painter.drawText(QRectF(left+index*32,24,30,18),Qt.AlignmentFlag.AlignCenter,part['ref'][:7])
        painter.setPen(QColor('#a9bdd1'));painter.drawText(QRectF(self.w-32,self.h-16,28,12),Qt.AlignmentFlag.AlignRight,str(self.drawer['col'])+'/'+str(self.drawer['row']))
        painter.setPen(QPen(QColor('#81a0bf'),3));painter.drawLine(QPointF(self.w*.38,self.h-6),QPointF(self.w*.62,self.h-6))
        painter.restore()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.chosen.emit(self.drawer['id']);event.accept()
        else:super().mousePressEvent(event)


class WallView(QGraphicsView):
    view_changed=Signal()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.view_changed.emit()
    def wheelEvent(self,event):
        if event.modifiers()&Qt.KeyboardModifier.ControlModifier:
            factor=1.15 if event.angleDelta().y()>0 else 1/1.15
            if .2<=self.transform().m11()*factor<=5:self.scale(factor,factor)
            self.view_changed.emit();event.accept()
        else:super().wheelEvent(event)


class StockPicker(QDialog):
    def __init__(self,db,engine,drawer_id,parent,changed):
        super().__init__(parent);self.db=db;self.drawer_id=drawer_id;self.changed=changed;self.rows=[]
        self.setWindowTitle(tr('Ajouter des références du stock au tiroir'));self.resize(900,580)
        layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText(tr('Référence, nom ou catégorie'));layout.addWidget(self.search)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Couleur'),tr('Stock en vrac'),tr('Aperçu')]);layout.addWidget(self.table,1)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.setColumnWidth(2,300)
        self.thumbs=PartThumbnails(self.table,db,engine,self.visible_rows,5,self) if engine else None
        row=QHBoxLayout();add=QPushButton(tr('Associer la sélection'));add.clicked.connect(self.add);row.addWidget(add);close=QPushButton(tr('Fermer'));close.clicked.connect(self.accept);row.addWidget(close);layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda:self.timer.start());self.reload()
    def visible_rows(self):return [self.rows[row_index(self.table,r)] for r in range(self.table.rowCount())]
    def reload(self):
        conditions=["i.kind IN ('part','minifig')","s.quantity>0"];args=[]
        for word in store.normalize(self.search.text()).split():conditions.append('norm(i.ref||\' \'||i.name||\' \'||i.category) LIKE ?');args.append('%'+word+'%')
        self.rows=self.db.rows('SELECT i.*,s.color AS chosen_color,s.quantity AS chosen_quantity FROM stock s JOIN items i ON i.id=s.item_id WHERE '+' AND '.join(conditions)+' ORDER BY i.ref,s.color LIMIT 5000',args)
        fill_table(self.table,[(p['source'],p['ref'],p['name'],p['chosen_color'],p['chosen_quantity'],tr('3D / photo à charger')) for p in self.rows])
        if self.thumbs:self.thumbs.reset()
    def add(self):
        selected=[self.rows[row_index(self.table,index.row())] for index in self.table.selectionModel().selectedRows()]
        if not selected:return
        try:store.assign(self.db,self.drawer_id,[(p['id'],p['chosen_color']) for p in selected])
        except ValueError as e:QMessageBox.warning(self,tr('Association impossible'),str(e));return
        self.changed();notify_changed(self)
    def done(self,result):
        if self.thumbs:self.thumbs.stop()
        super().done(result)


class StoragePanel(QWidget):
    selected=Signal(object)
    def __init__(self,db,engine,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.drawer_id=None;self.wall_id=None;self.rows=[];self.matches=[];self.drawers=[];self.items={};self.icons=OrderedDict();self.loading=False;self.icon_token=0
        layout=QVBoxLayout(self);bar=QHBoxLayout();self.wall=QComboBox();bar.addWidget(self.wall,1)
        organise=QPushButton(tr('Organiser le meuble'));menu=QMenu(organise)
        for name,fn in [(tr('Créer un meuble'),self.new_wall),(tr('Ajouter un tiroir'),lambda:self.edit_drawer(True)),(tr('Modifier le tiroir'),self.edit_drawer),(tr('Supprimer le tiroir'),self.remove_drawer)]:menu.addAction(name,fn)
        organise.setMenu(menu);bar.addWidget(organise)
        layout.addLayout(bar);self.query=QLineEdit();self.query.setPlaceholderText(tr('Pièce, référence, dimensions, couleur ou nom du tiroir'));layout.addWidget(self.query);bar=QHBoxLayout()
        self.all_walls=QCheckBox(tr('Tous les meubles'));self.all_walls.setChecked(True);bar.addWidget(self.all_walls)
        self.front=QCheckBox(tr('Vue de face'));bar.addWidget(self.front);bar.addWidget(QLabel(tr('Angle')))
        self.angle=QSlider(Qt.Orientation.Horizontal);self.angle.setRange(-35,35);self.angle.setValue(db.setting('storage_wall_angle',18));self.angle.setMaximumWidth(120);bar.addWidget(self.angle);layout.addLayout(bar)
        split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split,1)
        self.scene=QGraphicsScene(self);self.view=WallView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setMinimumHeight(180);split.addWidget(self.view)
        details=QWidget();d=QVBoxLayout(details);self.status=QLabel(tr('Crée un meuble puis associe les références de ton stock aux tiroirs.'));self.status.setWordWrap(True);d.addWidget(self.status)
        self.results=QTableWidget(0,5);self.results.setHorizontalHeaderLabels([tr('Meuble'),tr('Emplacement'),tr('Référence'),tr('Pièce'),tr('Couleur')]);self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.results.setMinimumHeight(70);self.results.setMaximumHeight(120);self.results.hide();d.addWidget(self.results)
        for column,width in enumerate((170,220,90,240,110)):self.results.setColumnWidth(column,width)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Couleur'),tr('Stock global en vrac'),tr('Aperçu 3D / photo')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.setMinimumHeight(140);d.addWidget(self.table,1)
        for column,width in enumerate((75,90,220,100,160,150)):self.table.setColumnWidth(column,width)
        self.thumbnails=PartThumbnails(self.table,db,engine,self.visible_parts,5,self) if engine else None
        row=QHBoxLayout();add=QPushButton(tr('Ajouter des références du stock'));add.clicked.connect(self.pick_stock);row.addWidget(add);remove=QPushButton(tr('Retirer les références du tiroir'));remove.clicked.connect(self.unassign);row.addWidget(remove);fit=QPushButton(tr('Vue complète'));fit.clicked.connect(self.fit);row.addWidget(fit);d.addLayout(row)
        split.addWidget(details);split.setSizes([350,350]);split.setStretchFactor(0,1);split.setStretchFactor(1,1)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(180);self.search_timer.timeout.connect(self.search)
        self.icon_timer=QTimer(self);self.icon_timer.setSingleShot(True);self.icon_timer.setInterval(100);self.icon_timer.timeout.connect(self.load_icons)
        self.wall.currentIndexChanged.connect(self.change_wall);self.query.textChanged.connect(lambda:self.search_timer.start());self.all_walls.toggled.connect(self.search)
        self.angle.valueChanged.connect(self.redraw);self.angle.sliderReleased.connect(lambda:self.db.set_setting('storage_wall_angle',self.angle.value()));self.front.toggled.connect(self.redraw)
        self.view.view_changed.connect(self.schedule_icons);self.view.verticalScrollBar().valueChanged.connect(self.schedule_icons);self.view.horizontalScrollBar().valueChanged.connect(self.schedule_icons)
        self.results.itemSelectionChanged.connect(self.select_result);self.table.itemSelectionChanged.connect(self.select_piece);self.table.itemDoubleClicked.connect(self.open_piece)
        if self.thumbnails:self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset())
        self.reload_walls()
    def visible_parts(self):return [self.rows[row_index(self.table,r)] for r in range(self.table.rowCount())]
    def reload_walls(self,preferred=None):
        current=preferred or self.wall.currentData();self.wall.blockSignals(True);self.wall.clear()
        for wall in store.walls(self.db):self.wall.addItem(wall['name'],wall['id'])
        index=self.wall.findData(current);self.wall.setCurrentIndex(max(0,index));self.wall.blockSignals(False);self.change_wall()
    def change_wall(self,*_):
        self.wall_id=self.wall.currentData();self.drawer_id=None;self.redraw();self.load_contents();self.search();self.fit()
    def redraw(self,*_):
        self.icon_token+=1;self.scene.clear();self.items={}
        if self.wall_id is None:return
        self.drawers=store.drawers(self.db,self.wall_id);parts={}
        for p in store.wall_contents(self.db,self.wall_id):parts.setdefault(p['drawer_id'],[]).append(p)
        yaw=0 if self.front.isChecked() else self.angle.value();pitch=0 if self.front.isChecked() else 10
        for drawer in self.drawers:
            item=DrawerItem(drawer,parts.get(drawer['id'],[]),self.icons,yaw,pitch);item.chosen.connect(self.choose_drawer);self.scene.addItem(item);self.items[drawer['id']]=item
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20,-20,20,20));self.highlight();self.schedule_icons()
    def fit(self):
        if self.scene.items():self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
        self.schedule_icons()
    def choose_drawer(self,drawer_id):self.drawer_id=drawer_id;self.load_contents();self.highlight()
    def load_contents(self):
        self.rows=store.contents(self.db,self.drawer_id) if self.drawer_id else []
        fill_table(self.table,[(p['source'],p['ref'],p['name'],p['chosen_color'],p['chosen_quantity'],tr('3D / photo à charger')) for p in self.rows])
        if self.thumbnails:self.thumbnails.reset()
        self.update_status()
    def update_status(self):
        drawer=next((d for d in self.drawers if d['id']==self.drawer_id),None)
        if self.query.text().strip() and not self.matches:self.status.setText('0'+tr(' correspondance(s) dans les tiroirs.'))
        elif drawer:self.status.setText(' · '.join(value for value in (self.wall.currentText(),store.address(drawer),drawer['name']) if value)+' — '+str(len(self.rows))+tr(' référence(s). Les quantités indiquent le stock global, pas le nombre dans ce tiroir.'))
        elif self.query.text().strip():self.status.setText(str(len(self.matches))+tr(' correspondance(s) dans les tiroirs.'))
        else:self.status.setText(tr('Crée un meuble puis associe les références de ton stock aux tiroirs.'))
    def highlight(self):
        hits={r['id'] for r in self.matches};searching=bool(self.query.text().strip())
        for identity,item in self.items.items():
            item.selected=identity==self.drawer_id;item.match=identity in hits;item.setOpacity(.45 if searching and not item.match else 1);item.update()
    def search(self,*_):
        self.matches=store.search(self.db,self.query.text(),None if self.all_walls.isChecked() else self.wall_id)
        self.results.blockSignals(True);fill_table(self.results,[(r['wall_name'],store.address(r),r['ref'],r['piece_name'],r['color_name'] or r['color']) for r in self.matches]);self.results.blockSignals(False)
        self.results.setVisible(bool(self.query.text().strip()));self.highlight()
        self.update_status()
        if self.matches and self.drawer_id is None:self.results.selectRow(0)
    def select_result(self):
        index=row_index(self.results)
        if not 0<=index<len(self.matches):return
        result=self.matches[index]
        if self.wall_id!=result['wall_id']:
            self.wall.blockSignals(True);self.wall.setCurrentIndex(self.wall.findData(result['wall_id']));self.wall.blockSignals(False);self.wall_id=result['wall_id'];self.redraw();self.fit()
        self.choose_drawer(result['id'])
        if self.drawer_id in self.items:self.view.ensureVisible(self.items[self.drawer_id])
    def select_piece(self):
        index=row_index(self.table)
        if 0<=index<len(self.rows):self.selected.emit(self.rows[index])
    def open_piece(self,*_):
        index=row_index(self.table)
        if not 0<=index<len(self.rows):return
        from .dialogs import RelationsDialog
        show_window(RelationsDialog(self.db,self.engine,self.rows[index],self),self)
    def new_wall(self):
        dialog=QDialog(self);dialog.setWindowTitle(tr('Créer un meuble de rangement'));form=QFormLayout(dialog)
        name=QLineEdit(tr('Mon meuble'));columns=QSpinBox();columns.setRange(1,100);columns.setValue(4);rows=QSpinBox();rows.setRange(1,100);rows.setValue(6)
        form.addRow(tr('Nom'),name);form.addRow(tr('Colonnes'),columns);form.addRow(tr('Tiroirs par colonne'),rows)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def save():
            try:identity=store.create_wall(self.db,name.text(),columns.value(),rows.value())
            except ValueError as e:QMessageBox.warning(dialog,tr('Meuble invalide'),str(e));return
            self.reload_walls(identity);dialog.accept()
        buttons.accepted.connect(save);show_window(dialog,self)
    def edit_drawer(self,new=False):
        if self.wall_id is None:return
        drawer=next((d for d in self.drawers if d['id']==self.drawer_id),None)
        if not new and not drawer:return
        captured_wall=self.wall_id;captured_id=None if new else drawer['id']
        dialog=QDialog(self);dialog.setWindowTitle(tr('Dimensions et nom du tiroir'));form=QFormLayout(dialog);fields={}
        for key,label in [('col',tr('Colonne')),('row',tr('Tiroir, depuis le haut')),('width',tr('Largeur en unités')),('height',tr('Hauteur en unités'))]:
            spin=QSpinBox();spin.setRange(1,100);spin.setValue((max((d['row']+d['height']-1 for d in self.drawers),default=0)+1 if key=='row' else 1) if new else drawer[key]);fields[key]=spin;form.addRow(label,spin)
        name=QLineEdit('' if new else drawer['name']);form.addRow(tr('Nom libre'),name)
        note=QLabel(tr('1 unité = un tiroir standard. Les tiroirs voisins vides seront réunis si tu agrandis celui-ci.'));note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def save():
            try:identity=store.save_drawer(self.db,captured_wall,fields['col'].value(),fields['row'].value(),fields['width'].value(),fields['height'].value(),name.text(),captured_id)
            except ValueError as e:QMessageBox.warning(dialog,tr('Tiroir invalide'),str(e));return
            if self.wall_id!=captured_wall:self.wall.setCurrentIndex(self.wall.findData(captured_wall))
            self.redraw();self.choose_drawer(identity);self.search();dialog.accept()
        buttons.accepted.connect(save);show_window(dialog,self)
    def remove_drawer(self):
        if not self.drawer_id:return
        if QMessageBox.question(self,tr('Supprimer le tiroir'),tr('Supprimer ce tiroir et ses liens de rangement ? Les pièces restent dans le stock.'))!=QMessageBox.StandardButton.Yes:return
        self.db.run('DELETE FROM storage_drawers WHERE id=?',(self.drawer_id,));self.drawer_id=None;self.redraw();self.load_contents();self.search()
    def pick_stock(self):
        if not self.drawer_id:return
        show_window(StockPicker(self.db,self.engine,self.drawer_id,self,self.refresh),self)
    def unassign(self):
        if not self.drawer_id:return
        selected=[self.rows[row_index(self.table,index.row())] for index in self.table.selectionModel().selectedRows()]
        with self.db.connect() as c:
            for p in selected:c.execute('DELETE FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(self.drawer_id,p['id'],p['chosen_color']))
        self.refresh()
    def refresh(self):
        if not self.isVisible():return
        self.redraw();self.load_contents();self.search()
    def invalidate(self,item=None):
        if item is None:self.icons.clear()
        else:
            for key in list(self.icons):
                if key[0]==item['id']:self.icons.pop(key,None)
        self.icon_token+=1;self.schedule_icons()
    def schedule_icons(self,*_):
        if self.isVisible():self.icon_timer.start()
    def load_icons(self):
        if not self.engine or not self.isVisible() or self.loading:return
        visible=self.view.mapToScene(self.view.viewport().rect()).boundingRect();wanted=[];identities=set();token=self.icon_token
        selected_items=[item for item in self.items.values() if visible.intersects(item.sceneBoundingRect()) and item.w*self.view.transform().m11()>=40][:80]
        for item in selected_items:
            if not visible.intersects(item.sceneBoundingRect()):continue
            for p in item.parts[:3]:
                identity=(p['id'],str(p['chosen_color']))
                if identity not in self.icons and identity not in identities:wanted.append((p,identity,self.thumbnails.state(p)));identities.add(identity)
                if len(wanted)>=32:break
            if len(wanted)>=32:break
        if not wanted:return
        self.loading=True;cache=self.engine.thumbnail_cache;generation=cache.generation
        def work(progress):
            for part,identity,key in wanted:
                if token!=self.icon_token:break
                def factory():
                    image=None
                    if part['kind']=='part' and key[2]=='3d' and not key[3]:
                        try:
                            if self.engine.renderer():image,_=self.engine.render_3d(part,(100,65),str(part['chosen_color']))
                        except Exception:pass
                    return image if image is not None else self.engine.photo(part,download=True,color=str(part['chosen_color']))
                try:image=cache.get_or_create(key,factory,generation)
                except Exception:image=None
                progress((identity,image))
        def delivered(data):
            if token!=self.icon_token or not self.isVisible():return
            identity,image=data;self.icons[identity]=pixmap(image)
            while len(self.icons)>256:self.icons.popitem(last=False)
            for item in self.items.values():item.update()
        def finished(*_):self.loading=False;self.schedule_icons()
        async_task(self,work,finished,finished,delivered)
    def showEvent(self,event):
        super().showEvent(event);self.refresh();QTimer.singleShot(0,self.fit)
    def hideEvent(self,event):
        self.icon_token+=1;self.icon_timer.stop();self.icons.clear()
        if self.thumbnails:self.thumbnails.suspend()
        super().hideEvent(event)
