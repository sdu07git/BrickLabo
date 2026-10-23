"""Construction projects, their requirements, and explicit loose-stock reservations."""
import sqlite3
from shiboken6 import isValid
from PySide6.QtCore import Qt,QTimer,Signal,QEvent
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QLineEdit,QComboBox,QSpinBox,QCheckBox,QDialogButtonBox,QTableWidget,
    QHeaderView,QAbstractItemView,QSplitter,QMessageBox,QInputDialog,QMenu,QScrollArea)
from .i18n import tr,tf
from .ui_common import FlowLayout
from .result_tables import fill_table,row_index
from .thumbnails import PartThumbnails
from .windows import show_window
from . import projects


class ReferencePicker(QDialog):
    def __init__(self, db, kind, parent=None):
        super().__init__(parent)
        self.db, self.kind, self.rows, self.chosen = db, kind, [], None
        self.setWindowTitle(tr('Choisir une référence du catalogue')); self.resize(800, 470)
        layout = QVBoxLayout(self)
        top = QHBoxLayout(); self.query = QLineEdit(); self.query.setPlaceholderText(tr('Référence, nom ou catégorie')); top.addWidget(self.query, 1)
        self.source = QComboBox()
        for label, value in [(tr('Tous les catalogues'), None), ('Rebrickable','RB'), ('BrickLink','BL'), ('BrickArchitect','BA'), (tr('Briques Alternatives'),'ALT')]: self.source.addItem(label, value)
        top.addWidget(self.source); layout.addLayout(top)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Nom'),tr('Catégorie')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((75,120,390,180)): self.table.setColumnWidth(column,width)
        layout.addWidget(self.table,1); self.count = QLabel(); layout.addWidget(self.count)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.choose); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.table.itemDoubleClicked.connect(self.choose)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(150); self.timer.timeout.connect(self.reload)
        self.query.textChanged.connect(lambda *_: self.timer.start()); self.source.currentIndexChanged.connect(self.reload)
        self.reload()

    def reload(self,*_):
        self.rows,total,_,_ = self.db.query(source=self.source.currentData(),kind=self.kind,search=self.query.text(),size=200)
        fill_table(self.table,[(row['source'],row['ref'],row['name'],row['category']) for row in self.rows])
        self.count.setText(tf('{0} résultat(s). Affine la recherche si la liste est trop longue.',total))
        if self.rows: self.table.selectRow(0)

    def choose(self,*_):
        index = row_index(self.table)
        if 0 <= index < len(self.rows): self.chosen = dict(self.rows[index]); self.accept()


def color_options(db, item):
    options = {str(row['color']): str(row['color']) for row in db.rows('SELECT color FROM stock WHERE item_id=? AND quantity>0 ORDER BY color',(item['id'],))}
    for color in db.available_colors(item): options[str(color['id'])] = color['name'] + ' (' + str(color['id']) + ')'
    from .alternative_catalogue import original
    item=original(item)
    if item['source']=='RB':
        for row in db.rows('SELECT id,name FROM colors ORDER BY name'): options.setdefault(str(row['id']), row['name']+' ('+str(row['id'])+')')
    elif item['source']=='BL':
        for key, color in db.setting('bl_colors',{}).items(): options.setdefault(str(key),color.get('name',str(key))+' ('+str(key)+')')
    return sorted(options.items(),key=lambda value:value[1])


