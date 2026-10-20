"""Stock tables that can be dragged onto drawers, and a size-based preview."""
import json
import sqlite3
import uuid

from PySide6.QtCore import Qt,QMimeData,QTimer,Signal,QItemSelectionModel
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QCheckBox,
    QTableWidget,QPushButton,QAbstractItemView,QHeaderView,QMessageBox,QFormLayout,QSplitter,QInputDialog,QSpinBox,QDialogButtonBox)
from .i18n import tr,tf
from .ui_common import FlowLayout
from .result_tables import fill_table,row_index
from .thumbnails import PartThumbnails
from . import storage_assignment as assignment
from . import storage_wall as walls
from .storage_draft import group_key,arrange_targets,spaced_references

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
        allocate=value.get('allocate_remaining',False)
        if type(allocate) is not bool or allocate and (catalogue or origin is not None):return None
        if type(catalogue) is not bool or catalogue and origin is not None:return None
        if origin is not None and (type(origin) is not int or origin<=0):return None
        if not isinstance(entries,list) or not 1<=len(entries)<=5000:return None
        if any(not isinstance(entry,list) or len(entry)!=2 or type(entry[0]) is not int or entry[0]<=0 or not isinstance(entry[1],str) or len(entry[1])>100 for entry in entries):return None
        if catalogue and any(entry[1] for entry in entries):return None
        return value
    except (ValueError,UnicodeError,TypeError):return None


