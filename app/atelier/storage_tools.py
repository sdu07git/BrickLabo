"""Stock tables that can be dragged onto drawers, and a size-based preview."""
import json
import sqlite3
import uuid

from PySide6.QtCore import Qt,QMimeData,QTimer,Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QLabel,QLineEdit,QComboBox,QCheckBox,
    QTableWidget,QPushButton,QAbstractItemView,QHeaderView,QMessageBox,QFormLayout)
from .i18n import tr,tf
from .ui_common import FlowLayout
from .result_tables import fill_table,row_index
from .thumbnails import PartThumbnails
from . import storage_assignment as assignment
from . import storage_wall as walls

MIME='application/x-bricklabo-stock-references'


def drag_token(db):
    if not hasattr(db,'_storage_drag_token'):db._storage_drag_token=uuid.uuid4().hex
    return db._storage_drag_token


def read_drag(mime,db):
    if not mime.hasFormat(MIME):return None
    raw=bytes(mime.data(MIME))
    if len(raw)>1024*1024:return None
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or value.get('session')!=drag_token(db):return None
        entries=value.get('entries');origin=value.get('origin')
        catalogue=value.get('catalogue',False)
        if type(catalogue) is not bool or catalogue and origin is not None:return None
        if origin is not None and (type(origin) is not int or origin<=0):return None
        if not isinstance(entries,list) or not 1<=len(entries)<=5000:return None
        if any(not isinstance(entry,list) or len(entry)!=2 or type(entry[0]) is not int or entry[0]<=0 or not isinstance(entry[1],str) or len(entry[1])>100 for entry in entries):return None
        if catalogue and any(entry[1] for entry in entries):return None
        return value
    except (ValueError,UnicodeError,TypeError):return None


class StorageDragTable(QTableWidget):
    def __init__(self,db,rows,origin=lambda:None,*args):
        super().__init__(*args);self.db=db;self.drag_rows=rows;self.drag_origin=origin;self.drag_catalogue=lambda:False;drag_token(db)
        self.setDragEnabled(True);self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def mimeData(self,items):
        rows=self.drag_rows();indices=sorted({row_index(self,index.row()) for index in self.selectionModel().selectedRows()})
        entries=[[rows[index]['id'],str(rows[index].get('chosen_color',''))] for index in indices if 0<=index<len(rows)]
        mime=QMimeData();mime.setData(MIME,json.dumps({'session':drag_token(self.db),'entries':entries,'origin':self.drag_origin(),'catalogue':self.drag_catalogue()}).encode())
        mime.setText(tf('{0} référence(s)',len(entries)));return mime

    def startDrag(self,supportedActions):
        mime=self.mimeData(self.selectedItems())
        if not read_drag(mime,self.db):return
        drag=QDrag(self);drag.setMimeData(mime)
        action=Qt.DropAction.MoveAction if self.drag_origin() is not None else Qt.DropAction.CopyAction
        drag.exec(action,action)


