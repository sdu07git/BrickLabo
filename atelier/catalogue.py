from __future__ import annotations

from PySide6.QtCore import Qt,Signal,QTimer,QItemSelectionModel
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
                              QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QMenu,
                              QMessageBox,QInputDialog,QSizePolicy,QSplitter,QGroupBox)

from .ui_common import edit_item,async_task,pixmap


COLUMNS=[('architect_rank','Classement'),('ldraw_model','Modèles LDraw'),('ref','Référence'),('name','Nom'),('category','Catégorie'),('has_print','Sérigraphie'),('has_sticker','Sticker'),('image','Aperçu 3D / photo'),
         ('source','Source'),('year','Année'),('chosen_color','Couleur'),('chosen_quantity','Quantité'),
         ('imported_at','Date d’import'),('date','Date'),('method','Méthode'),('alternate','Autres références'),('weight','Poids (g)'),('dimensions','Dimensions')]


class Catalogue(QWidget):
    selected=Signal(object)
    opened=Signal(object)
    changed=Signal()
    def __init__(self,db,source=None,kind=None,scope='catalogue',parent=None):
        super().__init__(parent);self.db=db;self.source=source;self.kind=kind;self.scope=scope
        self.page=1;self.sort='ref';self.desc=False;self.rows=[];self.ids=set();self.loading=False;self.total=0
        self.engine=None;self.thumbnail_token=0;self.visual_versions={}
        self.key=f'columns_{source}_{kind}_{scope}'
        self.visible_columns=self.db.setting(self.key,['ref','name','category']+(['has_print','has_sticker'] if kind!='set' else [])+['image']+(['chosen_color','chosen_quantity'] if scope in ('queue','stock') else [])+(['date','method'] if scope=='history' else ['date'] if scope=='queue' else []))
        if kind!='set' and not self.db.setting('decoration_columns_added_'+self.key,False):
            for key in ('has_print','has_sticker'):
                if key not in self.visible_columns:self.visible_columns.insert(self.visible_columns.index('image') if 'image' in self.visible_columns else len(self.visible_columns),key)
            self.db.set_setting(self.key,self.visible_columns);self.db.set_setting('decoration_columns_added_'+self.key,True)
        self.hide_decorated=self.db.setting('hide_decorated_'+self.key,False)
        if not self.db.setting('import_date_column_added_'+self.key,False):
            if 'imported_at' not in self.visible_columns:self.visible_columns.insert(self.visible_columns.index('image') if 'image' in self.visible_columns else len(self.visible_columns),'imported_at')
            self.db.set_setting(self.key,self.visible_columns);self.db.set_setting('import_date_column_added_'+self.key,True)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        filters=QHBoxLayout();self.search=QLineEdit();self.search.setMinimumWidth(260);self.search.setPlaceholderText('Rechercher : référence, nom, catégorie, 1x1 ou 1 x 1…');filters.addWidget(self.search,1)
        self.category=QComboBox();self.category.setMinimumWidth(150);self.category.setMaximumWidth(260);self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.category.setMinimumContentsLength(18);filters.addWidget(self.category)
        self.year=None
        if kind=='set' and scope=='catalogue':
            self.year=QComboBox();self.year.setMinimumWidth(150);self.year.setMaximumWidth(200);self.year.setAccessibleName('Année de sortie du set');self.year.setToolTip('Afficher les sets de l’année choisie');filters.addWidget(self.year)
        columns=QPushButton('Colonnes');columns.clicked.connect(self.column_menu);filters.addWidget(columns)
        if source=='ALT':
            b=QPushButton('Ajouter');b.clicked.connect(self.new_alternative);filters.addWidget(b)
            if scope=='catalogue':
                b=QPushButton('Supprimer');b.clicked.connect(self.delete_selected);filters.addWidget(b)
        layout.addLayout(filters)
        if kind!='set':
            row=QHBoxLayout();self.decorated_button=QPushButton('Masquer stickers et sérigraphies');self.decorated_button.setCheckable(True);self.decorated_button.setChecked(self.hide_decorated);self.decorated_button.setText('Réafficher stickers et sérigraphies' if self.hide_decorated else 'Masquer stickers et sérigraphies');self.decorated_button.toggled.connect(self.toggle_decorated);row.addWidget(self.decorated_button);row.addStretch();layout.addLayout(row)
        self.table=QTableWidget();self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionsMovable(True);self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_changed);self.table.horizontalHeader().sectionMoved.connect(self.save_column_order)
        header=self.table.horizontalHeader();header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);header.customContextMenuRequested.connect(lambda pos:self.column_menu(header.mapToGlobal(pos)))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.itemSelectionChanged.connect(self.selection_changed);self.table.itemDoubleClicked.connect(lambda _:self.open_current())
        self.documents=None
        if kind=='set' and scope=='catalogue':
            from .documents import DocumentsPanel
            vertical=QSplitter(Qt.Orientation.Vertical);vertical.addWidget(self.table)
            self.documents=DocumentsPanel(db);vertical.addWidget(self.documents);vertical.setSizes([600,210]);layout.addWidget(vertical,1)
        else:layout.addWidget(self.table,1)
        footer=QHBoxLayout();self.count=QLabel();footer.addWidget(self.count,1)
        self.back=QPushButton('‹');self.back.clicked.connect(lambda:self.go_page(self.page-1));footer.addWidget(self.back)
        self.pages=QComboBox();self.pages.currentIndexChanged.connect(lambda i:self.go_page(i+1) if not self.loading else None);footer.addWidget(self.pages)
        self.next=QPushButton('›');self.next.clicked.connect(lambda:self.go_page(self.page+1));footer.addWidget(self.next)
        self.page_size=QComboBox();self.page_size.addItems(['50','100','200']);self.page_size.setCurrentText('100');self.page_size.currentTextChanged.connect(lambda _:self.reset());footer.addWidget(self.page_size)
        layout.addLayout(footer)
        buttons=QHBoxLayout()
        for label,target in [('Ajouter au stock','stock'),('Ajouter aux étiquettes à imprimer','queue')]:
            b=QPushButton(label);b.clicked.connect(lambda checked=False,t=target:self.add_selected(t));buttons.addWidget(b)
        b=QPushButton('Copier vers catalogue alternatif');b.clicked.connect(self.copy_selected);buttons.addWidget(b);layout.addLayout(buttons)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(250);self.timer.timeout.connect(self.reset)
        self.search.textChanged.connect(lambda _:self.timer.start());self.category.currentIndexChanged.connect(lambda _:self.reset() if not self.loading else None)
        if self.year is not None:self.year.currentIndexChanged.connect(lambda _:self.reset() if not self.loading else None)
        self.reload_categories();self.reload()

    def reload_categories(self):
        current=self.category.currentText();self.loading=True;self.category.clear();self.category.addItem('Toutes les catégories','')
        for cat in self.db.categories(self.source,self.kind):
            if cat:self.category.addItem(cat,cat)
        idx=self.category.findText(current)
        if idx>=0:self.category.setCurrentIndex(idx)
        if self.year is not None:
            selected=self.year.currentData();self.year.clear();self.year.addItem('Toutes les années','')
            for year in self.db.years(self.source,self.kind):
                self.year.addItem(year if year else 'Année non renseignée',year if year else '__unknown__')
            idx=self.year.findData(selected)
            if idx>=0:self.year.setCurrentIndex(idx)
        self.loading=False

    def toggle_decorated(self,checked):
        self.hide_decorated=checked;self.db.set_setting('hide_decorated_'+self.key,checked)
        self.decorated_button.setText('Réafficher stickers et sérigraphies' if checked else 'Masquer stickers et sérigraphies');self.reset()

    def reset(self):self.page=1;self.ids.clear();self.reload()

    def reload(self):
        self.loading=True
        self.rows,self.total,n_pages,self.page=self.db.query(self.source,self.kind,self.search.text(),self.category.currentData() or '',self.scope,self.page,int(self.page_size.currentText()),self.sort,self.desc,self.hide_decorated,year=(self.year.currentData() or '') if self.year is not None else '')
        self.table.setColumnCount(len(self.visible_columns));self.table.setHorizontalHeaderLabels([dict(COLUMNS).get(k,k) for k in self.visible_columns]);self.table.setRowCount(len(self.rows))
        self.table.clearSelection()
        for r,row in enumerate(self.rows):
            row['_scope']=self.scope
            for c,key in enumerate(self.visible_columns):
                value=row.get(key,'')
                if key in ('has_print','has_sticker'):value='Oui' if value else 'Non'
                if key=='imported_at' and not value:value='Inconnue'
                if key=='image':value='Photo' if row.get('image') else '3D / photo à charger'
                cell=QTableWidgetItem(str(value or ''));cell.setData(Qt.ItemDataRole.UserRole,row['id']);self.table.setItem(r,c,cell)
            if self.row_key(row) in self.ids:self.table.selectionModel().select(self.table.model().index(r,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        self.table.setColumnWidth(0,115)
        if 'name' in self.visible_columns:self.table.setColumnWidth(self.visible_columns.index('name'),300)
        if 'category' in self.visible_columns:self.table.setColumnWidth(self.visible_columns.index('category'),180)
        if 'image' in self.visible_columns:self.table.setColumnWidth(self.visible_columns.index('image'),165)
        if 'ldraw_model' in self.visible_columns:self.table.setColumnWidth(self.visible_columns.index('ldraw_model'),190)
        if 'architect_rank' in self.visible_columns:self.table.setColumnWidth(self.visible_columns.index('architect_rank'),100)
        if 'imported_at' in self.visible_columns:self.table.setColumnWidth(self.visible_columns.index('imported_at'),160)
        self.pages.clear();self.pages.addItems([f'Page {i} / {n_pages}' for i in range(1,n_pages+1)]);self.pages.setCurrentIndex(self.page-1)
        self.back.setEnabled(self.page>1);self.next.setEnabled(self.page<n_pages)
        if getattr(self,'thumbnails',None):self.thumbnails.reset()
        self.loading=False;self.update_count();self.load_thumbnails()

    def load_thumbnails(self,row_keys=None):
        if not self.engine or not self.isVisible() or 'image' not in self.visible_columns:return
        from .thumbnails import PartThumbnails
        column=self.visible_columns.index('image')
        if not getattr(self,'thumbnails',None) or self.thumbnails.column!=column:
            if getattr(self,'thumbnails',None):self.thumbnails.stop();self.thumbnails.deleteLater()
            self.thumbnails=PartThumbnails(self.table,self.db,self.engine,lambda:self.rows,column,self)
        if row_keys is not None:
            for row in self.rows:
                if self.row_key(row) in row_keys:self.thumbnails.invalidate(row)
        self.thumbnails.load()

    def refresh_visual(self,item):
        if not item:
            self.load_thumbnails();return
        affected=set()
        for index,row in enumerate(self.rows):
            if row['id']!=item['id']:continue
            affected.add(self.row_key(row))
            if row.get('entry_id') and row.get('entry_id')==item.get('entry_id') and self.scope in ('queue','stock'):
                row['chosen_color']=item.get('chosen_color',row.get('chosen_color',''))
                if 'chosen_color' in self.visible_columns:self.table.item(index,self.visible_columns.index('chosen_color')).setText(str(row['chosen_color']))
        if affected:self.load_thumbnails(affected)

    def showEvent(self,event):
        super().showEvent(event);self.load_thumbnails()

    def hideEvent(self,event):
        self.thumbnail_token+=1
        if getattr(self,'thumbnails',None):self.thumbnails.suspend()
        super().hideEvent(event)

    @staticmethod
    def row_key(row):return row.get('entry_id',row['id'])

    def selection_changed(self):
        if self.loading:return
        self.ids.difference_update(self.row_key(r) for r in self.rows)
        self.ids.update(self.row_key(self.rows[x.row()]) for x in self.table.selectionModel().selectedRows())
        row=self.table.currentRow()
        if row>=0 and row<len(self.rows):
            self.selected.emit(self.rows[row])
            if self.documents:self.documents.set_item(self.rows[row])
        self.update_count()

    def update_count(self):self.count.setText(f'{self.total:,} résultats · {len(self.ids)} sélection(s)'.replace(',',' '))

    def selection(self):
        if not self.ids:
            r=self.table.currentRow()
            if 0<=r<len(self.rows):return [self.rows[r]]
            return []
        if self.scope=='catalogue':
            ids=sorted(self.ids)
            return self.db.rows('SELECT * FROM items WHERE id IN ('+','.join('?' for _ in ids)+')',ids)
        ids=sorted(self.ids);extra='date' if self.scope=='history' else 'added'
        return [dict(row,_scope=self.scope) for row in self.db.rows(f'SELECT i.*,s.id AS entry_id,s.color AS chosen_color,s.quantity AS chosen_quantity,s.{extra} AS date FROM {self.scope} s JOIN items i ON i.id=s.item_id WHERE s.id IN ('+','.join('?' for _ in ids)+')',ids)]

    def go_page(self,page):
        if page<1:return
        self.page=page;self.reload()

    def sort_changed(self,col):
        key=self.visible_columns[col]
        if key=='image':return
        self.desc=not self.desc if self.sort==key else False;self.sort=key;self.page=1;self.reload()

    def column_menu(self,position=None):
        menu=QMenu(self)
        for key,label in COLUMNS:
            a=menu.addAction(label);a.setCheckable(True);a.setChecked(key in self.visible_columns)
            a.triggered.connect(lambda enabled,k=key:self.toggle_column(k,enabled))
        menu.exec(position if hasattr(position,'x') else self.mapToGlobal(self.rect().topRight()))

    def toggle_column(self,key,enabled):
        if enabled and key not in self.visible_columns:self.visible_columns.append(key)
        elif not enabled and key in self.visible_columns and len(self.visible_columns)>1:self.visible_columns.remove(key)
        self.db.set_setting(self.key,self.visible_columns);self.reload()

    def save_column_order(self,*_):
        if self.loading:return
        h=self.table.horizontalHeader();order=[self.visible_columns[h.logicalIndex(i)] for i in range(h.count())]
        self.db.set_setting(self.key,order)

    def open_current(self):
        r=self.table.currentRow()
        if 0<=r<len(self.rows):self.opened.emit(self.rows[r])

    def add_selected(self,target):
        selected=self.selection()
        if not selected:QMessageBox.information(self,'Sélection','Sélectionne une ou plusieurs lignes.');return
        count=0
        for item in selected:
            # Le stock conserve le set et ses composants via Database.add.
            if item['kind']=='set' and target=='queue':
                components=self.db.components(item)
                if not components:
                    QMessageBox.information(self,'Inventaire indisponible','Pas d’inventaire disponible pour '+item['ref']+'. Ouvre le set pour charger son inventaire BrickLink ou le définir pour un set alternatif.');continue
                for p in components:self.db.add(target,p['id'],p.get('chosen_color',''),p.get('chosen_quantity',1));count+=1
            else:
                color=item.get('chosen_color',self.db.visual(item['id'])['color'])
                try:count+=self.db.add(target,item['id'],color,item.get('chosen_quantity',1))
                except ValueError as e:QMessageBox.warning(self,'Ajout au stock' if target=='stock' else 'Ajout aux étiquettes',str(e))
        self.changed.emit();self.update_count();self.count.setText(self.count.text()+f' · {count} ajoutée(s)')

    def copy_selected(self):
        for row in self.selection():self.db.copy_alternative(row)
        self.changed.emit()

    def context_menu(self,pos):
        index=self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isRowSelected(index.row(),index.parent()):self.table.selectRow(index.row())
        menu=QMenu(self);menu.addAction('Ouvrir',self.open_current)
        menu.addAction('Ajouter aux étiquettes',lambda:self.add_selected('queue'));menu.addAction('Ajouter au stock',lambda:self.add_selected('stock'))
        menu.addAction('Colonnes…',self.column_menu)
        item=dict(self.rows[index.row()]) if index.isValid() and index.row()<len(self.rows) else None
        if item and item.get('kind')=='set':
            from .boxes import boxes_for_set
            action=menu.addAction('Afficher la boîte d’origine',lambda:self.show_box(item));action.setEnabled(bool(boxes_for_set(self.db,item)));action.setToolTip('Ouvrir la boîte BrickLink du set.' if action.isEnabled() else 'Aucune boîte répertoriée pour ce set ; importer Original Boxes.txt si nécessaire.');menu.setToolTipsVisible(True)
        if self.scope in ('stock','queue','history') or (self.source=='ALT' and self.scope=='catalogue'):
            menu.addAction('Supprimer la sélection',self.delete_selected)
        if self.scope in ('stock','queue'):
            menu.addAction('Changer la quantité',self.change_quantity);menu.addAction('Changer la couleur',self.change_color)
        if self.source=='ALT':menu.addAction('Modifier la référence',self.edit_alternative)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def show_box(self,item):
        from .boxes import BoxDialog
        if self.engine:BoxDialog(self.db,self.engine,item,self).exec()

    def delete_selected(self):
        selected=self.selection()
        if not selected:return
        if self.source=='ALT' and self.scope=='catalogue':
            answer=QMessageBox.question(self,'Supprimer du catalogue alternatif',
                'Supprimer '+str(len(selected))+' référence(s) du catalogue alternatif ?\n\nLes exemplaires déjà ajoutés au stock, aux étiquettes et à l’historique sont conservés, ainsi que les pièces des sets.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            try:self.db.delete_alternatives([x['id'] for x in selected])
            except ValueError as e:QMessageBox.warning(self,'Suppression',str(e));return
            self.ids.clear();self.reload_categories();self.reload();self.selected.emit(None)
            if self.documents:self.documents.set_item(None)
            self.changed.emit();return
        if self.scope not in ('stock','queue','history'):return
        remove_parts=False
        sets=[x for x in selected if x['kind']=='set']
        if self.scope=='stock' and sets:
            answer=QMessageBox.question(self,'Retirer du stock',
                'Retirer également les pièces des '+str(len(sets))+' set(s) sélectionné(s) ?\n\nOui : soustraire leurs quantités de pièces et mini-figs.\nNon : conserver les pièces dans le stock.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No|QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Cancel:return
            remove_parts=answer==QMessageBox.StandardButton.Yes
        try:self.db.remove(self.scope,[x['entry_id'] for x in selected],remove_set_parts=remove_parts)
        except ValueError as e:QMessageBox.warning(self,'Retirer du stock',str(e));return
        self.ids.clear();self.reload();self.changed.emit()

    def change_quantity(self):
        q,ok=QInputDialog.getInt(self,'Quantité','Quantité pour la sélection',1,1,9999)
        if ok:
            for x in self.selection():self.db.run(f'UPDATE {self.scope} SET quantity=? WHERE id=?',(q,x['entry_id']))
            self.reload()

    def change_color(self):
        c,ok=QInputDialog.getText(self,'Couleur','Identifiant de couleur de la source ou code #RRGGBB :')
        if ok:
            try:
                for x in self.selection():self.db.run(f'UPDATE {self.scope} SET color=? WHERE id=?',(c,x['entry_id']))
                self.reload()
            except Exception as e:QMessageBox.warning(self,'Couleur',str(e)+'\nCette couleur existe déjà dans la liste pour cette référence.')

    def new_alternative(self):
        if edit_item(self,self.db,kind=self.kind or 'part'):self.reload_categories();self.reload()

    def edit_alternative(self):
        rows=self.selection()
        if rows and edit_item(self,self.db,rows[0]):self.reload_categories();self.reload()