class NewProjectDialog(QDialog):
    def __init__(self, panel, item=None, copies=1, exclude_minifigs=False, context_note='', ignore_colors=False, include_set_stock=False):
        super().__init__(panel); self.panel, self.db, self.item = panel, panel.db, item
        self.setWindowTitle(tr('Nouveau projet de construction')); self.resize(700,440);self.picker=None;self.closed=False
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize);scroll.setWidget(body);outer.addWidget(scroll,1)
        form = QFormLayout(); layout.addLayout(form)
        self.kind = QComboBox(); self.kind.addItem(tr('Set du catalogue'),'set'); self.kind.addItem(tr('Construction personnelle'),'custom')
        self.name = QLineEdit(); self.set_name = QLabel(); self.set_name.setWordWrap(True)
        self.choose = QPushButton(tr('Choisir un set…')); self.choose.clicked.connect(self.choose_set)
        self.copies = QSpinBox(); self.copies.setRange(1,10000);self.copies.setValue(copies)
        self.ignore_colors=QCheckBox(tr('Ignorer les couleurs'));self.ignore_colors.setObjectName('new_project_ignore_colors');self.ignore_colors.setChecked(ignore_colors)
        self.ignore_colors.setToolTip(tr('Utiliser toutes les couleurs de chaque référence, en conservant les couleurs prévues pour pouvoir revenir au mode officiel.'))
        self.include_set_stock=QCheckBox(tr('Compter aussi les pièces de mes sets possédés'));self.include_set_stock.setObjectName('new_project_include_set_stock');self.include_set_stock.setChecked(include_set_stock)
        self.include_set_stock.setToolTip(tr('Ajouter au calcul les inventaires de tous les sets de Mon stock set, sans les transférer dans le vrac. Les réservations et prélèvements utilisent le vrac.'))
        self.spares = QCheckBox(tr('Inclure les pièces supplémentaires'))
        self.exclude_minifigs = QCheckBox(tr('Exclure les minifigurines'));self.exclude_minifigs.setChecked(exclude_minifigs)
        self.alternatives=QCheckBox(tr('Autoriser les briques alternatives équivalentes'));self.alternatives.setChecked(self.db.setting('build_allow_alternatives',False));self.alternatives.setToolTip(tr('Utiliser les équivalences d’origine connue du vrac libre, en conservant les références et couleurs physiques dans le projet.'))
        form.addRow(tr('Type de projet'),self.kind); form.addRow(tr('Nom'),self.name); form.addRow(self.set_name,self.choose)
        form.addRow(tr('Exemplaires'),self.copies); form.addRow(self.spares);form.addRow(self.exclude_minifigs);form.addRow(self.ignore_colors);form.addRow(self.include_set_stock);form.addRow(self.alternatives)
        from .set_picker import SetImagePreview
        self.preview=SetImagePreview(panel.engine,self);layout.addWidget(self.preview,1)
        if context_note:
            context=QLabel(context_note);context.setWordWrap(True);layout.addWidget(context)
        note = QLabel(tr('Le projet conserve une copie des besoins. Sa création ne modifie pas le stock et ne réserve aucune pièce.')); note.setWordWrap(True); layout.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save); self.buttons.rejected.connect(self.reject); outer.addWidget(self.buttons)
        self.kind.currentIndexChanged.connect(self.update_kind); self.update_kind()
        if item: self.set_item(item)

    def update_kind(self,*_):
        is_set = self.kind.currentData()=='set'
        for widget in (self.choose,self.set_name,self.copies,self.spares,self.exclude_minifigs,self.alternatives): widget.setEnabled(is_set)
        self.preview.setVisible(is_set)

    def set_item(self,item):
        self.item = dict(item); self.set_name.setText(item['source']+' '+item['ref']+' · '+item['name'])
        self.name.setText(item['ref']+' · '+item['name']);self.preview.set_item(item)

    def choose_set(self):
        if self.closed or not isValid(self):return
        if self.picker is not None and isValid(self.picker) and not self.picker.closed:
            self.picker.show();self.picker.raise_();self.picker.activateWindow();return
        self.picker=None
        from .set_picker import SetPicker
        picker=SetPicker(self.db,self.panel.engine,self);self.picker=picker
        def forget(*_):
            if self.picker is picker:self.picker=None
        picker.destroyed.connect(forget)
        def chosen(result):
            forget()
            if not self.closed and isValid(self) and result==QDialog.DialogCode.Accepted and picker.chosen:self.set_item(picker.chosen)
        show_window(picker,self,chosen,refresh_counts=False)

    def save(self):
        try:
            if self.kind.currentData()=='set':
                if self.item is None: raise ValueError(tr('Choisis un set.'))
                identity = projects.from_set(self.db,self.item['id'],self.copies.value(),self.name.text(),self.spares.isChecked(),self.exclude_minifigs.isChecked(),self.alternatives.isChecked(),ignore_colors=self.ignore_colors.isChecked(),include_set_stock=self.include_set_stock.isChecked())
            else: identity = projects.create(self.db,self.name.text(),ignore_colors=self.ignore_colors.isChecked(),include_set_stock=self.include_set_stock.isChecked())
        except (ValueError,sqlite3.Error) as error: QMessageBox.warning(self,tr('Projet'),str(error)); return
        self.panel.refresh(identity); self.panel.changed.emit(); self.accept()


    def done(self,result):
        if self.closed or not isValid(self):return
        self.closed=True;self.preview.stop()
        picker,self.picker=self.picker,None
        if picker is not None and isValid(picker):picker.reject()
        super().done(result)