class StockToDrawers(QWidget):
    selected=Signal(object)
    opened=Signal(object)
    def __init__(self,db,engine,place,parent=None):
        super().__init__(parent);self.db=db;self.rows=[];self.place=place
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        hint=QLabel(tr('Sélectionne des pièces puis glisse-les sur un tiroir du meuble. Ctrl et Maj permettent une sélection multiple.'));hint.setWordWrap(True);layout.addWidget(hint)
        self.origin=QComboBox();self.origin.setAccessibleName(tr('Origine des pièces à ranger'))
        for label,value in [(tr('Stock en vrac'),'stock'),(tr('Tous les catalogues'),'catalogue'),(tr('Catalogue Rebrickable'),'RB'),(tr('Catalogue BrickLink'),'BL'),('BrickArchitect','BA'),(tr('Catalogue Briques Alternatives'),'ALT'),(tr('Catalogue Mini-Figs'),'minifig')]:self.origin.addItem(label,value)
        layout.addWidget(self.origin)
        controls=FlowLayout();self.query=QLineEdit();self.query.setPlaceholderText(tr('Référence, nom ou catégorie'));self.query.setMinimumWidth(180);controls.addWidget(self.query)
        self.category=QComboBox();self.category.setMinimumContentsLength(16);self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);controls.addWidget(self.category)
        self.unlocated=QCheckBox(tr('Sans emplacement uniquement'));self.unlocated.setChecked(True);controls.addWidget(self.unlocated);layout.addLayout(controls)
        self.table=StorageDragTable(db,lambda:self.rows,lambda:None,0,7)
        self.table.drag_catalogue=lambda:self.catalogue_mode()
        self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Couleur'),tr('Pièce'),tr('Catégorie'),tr('Stock en vrac'),tr('Aperçu')])
        for column,width in enumerate((70,90,80,210,140,100,130)):self.table.setColumnWidth(column,width)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.setMinimumHeight(150);layout.addWidget(self.table,1)
        self.thumbnails=PartThumbnails(self.table,db,engine,self.visible_rows,6,self) if engine else None
        row=FlowLayout();self.count=QLabel();row.addWidget(self.count);self.add=QPushButton(tr('Associer au tiroir sélectionné'));self.add.clicked.connect(self.add_selection);row.addWidget(self.add);layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.reload)
        for signal in (self.query.textChanged,self.category.currentIndexChanged,self.unlocated.toggled):signal.connect(lambda *_:self.timer.start())
        self.table.itemSelectionChanged.connect(self.select);self.table.itemDoubleClicked.connect(self.open)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset() if self.thumbnails else None)
        self.origin.currentIndexChanged.connect(self.change_origin)
        self.reload_categories();self.reload()

    def catalogue_mode(self):return self.origin.currentData()!='stock'

    def change_origin(self,*_):
        self.timer.stop();self.reload_categories();self.reload()

    def reload_categories(self):
        current=self.category.currentData();self.category.blockSignals(True);self.category.clear();self.category.addItem(tr('Toutes les catégories'),'')
        origin=self.origin.currentData();args=[]
        if origin=='stock':sql="SELECT DISTINCT i.category FROM stock s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 AND i.kind IN ('part','minifig') AND i.category<>''"
        else:
            sql="SELECT DISTINCT i.category FROM items i WHERE i.catalogue_hidden=0 AND i.kind IN ('part','minifig') AND i.category<>''"
            if origin=='minifig':sql+=" AND i.kind='minifig'"
            elif origin!='catalogue':sql+=' AND i.source=?';args.append(origin)
        for row in self.db.rows(sql+' ORDER BY i.category',args):self.category.addItem(row['category'],row['category'])
        self.category.setCurrentIndex(max(0,self.category.findData(current)));self.category.blockSignals(False)

    def reload(self):
        if self.catalogue_mode():
            origin=self.origin.currentData();source=origin if origin not in ('catalogue','minifig') else None
            self.rows=assignment.catalogue_rows(self.db,self.query.text(),self.category.currentData() or '',self.unlocated.isChecked(),source,'minifig' if origin=='minifig' else None,5001)
        else:self.rows=assignment.stock_rows(self.db,self.query.text(),self.category.currentData() or '',self.unlocated.isChecked(),5001)
        limited=len(self.rows)>5000;self.rows=self.rows[:5000]
        self.table.setColumnHidden(5,self.catalogue_mode())
        fill_table(self.table,[(p['source'],p['ref'],tr('Non précisée') if self.catalogue_mode() else p['chosen_color'],p['name'],p['category'],p.get('chosen_quantity',''),tr('3D / photo à charger')) for p in self.rows])
        for row in range(self.table.rowCount()):
            part=self.rows[row_index(self.table,row)];self.table.item(row,1).setToolTip(part['name']+'\n'+part['category']+'\n'+tr('Couleur')+' : '+part['chosen_color'])
        self.count.setText(tf('{0} référence(s)',len(self.rows))+(tr(' — affine la recherche pour afficher les autres.') if limited else ''))
        if self.thumbnails:self.thumbnails.reset()

    def visible_rows(self):return [self.rows[row_index(self.table,index)] for index in range(self.table.rowCount())]
    def selection(self):return [self.rows[row_index(self.table,index.row())] for index in self.table.selectionModel().selectedRows()]
    def add_selection(self):
        rows=self.selection()
        if rows:self.place({'entries':[(p['id'],p['chosen_color']) for p in rows],'origin':None,'catalogue':self.catalogue_mode()})
    def select(self):
        index=row_index(self.table)
        if 0<=index<len(self.rows):self.selected.emit(self.rows[index])
    def open(self,*_):
        index=row_index(self.table)
        if 0<=index<len(self.rows):self.opened.emit(self.rows[index])
    def hideEvent(self,event):
        self.timer.stop()
        if self.thumbnails:self.thumbnails.suspend()
        super().hideEvent(event)


