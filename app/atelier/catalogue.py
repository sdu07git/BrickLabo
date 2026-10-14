from __future__ import annotations
from .windows import show_window

from .i18n import tr,tf

from PySide6.QtCore import Qt,Signal,QTimer,QItemSelectionModel
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
                              QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QMenu,
                              QMessageBox,QInputDialog,QSizePolicy,QSplitter,QGroupBox,QScrollArea)

from .ui_common import edit_item,async_task,pixmap,FlowLayout,HorizontalControls


COLUMNS=[('architect_rank',tr('Classement')),('ldraw_model',tr('Modèles LDraw')),('ref',tr('Référence')),('name',tr('Nom')),('category',tr('Catégorie')),('has_print',tr('Sérigraphie')),('has_sticker',tr('Sticker')),('image',tr('Aperçu 3D / photo')),
         ('source',tr('Source')),('year',tr('Année')),('chosen_color',tr('Couleur')),('chosen_quantity',tr('Quantité')),
         ('reserved_quantity',tr('Réservée aux projets')),('available_quantity',tr('Disponible pour construire')),('allocated_quantity',tr('Répartie dans les tiroirs')),('remaining_quantity',tr('Restant à ranger')),
         ('imported_at',tr('Date d’import')),('date',tr('Date')),('method',tr('Méthode')),('alternate',tr('Autres références')),('weight',tr('Poids (g)')),('dimensions',tr('Dimensions'))]