class StorageDragTable(QTableWidget):
    def __init__(self,db,rows,origin=lambda:None,*args):
        super().__init__(*args);self.db=db;self.drag_rows=rows;self.drag_origin=origin;self.drag_catalogue=lambda:False;self.drag_allocate_remaining=lambda:False;drag_token(db)
        self.setDragEnabled(True);self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def mimeData(self,items):
        rows=self.drag_rows();indices=sorted({row_index(self,index.row()) for index in self.selectionModel().selectedRows()})
        entries=[[rows[index]['id'],str(rows[index].get('chosen_color',''))] for index in indices if 0<=index<len(rows)]
        mime=QMimeData();mime.setData(MIME,json.dumps({'session':drag_token(self.db),'entries':entries,'origin':self.drag_origin(),'catalogue':self.drag_catalogue(),'allocate_remaining':self.drag_allocate_remaining()}).encode())
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
    plan_requested=Signal()
    target_wall_changed=Signal(object)
    def __init__(self,db,engine,place,parent=None):
        super().__init__(parent);self.db=db;self.rows=[];self.place=place
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        hint=QLabel(tr('Sélectionne des pièces puis glisse-les sur un tiroir du meuble. Ctrl et Maj permettent une sélection multiple.'));hint.setWordWrap(True);layout.addWidget(hint)
        self.origin=QComboBox();self.origin.setAccessibleName(tr('Origine des pièces à ranger'))
        for label,value in [(tr('Stock en vrac'),'stock'),(tr('Tous les catalogues'),'catalogue'),(tr('Catalogue Rebrickable'),'RB'),(tr('Catalogue BrickLink'),'BL'),('BrickArchitect','BA'),(tr('Catalogue Briques Alternatives'),'ALT'),(tr('Catalogue Mini-Figs'),'minifig')]:self.origin.addItem(label,value)
        layout.addWidget(self.origin)
        destination=QHBoxLayout();destination.addWidget(QLabel(tr('Meuble de destination')));self.target_wall=QComboBox();self.target_wall.setAccessibleName(tr('Meuble de destination'));self.target_wall.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.target_wall.setMinimumContentsLength(12);self.target_wall.setMaximumWidth(260);destination.addWidget(self.target_wall,1);layout.addLayout(destination)
        controls=FlowLayout();self.query=QLineEdit();self.query.setPlaceholderText(tr('Référence, nom ou catégorie'));self.query.setMinimumWidth(180);controls.addWidget(self.query)
        self.category=QComboBox();self.category.setMinimumContentsLength(16);self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);controls.addWidget(self.category)
        self.unlocated=QCheckBox(tr('Sans emplacement uniquement'));self.unlocated.setChecked(True);controls.addWidget(self.unlocated);layout.addLayout(controls)
        self.table=StorageDragTable(db,lambda:self.rows,lambda:None,0,8)
        self.table.drag_catalogue=lambda:self.catalogue_mode()
        self.table.drag_allocate_remaining=lambda:not self.catalogue_mode()
        self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Couleur'),tr('Pièce'),tr('Catégorie'),tr('Stock en vrac'),tr('Aperçu'),tr('Restant à ranger')])
        for column,width in enumerate((70,90,80,210,140,100,130,140)):self.table.setColumnWidth(column,width)
        self.table.horizontalHeader().moveSection(7,2)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.setMinimumHeight(150);layout.addWidget(self.table,1)
        self.thumbnails=PartThumbnails(self.table,db,engine,self.visible_rows,6,self) if engine else None
        row=FlowLayout();self.count=QLabel();row.addWidget(self.count);self.add=QPushButton(tr('Associer au tiroir sélectionné'));self.add.clicked.connect(self.add_selection);row.addWidget(self.add)
        self.auto_sort=QPushButton(tr('Rangement automatique…'));self.auto_sort.setToolTip(tr('Préparer un rangement par catégorie et taille, des plus petites pièces en haut aux plus grandes en bas.'));self.auto_sort.clicked.connect(lambda:self.plan_requested.emit());row.addWidget(self.auto_sort);layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.reload)
        for signal in (self.query.textChanged,self.category.currentIndexChanged,self.unlocated.toggled):signal.connect(lambda *_:self.timer.start())
        self.table.itemSelectionChanged.connect(self.select);self.table.itemDoubleClicked.connect(self.open)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset() if self.thumbnails else None)
        self.origin.currentIndexChanged.connect(self.change_origin)
        self.target_wall.currentIndexChanged.connect(lambda:self.target_wall_changed.emit(self.target_wall.currentData()))
        self.target_wall.currentTextChanged.connect(self.target_wall.setToolTip)
        self.reload_target_walls()
        self.reload_categories();self.reload()

    def set_target_wall(self,identity):
        if self.target_wall.currentData()=='all' and identity!='all':return
        blocked=self.target_wall.blockSignals(True);self.target_wall.setCurrentIndex(max(0,self.target_wall.findData(identity)));self.target_wall.blockSignals(blocked)
    def reload_target_walls(self,preferred=None):
        current=self.target_wall.currentData()
        if current!='all' and preferred is not None:current=preferred
        blocked=self.target_wall.blockSignals(True);self.target_wall.clear();available=walls.walls(self.db)
        if available:self.target_wall.addItem(tr('Tous les meubles'),'all')
        for wall in available:self.target_wall.addItem(wall['name'],wall['id'])
        index=self.target_wall.findData(current);self.target_wall.setCurrentIndex(index if index>=0 else 1 if available else -1);self.target_wall.setEnabled(bool(available));self.target_wall.blockSignals(blocked)

    def catalogue_mode(self):return self.origin.currentData()!='stock'

    def change_origin(self,*_):
        self.unlocated.setText(tr('Sans emplacement uniquement') if self.catalogue_mode() else tr('Quantités restant à ranger'))
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
        else:self.rows=assignment.stock_rows(self.db,self.query.text(),self.category.currentData() or '',False,5001,remaining_only=self.unlocated.isChecked())
        limited=len(self.rows)>5000;self.rows=self.rows[:5000]
        self.table.setColumnHidden(5,self.catalogue_mode())
        self.table.setColumnHidden(7,self.catalogue_mode());self.unlocated.setText(tr('Sans emplacement uniquement') if self.catalogue_mode() else tr('Quantités restant à ranger'))
        fill_table(self.table,[(p['source'],p['ref'],tr('Non précisée') if self.catalogue_mode() else p['chosen_color'],p['name'],p['category'],p.get('chosen_quantity',''),tr('3D / photo à charger'),p.get('remaining_quantity','')) for p in self.rows])
        for row in range(self.table.rowCount()):
            part=self.rows[row_index(self.table,row)];self.table.item(row,1).setToolTip(part['name']+'\n'+part['category']+'\n'+tr('Couleur')+' : '+part['chosen_color'])
        self.count.setText(tf('{0} référence(s)',len(self.rows))+(tr(' — affine la recherche pour afficher les autres.') if limited else ''))
        if self.thumbnails:self.thumbnails.reset()

    def visible_rows(self):return [self.rows[row_index(self.table,index)] for index in range(self.table.rowCount())]
    def selection(self):return [self.rows[row_index(self.table,index.row())] for index in self.table.selectionModel().selectedRows()]
    def add_selection(self):
        rows=self.selection()
        if rows:self.place({'entries':[(p['id'],p['chosen_color']) for p in rows],'origin':None,'catalogue':self.catalogue_mode(),'allocate_remaining':not self.catalogue_mode()})
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


