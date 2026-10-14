"""Editable physical inventory of a captured drawer, with bounded stock counts."""
import html
import sqlite3
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QSpinBox,QCheckBox,QDialogButtonBox,QTableWidget,QAbstractItemView,QHeaderView,QMenu,QMessageBox
from .i18n import tr,tf
from .ui_common import FlowLayout
from .result_tables import fill_table,row_index
from .windows import show_window,notify_changed
from . import storage_wall as walls
from .storage_quantities import put_entry


def color_names(db):
    from .color_links import rb_palette,bl_palette
    rb={key:value.get('name',key) for key,value in rb_palette().items()}
    rb.update({str(row['id']):row['name'] for row in db.rows('SELECT id,name FROM colors')})
    return {'RB':rb,'BL':{key:value.get('name',key) for key,value in bl_palette(db.setting).items()}}


def color_label(part,names=None):
    color=str(part.get('chosen_color') or '')
    if not color:return tr('Non précisée')
    name=part.get('color_name')
    if not name:
        if names is None:
            from .color_links import rb_palette,bl_palette
            palette=bl_palette(lambda key,default=None:default) if part['source']=='BL' else rb_palette()
            name=palette.get(color,{}).get('name')
        else:name=names.get('BL' if part['source']=='BL' else 'RB',{}).get(color)
    return name+' ('+color+')' if name else color


def drawer_tooltip(drawer,parts):
    def escape(value):return html.escape(str(value))
    caption=' · '.join(value for value in (drawer.get('wall_name',''),walls.address(drawer),drawer['name']) if value)
    rows=[]
    for part in parts[:30]:
        quantity=part.get('stored_quantity')
        rows.append('<tr><td>'+escape(part['source']+' '+part['ref'])+'<br>'+escape(part['name'])+'</td><td>'+escape(part.get('color_label') or color_label(part))+'</td><td>'+escape(tr('À renseigner') if quantity is None else quantity)+'</td></tr>')
    text='<b>'+escape(caption)+'</b>'
    if rows:text+='<table cellspacing="5"><tr><th>'+escape(tr('Référence'))+'</th><th>'+escape(tr('Couleur'))+'</th><th>'+escape(tr('Quantité dans ce tiroir'))+'</th></tr>'+''.join(rows)+'</table>'
    else:text+='<br>'+escape(tr('Vide'))
    if len(parts)>30:text+='<br>'+escape(tf('{0} autres références.',len(parts)-30))
    return text+'<br>'+escape(tr('Double-clique pour modifier l’inventaire du tiroir.'))


class DrawerEntryDialog(QDialog):
    def __init__(self,inventory,part=None):
        super().__init__(inventory);self.inventory=inventory;self.db=inventory.db;self.drawer_id=inventory.drawer_id;self.previous=dict(part) if part else None;self.item=dict(part) if part else None;self._storage_wall_id=inventory._storage_wall_id
        self.setWindowTitle(tr('Modifier le contenu du tiroir') if part else tr('Ajouter une référence au tiroir'));self.resize(570,330)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.reference=QLabel();self.reference.setWordWrap(True);form.addRow(self.reference)
        choose=QPushButton(tr('Choisir une référence…'));choose.clicked.connect(self.choose_reference);form.addRow(choose)
        self.color=QComboBox();self.color.setMinimumContentsLength(16);self.color.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);form.addRow(tr('Couleur'),self.color)
        self.quantity=QSpinBox();self.quantity.setRange(0,1000000000);form.addRow(tr('Quantité dans ce tiroir'),self.quantity)
        self.unknown=QCheckBox(tr('Quantité à renseigner'));self.unknown.toggled.connect(lambda value:self.quantity.setEnabled(not value));form.addRow(self.unknown)
        note=QLabel(tr('Le comptage dans les tiroirs ne peut pas dépasser le stock en vrac de la même référence et de la même couleur.'));note.setWordWrap(True);layout.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        if part:self.quantity.setValue(part.get('stored_quantity') or 0)
        self.unknown.setChecked(part is None or part.get('stored_quantity') is None);self.set_item(self.item,part.get('chosen_color','') if part else '')

    def set_item(self,item,color=''):
        from .projects_panel import color_options
        self.item=dict(item) if item else None;self.reference.setText(item['source']+' '+item['ref']+' · '+item['name'] if item else tr('Choisis une référence.'))
        self.color.clear();self.color.addItem(tr('Non précisée'),'')
        if item:
            for code,name in color_options(self.db,item):self.color.addItem(name,code)
        if self.color.findData(str(color))<0:self.color.addItem(str(color),str(color))
        self.color.setCurrentIndex(max(0,self.color.findData(str(color))))

    def choose_reference(self):
        from .projects_panel import ReferencePicker
        picker=ReferencePicker(self.db,('part','minifig'),self)
        if picker.exec()==QDialog.DialogCode.Accepted:self.set_item(picker.chosen)

    def save(self):
        if not self.item:QMessageBox.warning(self,tr('Tiroir'),tr('Choisis une référence.'));return
        try:put_entry(self.db,self.drawer_id,self.item['id'],self.color.currentData(),None if self.unknown.isChecked() else self.quantity.value(),self.previous)
        except (ValueError,sqlite3.Error) as error:QMessageBox.warning(self,tr('Modification impossible'),str(error));return
        self.inventory.changed();self.accept()