class CatalogueToDrawerDialog(QDialog):
    """Assign exact catalogue identities without writing any stock entry."""
    def __init__(self,db,items,parent=None,changed=lambda:None):
        super().__init__(parent);self.db=db;self.items=[dict(item) for item in items];self.changed=changed
        self.setWindowTitle(tr('Associer à un tiroir…'));self.resize(820,520)
        layout=QVBoxLayout(self);self.hint=QLabel(tr('Choisis un meuble et un tiroir. Ces références seront associées sans couleur imposée, sans ajout au stock et sans quantité à renseigner.'));self.hint.setWordWrap(True);layout.addWidget(self.hint)
        form=QFormLayout();self.wall=QComboBox();self.drawer=QComboBox();form.addRow(tr('Meuble'),self.wall);form.addRow(tr('Tiroir'),self.drawer);layout.addLayout(form)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0,90);self.table.setColumnWidth(1,140);fill_table(self.table,[(p['source'],p['ref'],p['name']) for p in self.items]);layout.addWidget(self.table,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=FlowLayout();refresh=QPushButton(tr('Actualiser les meubles'));refresh.clicked.connect(self.reload_walls);row.addWidget(refresh)
        self.apply_button=QPushButton(tr('Associer les références au tiroir'));self.apply_button.clicked.connect(self.apply);row.addWidget(self.apply_button)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
        self.wall.currentIndexChanged.connect(self.reload_drawers);self.drawer.currentIndexChanged.connect(lambda *_:self.apply_button.setEnabled(bool(self.items) and self.drawer.currentData() is not None));self.reload_walls()

    def reload_walls(self):
        current=self.wall.currentData();self.wall.blockSignals(True);self.wall.clear()
        for wall in walls.walls(self.db):self.wall.addItem(wall['name'],wall['id'])
        self.wall.setCurrentIndex(max(0,self.wall.findData(current)));self.wall.blockSignals(False);self.reload_drawers()

    def reload_drawers(self,*_):
        current=self.drawer.currentData();self.drawer.blockSignals(True);self.drawer.clear()
        if self.wall.currentData() is not None:
            for drawer in walls.drawers(self.db,self.wall.currentData()):self.drawer.addItem(walls.address(drawer)+(' — '+drawer['name'] if drawer['name'] else ''),drawer['id'])
        self.drawer.setCurrentIndex(max(0,self.drawer.findData(current)));self.drawer.blockSignals(False)
        self.apply_button.setEnabled(bool(self.items) and self.drawer.currentData() is not None)
        self.status.setText(tr('Aucun meuble disponible. Crée un meuble dans Mon rangement, puis actualise cette liste.') if self.wall.count()==0 else tf('{0} référence(s)',len(self.items)))

    def apply(self):
        target=self.drawer.currentData()
        if target is None or not self.items:return
        try:assignment.place_entries(self.db,target,[(p['id'],'') for p in self.items],from_catalogue=True)
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Rangement impossible'),str(error));return
        self.changed();self.accept()


class StoragePlanDialog(QDialog):
    def __init__(self,db,wall_id,parent=None,changed=lambda:None):
        super().__init__(parent);self.db=db;self.wall_id=wall_id;self.changed=changed;self.plan=None;self.targets=[]
        self.setWindowTitle(tr('Ranger par catégorie et taille en tenons'));self.resize(960,650)
        layout=QVBoxLayout(self)
        hint=QLabel(tr('Choisis une catégorie, par exemple Bricks. Les dimensions écrites dans les noms des pièces regroupent les références par taille, de la plus petite à la plus grande. Les couleurs restent ensemble sauf si tu les sépares. Ajuste les tiroirs proposés avant d’appliquer.'));hint.setWordWrap(True);layout.addWidget(hint)
        controls=FlowLayout();self.category=QComboBox();self.category.addItem(tr('Toutes les catégories'),'')
        for row in db.rows("SELECT DISTINCT category FROM (SELECT i.category FROM stock s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 AND i.kind IN ('part','minifig') UNION SELECT i.category FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN items i ON i.id=p.item_id WHERE d.wall_id=?) WHERE category<>'' ORDER BY category",(wall_id,)):self.category.addItem(row['category'],row['category'])
        controls.addWidget(self.category);self.colors=QCheckBox(tr('Séparer les couleurs'));controls.addWidget(self.colors)
        self.reorganize=QCheckBox(tr('Réorganiser cette catégorie dans ce meuble'));controls.addWidget(self.reorganize);layout.addLayout(controls)
        explanation=QLabel(tr('Par défaut : pièces sans emplacement et tiroirs vides sans nom. La réorganisation remplace les liens des tiroirs contenant uniquement cette catégorie. Les tiroirs mixtes, les autres meubles et toutes les quantités sont conservés.'));explanation.setWordWrap(True);layout.addWidget(explanation)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels([tr('Catégorie'),tr('Dimensions en tenons'),tr('Couleur'),tr('Références'),tr('Tiroir proposé')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.ensurePolished()
        for column,width in enumerate((145,190,90,175,260)):
            self.table.setColumnWidth(column,max(width,self.table.fontMetrics().horizontalAdvance(self.table.horizontalHeaderItem(column).text())+28))
        layout.addWidget(self.table,1);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        row=FlowLayout();prepare=QPushButton(tr('Préparer une proposition'));prepare.clicked.connect(self.rebuild);row.addWidget(prepare)
        self.apply_button=QPushButton(tr('Appliquer le rangement proposé'));self.apply_button.clicked.connect(self.apply);row.addWidget(self.apply_button)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
        self.category.currentIndexChanged.connect(self.rebuild);self.colors.toggled.connect(self.rebuild);self.reorganize.toggled.connect(self.rebuild);self.rebuild()

    def rebuild(self,*_):
        category=self.category.currentData() or '';self.reorganize.setEnabled(bool(category))
        if not category:self.reorganize.blockSignals(True);self.reorganize.setChecked(False);self.reorganize.blockSignals(False)
        try:self.plan=assignment.propose(self.db,self.wall_id,category,self.colors.isChecked(),self.reorganize.isChecked())
        except (ValueError,sqlite3.Error,OSError) as error:
            self.plan=None;self.table.setRowCount(0);self.summary.setText(str(error));self.apply_button.setEnabled(False);return
        self.targets=[];fill_table(self.table,[(g['category'],assignment.dimensions_text(g['dimensions']),g['color'],str(len(g['entries'])),'') for g in self.plan['groups']],sortable=False)
        for index,group in enumerate(self.plan['groups']):
            self.table.item(index,3).setToolTip('\n'.join(group['references']))
            target=QComboBox();target.addItem(tr('Laisser sans emplacement'),None)
            for drawer in self.plan['available']:target.addItem(walls.address(drawer)+(' — '+drawer['name'] if drawer['name'] else ''),drawer['id'])
            target.setCurrentIndex(max(0,target.findData(group['drawer_id'])));self.table.setCellWidget(index,4,target);self.targets.append(target)
            target.currentIndexChanged.connect(self.update_summary)
        self.update_summary()

    def update_summary(self,*_):
        if not self.plan:return
        chosen=[w.currentData() for w in self.targets];assigned=[identity for identity in chosen if identity is not None]
        self.summary.setText(tf('{0} groupe(s), {1} tiroir(s) disponible(s), {2} groupe(s) à ranger, {3} sans tiroir. {4} référence(s) sans dimensions restent à ranger manuellement.',len(chosen),len(self.plan['available']),len(assigned),len(chosen)-len(assigned),len(self.plan['unknown'])))
        self.apply_button.setEnabled(bool(assigned) and len(assigned)==len(set(assigned)))

    def apply(self):
        if not self.plan:return
        try:count,references=assignment.apply_proposal(self.db,self.plan,[w.currentData() for w in self.targets])
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Rangement impossible'),str(error));return
        self.changed();QMessageBox.information(self,tr('Rangement enregistré'),tf('{0} tiroir(s) renseigné(s), {1} référence(s) associée(s). Les quantités du stock sont conservées.',count,references));self.accept()