class ReferenceDrawerCountsDialog(QDialog):
    """Choose a separate drawer count for each physical catalogue identity."""
    def __init__(self,db,parts,counts,quantities,engine=None,parent=None):
        super().__init__(parent);self.rows=parts;self.spins={}
        self.setWindowTitle(tr('Nombre de tiroirs par référence'));self.resize(900,540)
        layout=QVBoxLayout(self);hint=QLabel(tr('Choisis 1, 2, 3 tiroirs ou davantage pour chaque référence. Le critère Référence sera coché. Les quantités connues sont réparties aussi également que possible, sans modifier le stock. Si les couleurs sont séparées, ce nombre s’applique à chaque couleur.'));hint.setWordWrap(True);layout.addWidget(hint)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels([tr('Aperçu'),tr('Source'),tr('Référence'),tr('Pièce'),tr('Quantité à répartir'),tr('Nombre de tiroirs')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        fill_table(self.table,[(tr('3D / photo à charger'),p['source'],p['ref'],p['name'],quantities.get(p['id'],tr('À renseigner')),'') for p in parts],sortable=False)
        for column,width in enumerate((110,65,95,195,140,140)):self.table.setColumnWidth(column,width)
        for visual,column in enumerate((0,2,5,4,3,1)):self.table.horizontalHeader().moveSection(self.table.horizontalHeader().visualIndex(column),visual)
        for row,part in enumerate(parts):
            spin=QSpinBox();spin.setRange(1,1000);spin.setValue(counts.get(part['id'],1));spin.setAccessibleName(tr('Nombre de tiroirs')+' '+part['source']+' '+part['ref']);self.spins[part['id']]=spin;self.table.setCellWidget(row,5,spin)
            cell=self.table.item(row,5);cell.setData(Qt.ItemDataRole.DisplayRole,spin.value());spin.valueChanged.connect(lambda value,item=cell:item.setData(Qt.ItemDataRole.DisplayRole,value))
        self.table.setSortingEnabled(True);self.table.sortItems(2,Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.table,1);self.thumbs=PartThumbnails(self.table,db,engine,self.visible_rows,0,self) if engine else None
        if self.thumbs:self.table.model().layoutChanged.connect(lambda *_:self.thumbs.reset())
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def visible_rows(self):return [self.rows[row_index(self.table,row)] for row in range(self.table.rowCount())]

    def counts(self):return {identity:spin.value() for identity,spin in self.spins.items() if spin.value()>1}

    def done(self,result):
        if self.thumbs:self.thumbs.stop()
        super().done(result)


class StoragePlanDialog(QDialog):
    def __init__(self,db,wall_id,parent=None,changed=lambda:None,entries=None,from_catalogue=False,category='',allocate_quantities=False):
        super().__init__(parent);self.db=db;self.wall_id=wall_id;self.changed=changed;self.plan=None;self.targets=[]
        from . import storage_order
        self.entries=list(entries) if entries is not None else None;self.from_catalogue=from_catalogue;self.drawer_counts={};self.thumbnail_rows=[];self.category_order=storage_order.saved(db)
        self.count_spins=[];self.target_overrides={};self.changed_counts=set();self.count_timer=QTimer(self);self.count_timer.setSingleShot(True);self.count_timer.setInterval(100);self.count_timer.timeout.connect(lambda:self.rebuild(preserve_targets=True))
        self.setWindowTitle(tr('Ranger par catégorie et taille en tenons'));self.setMinimumSize(800,480)
        available=self.screen().availableGeometry();self.resize(min(1360,max(800,available.width()-32)),min(820,max(480,available.height()-56)))
        layout=QVBoxLayout(self)
        hint=QLabel(tr('Coche les critères, puis règle Nombre de tiroirs directement dans le tableau. L’aperçu s’actualise ; les destinations choisies manuellement sont conservées lors de ce réglage.'));hint.setWordWrap(True);layout.addWidget(hint)
        if self.entries is not None:
            scope_hint=QLabel(tr('Cette proposition utilise la sélection de Pièces à ranger, ou les références affichées si aucune ligne n’est sélectionnée.'));scope_hint.setWordWrap(True);layout.addWidget(scope_hint)
        drafts=FlowLayout()
        from .storage_sessions import save as save_draft,load as load_draft
        for title,callback in [(tr('Enregistrer un brouillon…'),lambda:save_draft(self)),(tr('Reprendre un brouillon…'),lambda:load_draft(self))]:
            button=QPushButton(title);button.clicked.connect(callback);drafts.addWidget(button)
        layout.addLayout(drafts)
        destination=FlowLayout();destination.addWidget(QLabel(tr('Meubles à utiliser')));self.destination=QComboBox();self.destination.setAccessibleName(tr('Meubles à utiliser'));self.destination.setMaximumWidth(300);self.destination.addItem(tr('Tous les meubles'),None)
        for wall in walls.walls(db):self.destination.addItem(wall['name'],wall['id'])
        self.destination.setCurrentIndex(max(0,self.destination.findData(wall_id)));destination.addWidget(self.destination)
        self.category_order_button=QPushButton(tr('Ordre des catégories…'));self.category_order_button.clicked.connect(self.choose_category_order);destination.addWidget(self.category_order_button);layout.addLayout(destination)
        self.destination_hint=QLabel(tr('Tous les meubles : ordre du haut vers le bas, de gauche à droite. Dans chaque meuble, les tiroirs sont remplis depuis le haut.'));self.destination_hint.setWordWrap(True);layout.addWidget(self.destination_hint)
        controls=FlowLayout();self.category=QComboBox();self.category.setMaximumWidth(280);self.category.addItem(tr('Toutes les catégories'),'')
        for row in db.rows("SELECT DISTINCT category FROM (SELECT i.category FROM stock s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 AND i.kind IN ('part','minifig') UNION SELECT i.category FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN items i ON i.id=p.item_id WHERE (? IS NULL OR d.wall_id=?)) WHERE category<>'' ORDER BY category",(None,None)):self.category.addItem(row['category'],row['category'])
        if self.from_catalogue:
            categories={self.category.itemData(index) for index in range(self.category.count())}
            for identity,color in self.entries or []:
                item=db.get_item(identity)
                if item and item['category'] and item['category'] not in categories:self.category.addItem(item['category'],item['category']);categories.add(item['category'])
        self.category.setCurrentIndex(max(0,self.category.findData(category)))
        controls.addWidget(self.category);self.grouping=QComboBox();self.grouping.setAccessibleName(tr('Mode de rangement'))
        for label,mode in [(tr('Regroupement automatique'),'size'),(tr('Une référence par tiroir'),'reference'),(tr('Regroupement libre de références'),'manual')]:self.grouping.addItem(label,mode)
        controls.addWidget(self.grouping);self.criteria={}
        for label,key in [(tr('Catégorie'),'category'),(tr('Taille en tenons'),'size'),(tr('Référence'),'reference')]:
            checkbox=QCheckBox(label);checkbox.setChecked(key in ('category','size'));checkbox.setAccessibleName(tr('Regrouper par ')+label);self.criteria[key]=checkbox;controls.addWidget(checkbox)
        self.colors=QCheckBox(tr('Séparer les couleurs'));controls.addWidget(self.colors)
        self.shared=QCheckBox(tr('Plusieurs références par tiroir'));self.shared.setToolTip(tr('Autorise plusieurs références dans un tiroir proposé. Les tiroirs demandés pour une même référence restent distincts.'));controls.addWidget(self.shared)
        self.quantities=QCheckBox(tr('Répartir les quantités restantes'));self.quantities.setChecked(bool(allocate_quantities) and not from_catalogue);self.quantities.setEnabled(not from_catalogue);controls.addWidget(self.quantities)
        self.reorganize=QCheckBox(tr('Réorganiser cette catégorie dans ce meuble'));controls.addWidget(self.reorganize);layout.addLayout(controls)
        self.scope_explanation=explanation=QLabel(tr('Par défaut : pièces sans emplacement et tiroirs vides sans nom. La réorganisation remplace les liens des tiroirs contenant uniquement cette catégorie. Les tiroirs mixtes, les autres meubles et toutes les quantités sont conservés.'));explanation.setWordWrap(True);layout.addWidget(explanation)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels([tr('Catégorie'),tr('Dimensions en tenons'),tr('Couleur'),tr('Références'),tr('Tiroir proposé'),tr('Aperçu'),tr('Quantité proposée'),tr('Nombre de tiroirs')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.ensurePolished()
        for column,width in enumerate((110,150,90,115,210,110,120,140)):
            self.table.setColumnWidth(column,max(width,self.table.fontMetrics().horizontalAdvance(self.table.horizontalHeaderItem(column).text())+28))
        for visual,column in enumerate((5,3,7,6,4,0,1,2)):self.table.horizontalHeader().moveSection(self.table.horizontalHeader().visualIndex(column),visual)
        self.table.horizontalHeader().setSortIndicator(-1,Qt.SortOrder.AscendingOrder)
        self.thumbs=PartThumbnails(self.table,db,getattr(parent,'engine',None),self.visible_thumbnail_rows,5,self) if getattr(parent,'engine',None) else None
        if self.thumbs:self.table.model().layoutChanged.connect(lambda *_:self.thumbs.reset())
        from .storage_preview import StorageProposalPreview
        self.proposal_preview=StorageProposalPreview(db,getattr(parent,'engine',None),self)
        self.proposal_preview.drawer_exchange_requested.connect(self.exchange_preview_drawers)
        self.proposal_preview.drawer_add_requested.connect(self.choose_preview_reference)
        self.splitter=QSplitter(Qt.Orientation.Horizontal);self.splitter.setChildrenCollapsible(False);self.splitter.addWidget(self.table);self.splitter.addWidget(self.proposal_preview);self.splitter.setSizes([800,560]);layout.addWidget(self.splitter,1)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        row=FlowLayout();prepare=QPushButton(tr('Préparer une proposition'));prepare.clicked.connect(self.rebuild);row.addWidget(prepare)
        self.combine=QPushButton(tr('Regrouper la sélection…'));self.combine.clicked.connect(self.combine_selection);self.combine.setToolTip(tr('Sélectionne les lignes avec Ctrl ou Maj, puis choisis leur tiroir commun. Active Plusieurs références par tiroir ou le regroupement libre.'));row.addWidget(self.combine)
        self.split_references=QPushButton(tr('Nombre de tiroirs par référence…'));self.split_references.clicked.connect(self.choose_drawer_counts);row.addWidget(self.split_references)
        self.apply_button=QPushButton(tr('Appliquer le rangement proposé'));self.apply_button.clicked.connect(self.apply);row.addWidget(self.apply_button)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
        self.category.currentIndexChanged.connect(self.rebuild);self.grouping.currentIndexChanged.connect(self.change_grouping);self.colors.toggled.connect(self.rebuild);self.reorganize.toggled.connect(self.rebuild)
        for checkbox in self.criteria.values():checkbox.toggled.connect(self.change_criteria)
        self.quantities.toggled.connect(self.rebuild);self.destination.currentIndexChanged.connect(self.rebuild)
        self.shared.toggled.connect(lambda:self.rebuild(preserve_targets=True))
        self.table.currentCellChanged.connect(self.group_selected);self.proposal_preview.drawer_selected.connect(self.drawer_selected);self.rebuild()

    def change_grouping(self,*_):
        mode=self.grouping.currentData()
        was_manual=not self.shared.isEnabled();self.shared.setEnabled(mode!='manual')
        if mode=='manual' or was_manual:self.shared.blockSignals(True);self.shared.setChecked(mode=='manual');self.shared.blockSignals(False)
        if mode!='reference':self.drawer_counts={}
        for key,checkbox in self.criteria.items():
            checkbox.setEnabled(mode!='manual')
            if mode!='manual':
                checkbox.blockSignals(True);checkbox.setChecked(key=='reference' if mode=='reference' else key in ('category','size'));checkbox.blockSignals(False)
        self.rebuild()

    def change_criteria(self,*_):
        if not self.criteria['reference'].isChecked():self.drawer_counts={}
        if self.grouping.currentData()=='reference':
            self.grouping.blockSignals(True);self.grouping.setCurrentIndex(self.grouping.findData('size'));self.grouping.blockSignals(False)
        self.rebuild()

    def visible_thumbnail_rows(self):return [self.thumbnail_rows[row_index(self.table,row)] for row in range(self.table.rowCount())]

    def change_drawer_count(self,identity,value):
        if value==self.drawer_counts.get(identity,1):return
        if value>1:self.drawer_counts[identity]=value
        else:self.drawer_counts.pop(identity,None)
        self.changed_counts.add(identity);self.criteria['reference'].blockSignals(True);self.criteria['reference'].setChecked(True);self.criteria['reference'].blockSignals(False);self.count_timer.start()

    def remember_target(self,index):
        if not self.plan:return
        self.target_overrides[group_key(self.plan['groups'][index])]=self.targets[index].currentData()

    def target_changed(self,index,*_):
        self.remember_target(index);self.update_summary()

    def make_plan(self,criteria=None,share_drawers=None):
        return assignment.propose(self.db,self.destination.currentData(),self.category.currentData() or '',self.colors.isChecked(),self.reorganize.isChecked(),self.entries,self.from_catalogue,self.grouping.currentData(),self.quantities.isChecked(),criteria if criteria is not None else [key for key,checkbox in self.criteria.items() if checkbox.isChecked()],self.drawer_counts,self.category_order,self.shared.isChecked() if share_drawers is None else share_drawers)

    def rebuild(self,*_,preserve_targets=False,prepared_plan=None):
        self.count_timer.stop();changed=set(self.changed_counts);self.changed_counts.clear();preserve_targets=preserve_targets or bool(changed)
        previous=self.plan if preserve_targets else None;previous_targets=[target.currentData() for target in self.targets] if previous else []
        if not preserve_targets:self.target_overrides={}
        focused=next((identity for identity,spin in self.count_spins if spin.hasFocus()),None)
        vertical=self.table.verticalScrollBar().value();horizontal=self.table.horizontalScrollBar().value();header=self.table.horizontalHeader();sort_column=header.sortIndicatorSection();sort_order=header.sortIndicatorOrder()
        for target in self.targets:target.blockSignals(True);target.hide()
        for identity,spin in self.count_spins:spin.blockSignals(True);spin.hide()
        self.count_spins=[];self.table.setSortingEnabled(False)
        self.wall_id=self.destination.currentData()
        self.reorganize.setText(tr('Réorganiser cette catégorie dans tous les meubles') if self.wall_id is None else tr('Réorganiser cette catégorie dans ce meuble'))
        self.scope_explanation.setText(tr('Par défaut : pièces sans emplacement et tiroirs vides sans nom. La réorganisation remplace uniquement les tiroirs contenant cette catégorie ; les tiroirs mixtes et le stock sont conservés.'))
        category=self.category.currentData() or '';self.reorganize.setEnabled(bool(category))
        if not category:self.reorganize.blockSignals(True);self.reorganize.setChecked(False);self.reorganize.blockSignals(False)
        self.category_order_button.setEnabled(self.grouping.currentData()!='manual')
        try:self.plan=prepared_plan if prepared_plan is not None else self.make_plan()
        except (ValueError,sqlite3.Error,OSError) as error:
            self.plan=None;self.thumbnail_rows=[];self.table.setRowCount(0);self.proposal_preview.set_proposal(None,[]);self.summary.setText(str(error));self.apply_button.setEnabled(False);self.combine.setEnabled(False);self.split_references.setEnabled(False)
            if self.thumbs:self.thumbs.reset()
            return
        self._storage_wall_ids={wall['id'] for wall in self.plan['preview']['walls']}
        if previous:
            proposed=arrange_targets(self.plan,previous,previous_targets,self.target_overrides,changed)
            for group,target in zip(self.plan['groups'],proposed):group['drawer_id']=target
        self.targets=[];self.table.blockSignals(True);self.table.setRowCount(0)
        def quantity(group):
            values=[assignment.group_quantities(self.plan,group).get(entry) for entry in group['entries']]
            return sum(values) if all(value is not None for value in values) else tr('À renseigner')
        def references(group):
            identities={identity for identity,color in group['entries']}
            return (group['references'][0] if len(identities)==1 else str(len(identities)))+(' ('+str(group['split_index']+1)+'/'+str(group['split_count'])+')' if group['split_count']>1 else '')
        fill_table(self.table,[(g['category'],assignment.dimensions_text(g['dimensions']) or (tr('Non indiquées') if 'size' in self.plan['criteria'] else '—'),g['color'],references(g),'',tr('3D / photo à charger'),quantity(g),g['split_count']) for g in self.plan['groups']],sortable=False)
        self.thumbnail_rows=[]
        for index,group in enumerate(self.plan['groups']):
            identity,color=group['entries'][0];self.thumbnail_rows.append(dict(self.plan['preview']['items'][identity],chosen_color=color));self.table.setRowHeight(index,72)
            self.table.item(index,3).setToolTip('\n'.join(group['references']))
            target=QComboBox();target.addItem(tr('Laisser sans emplacement'),None)
            for drawer in self.plan['available']:target.addItem(assignment.drawer_label(self.plan,drawer)+(' — '+drawer['name'] if drawer['name'] else ''),drawer['id'])
            target.setCurrentIndex(max(0,target.findData(group['drawer_id'])));self.table.setCellWidget(index,4,target);self.targets.append(target)
            cell=self.table.item(index,4);cell.setText(target.currentText());target.currentTextChanged.connect(lambda text,item=cell:item.setText(text))
            target.setToolTip(target.currentText());target.currentTextChanged.connect(target.setToolTip)
            target.currentIndexChanged.connect(lambda value,i=index:self.target_changed(i))
            target.activated.connect(lambda value,i=index:self.remember_target(i))
            identities={identity for identity,color in group['entries']}
            if len(identities)==1:
                identity=next(iter(identities));spin=QSpinBox();spin.setRange(1,1000);spin.setKeyboardTracking(False);spin.setValue(group['split_count']);spin.setEnabled(self.grouping.currentData()!='manual');spin.setAccessibleName(tr('Nombre de tiroirs')+' '+self.plan['preview']['items'][identity]['source']+' '+self.plan['preview']['items'][identity]['ref']);self.table.setCellWidget(index,7,spin);self.count_spins.append((identity,spin))
                spin.setToolTip(tr('Nombre total de tiroirs pour cette référence, par couleur si les couleurs sont séparées. Modifier une ligne actualise toutes les lignes de la référence et l’aperçu.'))
                spin.valueChanged.connect(lambda value,item=identity:self.change_drawer_count(item,value))
            else:self.table.item(index,7).setText('—');self.table.item(index,7).setToolTip(tr('Coche Référence pour régler le nombre de tiroirs de chaque pièce directement dans ce tableau.'))
        self.table.setSortingEnabled(True)
        if sort_column>=0:self.table.sortItems(sort_column,sort_order)
        self.table.blockSignals(False);self.combine.setEnabled(self.plan['shared_drawers'] and bool(self.plan['available']))
        self.split_references.setEnabled(self.grouping.currentData()!='manual' and bool(self.plan['groups']))
        if self.thumbs:self.thumbs.reset()
        self.reset_preview=not preserve_targets;self.update_summary()
        if preserve_targets:
            self.table.verticalScrollBar().setValue(vertical);self.table.horizontalScrollBar().setValue(horizontal)
            spin=next((spin for identity,spin in self.count_spins if identity==focused),None)
            if spin:spin.setFocus()

    def update_summary(self,*_):
        if not self.plan:return
        chosen=[w.currentData() for w in self.targets];assigned=[identity for identity in chosen if identity is not None]
        self.summary.setText(tf('{0} groupe(s), {1} tiroir(s) disponible(s), {2} groupe(s) à ranger, {3} sans tiroir. {4} référence(s) sans dimensions restent à ranger manuellement.',len(chosen),len(self.plan['available']),len(assigned),len(chosen)-len(assigned),len(self.plan['unknown'])))
        spaced=spaced_references(self.plan,chosen)
        if spaced:self.summary.setText(self.summary.text()+' '+tf('Tiroirs espacés pour {0} : les places voisines sont indisponibles ou des destinations ont été choisies manuellement.',', '.join(spaced)))
        try:assignment.validate_targets(self.plan,chosen)
        except ValueError as error:self.apply_button.setEnabled(False);self.summary.setText(self.summary.text()+' '+str(error))
        else:self.apply_button.setEnabled(True)
        self.proposal_preview.set_proposal(self.plan,chosen,reset=getattr(self,'reset_preview',False));self.reset_preview=False

    def group_selected(self,row,*_):
        if self.plan and len(self.targets)==len(self.plan['groups']):self.proposal_preview.show_group(row_index(self.table,row),[w.currentData() for w in self.targets])

    def exchange_preview_drawers(self,source,destination):
        if not self.plan or self.proposal_preview.closed or source==destination:return
        allowed={drawer['id'] for drawer in self.plan['available']}
        if source not in allowed or destination not in allowed:return
        origin=[index for index,target in enumerate(self.targets) if target.currentData()==source]
        other=[index for index,target in enumerate(self.targets) if target.currentData()==destination]
        if not origin:return
        cells={row_index(self.table,row):self.table.item(row,4) for row in range(self.table.rowCount())}
        blocked=self.table.blockSignals(True)
        for indices,target in ((origin,destination),(other,source)):
            for index in indices:
                combo=self.targets[index];combo.blockSignals(True);combo.setCurrentIndex(combo.findData(target));combo.blockSignals(False)
                cells[index].setText(combo.currentText());combo.setToolTip(combo.currentText());self.remember_target(index)
        self.table.blockSignals(blocked)
        self.update_summary();self.proposal_preview.choose_drawer(destination);self.proposal_preview.tabs.setCurrentIndex(0)

    def drawer_selected(self,identity):
        indices=[row for row in range(self.table.rowCount()) if self.targets[row_index(self.table,row)].currentData()==identity]
        horizontal=self.table.horizontalScrollBar().value()
        self.table.blockSignals(True);self.table.clearSelection()
        for index in indices:self.table.selectionModel().select(self.table.model().index(index,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        if indices:self.table.scrollToItem(self.table.item(indices[0],0))
        self.table.horizontalScrollBar().setValue(horizontal)
        self.table.blockSignals(False)

    def choose_preview_reference(self,identity):
        if self.count_timer.isActive():self.rebuild(preserve_targets=True)
        if not self.plan or self.proposal_preview.closed or identity not in {drawer['id'] for drawer in self.plan['available']}:return
        revision=self.proposal_preview.revision
        try:plan=self.make_plan(criteria=sorted(set(self.plan['criteria'])|{'reference'}),share_drawers=True)
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Rangement'),str(error));return
        if plan['fingerprint']!=self.plan['fingerprint']:
            QMessageBox.warning(self,tr('Rangement'),tr('Le stock ou le rangement a changé. Prépare une nouvelle proposition.'));return
        old={(entry,group['split_index']):target.currentData() for group,target in zip(self.plan['groups'],self.targets) for entry in group['entries']}
        targets=[old.get((group['entries'][0],group['split_index'])) for group in plan['groups']]
        from .storage_proposal_picker import ProposalReferencePicker
        from .windows import show_window
        dialog=ProposalReferencePicker(self.db,plan,targets,identity,getattr(self.parent(),'engine',None),self)
        def accepted(result):
            if result!=QDialog.DialogCode.Accepted or self.proposal_preview.closed:return
            if revision!=self.proposal_preview.revision:
                QMessageBox.warning(self,tr('Rangement'),tr('La proposition a changé. Rouvre le choix des références depuis le tiroir.'));return
            index=dialog.selected_index
            if index is None:return
            targets[index]=identity
            for group,target in zip(plan['groups'],targets):group['drawer_id']=target
            self.shared.blockSignals(True);self.shared.setChecked(True);self.shared.blockSignals(False)
            if self.grouping.currentData()!='manual':self.criteria['reference'].blockSignals(True);self.criteria['reference'].setChecked(True);self.criteria['reference'].blockSignals(False)
            self.target_overrides={group_key(group):target for group,target in zip(plan['groups'],targets)}
            self.rebuild(preserve_targets=True,prepared_plan=plan);self.proposal_preview.choose_drawer(identity);self.proposal_preview.tabs.setCurrentIndex(0)
        show_window(dialog,self,accepted);return dialog

    def combine_selection(self):
        if not self.plan or not self.plan.get('shared_drawers'):return
        indices=sorted(row_index(self.table,index.row()) for index in self.table.selectionModel().selectedRows())
        if not indices:
            QMessageBox.information(self,tr('Rangement'),tr('Sélectionne les références à réunir avec Ctrl ou Maj.'));return
        labels=[assignment.drawer_label(self.plan,drawer) for drawer in self.plan['available']]
        text,ok=QInputDialog.getItem(self,tr('Tiroir commun'),tr('Choisis le tiroir pour les références sélectionnées :'),labels,0,False)
        if not ok:return
        identity=self.plan['available'][labels.index(text)]['id']
        for index in indices:self.targets[index].blockSignals(True);self.targets[index].setCurrentIndex(self.targets[index].findData(identity));self.targets[index].blockSignals(False);self.target_overrides[group_key(self.plan['groups'][index])]=identity
        self.update_summary();self.proposal_preview.choose_drawer(identity,emit=False);self.proposal_preview.tabs.setCurrentIndex(0)

    def choose_drawer_counts(self):
        if not self.plan:return
        ids={identity for group in self.plan['groups'] for identity,color in group['entries']};parts=[self.plan['preview']['items'][identity] for identity in sorted(ids,key=lambda identity:(self.plan['preview']['items'][identity]['source'],self.plan['preview']['items'][identity]['ref']))]
        quantities={}
        for (identity,color),quantity in self.plan['quantities'].items():
            if quantity is not None:quantities[identity]=quantities.get(identity,0)+quantity
        dialog=ReferenceDrawerCountsDialog(self.db,parts,self.drawer_counts,quantities,getattr(self.parent(),'engine',None),self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        counts=dialog.counts();self.changed_counts.update(identity for identity in set(counts)|set(self.drawer_counts) if counts.get(identity,1)!=self.drawer_counts.get(identity,1));self.drawer_counts=counts
        if self.grouping.currentData()=='manual':self.grouping.blockSignals(True);self.grouping.setCurrentIndex(self.grouping.findData('size'));self.grouping.blockSignals(False)
        self.criteria['reference'].blockSignals(True);self.criteria['reference'].setChecked(True);self.criteria['reference'].blockSignals(False)
        self.rebuild(preserve_targets=True)

    def choose_category_order(self):
        if self.grouping.currentData()=='manual':return
        from . import storage_order
        from .storage_order_dialog import StorageCategoryOrderDialog
        from .windows import show_window
        criteria=['category','size']+(['reference'] if self.criteria['reference'].isChecked() else [])
        try:
            basis=assignment.propose(self.db,self.destination.currentData(),self.category.currentData() if self.reorganize.isChecked() else '',self.colors.isChecked(),self.reorganize.isChecked(),self.entries,self.from_catalogue,'size',self.quantities.isChecked(),criteria,self.drawer_counts,self.category_order)
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Rangement impossible'),str(error));return
        rows=storage_order.category_rows(basis)
        if not rows:QMessageBox.information(self,tr('Rangement'),tr('Aucune catégorie à ordonner dans cette sélection de pièces.'));return
        dialog=StorageCategoryOrderDialog(self.db,rows,self.category_order,self)
        def accepted():
            self.category_order=dialog.order()
            self.grouping.blockSignals(True);self.grouping.setCurrentIndex(self.grouping.findData('size'));self.grouping.blockSignals(False)
            for key,checkbox in self.criteria.items():
                checkbox.setEnabled(True)
                if key in ('category','size'):checkbox.blockSignals(True);checkbox.setChecked(True);checkbox.blockSignals(False)
            self.rebuild()
        dialog.accepted.connect(accepted);self.finished.connect(dialog.reject);show_window(dialog,self,refresh_counts=False);return dialog

    def refresh_storage_visuals(self):
        if self.thumbs:self.thumbs.reset()
        self.proposal_preview.invalidate()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        compact=self.width()<1050 and self.height()<650
        if hasattr(self,'destination_hint'):self.destination_hint.setVisible(not compact)
        if hasattr(self,'scope_explanation'):self.scope_explanation.setVisible(not compact)

    def done(self,result):
        self.count_timer.stop()
        if self.thumbs:self.thumbs.stop()
        from .collection_dialogs import close_children
        close_children(self)
        self.proposal_preview.stop();super().done(result)

    def apply(self):
        if self.count_timer.isActive():self.rebuild(preserve_targets=True)
        if not self.plan:return
        try:count,references=assignment.apply_proposal(self.db,self.plan,[w.currentData() for w in self.targets])
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Rangement impossible'),str(error));return
        self.changed();QMessageBox.information(self,tr('Rangement enregistré'),tf('{0} tiroir(s) renseigné(s), {1} référence(s) associée(s). Les quantités du stock sont conservées.',count,references));self.accept()
