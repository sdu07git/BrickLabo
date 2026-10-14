"""Native drawer-wall view. Scene transforms do not render or write files."""
from collections import OrderedDict
import math
import sqlite3
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QTimer,QEvent
from PySide6.QtGui import QColor,QPainter,QPen,QPolygonF,QTransform,QFont
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,
    QLineEdit,QSpinBox,QDoubleSpinBox,QCheckBox,QTableWidget,QHeaderView,QAbstractItemView,QSplitter,QSlider,
    QGraphicsObject,QGraphicsScene,QGraphicsView,QMessageBox,QDialogButtonBox,QMenu,QScrollArea,QTabWidget)
from .i18n import tr,tf
from . import storage_wall as store
from .ui_common import async_task,pixmap,FlowLayout
from .windows import show_window,notify_changed,application_owner
from .result_tables import fill_table,row_index
from .thumbnails import PartThumbnails,load_thumbnail
from .storage_tools import StorageDragTable,StockToDrawers,StoragePlanDialog,read_drag
from .storage_assignment import place_entries


def face_transforms(yaw,pitch):
    a,b=math.radians(yaw),math.radians(pitch)
    return (QTransform(math.cos(a),math.sin(a)*math.sin(b),0,math.cos(b),0,0),
            QTransform(math.cos(a),math.sin(a)*math.sin(b),0,math.cos(b),28*math.sin(a),-28*math.cos(a)*math.sin(b)))