class Catalogue(QWidget):
    selected=Signal(object)
    opened=Signal(object)
    changed=Signal()
    reloaded=Signal()
    def __init__(self,db,source=None,kind=None,scope='catalogue',parent=None,selection_only=False):
        super().__init__(parent);self.db=db;self.source=source;self.kind=kind;self.scope=scope;self.selection_only=selection_only
        self.page=1;self.sort='ref';self.desc=False;self.rows=[];self.ids=set();self.loading=False;self.total=0
        self.engine=None;self.thumbnail_token=0;self.visual_versions={};self.advanced={};self.reference_filter=None
        self.key=f'columns_{source}_{kind}_{scope}'+('_picker' if selection_only else '')
        default_columns=['ref','name','chosen_quantity','image'] if scope=='stock_sets' else ['ref','name','category']+(['has_print','has_sticker'] if kind!='set' else [])+['image']+(['chosen_color','chosen_quantity'] if scope in ('queue','stock') else [])+(['date','method'] if scope=='history' else ['date'] if scope=='queue' else [])
        if scope=='stock':default_columns+=['reserved_quantity','available_quantity']
        if selection_only:default_columns=['source','ref','name','category','year','image']
        self.visible_columns=self.db.setting(self.key,default_columns)
        if kind!='set' and not self.db.setting('decoration_columns_added_'+self.key,False):
            for key in ('has_print','has_sticker'):
                if key not in self.visible_columns:self.visible_columns.insert(self.visible_columns.index('image') if 'image' in self.visible_columns else len(self.visible_columns),key)
            self.db.set_setting(self.key,self.visible_columns);self.db.set_setting('decoration_columns_added_'+self.key,True)
        self.hide_decorated=self.db.setting('hide_decorated_'+self.key,False)
        if not selection_only and not self.db.setting('import_date_column_added_'+self.key,False):
            if 'imported_at' not in self.visible_columns:self.visible_columns.insert(self.visible_columns.index('image') if 'image' in self.visible_columns else len(self.visible_columns),'imported_at')
            self.db.set_setting(self.key,self.visible_columns);self.db.set_setting('import_date_column_added_'+self.key,True)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);self.controls_scroll=QScrollArea();self.controls_scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,0,0,0);layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize);self.controls_scroll.setWidget(body);outer.addWidget(self.controls_scroll)
        self.filter_scroll=HorizontalControls();layout.addWidget(self.filter_scroll);filters=self.filter_scroll.row
        self.filter_scroll.setAccessibleName(tr('Recherche et filtres du catalogue'))
        self.search=QLineEdit();self.search.setMinimumWidth(130);self.search.setMaximumWidth(240);self.search.setPlaceholderText(tr('Rechercher…'));self.search.setAccessibleName(tr('Rechercher dans le catalogue'));self.search.setToolTip(tr('Rechercher : référence, nom, catégorie, 1x1 ou 1 x 1…'));filters.addWidget(self.search)
        from .category_tags import CheckableCategoryBox
        self.category=CheckableCategoryBox();self.category.setMinimumWidth(190);self.category.setMaximumWidth(210);self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.category.setMinimumContentsLength(14);filters.addWidget(self.category)
        self.year=None
        if kind=='set' and scope=='catalogue' and not selection_only:
            self.year=QComboBox();self.year.setMinimumWidth(150);self.year.setMaximumWidth(200);self.year.setAccessibleName(tr('Année de sortie du set'));self.year.setToolTip(tr('Afficher les sets de l’année choisie'));filters.addWidget(self.year)
        columns=QPushButton(tr('Colonnes'));columns.clicked.connect(self.column_menu);filters.addWidget(columns)
        self.filters_button=QPushButton(tr('Filtres avancés…'));self.filters_button.clicked.connect(self.advanced_filters);filters.addWidget(self.filters_button)
        if kind!='set':
            self.decorated_button=QPushButton();self.decorated_button.setCheckable(True);self.decorated_button.setChecked(self.hide_decorated);self.update_decorated_button();self.decorated_button.toggled.connect(self.toggle_decorated);filters.addWidget(self.decorated_button)
        if source=='ALT' and not selection_only:
            b=QPushButton(tr('Ajouter'));b.clicked.connect(self.new_alternative);filters.addWidget(b)
            if scope=='catalogue':
                b=QPushButton(tr('Supprimer'));b.clicked.connect(self.delete_selected);filters.addWidget(b)
        filter_row=FlowLayout()
        self.reference_tag=QPushButton();self.reference_tag.setToolTip(tr('Retirer le filtre de référence exacte'));self.reference_tag.clicked.connect(self.reset);self.reference_tag.hide();filter_row.addWidget(self.reference_tag);layout.addLayout(filter_row)
        if kind=='set' and scope=='catalogue' and not selection_only:
            self.moc_search_button=QPushButton(tr('MOC par mot clé / créateur'));self.moc_search_button.setToolTip(tr('Rechercher sur Rebrickable dans tous les MOC et alternatives, sans filtre de stock.'));self.moc_search_button.clicked.connect(self.search_mocs);filters.addWidget(self.moc_search_button)
        filters.addStretch()
        self.table=QTableWidget();self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection if selection_only else QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionsMovable(True);self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_changed);self.table.horizontalHeader().sectionMoved.connect(self.save_column_order)
        header=self.table.horizontalHeader();header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);header.customContextMenuRequested.connect(lambda pos:self.column_menu(header.mapToGlobal(pos)))
        if not selection_only:
            self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.itemSelectionChanged.connect(self.selection_changed);self.table.itemDoubleClicked.connect(lambda _:self.open_current())
        self.documents=None
        if kind=='set' and scope=='catalogue':
            from .documents import DocumentsPanel
            vertical=QSplitter(Qt.Orientation.Vertical);vertical.addWidget(self.table)
            self.documents=DocumentsPanel(db);vertical.addWidget(self.documents);vertical.setSizes([600,210]);layout.addWidget(vertical,1)
        else:layout.addWidget(self.table,1)
        footer=QHBoxLayout();self.count=QLabel();self.count.setWordWrap(True);footer.addWidget(self.count,1)
        self.back=QPushButton('‹');self.back.clicked.connect(lambda:self.go_page(self.page-1));footer.addWidget(self.back)
        self.pages=QComboBox();self.pages.currentIndexChanged.connect(lambda i:self.go_page(i+1) if not self.loading else None);footer.addWidget(self.pages)
        self.next=QPushButton('›');self.next.clicked.connect(lambda:self.go_page(self.page+1));footer.addWidget(self.next)
        self.page_size=QComboBox();self.page_size.addItems(['50','100','200']);self.page_size.setCurrentText('100');self.page_size.currentTextChanged.connect(lambda _:self.reset());footer.addWidget(self.page_size)
        layout.addLayout(footer)
        if not selection_only:
            buttons=FlowLayout()
            if kind!='set' and scope!='stock_sets':
                self.edit_labels_button=QPushButton(tr('Disposition de la sélection…'));self.edit_labels_button.clicked.connect(self.edit_selected_labels);buttons.addWidget(self.edit_labels_button)
            for label,target in [(tr('Ajouter au stock'),'stock'),(tr('Ajouter aux étiquettes à imprimer'),'queue')]:
                b=QPushButton(label)
                if kind=='set' and target=='stock':
                    b.setText(tr('Ajouter au stock…'));choices=QMenu(b);self.set_stock_choices(choices);b.setMenu(choices)
                else:b.clicked.connect(lambda checked=False,t=target:self.add_selected(t))
                buttons.addWidget(b)
            if scope=='catalogue' and kind!='set':
                self.drawer_button=QPushButton(tr('Associer à un tiroir…'));self.drawer_button.clicked.connect(self.assign_drawer);buttons.addWidget(self.drawer_button)
            b=QPushButton(tr('Copier vers catalogue alternatif'));b.clicked.connect(self.copy_selected);buttons.addWidget(b);layout.addLayout(buttons)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(250);self.timer.timeout.connect(self.reset)
        self.search.textChanged.connect(lambda _:self.timer.start());self.category.currentIndexChanged.connect(self.category_changed)
        self.category.values_changed.connect(self.categories_checked)
        if self.year is not None:self.year.currentIndexChanged.connect(lambda _:self.reset() if not self.loading else None)
        self.reload_categories();self.reload()

    def category_changed(self):
        if self.loading:return
        self.advanced.pop('categories',None);self.refresh_filter_tags();self.reset()
    def categories_checked(self,values):
        if self.loading:return
        if values:self.advanced['categories']=list(values)
        else:self.advanced.pop('categories',None)
        self.refresh_filter_tags();self.reset()
    def update_decorated_button(self):
        self.decorated_button.setText(tr('Réafficher pièces décorées') if self.hide_decorated else tr('Masquer pièces décorées'))
        self.decorated_button.setToolTip(tr('Réafficher les pièces avec stickers et sérigraphies dans le tableau.') if self.hide_decorated else tr('Masquer les pièces avec stickers et sérigraphies dans le tableau.'))
    def refresh_filter_tags(self):
        values=self.advanced.get('categories') or ([self.category.currentData()] if self.category.currentData() else [])
        self.category.set_values(values)
        self.filters_button.setText(tr('Filtres avancés…')+(' ('+str(len(self.advanced))+')' if self.advanced else ''))
    def remove_category_tag(self,value):
        values=[v for v in self.advanced.get('categories',[]) if v!=value]
        if values:self.advanced['categories']=values
        else:self.advanced.pop('categories',None)
        self.category.set_values(values)
        self.refresh_filter_tags();self.reset()

    def advanced_filters(self):
        from .search_filters import FilterDialog
        d=FilterDialog(self)
        show_window(d,self,lambda result:self.apply_filter_state(d.state()) if result==d.DialogCode.Accepted else None)

    def search_mocs(self):
        from .moc_search import MocSearchDialog
        show_window(MocSearchDialog(self.db,self.engine,self,keyword=self.search.text().strip()),self)

    def filter_state(self):
        return {'search':self.search.text(),'category':self.category.currentData() or '',
                'year':self.year.currentData() or '' if self.year is not None else '',
                'hide_decorated':self.hide_decorated,'advanced':dict(self.advanced)}

    def apply_filter_state(self,state):
        self.loading=True;self.timer.stop()
        self.search.blockSignals(True);self.search.setText(state.get('search',''));self.search.blockSignals(False)
        self.category.setCurrentIndex(max(0,self.category.findData(state.get('category',''))))
        if self.year is not None:self.year.setCurrentIndex(max(0,self.year.findData(state.get('year',''))))
        self.hide_decorated=bool(state.get('hide_decorated',False))
        if hasattr(self,'decorated_button'):
            self.decorated_button.blockSignals(True);self.decorated_button.setChecked(self.hide_decorated);self.decorated_button.blockSignals(False)
            self.update_decorated_button()
        self.db.set_setting('hide_decorated_'+self.key,self.hide_decorated)
        self.advanced=dict(state.get('advanced',{}))
        if self.advanced.get('categories'):self.category.setCurrentIndex(0)
        self.refresh_filter_tags()
        self.loading=False;self.reset()

    def reload_categories(self):
        current=self.category.currentText();self.loading=True;self.category.clear();self.category.addItem(tr('Toutes les catégories'),'')
        for cat in self.db.categories(self.source,self.kind):
            if cat:self.category.addItem(cat,cat)
        if self.advanced.get('categories'):self.category.setItemText(0,tr('Catégories sélectionnées : ')+str(len(self.advanced['categories'])))
        idx=self.category.findText(current)
        if idx>=0:self.category.setCurrentIndex(idx)
        self.refresh_filter_tags()
        if self.year is not None:
            selected=self.year.currentData();self.year.clear();self.year.addItem(tr('Toutes les années'),'')
            for year in self.db.years(self.source,self.kind):
                self.year.addItem(year if year else tr('Année non renseignée'),year if year else '__unknown__')
            idx=self.year.findData(selected)
            if idx>=0:self.year.setCurrentIndex(idx)
        self.loading=False

    def toggle_decorated(self,checked):
        self.hide_decorated=checked;self.db.set_setting('hide_decorated_'+self.key,checked)
        self.update_decorated_button();self.reset()

    def reset(self):self.reference_filter=None;self.reference_tag.hide();self.page=1;self.ids.clear();self.reload()

    def reveal_item(self,item_id):
        item=self.db.get_item(item_id)
        if (not item or item.get('catalogue_hidden') or self.scope!='catalogue' or self.source!=item['source'] or self.kind!=item['kind']):return False
        self.loading=True;self.timer.stop()
        self.search.blockSignals(True);self.search.setText(item['ref']);self.search.blockSignals(False)
        self.category.setCurrentIndex(0)
        if self.year is not None:self.year.setCurrentIndex(0)
        self.advanced={};self.refresh_filter_tags();self.reference_filter=item['ref'];self.page=1;self.ids.clear()
        self.reference_tag.setText(tf('Référence exacte : {}',item['ref'])+' ×');self.reference_tag.show()
        self.loading=False;self.reload()
        row=next((index for index,value in enumerate(self.rows) if value['id']==item_id),None)
        if row is None:return False
        self.table.selectRow(row);self.table.scrollToItem(self.table.item(row,0));return True

    def reload(self):
        self.loading=True
        if self.selection_only:self.ids.clear()
        self.rows,self.total,n_pages,self.page=self.db.query(self.source,self.kind,self.search.text(),self.category.currentData() or '',self.scope,self.page,int(self.page_size.currentText()),self.sort,self.desc,self.hide_decorated,year=(self.year.currentData() or '') if self.year is not None else '',advanced=self.advanced,reference=self.reference_filter)
        self.table.setColumnCount(len(self.visible_columns));self.table.setHorizontalHeaderLabels([dict(COLUMNS).get(k,k) for k in self.visible_columns]);self.table.setRowCount(len(self.rows))
        self.table.clearSelection()
        for r,row in enumerate(self.rows):
            row['_scope']=self.scope
            for c,key in enumerate(self.visible_columns):
                value=row.get(key,'')
                if key in ('has_print','has_sticker'):value=tr('Oui') if value else tr('Non')
                if key=='imported_at' and not value:value=tr('Inconnue')
                if key=='image':value=tr('Photo') if row.get('image') else tr('3D / photo à charger')
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
        self.loading=False;self.update_count();self.load_thumbnails();self.reloaded.emit()

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
            if row.get('entry_id') and row.get('entry_id')==item.get('entry_id') and self.scope in ('queue','stock','stock_sets'):
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

    def update_count(self):self.count.setText(tf('{0} résultats · {2} sélection(s)',format(self.total,','),None,len(self.ids)).replace(',',' '))

    def selection(self):
        if self.selection_only:
            row=self.table.currentRow()
            return [self.rows[row]] if 0<=row<len(self.rows) else []
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
        if not selected:QMessageBox.information(self,tr('Sélection'),tr('Sélectionne une ou plusieurs lignes.'));return
        entries=[]
        try:
            for item in selected:
                if target=='set_parts_stock':
                    if item['kind']!='set':raise ValueError(tr('Sélectionne uniquement des sets.'))
                    components=self.db.components(item,strict=True)
                    if not components:raise ValueError(tr('Inventaire indisponible pour ')+item['ref'])
                    multiplier=int(item.get('chosen_quantity',1))
                    if multiplier<1:raise ValueError(tr('Quantité positive requise'))
                    for part in components:
                        native=self.db.get_item(part.get('id'));quantity=int(part.get('chosen_quantity',1))
                        if not native or native['kind'] not in ('part','minifig') or quantity<1:raise ValueError(tr('Inventaire incomplet : ')+item['ref'])
                        entries.append(('stock',native['id'],part.get('chosen_color',''),quantity*multiplier))
                elif item['kind']=='set' and target=='queue':
                    components=self.db.components(item,strict=True)
                    if not components:raise ValueError(tr('Inventaire indisponible pour ')+item['ref'])
                    entries.extend((target,p['id'],p.get('chosen_color',''),p.get('chosen_quantity',1)) for p in components)
                else:entries.append((target,item['id'],item.get('chosen_color',self.db.visual(item['id'])['color']),item.get('chosen_quantity',1)))
            count=self.db.add_many(entries,tr('Ajout des inventaires de sets à Mon stock')) if target=='set_parts_stock' else self.db.add_many(entries)
        except ValueError as error:QMessageBox.warning(self,tr('Ajout interrompu'),str(error));return
        self.changed.emit();self.update_count();self.count.setText(self.count.text()+tf(' · {1} ajoutée(s)', None, count, None))

    def set_stock_choices(self,menu):
        menu.addAction(tr('Ajouter l’inventaire à Mon stock'),lambda:self.add_selected('set_parts_stock'))
        menu.addAction(tr('Ajouter le set à Mon stock set'),lambda:self.add_selected('stock_sets'))

    def copy_selected(self):
        for row in self.selection():self.db.copy_alternative(row)
        self.changed.emit()

    def assign_drawer(self):
        selected=self.selection()
        if not selected:QMessageBox.information(self,tr('Sélection'),tr('Sélectionne une ou plusieurs lignes.'));return
        if any(p['kind'] not in ('part','minifig') for p in selected):
            QMessageBox.information(self,tr('Rangement'),tr('Seules les pièces et les mini-figs peuvent être associées à un tiroir.'));return
        from .storage_tools import CatalogueToDrawerDialog
        from .windows import application_owner
        def changed():
            owner=application_owner(self)
            if hasattr(owner,'storage'):owner.storage.refresh()
        window=CatalogueToDrawerDialog(self.db,selected,self,changed);show_window(window,self,refresh_counts=False);return window

    def context_menu(self,pos):
        index=self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isRowSelected(index.row(),index.parent()):self.table.selectRow(index.row())
        menu=QMenu(self);menu.addAction(tr('Ouvrir'),self.open_current)
        menu.addAction(tr('Ajouter aux étiquettes'),lambda:self.add_selected('queue'))
        if self.kind=='set':self.set_stock_choices(menu)
        else:menu.addAction(tr('Ajouter au stock'),lambda:self.add_selected('stock'))
        if self.kind!='set' and self.scope!='stock_sets':menu.addAction(tr('Disposition des étiquettes sélectionnées…'),self.edit_selected_labels)
        if self.scope=='catalogue' and self.kind!='set':menu.addAction(tr('Associer à un tiroir…'),self.assign_drawer)
        menu.addAction(tr('Colonnes…'),self.column_menu)
        item=dict(self.rows[index.row()]) if index.isValid() and index.row()<len(self.rows) else None
        if item and item.get('kind')=='set':
            from .windows import application_owner
            owner=application_owner(self)
            if hasattr(owner,'create_project'):menu.addAction(tr('Créer un projet de construction…'),lambda:owner.create_project(item))
            menu.addAction(tr('Voir les constructions alternatives'),lambda:self.show_alternates(item))
            from .boxes import boxes_for_set
            action=menu.addAction(tr('Afficher la boîte d’origine'),lambda:self.show_box(item));action.setEnabled(bool(boxes_for_set(self.db,item)));action.setToolTip(tr('Ouvrir la boîte BrickLink du set.') if action.isEnabled() else tr('Aucune boîte répertoriée pour ce set ; importer Original Boxes.txt si nécessaire.'));menu.setToolTipsVisible(True)
        if self.scope in ('stock','stock_sets','queue','history') or (self.source=='ALT' and self.scope=='catalogue'):
            menu.addAction(tr('Supprimer la sélection'),self.delete_selected)
        if self.scope in ('stock','stock_sets','queue'):
            menu.addAction(tr('Changer la quantité'),self.change_quantity);menu.addAction(tr('Changer la couleur'),self.change_color)
        if self.source=='ALT':menu.addAction(tr('Modifier la référence'),self.edit_alternative)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def edit_selected_labels(self):
        selected=self.selection()
        if not selected:QMessageBox.information(self,tr('Sélection'),tr('Sélectionne une ou plusieurs lignes.'));return
        if not self.engine:return
        from .editor import LabelEditor
        from .windows import application_owner
        owner=application_owner(self)
        def saved(result):
            if result and hasattr(owner,'preview'):owner.preview.refresh()
        window=LabelEditor(self.db,self.engine,selected[0],self,targets=selected,selection_mode=True)
        show_window(window,self,saved,refresh_counts=False);return window

    def show_alternates(self,item):
        from .alternates import AlternatesDialog
        show_window(AlternatesDialog(self.db,self.engine,item,self),self)

    def show_box(self,item):
        from .boxes import BoxDialog
        if self.engine:show_window(BoxDialog(self.db,self.engine,item,self),self)

    def delete_selected(self):
        selected=self.selection()
        if not selected:return
        if self.source=='ALT' and self.scope=='catalogue':
            answer=QMessageBox.question(self,tr('Supprimer du catalogue alternatif'),
                tr('Supprimer ')+str(len(selected))+tr(' référence(s) du catalogue alternatif ?\n\nLes exemplaires déjà ajoutés au stock, aux étiquettes et à l’historique sont conservés, ainsi que les pièces des sets.'),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            try:self.db.delete_alternatives([x['id'] for x in selected])
            except ValueError as e:QMessageBox.warning(self,tr('Suppression'),str(e));return
            self.ids.clear();self.reload_categories();self.reload();self.selected.emit(None)
            if self.documents:self.documents.set_item(None)
            self.changed.emit();return
        if self.scope not in ('stock','stock_sets','queue','history'):return
        remove_parts=False
        sets=[x for x in selected if x['kind']=='set']
        if self.scope=='stock_sets' and sets:
            answer=QMessageBox.question(self,tr('Retirer du stock'),
                tr('Retirer également les pièces des ')+str(len(sets))+tr(' set(s) sélectionné(s) ?\n\nOui : soustraire leurs quantités de pièces et mini-figs.\nNon : conserver les pièces dans le stock.'),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No|QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Cancel:return
            remove_parts=answer==QMessageBox.StandardButton.Yes
        try:self.db.remove(self.scope,[x['entry_id'] for x in selected],remove_set_parts=remove_parts)
        except ValueError as e:QMessageBox.warning(self,tr('Retirer du stock'),str(e));return
        self.ids.clear();self.reload();self.changed.emit()

    def change_quantity(self):
        q,ok=QInputDialog.getInt(self,tr('Quantité'),tr('Quantité pour la sélection'),1,1,9999)
        if ok:
            try:self.db.change_entries(self.scope,[x['entry_id'] for x in self.selection()],'quantity',q)
            except ValueError as error:QMessageBox.warning(self,tr('Quantité'),str(error));return
            self.reload();self.changed.emit()

    def change_color(self):
        c,ok=QInputDialog.getText(self,tr('Couleur'),tr('Identifiant de couleur de la source ou code #RRGGBB :'))
        if ok:
            try:
                self.db.change_entries(self.scope,[x['entry_id'] for x in self.selection()],'color',c)
                self.reload();self.changed.emit()
            except Exception as e:QMessageBox.warning(self,tr('Couleur'),str(e)+tr('\nCette couleur existe déjà dans la liste pour cette référence.'))

    def new_alternative(self):
        if edit_item(self,self.db,kind=self.kind or 'part'):self.reload_categories();self.reload()

    def edit_alternative(self):
        rows=self.selection()
        if rows and edit_item(self,self.db,rows[0]):self.reload_categories();self.reload()