class DrawerInventoryDialog(QDialog):
    def __init__(self,db,engine,drawer_id,parent=None,changed=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.drawer_id=drawer_id;self.on_changed=changed;self.rows=[];self.closed=False;self.entry_windows=set()
        found=db.rows('SELECT wall_id FROM storage_drawers WHERE id=?',(drawer_id,));self._storage_wall_id=found[0]['wall_id'] if found else None
        self.setWindowTitle(tr('Inventaire du tiroir'));self.resize(950,580);layout=QVBoxLayout(self);actions=FlowLayout();layout.addLayout(actions)
        self.add_button=QPushButton(tr('Ajouter une référence…'));self.add_button.clicked.connect(lambda:self.open_editor());actions.addWidget(self.add_button)
        self.edit_button=QPushButton(tr('Modifier référence, couleur et quantité…'));self.edit_button.clicked.connect(self.edit);actions.addWidget(self.edit_button)
        self.remove_button=QPushButton(tr('Retirer la sélection'));self.remove_button.clicked.connect(self.remove);actions.addWidget(self.remove_button)
        refresh=QPushButton(tr('Actualiser'));refresh.clicked.connect(self.refresh);actions.addWidget(refresh)
        self.title=QLabel();self.title.setWordWrap(True);layout.addWidget(self.title)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Couleur'),tr('Quantité dans ce tiroir'),tr('Pièce'),tr('Catégorie'),tr('Stock en vrac total'),tr('Aperçu')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column,width in enumerate((65,100,150,170,220,160,150,130)):self.table.setColumnWidth(column,width)
        layout.addWidget(self.table,1);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.thumbnails=None
        if engine:
            from .thumbnails import PartThumbnails
            self.thumbnails=PartThumbnails(self.table,db,engine,self.visible_parts,7,self)
            self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset())
        self.table.itemSelectionChanged.connect(self.update_actions);self.table.itemDoubleClicked.connect(self.edit)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.table.customContextMenuRequested.connect(self.context_menu)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);layout.addWidget(close);self.refresh()

    def selection(self):return [self.rows[row_index(self.table,row.row())] for row in self.table.selectionModel().selectedRows()]
    def visible_parts(self):return [self.rows[row_index(self.table,row)] for row in range(self.table.rowCount())]
    def update_actions(self):
        selected=self.selection();self.edit_button.setEnabled(len(selected)==1);self.remove_button.setEnabled(bool(selected))

    def refresh(self):
        if self.closed:return
        found=self.db.rows('SELECT d.*,w.name AS wall_name FROM storage_drawers d JOIN storage_walls w ON w.id=d.wall_id WHERE d.id=?',(self.drawer_id,))
        self.add_button.setEnabled(bool(found));self.rows=walls.contents(self.db,self.drawer_id) if found else [];names=color_names(self.db)
        self.title.setText(' · '.join(v for v in (found[0]['wall_name'],walls.address(found[0]),found[0]['name']) if v) if found else tr('Ce tiroir n’existe plus.'))
        fill_table(self.table,[(p['source'],p['ref'],color_label(p,names),p['stored_quantity'] if p['stored_quantity'] is not None else tr('À renseigner'),p['name'],p['category'],p['chosen_quantity'],tr('3D / photo à charger')) for p in self.rows])
        if self.thumbnails:self.thumbnails.reset()
        self.summary.setText(tf('{0} pièces comptées · {1} références à renseigner.',sum(p['stored_quantity'] or 0 for p in self.rows),sum(p['stored_quantity'] is None for p in self.rows)));self.update_actions()

    def changed(self):
        self.refresh()
        if self.on_changed:self.on_changed()
        notify_changed(self)

    def refresh_action_history(self):self.refresh()
    def open_editor(self,part=None):
        if self.closed:return
        window=DrawerEntryDialog(self,part);self.entry_windows.add(window)
        show_window(window,self,lambda *_:self.entry_windows.discard(window),refresh_counts=False);return window
    def edit(self,*_):
        selected=self.selection()
        if len(selected)==1:return self.open_editor(selected[0])
    def remove(self):
        selected=self.selection()
        if not selected:return
        walls.unassign(self.db,self.drawer_id,[(p['id'],p['chosen_color']) for p in selected]);self.changed()
    def context_menu(self,pos):
        index=self.table.indexAt(pos)
        if not index.isValid():return
        if not self.table.selectionModel().isRowSelected(index.row(),index.parent()):self.table.selectRow(index.row())
        menu=QMenu(self);edit=menu.addAction(tr('Modifier référence, couleur et quantité…'),self.edit);edit.setEnabled(len(self.selection())==1);menu.addAction(tr('Retirer la sélection'),self.remove);menu.exec(self.table.viewport().mapToGlobal(pos))
    def done(self,result):
        self.closed=True
        for window in list(self.entry_windows):window.reject()
        if self.thumbnails:self.thumbnails.stop()
        super().done(result)