class ProjectsPanel(QWidget):
    changed = Signal()
    selected = Signal(object)
    def __init__(self, db, engine=None, parent=None):
        super().__init__(parent); self.db,self.engine,self.rows,self.parts,self.project_id = db,engine,[],[],None
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        actions = FlowLayout()
        for label, callback in [(tr('Nouveau projet…'),self.new_project),(tr('Actualiser'),self.refresh)]:
            button = QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
        self.view_set=QPushButton(tr('Voir le set'));self.view_set.clicked.connect(self.open_project);actions.addWidget(self.view_set)
        self.manage=QPushButton(tr('Gérer le projet'));menu=QMenu(self.manage)
        menu.addAction(tr('Affecter des sets possédés…'),self.allocate_sets);menu.addAction(tr('Importer un inventaire MOC…'),self.import_moc);menu.addAction(tr('Liste d’achats des projets…'),self.shopping);menu.addAction(tr('Renommer le projet…'),self.rename);menu.addAction(tr('Supprimer le projet…'),self.delete);self.manage.setMenu(menu);actions.addWidget(self.manage)
        self.pick_button=QPushButton(tr('Liste de prélèvement…'));self.pick_button.clicked.connect(self.pick_list);actions.addWidget(self.pick_button)
        self.status = QComboBox()
        for key,label in projects.STATES.items(): self.status.addItem(tr(label),key)
        self.status.activated.connect(self.change_status); actions.addWidget(self.status); layout.addLayout(actions)
        split = QSplitter(Qt.Orientation.Vertical); layout.addWidget(split,1)
        self.table = QTableWidget(0,6); self.table.setHorizontalHeaderLabels([tr('Projet'),tr('État'),tr('Set'),tr('Nécessaire'),tr('Réservée'),tr('Manquante')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column,width in enumerate((230,115,85,100,100,100)): self.table.setColumnWidth(column,width)
        self.table.horizontalHeader().moveSection(2,5)
        self.table.setMinimumHeight(90); split.addWidget(self.table)
        detail = QWidget();self.detail_body=detail;detail.installEventFilter(self);box = QVBoxLayout(detail);box.setContentsMargins(0,4,0,0)
        self.summary = QLabel(); self.summary.setWordWrap(True); box.addWidget(self.summary)
        self.ignore_colors=QCheckBox(tr('Ignorer les couleurs'));self.ignore_colors.setObjectName('project_ignore_colors');self.ignore_colors.setToolTip(tr('Ce choix est enregistré pour le projet sélectionné. Les réservations suivent les couleurs réelles du stock.'));self.ignore_colors.toggled.connect(self.change_colors);box.addWidget(self.ignore_colors)
        self.include_set_stock=QCheckBox(tr('Compter aussi les pièces de mes sets possédés'));self.include_set_stock.setObjectName('project_include_set_stock');self.include_set_stock.setToolTip(tr('Ajouter au calcul les inventaires de tous les sets de Mon stock set, sans les transférer dans le vrac. Les réservations et prélèvements utilisent le vrac.'));self.include_set_stock.toggled.connect(self.change_stock);box.addWidget(self.include_set_stock)
        self.stock_warning=QLabel();self.stock_warning.setWordWrap(True);self.stock_warning.hide();box.addWidget(self.stock_warning)
        self.detail = QTableWidget(0,11); self.detail.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Catégorie'),tr('Couleur'),tr('Nécessaire'),tr('Réservée'),tr('Libre en vrac'),tr('Manquante'),tr('Aperçu'),tr('Apport des sets')])
        self.detail.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.detail.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.detail.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.detail.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column,width in enumerate((60,90,230,150,85,100,100,115,100,130,115)): self.detail.setColumnWidth(column,width)
        self.detail.horizontalHeaderItem(10).setToolTip(tr('Pièces des sets possédés utilisées pour compléter le besoin après le vrac libre et les réservations de ce projet.'))
        header = self.detail.horizontalHeader()
        for position,column in enumerate((0,1,4,5,6,7,10,8,2,3,9)):
            header.moveSection(header.visualIndex(column),position)
        self.detail.setMinimumHeight(120); box.addWidget(self.detail,1)
        self.thumbnails = PartThumbnails(self.detail,db,engine,self.visible_parts,9,self) if engine else None
        controls = FlowLayout()
        self.part_button=QPushButton(tr('Pièces du projet'));self.part_menu=QMenu(self.part_button);self.part_actions=[]
        for label, callback in [(tr('Ajouter une pièce…'),self.add_part),(tr('Quantité nécessaire…'),self.edit_required),(tr('Retirer les pièces sélectionnées'),self.remove_parts),(tr('Réserver la sélection'),self.reserve_selected),(tr('Régler la réservation…'),self.edit_reserved)]:
            self.part_actions.append(self.part_menu.addAction(label,callback))
        self.part_button.setMenu(self.part_menu);self.part_menu.aboutToShow.connect(self.update_part_actions);controls.addWidget(self.part_button)
        self.reserve_button = QPushButton(tr('Réserver le vrac disponible'))
        self.reserve_button.clicked.connect(self.reserve_all); controls.addWidget(self.reserve_button)
        self.release_button = QPushButton(tr('Libérer les réservations'))
        self.release_button.clicked.connect(self.release); controls.addWidget(self.release_button)
        box.addLayout(controls)
        note = QLabel(tr('Le calcul utilise le vrac libre et, si la case est cochée, les pièces de tous les sets possédés. Affecter des sets possédés permet de choisir des exemplaires à démonter et de réserver leur inventaire pour ce projet. Les réservations et prélèvements utilisent uniquement le vrac. Un projet terminé garde ses réservations jusqu’à leur libération.')); note.setWordWrap(True); box.addWidget(note)
        self.detail_scroll=QScrollArea();self.detail_scroll.setWidgetResizable(True);self.detail_scroll.setWidget(detail);self.detail_scroll.setMinimumHeight(150)
        split.addWidget(self.detail_scroll);split.setSizes([150,450]);split.setChildrenCollapsible(False)
        self.table.itemDoubleClicked.connect(self.open_project);self.table.itemSelectionChanged.connect(self.choose_project); self.detail.itemSelectionChanged.connect(self.select_part); self.detail.itemDoubleClicked.connect(self.open_part)
        if self.thumbnails:self.detail.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset())
        self.refresh()

    def allocate_sets(self):
        if self.project_id is None:return
        from .collection_extensions_ui import SetAllocationDialog
        return show_window(SetAllocationDialog(self.db,self.project_id,self.engine,self),self,lambda *_:(self.refresh(),self.changed.emit()))

    def import_moc(self):
        from .collection_extensions_ui import MOCImportDialog
        return show_window(MOCImportDialog(self.db,self,lambda identity:(self.refresh(identity),self.changed.emit())),self)

    def shopping(self):
        from .collection_extensions_ui import ShoppingDialog
        return show_window(ShoppingDialog(self.db,self),self)

    def refresh(self, preferred=None):
        self._dirty=False
        if type(preferred) is not int: preferred = self.project_id
        self.rows = projects.list_projects(self.db)
        self.table.blockSignals(True)
        fill_table(self.table,[(row['name'],tr(projects.STATES[row['status']]),row['set_ref'],row['required'],row['reserved'],row['missing']) for row in self.rows])
        self.table.blockSignals(True)
        index = next((n for n,row in enumerate(self.rows) if row['id']==preferred),0)
        if self.rows:self.table.selectRow(next(row for row in range(self.table.rowCount()) if row_index(self.table,row)==index))
        self.table.blockSignals(False); self.choose_project()

    def invalidate(self):
        self._dirty=True
        if self.isVisible():self.refresh()

    def showEvent(self,event):
        super().showEvent(event)
        if getattr(self,'_dirty',False):self.refresh()

    def choose_project(self):
        index = row_index(self.table)
        self.project_id = self.rows[index]['id'] if 0<=index<len(self.rows) else None
        self.ignore_colors.blockSignals(True);self.ignore_colors.setEnabled(self.project_id is not None);self.ignore_colors.setChecked(bool(self.rows[index]['ignore_colors']) if self.project_id is not None else False);self.ignore_colors.blockSignals(False)
        self.include_set_stock.blockSignals(True);self.include_set_stock.setEnabled(self.project_id is not None);self.include_set_stock.setChecked(bool(self.rows[index]['include_set_stock']) if self.project_id is not None else False);self.include_set_stock.blockSignals(False)
        warnings=self.rows[index]['set_stock_warnings'] if self.project_id is not None else []
        self.stock_warning.setText('\n'.join(warnings));self.stock_warning.setVisible(bool(warnings))
        self.parts = projects.detail(self.db,self.project_id) if self.project_id is not None else []
        fill_table(self.detail,[(row['source'],row['ref'],row['name'],row['category'],tf('{} (ignorée)',row['chosen_color'] or tr('Non précisée')) if row.get('ignore_colors') else row['chosen_color'] or tr('Non précisée'),row['required'],row['reserved'],row['free_quantity'],row['missing'],tr('3D / photo à charger'),row['set_quantity']) for row in self.parts])
        for position in range(self.detail.rowCount()):
            row=self.parts[row_index(self.detail,position)]
            self.detail.item(position,10).setToolTip(tf('Quantité présente dans les sets possédés pour cette référence et ce choix de couleurs : {}',row['owned_set_quantity']))
            if row.get('ignore_colors'):
                colors=', '.join((str(color) or tr('Non précisée'))+' × '+str(quantity) for color,quantity in sorted(row['reserved_colors'].items()))
                self.detail.item(position,4).setToolTip(tf('Couleurs réellement réservées : {}',colors or tr('Aucune réservation')))
        if self.thumbnails: self.thumbnails.reset()
        self.view_set.setEnabled(self.project_item() is not None);self.publish_selection()
        self.status.setEnabled(self.project_id is not None)
        self.pick_button.setEnabled(self.project_id is not None)
        self.manage.setEnabled(self.project_id is not None);self.part_button.setEnabled(self.project_id is not None)
        self.reserve_button.setEnabled(any(min(row['required'],row.get('reservable_quantity',row['reserved']+row['free_quantity']))>row['reserved'] for row in self.parts))
        self.release_button.setEnabled(any(row['reserved'] > 0 for row in self.parts))
        if self.project_id is None: self.summary.setText(tr('Crée un projet depuis un set ou prépare une construction personnelle.')); return
        project = self.rows[index]; self.status.setCurrentIndex(self.status.findData(project['status']))
        self.summary.setText(tf('{0} · {1} pièce(s) nécessaire(s) · {2} réservée(s) · {3} manquante(s)',project['name'],project['required'],project['reserved'],project['missing'])+tf(' · Disponible : {:.1f} %',100*(project['required']-project['missing'])/project['required'] if project['required'] else 0))

    def change_colors(self,value):
        if self.project_id is not None and not self.run(lambda:projects.set_ignore_colors(self.db,self.project_id,value)):self.choose_project()

    def change_stock(self,value):
        if self.project_id is not None and not self.run(lambda:projects.set_include_set_stock(self.db,self.project_id,value)):self.choose_project()

    def pick_list(self):
        if self.project_id is None:return
        from .collection_dialogs import PickListDialog
        show_window(PickListDialog(self.db,self.project_id,self.engine,self),self,lambda *_:self.refresh())

    def project_item(self):
        row=next((row for row in self.rows if row['id']==self.project_id),None)
        return self.db.get_item(row['set_id']) if row and row['set_id'] else None

    def publish_selection(self):
        if self.isVisible():self.selected.emit(self.project_item())

    def showEvent(self,event):
        super().showEvent(event);self.publish_selection()

    def open_project(self,*_):
        item=self.project_item()
        if item:
            from .dialogs import RelationsDialog
            return show_window(RelationsDialog(self.db,self.engine,item,self),self)

    def eventFilter(self,watched,event):
        if watched is getattr(self,'detail_body',None) and event.type() in (QEvent.Type.Resize,QEvent.Type.LayoutRequest):
            height=watched.layout().totalHeightForWidth(watched.width())
            if height>0 and watched.minimumHeight()!=height:watched.setMinimumHeight(height)
        return super().eventFilter(watched,event)

    def update_part_actions(self):
        rows=self.selection();selected=len(rows);present=self.project_id is not None
        reservable=any(min(row['required'],row.get('reservable_quantity',row['reserved']+row['free_quantity']))>row['reserved'] for row in rows)
        for action,enabled in zip(self.part_actions,(present,present and selected==1,present and selected>0,present and reservable,present and selected==1)):action.setEnabled(enabled)

    def visible_parts(self): return [self.parts[row_index(self.detail,index)] for index in range(self.detail.rowCount())]
    def selection(self): return [self.parts[row_index(self.detail,index.row())] for index in self.detail.selectionModel().selectedRows()]
    def select_part(self):
        index = row_index(self.detail)
        if 0<=index<len(self.parts): self.selected.emit(dict(self.parts[index]))
    def open_part(self,*_):
        selected = self.selection()
        if selected:
            from .dialogs import RelationsDialog
            show_window(RelationsDialog(self.db,self.engine,selected[0],self),self)

    def run(self,callback):
        try: callback()
        except (ValueError,sqlite3.Error) as error: QMessageBox.warning(self,tr('Projet'),str(error)); return False
        self.refresh(); self.changed.emit(); return True

    def new_project(self,*_): return self.create_from_item()
    def create_from_item(self,item=None,copies=1,exclude_minifigs=False,context_note='',ignore_colors=False,include_set_stock=False):
        window = NewProjectDialog(self,item,copies,exclude_minifigs,context_note,ignore_colors=ignore_colors,include_set_stock=include_set_stock); show_window(window,self); return window
    def rename(self):
        if self.project_id is None: return
        project = next(row for row in self.rows if row['id']==self.project_id)
        name,ok = QInputDialog.getText(self,tr('Renommer le projet'),tr('Nom'),text=project['name'])
        if ok: self.run(lambda:projects.edit(self.db,self.project_id,name=name))
    def change_status(self,*_):
        if self.project_id is not None: self.run(lambda:projects.edit(self.db,self.project_id,status=self.status.currentData()))
    def delete(self):
        if self.project_id is None: return
        if QMessageBox.question(self,tr('Projet'),tr('Supprimer ce projet et libérer ses réservations ? Les pièces prélevées restent dans le stock, sans affectation comptée à un tiroir.'))==QMessageBox.StandardButton.Yes:
            self.run(lambda:projects.delete(self.db,self.project_id))

    def add_part(self):
        if self.project_id is None: return
        project_id = self.project_id
        picker = ReferencePicker(self.db,('part','minifig'),self)
        if picker.exec()!=QDialog.DialogCode.Accepted: return
        item = picker.chosen
        dialog = QDialog(self); dialog.setWindowTitle(tr('Ajouter une pièce au projet')); form = QFormLayout(dialog)
        label = QLabel(item['source']+' '+item['ref']+' · '+item['name']); label.setWordWrap(True); form.addRow(label)
        color = QComboBox(); color.addItem(tr('Non précisée'),'')
        for key,name in color_options(self.db,item): color.addItem(name,key)
        quantity = QSpinBox(); quantity.setRange(1,1000000000); form.addRow(tr('Couleur'),color); form.addRow(tr('Quantité nécessaire'),quantity)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); form.addRow(buttons); buttons.rejected.connect(dialog.reject)
        def save():
            if self.run(lambda:projects.put_part(self.db,project_id,item['id'],color.currentData(),quantity.value())): dialog.accept()
        buttons.accepted.connect(save); show_window(dialog,self)

    def edit_required(self):
        selected = self.selection()
        if self.project_id is None or len(selected)!=1: return
        row = selected[0]; quantity,ok = QInputDialog.getInt(self,tr('Quantité nécessaire'),row['ref'],row['required'],1,1000000000)
        if ok: self.run(lambda:projects.put_part(self.db,self.project_id,row['id'],row['chosen_color'],quantity))
    def remove_parts(self):
        selected = self.selection()
        if self.project_id is not None and selected:
            self.run(lambda:projects.remove_parts(self.db,self.project_id,[(row['id'],row['chosen_color']) for row in selected]))
    def reserve_all(self):
        if self.project_id is not None: self.run(lambda:projects.reserve(self.db,self.project_id))
    def reserve_selected(self):
        selected = self.selection()
        if self.project_id is not None and selected:
            self.run(lambda:projects.reserve(self.db,self.project_id,[(row['id'],row['chosen_color']) for row in selected]))
    def edit_reserved(self):
        selected = self.selection()
        if self.project_id is None or len(selected)!=1: return
        row = selected[0]; maximum = min(row['required'],row.get('reservable_quantity',row['reserved']+row['free_quantity']))
        quantity,ok = QInputDialog.getInt(self,tr('Réservation'),row['ref'],row['reserved'],0,maximum)
        if ok: self.run(lambda:projects.reserve(self.db,self.project_id,[(row['id'],row['chosen_color'])],quantity))
    def release(self):
        if self.project_id is not None: self.run(lambda:projects.release(self.db,self.project_id))