class CabinetItem(QGraphicsObject):
    chosen=Signal(int)
    moved=Signal(int,float,float)
    def __init__(self,wall,yaw,pitch,overview,arranging):
        super().__init__();self.wall=wall;self.overview=overview;self.active=False
        self.back,self.face=face_transforms(yaw,pitch)
        width,height=store.extent(wall);self.w=width*112-6;self.h=height*70-6
        corners=[QPointF(0,0),QPointF(self.w,0),QPointF(self.w,self.h),QPointF(0,self.h)]
        self.front=QPolygonF([self.face.map(p) for p in corners]);rear=[self.back.map(p) for p in corners]
        self.top=QPolygonF([rear[0],rear[1],self.front[1],self.front[0]])
        self.side=QPolygonF([rear[1],rear[2],self.front[2],self.front[1]])
        self.bounds=self.front.boundingRect().united(self.top.boundingRect()).united(self.side.boundingRect()).adjusted(-3,-3,3,3)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable,arranging)
        self.setCursor(Qt.CursorShape.OpenHandCursor if arranging else Qt.CursorShape.ArrowCursor)
        self.snap_position(wall['x'],wall['y'])
    def boundingRect(self):return self.bounds
    def snap_position(self,x,y):
        self.wall['x'],self.wall['y']=x,y
        self.setPos(self.back.map(QPointF(x*112,y*70)) if self.overview else QPointF())
        self.setToolTip(self.wall['name'])
    def paint(self,painter,option,widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#111c2b'),1));painter.setBrush(QColor('#293a4f'));painter.drawPolygon(self.top)
        painter.setBrush(QColor('#172536'));painter.drawPolygon(self.side)
        painter.save();painter.setTransform(self.face,True)
        painter.setBrush(QColor('#172536'));painter.setPen(QPen(QColor('#7dc8ff' if self.active else '#53687d'),2 if self.active else 1))
        painter.drawRoundedRect(QRectF(0,0,self.w,self.h),4,4)
        painter.setFont(QFont('Segoe UI',9,QFont.Weight.DemiBold));painter.setPen(QColor('#e8edf5'))
        painter.drawText(QRectF(10,3,self.w-20,20),Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(self.wall['name'],Qt.TextElideMode.ElideRight,int(self.w-20)))
        painter.restore()
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return super().mousePressEvent(event)
        self.start_position=QPointF(self.pos());self.chosen.emit(self.wall['id'])
        super().mousePressEvent(event);event.accept()
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if self.overview and self.flags()&QGraphicsObject.GraphicsItemFlag.ItemIsMovable and self.pos()!=getattr(self,'start_position',self.pos()):
            inverse,valid=self.back.inverted()
            if valid:
                point=inverse.map(self.pos());self.moved.emit(self.wall['id'],round(point.x()/112,1),round(point.y()/70,1))


class DrawerItem(QGraphicsObject):
    opened=Signal(int)
    chosen=Signal(int)
    moved=Signal(int,object)
    def __init__(self,drawer,parts,icons,yaw,pitch,parent=None,arranging=False,dragging=False,thumbnail_size=100):
        super().__init__(parent)
        self.drawer=drawer;self.parts=parts;self.icons=icons;self.selected=False;self.match=False;self.drop_active=False;self.thumbnail_size=thumbnail_size
        self.w=drawer['width']*112-6;self.h=drawer['height']*70-6
        self.back,self.transform_face=face_transforms(yaw,pitch)
        x=(drawer['col']-1)*112+(12 if parent else 0);y=(drawer['row']-1)*70+(26 if parent else 0)
        self.setPos(self.back.map(QPointF(x,y)))
        corners=[QPointF(0,0),QPointF(self.w,0),QPointF(self.w,self.h),QPointF(0,self.h)]
        self.front=QPolygonF([self.transform_face.map(p) for p in corners]);rear=[self.back.map(p) for p in corners]
        self.top=QPolygonF([rear[0],rear[1],self.front[1],self.front[0]])
        self.side=QPolygonF([rear[1],rear[2],self.front[2],self.front[1]])
        self.bounds=self.front.boundingRect().united(self.top.boundingRect()).united(self.side.boundingRect()).adjusted(-3,-3,3,3)
        from .drawer_inventory import drawer_tooltip
        self.setToolTip(drawer_tooltip(drawer,parts))
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton if arranging else Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable,dragging)
        self.setCursor(Qt.CursorShape.OpenHandCursor if dragging else Qt.CursorShape.ArrowCursor)
    def boundingRect(self):return self.bounds
    def paint(self,painter,option,widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#172231'),1));painter.setBrush(QColor('#34475c'));painter.drawPolygon(self.top)
        painter.setBrush(QColor('#223449'));painter.drawPolygon(self.side)
        painter.save();painter.setTransform(self.transform_face,True)
        painter.setBrush(QColor('#28705b' if self.drop_active else '#284e73' if self.match else '#344359'))
        painter.setPen(QPen(QColor('#7deac0' if self.drop_active else '#7dc8ff' if self.match or self.selected else '#54677e'),2 if self.match or self.selected or self.drop_active else 1))
        painter.drawRoundedRect(QRectF(0,0,self.w,self.h),3,3)
        painter.setFont(QFont('Segoe UI',8));painter.setPen(QColor('#e8edf5'))
        label=self.drawer['name'] or (self.parts[0]['ref'] if self.parts else tr('Vide'))
        if len(self.parts)>1 and not self.drawer['name']:label+=' +'+str(len(self.parts)-1)
        painter.drawText(QRectF(5,3,self.w-43,16),Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,int(self.w-43)))
        for part,box in self.thumbnail_boxes():
            image=self.icons.get((part['id'],str(part['chosen_color'])))
            if image and not image.isNull():
                image=image.scaled(max(1,int(box.width())),max(1,int(box.height())),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(QPointF(box.center().x()-image.width()/2,box.center().y()-image.height()/2),image)
            else:
                painter.setPen(QColor('#bdc9d7'));painter.drawText(box,Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(part['ref'],Qt.TextElideMode.ElideRight,int(box.width())))
        counts=[part.get('stored_quantity') for part in self.parts]
        badge='×'+str(sum(counts)) if counts and all(value is not None for value in counts) else str(self.drawer['col'])+'/'+str(self.drawer['row'])
        painter.setFont(QFont('Segoe UI',7));painter.setPen(QColor('#a9bdd1'));painter.drawText(QRectF(self.w-34,5,30,12),Qt.AlignmentFlag.AlignRight,badge)
        painter.setPen(QPen(QColor('#81a0bf'),3));painter.drawLine(QPointF(self.w*.38,self.h-6),QPointF(self.w*.62,self.h-6))
        painter.restore()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.opened.emit(self.drawer['id']);event.accept()
        else:super().mouseDoubleClickEvent(event)
    def thumbnail_boxes(self):
        shown=self.parts[:min(3,max(1,int(self.w/35)))];count=len(shown)
        if not count:return []
        cell_width=(self.w-12)/count;factor=self.thumbnail_size/100
        width=min(120,cell_width-4)*factor;height=min(78,self.h-31)*factor
        return [(part,QRectF(6+index*cell_width+(cell_width-width)/2,20+(self.h-31-height)/2,width,height)) for index,part in enumerate(shown)]
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return super().mousePressEvent(event)
        self.start_position=QPointF(self.pos());self.chosen.emit(self.drawer['id'])
        if self.flags()&QGraphicsObject.GraphicsItemFlag.ItemIsMovable:
            self.setZValue(10)
            if self.parentItem():self.parentItem().setZValue(1)
        super().mousePressEvent(event);event.accept()
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self.setZValue(0)
        if self.parentItem():self.parentItem().setZValue(0)
        if self.flags()&QGraphicsObject.GraphicsItemFlag.ItemIsMovable and self.pos()!=getattr(self,'start_position',self.pos()):
            self.moved.emit(self.drawer['id'],self.mapToScene(QPointF()))


class WallView(QGraphicsView):
    view_changed=Signal()
    def __init__(self,*args):
        super().__init__(*args);self._fit_bounds=None;self._fitting=False
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.setInterval(0);self.fit_timer.timeout.connect(self.repeat_fit)
    def drag_payload(self,event):
        db=getattr(self,'drop_db',None)
        return read_drag(event.mimeData(),db) if db is not None else None
    def drop_target(self,event):
        item=self.itemAt(event.position().toPoint())
        return item if isinstance(item,DrawerItem) else None
    def clear_drop(self):
        for item in self.scene().items():
            if isinstance(item,DrawerItem) and item.drop_active:item.drop_active=False;item.update()
    def dragEnterEvent(self,event):
        if self.drag_payload(event):event.acceptProposedAction()
        else:event.ignore()
    def dragMoveEvent(self,event):
        self.clear_drop();target=self.drop_target(event) if self.drag_payload(event) else None
        if target:
            target.drop_active=True;target.update();event.acceptProposedAction()
        else:event.ignore()
    def dragLeaveEvent(self,event):self.clear_drop();event.accept()
    def dropEvent(self,event):
        payload=self.drag_payload(event);target=self.drop_target(event) if payload else None
        identity=target.drawer['id'] if target else None;self.clear_drop()
        if identity is not None and self.place_drop(identity,payload):
            event.setDropAction(Qt.DropAction.MoveAction if payload['origin'] is not None else Qt.DropAction.CopyAction);event.accept()
        else:event.ignore()
    def zoom(self,factor,position=None):
        self._fit_bounds=None;self.fit_timer.stop()
        current=self.transform().m11()
        if current<=0:return
        target=min(16,max(.000001,current*factor))
        before=self.mapToScene(position) if position is not None else None
        self.scale(target/current,target/current)
        if before is not None:
            after=self.mapToScene(position);self.translate(after.x()-before.x(),after.y()-before.y())
        self.view_changed.emit()
    def fit_rect(self,bounds):
        if bounds.isEmpty():return
        self._fit_bounds=QRectF(bounds);self.repeat_fit()
    def repeat_fit(self):
        if self._fit_bounds is None or self._fitting:return
        self._fitting=True
        try:self.resetTransform();self.fitInView(self._fit_bounds,Qt.AspectRatioMode.KeepAspectRatio);self.centerOn(self._fit_bounds.center());self.view_changed.emit()
        finally:self._fitting=False
    def resizeEvent(self,event):
        super().resizeEvent(event);self.view_changed.emit()
        if self._fit_bounds is not None:self.fit_timer.start()
    def wheelEvent(self,event):
        if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:return super().wheelEvent(event)
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if delta:self.zoom(1.15**(max(-480,min(480,delta))/120),event.position().toPoint())
        event.accept()


class StockPicker(QDialog):
    def __init__(self,db,engine,drawer_id,parent,changed):
        super().__init__(parent);self.db=db;self.drawer_id=drawer_id;self.changed=changed;self.rows=[]
        self.setWindowTitle(tr('Ajouter des références du stock au tiroir'));self.resize(900,580)
        layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText(tr('Référence, nom ou catégorie'));layout.addWidget(self.search)
        self.table=StorageDragTable(db,lambda:self.rows,lambda:None,0,6);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Couleur'),tr('Stock en vrac'),tr('Aperçu')]);layout.addWidget(self.table,1)
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
        self.timer.stop()
        if self.thumbs:self.thumbs.stop()
        super().done(result)


class StoragePanel(QWidget):
    selected=Signal(object)
    def __init__(self,db,engine,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.drawer_id=None;self.wall_id=None;self.rows=[];self.matches=[];self.drawers=[];self.items={};self.cabinets={};self.wall_drawers={};self.icons=OrderedDict();self.loading=False;self.icon_token=0
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);self.controls_scroll=QScrollArea();self.controls_scroll.setWidgetResizable(True);content=QWidget();layout=QVBoxLayout(content);layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize);self.controls_scroll.setWidget(content);outer.addWidget(self.controls_scroll);self.wall=QComboBox();self.wall.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.wall.setMinimumContentsLength(16);layout.addWidget(self.wall);bar=FlowLayout()
        organise=QPushButton(tr('Organiser le meuble'));menu=QMenu(organise)
        for name,fn in [(tr('Créer un meuble'),self.new_wall),(tr('Renommer le meuble…'),self.rename_dialog),(tr('Positionner le meuble…'),self.position_dialog),(tr('Supprimer le meuble'),self.remove_wall),(tr('Ajouter un tiroir'),lambda:self.edit_drawer(True)),(tr('Modifier le tiroir'),self.edit_drawer),(tr('Supprimer le tiroir'),self.remove_drawer)]:menu.addAction(name,fn)
        menu.addSeparator();self.drag_drawers=menu.addAction(tr('Déplacer les tiroirs'));self.drag_drawers.setCheckable(True)
        self.print_action=menu.addAction(tr('Imprimer les meubles sur A4…'),self.print_wall)
        self.plan_action=menu.addAction(tr('Ranger par catégorie et taille…'),self.plan_storage)
        organise.setMenu(menu);bar.addWidget(organise)
        self.arrange=QPushButton(tr('Disposer les meubles'));self.arrange.setCheckable(True);bar.addWidget(self.arrange)
        self.plan_button=QPushButton(tr('Ranger par catégorie et taille…'));self.plan_button.clicked.connect(self.plan_storage);bar.addWidget(self.plan_button)
        layout.addLayout(bar);self.query=QLineEdit();self.query.setPlaceholderText(tr('Pièce, référence, dimensions, couleur ou nom du tiroir'));layout.addWidget(self.query);bar=QHBoxLayout()
        self.all_walls=QCheckBox(tr('Tous les meubles'));self.all_walls.setChecked(True);bar.addWidget(self.all_walls)
        self.front=QCheckBox(tr('Vue de face'));bar.addWidget(self.front);bar.addWidget(QLabel(tr('Angle')))
        self.angle=QSlider(Qt.Orientation.Horizontal);self.angle.setRange(-35,35);self.angle.setValue(db.setting('storage_wall_angle',18));self.angle.setMaximumWidth(120);bar.addWidget(self.angle);layout.addLayout(bar)
        bar=FlowLayout();bar.addWidget(QLabel(tr('Zoom')))
        self.zoom_out=QPushButton('−');self.zoom_in=QPushButton('+')
        for button,label in [(self.zoom_out,tr('Dézoomer')),(self.zoom_in,tr('Zoomer'))]:button.setFixedWidth(36);button.setToolTip(label);button.setAccessibleName(label);bar.addWidget(button)
        self.zoom_label=QLabel();self.zoom_label.setMinimumWidth(55);bar.addWidget(self.zoom_label)
        self.focus_button=QPushButton(tr('Zoom sur le meuble'));bar.addWidget(self.focus_button)
        self.fit_button=QPushButton(tr('Vue complète'));bar.addWidget(self.fit_button);layout.addLayout(bar)
        bar=QHBoxLayout();bar.addWidget(QLabel(tr('Taille des aperçus sur les tiroirs')))
        self.thumbnail_size=QSlider(Qt.Orientation.Horizontal);self.thumbnail_size.setRange(25,100);self.thumbnail_size.setValue(db.setting('storage_thumbnail_size',100));self.thumbnail_size.setMaximumWidth(180);bar.addWidget(self.thumbnail_size)
        self.thumbnail_size_label=QLabel(str(self.thumbnail_size.value())+' %');bar.addWidget(self.thumbnail_size_label);bar.addStretch();layout.addLayout(bar)
        self._saved_thumbnail_size=self.thumbnail_size.value()
        self.thumbnail_save_timer=QTimer(self);self.thumbnail_save_timer.setSingleShot(True);self.thumbnail_save_timer.setInterval(500);self.thumbnail_save_timer.timeout.connect(self.save_thumbnail_size)
        self.placement_hint=QLabel();self.placement_hint.setWordWrap(True);self.placement_hint.hide();layout.addWidget(self.placement_hint)
        split=QSplitter(Qt.Orientation.Vertical);self.content_split=split;layout.addWidget(split,1)
        self.scene=QGraphicsScene(self);self.view=WallView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter);self.view.setMinimumHeight(180);self.view.setToolTip(tr('Molette : zoomer. Maj + molette : faire défiler. Vue complète : afficher tous les meubles.'));split.addWidget(self.view)
        self.view.setAcceptDrops(True);self.view.drop_db=db;self.view.place_drop=self.drop_parts
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.view.customContextMenuRequested.connect(self.drawer_context_menu)
        details=QWidget();d=QVBoxLayout(details);self.details=details;self.details_layout=d;details.installEventFilter(self);self.status=QLabel(tr('Crée un meuble puis associe les références de tes catalogues ou de ton stock aux tiroirs.'));self.status.setWordWrap(True);d.addWidget(self.status)
        self.results=QTableWidget(0,5);self.results.setHorizontalHeaderLabels([tr('Meuble'),tr('Emplacement'),tr('Référence'),tr('Pièce'),tr('Couleur')]);self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.results.setMinimumHeight(70);self.results.setMaximumHeight(120);self.results.hide();d.addWidget(self.results)
        for column,width in enumerate((170,220,90,240,110)):self.results.setColumnWidth(column,width)
        self.table=StorageDragTable(db,lambda:self.rows,lambda:self.drawer_id,0,8);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Catégorie'),tr('Couleur'),tr('Stock global en vrac'),tr('Aperçu 3D / photo'),tr('Quantité dans ce tiroir')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.setMinimumHeight(140);d.addWidget(self.table,1)
        for column,width in enumerate((75,90,220,180,100,160,150)):self.table.setColumnWidth(column,width)
        self.table.setColumnWidth(7,180)
        self.table.horizontalHeader().moveSection(7,2)
        self.thumbnails=PartThumbnails(self.table,db,engine,self.visible_parts,6,self) if engine else None
        row=FlowLayout();add=QPushButton(tr('Ajouter des références du stock'));add.clicked.connect(self.pick_stock);row.addWidget(add);self.remove_references=QPushButton(tr('Retirer les références du tiroir'));self.remove_references.clicked.connect(self.unassign);self.remove_references.setToolTip(tr('Retire les lignes sélectionnées. Sans sélection, propose de retirer toutes les références du tiroir. Les pièces restent dans le stock.'));row.addWidget(self.remove_references);d.addLayout(row)
        self.inventory_button=QPushButton(tr('Ouvrir l’inventaire du tiroir…'));self.inventory_button.clicked.connect(lambda:self.open_drawer_inventory());row.addWidget(self.inventory_button)
        self._drawer_windows={}
        catalogue=QPushButton(tr('Ajouter depuis un catalogue'));catalogue.clicked.connect(self.pick_catalogue);row.addWidget(catalogue)
        self.quantity_button=QPushButton(tr('Quantité dans ce tiroir…'));self.quantity_button.clicked.connect(self.edit_drawer_quantity);row.addWidget(self.quantity_button)
        self.transfer_button=QPushButton(tr('Transférer une quantité…'));self.transfer_button.clicked.connect(lambda:self.edit_drawer_quantity(True));row.addWidget(self.transfer_button)
        self.details_tabs=QTabWidget();self.details_tabs.addTab(details,tr('Contenu du tiroir'))
        self.stock_browser=StockToDrawers(db,engine,self.place_selected,self);self.stock_browser.selected.connect(self.selected.emit);self.stock_browser.opened.connect(self.open_stock_piece);self.details_tabs.addTab(self.stock_browser,tr('Pièces à ranger'))
        self.stock_browser.plan_requested.connect(lambda:self.plan_storage(True))
        self.stock_browser.target_wall_changed.connect(self.choose_storage_destination)
        self.details_tabs.currentChanged.connect(self.parts_mode_changed)
        split.addWidget(self.details_tabs);split.setSizes([350,350]);split.setStretchFactor(0,1);split.setStretchFactor(1,1);split.setChildrenCollapsible(False)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(180);self.search_timer.timeout.connect(self.search)
        self.icon_timer=QTimer(self);self.icon_timer.setSingleShot(True);self.icon_timer.setInterval(100);self.icon_timer.timeout.connect(self.load_icons)
        self.drawer_refresh_timer=QTimer(self);self.drawer_refresh_timer.setSingleShot(True);self.drawer_refresh_timer.setInterval(0);self.drawer_refresh_timer.timeout.connect(self.finish_drawer_move)
        self.wall.currentIndexChanged.connect(self.change_wall);self.query.textChanged.connect(lambda:self.search_timer.start());self.all_walls.toggled.connect(self.overview_changed);self.arrange.toggled.connect(self.arrangement_changed)
        self.drag_drawers.toggled.connect(self.drawer_arrangement_changed)
        self.zoom_in.clicked.connect(lambda:self.view.zoom(1.25));self.zoom_out.clicked.connect(lambda:self.view.zoom(1/1.25));self.focus_button.clicked.connect(self.focus_wall);self.fit_button.clicked.connect(self.fit_all)
        self.thumbnail_size.valueChanged.connect(self.change_thumbnail_size);self.thumbnail_size.sliderReleased.connect(self.save_thumbnail_size)
        self.angle.valueChanged.connect(self.redraw);self.angle.sliderReleased.connect(lambda:self.db.set_setting('storage_wall_angle',self.angle.value()));self.front.toggled.connect(self.redraw)
        self.view.view_changed.connect(self.update_zoom_label);self.view.view_changed.connect(self.schedule_icons);self.view.verticalScrollBar().valueChanged.connect(self.schedule_icons);self.view.horizontalScrollBar().valueChanged.connect(self.schedule_icons)
        self.results.itemSelectionChanged.connect(self.select_result);self.table.itemSelectionChanged.connect(self.select_piece);self.table.itemDoubleClicked.connect(self.open_piece)
        if self.thumbnails:self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset())
        self.reload_walls()
    def eventFilter(self,watched,event):
        if watched is getattr(self,'details',None) and event.type() in (QEvent.Type.Resize,QEvent.Type.LayoutRequest):
            height=self.details_layout.totalHeightForWidth(watched.width())
            if height>0 and watched.minimumHeight()!=height:watched.setMinimumHeight(height)
        return super().eventFilter(watched,event)

    def visible_parts(self):return [self.rows[row_index(self.table,r)] for r in range(self.table.rowCount())]
    def parts_mode_changed(self,index):
        side_by_side=self.details_tabs.currentWidget() is self.stock_browser
        self.content_split.setOrientation(Qt.Orientation.Horizontal if side_by_side else Qt.Orientation.Vertical)
        self.content_split.setSizes([350,450] if side_by_side else [350,350]);QTimer.singleShot(0,self.fit)
    def reload_walls(self,preferred=None):
        current=preferred or self.wall.currentData();self.wall.blockSignals(True);self.wall.clear()
        for wall in store.walls(self.db):self.wall.addItem(wall['name'],wall['id'])
        index=self.wall.findData(current);self.wall.setCurrentIndex(max(0,index));self.wall.blockSignals(False);self.change_wall()
    def choose_storage_destination(self,identity):
        index=self.wall.findData(identity)
        if index<0:return
        self.wall.setCurrentIndex(index);self.focus_wall();self.details_tabs.setCurrentWidget(self.stock_browser)
    def change_wall(self,*_):
        self.wall_id=self.wall.currentData();self.drawer_id=None;self.stock_browser.reload_target_walls(self.wall_id);self.stock_browser.auto_sort.setEnabled(self.wall_id is not None);self.redraw();self.load_contents();self.search();self.fit()
    def overview_changed(self,*_):
        if not self.all_walls.isChecked() and self.arrange.isChecked():
            self.arrange.blockSignals(True);self.arrange.setChecked(False);self.arrange.blockSignals(False)
            self.arrange.setText(tr('Disposer les meubles'));self.placement_hint.hide()
        self.redraw();self.search();self.fit()
    def arrangement_changed(self,enabled):
        if enabled:
            self.all_walls.blockSignals(True);self.all_walls.setChecked(True);self.all_walls.blockSignals(False)
            self.drag_drawers.blockSignals(True);self.drag_drawers.setChecked(False);self.drag_drawers.blockSignals(False)
        self.arrange.setText(tr('Terminer le placement') if enabled else tr('Disposer les meubles'))
        self.placement_hint.setText(tr('Glisse un meuble pour le déplacer. Sa position est enregistrée quand tu relâches la souris. Les meubles ne peuvent pas se chevaucher.'))
        self.placement_hint.setVisible(enabled);self.redraw();self.search();self.fit()
    def drawer_arrangement_changed(self,enabled):
        if enabled:
            self.arrange.blockSignals(True);self.arrange.setChecked(False);self.arrange.blockSignals(False);self.arrange.setText(tr('Disposer les meubles'))
        self.placement_hint.setText(tr('Glisse un tiroir vers une case du même meuble ou d’un autre meuble visible. Deux tiroirs de même taille échangent leurs positions. Les références suivent le tiroir. Décoche « Déplacer les tiroirs » pour terminer.'))
        self.placement_hint.setVisible(enabled);self.redraw();self.search()
    def redraw(self,*_):
        self.icon_token+=1;self.scene.clear();self.items={};self.cabinets={};self.wall_drawers={};self.drawers=[]
        self.arrange.setEnabled(self.wall_id is not None)
        self.drag_drawers.setEnabled(self.wall_id is not None);self.print_action.setEnabled(self.wall_id is not None)
        self.plan_action.setEnabled(self.wall_id is not None);self.plan_button.setEnabled(self.wall_id is not None)
        if self.wall_id is None:
            self.arrange.blockSignals(True);self.arrange.setChecked(False);self.arrange.blockSignals(False)
            self.arrange.setText(tr('Disposer les meubles'));self.placement_hint.hide()
            self.drag_drawers.blockSignals(True);self.drag_drawers.setChecked(False);self.drag_drawers.blockSignals(False)
            self.scene.setSceneRect(QRectF());return
        overview=self.all_walls.isChecked();arranging=self.arrange.isChecked()
        visible_walls=[w for w in store.walls(self.db) if overview or w['id']==self.wall_id];parts={}
        for p in store.wall_contents(self.db,None if overview else self.wall_id):parts.setdefault(p['drawer_id'],[]).append(p)
        for drawer in store.layout_drawers(self.db,None if overview else self.wall_id):self.wall_drawers.setdefault(drawer['wall_id'],[]).append(drawer)
        self.drawers=self.wall_drawers.get(self.wall_id,[])
        yaw=0 if self.front.isChecked() else self.angle.value();pitch=0 if self.front.isChecked() else 10
        for wall in visible_walls:
            cabinet=CabinetItem(wall,yaw,pitch,overview,arranging);cabinet.chosen.connect(self.choose_wall);cabinet.moved.connect(self.move_wall);self.scene.addItem(cabinet);self.cabinets[wall['id']]=cabinet
            for drawer in self.wall_drawers.get(wall['id'],[]):
                item=DrawerItem(drawer,parts.get(drawer['id'],[]),self.icons,yaw,pitch,cabinet,arranging,self.drag_drawers.isChecked(),self.thumbnail_size.value());item.opened.connect(self.open_drawer_inventory);item.chosen.connect(self.choose_drawer);item.moved.connect(self.move_drawer);self.items[drawer['id']]=item
        if self.drawer_id not in self.items:self.drawer_id=None
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20,-20,20,20));self.highlight();self.schedule_icons()
    def fit(self):
        if self.scene.items():
            bounds=self.scene.itemsBoundingRect().adjusted(-20,-20,20,20);self.scene.setSceneRect(bounds);self.view.fit_rect(bounds)
        self.update_zoom_label();self.schedule_icons()
    def fit_all(self):
        self.all_walls.setChecked(True);self.fit()
    def focus_wall(self):
        self.all_walls.setChecked(False)
        cabinet=self.cabinets.get(self.wall_id)
        if cabinet:self.view.fit_rect(cabinet.sceneBoundingRect().united(cabinet.mapRectToScene(cabinet.childrenBoundingRect())).adjusted(-20,-20,20,20))
    def update_zoom_label(self):
        self.zoom_label.setText(f'{self.view.transform().m11()*100:.1f} %')
        available=bool(self.cabinets)
        for button in (self.zoom_in,self.zoom_out,self.fit_button,self.focus_button):button.setEnabled(available)
    def change_thumbnail_size(self,value):
        self.thumbnail_size_label.setText(str(value)+' %')
        for item in self.items.values():item.thumbnail_size=value;item.update()
        if not self.thumbnail_size.isSliderDown():self.thumbnail_save_timer.start()
    def save_thumbnail_size(self):
        self.thumbnail_save_timer.stop();value=self.thumbnail_size.value()
        if value!=self._saved_thumbnail_size:self.db.set_setting('storage_thumbnail_size',value);self._saved_thumbnail_size=value
    def activate_wall(self,wall_id):
        index=self.wall.findData(wall_id)
        if index<0:return False
        # Item mouse handlers must keep their scene objects alive until release.
        self.wall.blockSignals(True);self.wall.setCurrentIndex(index);self.wall.blockSignals(False)
        self.wall_id=wall_id;self.stock_browser.set_target_wall(wall_id);self.drawers=self.wall_drawers.get(wall_id,[]);return True
    def choose_wall(self,wall_id):
        if self.activate_wall(wall_id):self.drawer_id=None;self.load_contents();self.highlight()
    def choose_drawer(self,drawer_id):
        item=self.items.get(drawer_id)
        if not item or not self.activate_wall(item.drawer['wall_id']):return
        self.drawer_id=drawer_id;self.details_tabs.setCurrentWidget(self.details);self.load_contents();self.highlight()
    def move_wall(self,wall_id,x,y):
        cabinet=self.cabinets.get(wall_id)
        if not cabinet:return
        old_x,old_y=cabinet.wall['x'],cabinet.wall['y']
        try:
            x,y=store.coordinate(x),store.coordinate(y);store.position_wall(self.db,wall_id,x,y)
        except (ValueError,sqlite3.Error,OSError) as e:
            cabinet.snap_position(old_x,old_y);self.placement_hint.setText(str(e));return
        cabinet.snap_position(x,y)
        self.placement_hint.setText(tr('Position enregistrée. Tu peux déplacer un autre meuble ou terminer le placement.'))
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20,-20,20,20));self.schedule_icons()
    def move_drawer(self,drawer_id,origin):
        item=self.items.get(drawer_id)
        if not item:return
        try:
            target=None
            for wall_id,cabinet in self.cabinets.items():
                inverse,valid=cabinet.back.inverted()
                if not valid:continue
                point=inverse.map(cabinet.mapFromScene(origin))
                col=math.floor((point.x()-12)/112+.5)+1;row=math.floor((point.y()-26)/70+.5)+1
                if 1<=col<=cabinet.wall['columns'] and 1<=row<=cabinet.wall['rows']:
                    target=(wall_id,col,row);break
            if target is None:raise ValueError(tr('Le tiroir doit rester entièrement dans un meuble.'))
            changed=store.move_drawer(self.db,drawer_id,*target)
        except (ValueError,sqlite3.Error,OSError) as e:
            item.setPos(getattr(item,'start_position',item.pos()));self.placement_hint.setText(str(e));return
        if not changed:item.setPos(getattr(item,'start_position',item.pos()));return
        self.activate_wall(target[0]);self.drawer_id=drawer_id
        self.placement_hint.setText(tr('Tiroir déplacé. Son nom et ses références ont été conservés.'))
        # Never clear a scene from inside a graphics item's mouseReleaseEvent.
        self.drawer_refresh_timer.start()
    def finish_drawer_move(self):
        self.redraw();self.load_contents();self.search()
        self.stock_browser.reload()
    def place_selected(self,payload):
        if self.drawer_id is None:
            QMessageBox.information(self,tr('Rangement'),tr('Sélectionne un tiroir ou glisse directement les pièces sur sa façade.'));return False
        return self.drop_parts(self.drawer_id,payload)
    def drop_parts(self,drawer_id,payload):
        target=self.items.get(drawer_id)
        if target is None:return False
        origin=payload.get('origin')
        if origin is not None and origin!=drawer_id:
            entries={(identity,str(color or '')) for identity,color in payload['entries']}
            source=[row for row in store.contents(self.db,origin) if (row['id'],str(row['chosen_color'] or '')) in entries]
            if len(source)!=len(entries):return False
            if any(row.get('stored_quantity') for row in source):
                from .storage_quantity_dialog import drop_quantity_dialog
                drop_quantity_dialog(self,origin,drawer_id,source);return True
        try:
            if payload.get('allocate_remaining'):
                from .storage_quantities import place_remaining
                place_remaining(self.db,drawer_id,payload['entries'])
            else:place_entries(self.db,drawer_id,payload['entries'],payload.get('origin'),payload.get('catalogue',False))
        except (ValueError,sqlite3.Error,OSError) as error:
            self.placement_hint.setText(str(error));self.placement_hint.show();return False
        self.activate_wall(target.drawer['wall_id']);self.drawer_id=drawer_id
        self.placement_hint.setText(tr('Références rangées. Les quantités du stock sont conservées.'));self.placement_hint.show()
        owner=application_owner(self)
        if hasattr(owner,'refresh_counts'):QTimer.singleShot(0,owner.refresh_counts)
        elif hasattr(owner,'update_undo'):owner.update_undo()
        self.drawer_refresh_timer.start();return True
    def open_stock_piece(self,item):
        from .dialogs import RelationsDialog
        show_window(RelationsDialog(self.db,self.engine,item,self),self)
    def plan_storage(self,from_parts=False):
        if self.wall_id is None:return
        options={}
        if from_parts:
            rows=self.stock_browser.selection() or self.stock_browser.rows
            options={'entries':[(p['id'],p['chosen_color']) for p in rows],'from_catalogue':self.stock_browser.catalogue_mode(),'category':self.stock_browser.category.currentData() or '','allocate_quantities':not self.stock_browser.catalogue_mode()}
        window=StoragePlanDialog(self.db,self.wall_id,self,self.refresh,**options);window._storage_wall_id=self.wall_id;show_window(window,self,refresh_counts=False);return window
    def print_wall(self):
        if self.wall_id is None:return
        from .storage_printing import StoragePrintPreview
        window=StoragePrintPreview(self.db,self.engine,self.wall_id,self)
        show_window(window,self)
        return window
    def open_drawer_inventory(self,drawer_id=None):
        if drawer_id is None:drawer_id=self.drawer_id
        if drawer_id is None:return
        existing=self._drawer_windows.get(drawer_id)
        if existing is not None:
            existing.show();existing.raise_();existing.activateWindow();return existing
        from .drawer_inventory import DrawerInventoryDialog
        window=DrawerInventoryDialog(self.db,self.engine,drawer_id,self,self.refresh);self._drawer_windows[drawer_id]=window
        show_window(window,self,lambda *_:self._drawer_windows.pop(drawer_id,None),refresh_counts=False);return window
    def load_contents(self):
        self.rows=store.contents(self.db,self.drawer_id) if self.drawer_id else []
        fill_table(self.table,[(p['source'],p['ref'],p['name'],p['category'],p['chosen_color'] or tr('Non précisée'),p['chosen_quantity'],tr('3D / photo à charger'),p['stored_quantity'] if p['stored_quantity'] is not None else tr('À renseigner')) for p in self.rows])
        if self.thumbnails:self.thumbnails.reset()
        self.update_status()
    def update_status(self):
        self.inventory_button.setEnabled(self.drawer_id is not None)
        self.remove_references.setEnabled(self.drawer_id is not None and bool(self.rows))
        self.update_quantity_actions()
        drawer=next((d for d in self.drawers if d['id']==self.drawer_id),None)
        if self.query.text().strip() and not self.matches:self.status.setText('0'+tr(' correspondance(s) dans les tiroirs.'))
        elif drawer:self.status.setText(' · '.join(value for value in (self.wall.currentText(),store.address(drawer),drawer['name']) if value)+' — '+str(len(self.rows))+tr(' référence(s). Les quantités non renseignées sont conservées sans supposer un comptage.'))
        elif self.query.text().strip():self.status.setText(str(len(self.matches))+tr(' correspondance(s) dans les tiroirs.'))
        elif self.wall_id is not None:self.status.setText(self.wall.currentText()+' — '+tr('Sélectionne un tiroir pour afficher ses références.'))
        else:self.status.setText(tr('Crée un meuble puis associe les références de tes catalogues ou de ton stock aux tiroirs.'))
    def highlight(self):
        hits={r['id'] for r in self.matches};searching=bool(self.query.text().strip())
        for identity,item in self.items.items():
            item.selected=identity==self.drawer_id;item.match=identity in hits;item.setOpacity(.45 if searching and not item.match else 1);item.update()
        for identity,cabinet in self.cabinets.items():cabinet.active=identity==self.wall_id;cabinet.update()
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
            self.activate_wall(result['wall_id'])
            if not self.all_walls.isChecked():self.redraw();self.fit()
        self.choose_drawer(result['id'])
        if self.drawer_id in self.items:self.view.ensureVisible(self.items[self.drawer_id])
    def update_quantity_actions(self):
        index=row_index(self.table)
        single=self.drawer_id is not None and len(self.table.selectionModel().selectedRows())==1 and 0<=index<len(self.rows)
        self.quantity_button.setEnabled(single)
        self.transfer_button.setEnabled(single and bool(self.rows[index].get('stored_quantity')))
    def select_piece(self):
        index=row_index(self.table)
        self.update_quantity_actions()
        if 0<=index<len(self.rows):self.selected.emit(self.rows[index])

    def edit_drawer_quantity(self,transfer=False):
        index=row_index(self.table)
        if len(self.table.selectionModel().selectedRows())!=1 or not 0<=index<len(self.rows):return
        from .storage_quantity_dialog import quantity_dialog
        return quantity_dialog(self,dict(self.rows[index]),transfer)
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
            except (ValueError,sqlite3.Error,OSError) as e:QMessageBox.warning(dialog,tr('Meuble invalide'),str(e));return
            self.reload_walls(identity);dialog.accept()
        buttons.accepted.connect(save);show_window(dialog,self)
    def rename_dialog(self):
        captured_wall=self.wall_id
        if captured_wall is None:return
        dialog=QDialog(self);dialog._storage_wall_id=captured_wall;dialog.setWindowTitle(tr('Renommer le meuble'));form=QFormLayout(dialog)
        name=QLineEdit(self.wall.currentText());name.setObjectName('cabinet_name');name.selectAll();form.addRow(tr('Nom'),name)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def save():
            try:value=store.rename_wall(self.db,captured_wall,name.text())
            except (ValueError,sqlite3.Error,OSError) as e:QMessageBox.warning(dialog,tr('Meuble invalide'),str(e));return
            index=self.wall.findData(captured_wall)
            if index>=0:
                self.wall.blockSignals(True);self.wall.setItemText(index,value);self.wall.blockSignals(False)
            cabinet=self.cabinets.get(captured_wall)
            if cabinet:cabinet.wall['name']=value;cabinet.setToolTip(value);cabinet.update()
            self.search();dialog.accept()
        buttons.accepted.connect(save);show_window(dialog,self);name.setFocus();return dialog
    def position_dialog(self):
        captured_wall=self.wall_id
        current=next((w for w in store.walls(self.db) if w['id']==captured_wall),None)
        if not current:return
        dialog=QDialog(self);dialog._storage_wall_id=captured_wall;dialog.setWindowTitle(tr('Positionner le meuble'));form=QFormLayout(dialog)
        name=QLineEdit(current['name']);form.addRow(tr('Nom'),name);positions={}
        for key,label in [('x',tr('Position horizontale')),('y',tr('Position verticale'))]:
            spin=QDoubleSpinBox();spin.setObjectName('position_'+key);spin.setDecimals(1);spin.setRange(-store.MAX_POSITION,store.MAX_POSITION);spin.setSingleStep(.1);spin.setValue(current[key]);positions[key]=spin;form.addRow(label,spin)
        note=QLabel(tr('Les positions sont mesurées en tiroirs standards. Les valeurs négatives permettent de placer un meuble à gauche ou au-dessus de l’origine.'));note.setWordWrap(True);form.addRow(note)
        reference=QComboBox();reference.setObjectName('reference_wall')
        for wall in store.walls(self.db):
            if wall['id']!=captured_wall:reference.addItem(wall['name'],wall['id'])
        form.addRow(tr('Par rapport au meuble'),reference)
        gap=QDoubleSpinBox();gap.setDecimals(1);gap.setRange(0,100);gap.setSingleStep(.1);gap.setValue(.2);form.addRow(tr('Écart entre les meubles'),gap)
        shortcuts=QHBoxLayout();form.addRow(shortcuts)
        def relative(direction):
            try:x,y=store.relative_position(self.db,captured_wall,reference.currentData(),direction,gap.value())
            except (ValueError,sqlite3.Error,OSError) as e:QMessageBox.warning(dialog,tr('Meuble invalide'),str(e));return
            positions['x'].setValue(x);positions['y'].setValue(y)
        for label,direction in [(tr('À gauche'),'left'),(tr('À droite'),'right'),(tr('Au-dessus'),'above'),(tr('En dessous'),'below')]:
            button=QPushButton(label);button.setEnabled(reference.count()>0);button.clicked.connect(lambda checked=False,d=direction:relative(d));shortcuts.addWidget(button)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def save():
            try:store.update_wall(self.db,captured_wall,name.text(),positions['x'].value(),positions['y'].value())
            except (ValueError,sqlite3.Error,OSError) as e:QMessageBox.warning(dialog,tr('Meuble invalide'),str(e));return
            self.reload_walls(captured_wall);dialog.accept()
        buttons.accepted.connect(save);show_window(dialog,self)
        return dialog
    def remove_wall(self):
        captured_wall=self.wall_id
        if captured_wall is None:return
        message=tf('Supprimer le meuble « {} », ses tiroirs et ses liens de rangement ? Les pièces et les sets restent dans leurs stocks.',self.wall.currentText())
        if QMessageBox.question(self,tr('Supprimer le meuble'),message)!=QMessageBox.StandardButton.Yes:return
        try:store.delete_wall(self.db,captured_wall)
        except (ValueError,sqlite3.Error,OSError) as e:QMessageBox.warning(self,tr('Meuble invalide'),str(e));return
        # Close cabinet-specific forms so an old editor cannot target a new
        # cabinet/drawer if SQLite subsequently reuses a deleted identifier.
        for window in list(getattr(application_owner(self),'_consultation_windows',[])):
            if getattr(window,'_storage_wall_id',None)==captured_wall:window.reject()
        self.reload_walls()
    def edit_drawer(self,new=False):
        if self.wall_id is None:return
        drawer=next((d for d in self.drawers if d['id']==self.drawer_id),None)
        if not new and not drawer:return
        captured_wall=self.wall_id;captured_id=None if new else drawer['id']
        dialog=QDialog(self);dialog._storage_wall_id=captured_wall;dialog.setWindowTitle(tr('Dimensions et nom du tiroir'));form=QFormLayout(dialog);fields={}
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
        dialog=StockPicker(self.db,self.engine,self.drawer_id,self,self.refresh);dialog._storage_wall_id=self.wall_id;show_window(dialog,self)
    def pick_catalogue(self):
        self.stock_browser.origin.setCurrentIndex(self.stock_browser.origin.findData('catalogue'));self.details_tabs.setCurrentWidget(self.stock_browser)
    def unassign(self):
        captured_drawer=self.drawer_id
        if captured_drawer is None or not self.rows:return
        selected=[self.rows[row_index(self.table,index.row())] for index in self.table.selectionModel().selectedRows()]
        return self.remove_drawer_references(captured_drawer,[(p['id'],p['chosen_color']) for p in selected] if selected else None)
    def remove_drawer_references(self,drawer_id,entries=None):
        if entries is None and QMessageBox.question(self,tr('Retirer les références du tiroir'),tr('Retirer toutes les références de ce tiroir ? Les pièces restent dans le stock.'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:count=store.unassign(self.db,drawer_id,entries)
        except (ValueError,sqlite3.Error,OSError) as e:QMessageBox.warning(self,tr('Retrait impossible'),str(e));return
        self.refresh();return count
    def drawer_context_menu(self,pos):
        item=self.view.itemAt(pos)
        if not isinstance(item,DrawerItem):return
        drawer_id=item.drawer['id'];self.choose_drawer(drawer_id);parts=store.contents(self.db,drawer_id)
        menu=QMenu(self);menu.addAction(tr('Ouvrir l’inventaire du tiroir…'),lambda:self.open_drawer_inventory(drawer_id));references=menu.addMenu(tr('Retirer une référence du tiroir'));references.setEnabled(bool(parts))
        for part in parts[:30]:
            label=part['source']+' '+part['ref']+' — '+part['name']+' · '+(part['chosen_color'] or tr('Non précisée'))
            references.addAction(label,lambda checked=False,p=part:self.remove_drawer_references(drawer_id,[(p['id'],p['chosen_color'])]))
        if len(parts)>30:
            menu.addAction(tr('Choisir les références dans le tableau'),lambda:self.choose_drawer(drawer_id))
        remove=menu.addAction(tr('Retirer toutes les références du tiroir…'),lambda:self.remove_drawer_references(drawer_id));remove.setEnabled(bool(parts))
        menu.exec(self.view.viewport().mapToGlobal(pos))
    def refresh(self):
        owner=application_owner(self)
        if hasattr(owner,'update_undo'):owner.update_undo()
        if not self.isVisible():return
        self.redraw();self.load_contents();self.search()
        self.stock_browser.reload_categories();self.stock_browser.reload()
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
                try:image,_=load_thumbnail(self.engine,part,key,generation)
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
        self.save_thumbnail_size()
        self.icon_token+=1;self.icon_timer.stop();self.search_timer.stop();self.icons.clear()
        if self.thumbnails:self.thumbnails.suspend()
        super().hideEvent(event)
