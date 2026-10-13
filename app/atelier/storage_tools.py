"""Stock tables that can be dragged onto drawers, and a size-based preview."""
import json
import sqlite3
import uuid

from PySide6.QtCore import Qt,QMimeData,QTimer,Signal,QItemSelectionModel
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QCheckBox,
    QTableWidget,QPushButton,QAbstractItemView,QHeaderView,QMessageBox,QFormLayout,QSplitter,QInputDialog)
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
        self.table=StorageDragTable(db,lambda:self.rows,lambda:None,0,7)
        self.table.drag_catalogue=lambda:self.catalogue_mode()
        self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Couleur'),tr('Pièce'),tr('Catégorie'),tr('Stock en vrac'),tr('Aperçu')])
        for column,width in enumerate((70,90,80,210,140,100,130)):self.table.setColumnWidth(column,width)
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
        blocked=self.target_wall.blockSignals(True);self.target_wall.setCurrentIndex(max(0,self.target_wall.findData(identity)));self.target_wall.blockSignals(blocked)
    def reload_target_walls(self,preferred=None):
        current=preferred if preferred is not None else self.target_wall.currentData();blocked=self.target_wall.blockSignals(True);self.target_wall.clear()
        for wall in walls.walls(self.db):self.target_wall.addItem(wall['name'],wall['id'])
        self.target_wall.setCurrentIndex(max(0,self.target_wall.findData(current)));self.target_wall.setEnabled(self.target_wall.count()>0);self.target_wall.blockSignals(blocked)

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
    def __init__(self,db,wall_id,parent=None,changed=lambda:None,entries=None,from_catalogue=False,category=''):
        super().__init__(parent);self.db=db;self.wall_id=wall_id;self.changed=changed;self.plan=None;self.targets=[]
        self.entries=list(entries) if entries is not None else None;self.from_catalogue=from_catalogue
        self.setWindowTitle(tr('Ranger par catégorie et taille en tenons'));self.setMinimumSize(800,480)
        available=self.screen().availableGeometry();self.resize(min(1360,max(800,available.width()-32)),min(820,max(480,available.height()-56)))
        layout=QVBoxLayout(self)
        hint=QLabel(tr('Choisis une catégorie, par exemple Bricks. Les dimensions écrites dans les noms des pièces regroupent les références par taille, de la plus petite à la plus grande. Les tiroirs sont remplis depuis le haut, de gauche à droite. Les couleurs restent ensemble sauf si tu les sépares. Ajuste les tiroirs proposés avant d’appliquer.'));hint.setWordWrap(True);layout.addWidget(hint)
        if self.entries is not None:
            scope_hint=QLabel(tr('Cette proposition utilise la sélection de Pièces à ranger, ou les références affichées si aucune ligne n’est sélectionnée.'));scope_hint.setWordWrap(True);layout.addWidget(scope_hint)
        controls=FlowLayout();self.category=QComboBox();self.category.setMaximumWidth(280);self.category.addItem(tr('Toutes les catégories'),'')
        for row in db.rows("SELECT DISTINCT category FROM (SELECT i.category FROM stock s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 AND i.kind IN ('part','minifig') UNION SELECT i.category FROM storage_contents p JOIN storage_drawers d ON d.id=p.drawer_id JOIN items i ON i.id=p.item_id WHERE d.wall_id=?) WHERE category<>'' ORDER BY category",(wall_id,)):self.category.addItem(row['category'],row['category'])
        if self.from_catalogue:
            categories={self.category.itemData(index) for index in range(self.category.count())}
            for identity,color in self.entries or []:
                item=db.get_item(identity)
                if item and item['category'] and item['category'] not in categories:self.category.addItem(item['category'],item['category']);categories.add(item['category'])
        self.category.setCurrentIndex(max(0,self.category.findData(category)))
        controls.addWidget(self.category);self.grouping=QComboBox();self.grouping.setAccessibleName(tr('Mode de rangement'))
        for label,mode in [(tr('Par catégorie et taille'),'size'),(tr('Une référence par tiroir'),'reference'),(tr('Regroupement libre de références'),'manual')]:self.grouping.addItem(label,mode)
        controls.addWidget(self.grouping);self.colors=QCheckBox(tr('Séparer les couleurs'));controls.addWidget(self.colors)
        self.reorganize=QCheckBox(tr('Réorganiser cette catégorie dans ce meuble'));controls.addWidget(self.reorganize);layout.addLayout(controls)
        explanation=QLabel(tr('Par défaut : pièces sans emplacement et tiroirs vides sans nom. La réorganisation remplace les liens des tiroirs contenant uniquement cette catégorie. Les tiroirs mixtes, les autres meubles et toutes les quantités sont conservés.'));explanation.setWordWrap(True);layout.addWidget(explanation)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels([tr('Catégorie'),tr('Dimensions en tenons'),tr('Couleur'),tr('Références'),tr('Tiroir proposé')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.ensurePolished()
        for column,width in enumerate((110,170,90,135,230)):
            self.table.setColumnWidth(column,max(width,self.table.fontMetrics().horizontalAdvance(self.table.horizontalHeaderItem(column).text())+28))
        from .storage_preview import StorageProposalPreview
        self.proposal_preview=StorageProposalPreview(db,getattr(parent,'engine',None),self)
        self.splitter=QSplitter(Qt.Orientation.Horizontal);self.splitter.setChildrenCollapsible(False);self.splitter.addWidget(self.table);self.splitter.addWidget(self.proposal_preview);self.splitter.setSizes([800,560]);layout.addWidget(self.splitter,1)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        row=FlowLayout();prepare=QPushButton(tr('Préparer une proposition'));prepare.clicked.connect(self.rebuild);row.addWidget(prepare)
        self.combine=QPushButton(tr('Regrouper la sélection…'));self.combine.clicked.connect(self.combine_selection);self.combine.setToolTip(tr('Choisis Regroupement libre de références, puis sélectionne les lignes avec Ctrl ou Maj.'));row.addWidget(self.combine)
        self.apply_button=QPushButton(tr('Appliquer le rangement proposé'));self.apply_button.clicked.connect(self.apply);row.addWidget(self.apply_button)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
        self.category.currentIndexChanged.connect(self.rebuild);self.grouping.currentIndexChanged.connect(self.rebuild);self.colors.toggled.connect(self.rebuild);self.reorganize.toggled.connect(self.rebuild)
        self.table.currentCellChanged.connect(self.group_selected);self.proposal_preview.drawer_selected.connect(self.drawer_selected);self.rebuild()

    def rebuild(self,*_):
        category=self.category.currentData() or '';self.reorganize.setEnabled(bool(category))
        if not category:self.reorganize.blockSignals(True);self.reorganize.setChecked(False);self.reorganize.blockSignals(False)
        try:self.plan=assignment.propose(self.db,self.wall_id,category,self.colors.isChecked(),self.reorganize.isChecked(),self.entries,self.from_catalogue,self.grouping.currentData())
        except (ValueError,sqlite3.Error,OSError) as error:
            self.plan=None;self.table.setRowCount(0);self.proposal_preview.set_proposal(None,[]);self.summary.setText(str(error));self.apply_button.setEnabled(False);self.combine.setEnabled(False);return
        self.targets=[];self.table.blockSignals(True)
        fill_table(self.table,[(g['category'],assignment.dimensions_text(g['dimensions']) or tr('Non indiquées'),g['color'],str(len(g['entries'])) if self.grouping.currentData()=='size' else g['references'][0],'') for g in self.plan['groups']],sortable=False)
        for index,group in enumerate(self.plan['groups']):
            self.table.item(index,3).setToolTip('\n'.join(group['references']))
            target=QComboBox();target.addItem(tr('Laisser sans emplacement'),None)
            for drawer in self.plan['available']:target.addItem(walls.address(drawer)+(' — '+drawer['name'] if drawer['name'] else ''),drawer['id'])
            target.setCurrentIndex(max(0,target.findData(group['drawer_id'])));self.table.setCellWidget(index,4,target);self.targets.append(target)
            target.currentIndexChanged.connect(self.update_summary)
        self.table.blockSignals(False);self.combine.setEnabled(self.grouping.currentData()=='manual' and bool(self.plan['available']))
        self.reset_preview=True;self.update_summary()

    def update_summary(self,*_):
        if not self.plan:return
        chosen=[w.currentData() for w in self.targets];assigned=[identity for identity in chosen if identity is not None]
        self.summary.setText(tf('{0} groupe(s), {1} tiroir(s) disponible(s), {2} groupe(s) à ranger, {3} sans tiroir. {4} référence(s) sans dimensions restent à ranger manuellement.',len(chosen),len(self.plan['available']),len(assigned),len(chosen)-len(assigned),len(self.plan['unknown'])))
        self.apply_button.setEnabled(bool(assigned) and (self.plan.get('shared_drawers') or len(assigned)==len(set(assigned))))
        self.proposal_preview.set_proposal(self.plan,chosen,reset=getattr(self,'reset_preview',False));self.reset_preview=False

    def group_selected(self,row,*_):
        if self.plan and len(self.targets)==len(self.plan['groups']):self.proposal_preview.show_group(row,[w.currentData() for w in self.targets])

    def drawer_selected(self,identity):
        indices=[i for i,w in enumerate(self.targets) if w.currentData()==identity]
        self.table.blockSignals(True);self.table.clearSelection()
        for index in indices:self.table.selectionModel().select(self.table.model().index(index,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        if indices:self.table.scrollToItem(self.table.item(indices[0],0))
        self.table.blockSignals(False)

    def combine_selection(self):
        if not self.plan or not self.plan.get('shared_drawers'):return
        indices=sorted(index.row() for index in self.table.selectionModel().selectedRows())
        if not indices:
            QMessageBox.information(self,tr('Rangement'),tr('Sélectionne les références à réunir avec Ctrl ou Maj.'));return
        labels=[walls.address(drawer) for drawer in self.plan['available']]
        text,ok=QInputDialog.getItem(self,tr('Tiroir commun'),tr('Choisis le tiroir pour les références sélectionnées :'),labels,0,False)
        if not ok:return
        identity=self.plan['available'][labels.index(text)]['id']
        for index in indices:self.targets[index].blockSignals(True);self.targets[index].setCurrentIndex(self.targets[index].findData(identity));self.targets[index].blockSignals(False)
        self.update_summary();self.proposal_preview.choose_drawer(identity,emit=False);self.proposal_preview.tabs.setCurrentIndex(0)

    def refresh_storage_visuals(self):self.proposal_preview.invalidate()

    def done(self,result):
        self.proposal_preview.stop();super().done(result)

    def apply(self):
        if not self.plan:return
        try:count,references=assignment.apply_proposal(self.db,self.plan,[w.currentData() for w in self.targets])
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Rangement impossible'),str(error));return
        self.changed();QMessageBox.information(self,tr('Rangement enregistré'),tf('{0} tiroir(s) renseigné(s), {1} référence(s) associée(s). Les quantités du stock sont conservées.',count,references));self.accept()
