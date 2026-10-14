"""Review, correct and resume collection imports without losing rejected rows."""
from pathlib import Path

from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QPushButton,QLabel,
    QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QFileDialog,QMessageBox,
    QAbstractItemView,QGroupBox,QScrollArea)

from .i18n import tr,tf
from .stock_import import resolve_rows
from . import stock_import_jobs as imports
from .ui_common import FlowLayout
from .windows import show_window,notify_changed


def compact_combo(combo):
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(16)


class ImportItemPicker(QDialog):
    def __init__(self,db,source,kind,parent):
        super().__init__(parent);self.db=db;self.source=source;self.kind=kind;self.page=1;self.item=None;self.rows=[]
        self.setWindowTitle(tr('Choisir une référence du catalogue'));self.resize(850,540)
        layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText(tr('Référence, nom ou catégorie'));layout.addWidget(self.search)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels([tr('Référence'),tr('Nom'),tr('Catégorie')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        row=FlowLayout();layout.addLayout(row)
        self.back=QPushButton(tr('Précédent'));self.back.clicked.connect(lambda:self.turn(-1));row.addWidget(self.back)
        self.next=QPushButton(tr('Suivant'));self.next.clicked.connect(lambda:self.turn(1));row.addWidget(self.next)
        self.choose_button=QPushButton(tr('Choisir cette référence'));self.choose_button.clicked.connect(self.choose);row.addWidget(self.choose_button)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);row.addWidget(close)
        self.count=QLabel();layout.addWidget(self.count);self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.reload)
        self.search.textChanged.connect(self.reset);self.table.itemSelectionChanged.connect(self.update_choice);self.table.cellDoubleClicked.connect(lambda *_:self.choose());self.reload()

    def reset(self):self.page=1;self.timer.start()
    def turn(self,delta):self.page+=delta;self.reload()
    def reload(self):
        self.rows,total,pages,self.page=self.db.query(self.source,self.kind,self.search.text(),page=self.page,size=100)
        self.table.setRowCount(len(self.rows))
        for r,item in enumerate(self.rows):
            for c,key in enumerate(('ref','name','category')):self.table.setItem(r,c,QTableWidgetItem(str(item[key])))
        self.count.setText(tf('{0} références — page {1}/{2}',total,self.page,pages));self.back.setEnabled(self.page>1);self.next.setEnabled(self.page<pages);self.update_choice()
    def update_choice(self):self.choose_button.setEnabled(bool(self.table.selectionModel().selectedRows()))
    def choose(self):
        selected=self.table.selectionModel().selectedRows()
        if selected:self.item=self.rows[selected[0].row()];self.accept()


class StockImportDialog(QDialog):
    def __init__(self,db,parent=None,destination='stock'):
        super().__init__(parent);self.db=db;self.path=None;self.rows=[];self.resolved=[];self.job_id=None;self.updating=False
        self.setWindowTitle(tr('Importer une collection'));self.resize(1100,800);self.setMinimumSize(680,520)
        outer=QVBoxLayout(self);self.body_scroll=QScrollArea();self.body_scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize);self.body_scroll.setWidget(body);outer.addWidget(self.body_scroll,1);row=QHBoxLayout();layout.addLayout(row)
        self.source=QComboBox()
        for text,value in [(tr('Détection automatique'),'auto'),('Rebrickable','RB'),('BrickLink','BL')]:self.source.addItem(text,value)
        row.addWidget(self.source);choose=QPushButton(tr('Ouvrir un fichier…'));choose.clicked.connect(self.choose);row.addWidget(choose)
        self.filename=QLabel();self.filename.setWordWrap(True);row.addWidget(self.filename,1)
        row=QHBoxLayout();layout.addLayout(row)
        self.pending=QComboBox();compact_combo(self.pending);row.addWidget(self.pending,1)
        self.resume_button=QPushButton(tr('Reprendre cet import'));self.resume_button.clicked.connect(self.resume);row.addWidget(self.resume_button)
        choices=QFormLayout();layout.addLayout(choices)
        self.destination=QComboBox();self.destination.addItem(tr('Mon stock — pièces en vrac'),'stock');self.destination.addItem(tr('Mon stock set — sets et leurs pièces'),'stock_sets');self.destination.setCurrentIndex(1 if destination=='stock_sets' else 0);choices.addRow(tr('Ajouter à :'),self.destination)
        self.target=QComboBox();compact_combo(self.target);self.reload_targets();choices.addRow(tr('Inventaire de destination'),self.target)
        self.name=QLineEdit();self.name.setPlaceholderText(tr('Nom du nouvel inventaire'));choices.addRow(tr('Nom du nouvel inventaire'),self.name)
        self.destination.currentIndexChanged.connect(self.update_destination);self.target.currentIndexChanged.connect(self.update_destination);self.name.textChanged.connect(self.update_destination)
        info=QLabel(tr('Ajoute les lignes prêtes et corrige les autres progressivement. Les lignes en attente et tes corrections sont enregistrées automatiquement. Les sets nécessitent un inventaire local complet. Chaque ajout peut être annulé.'));info.setWordWrap(True);layout.addWidget(info)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels([tr('Ligne'),tr('Source'),tr('Type'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité'),tr('Vérification')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(7,QHeaderView.ResizeMode.Stretch);self.table.setSortingEnabled(True);self.table.setMinimumHeight(130)
        for column,width in ((0,55),(1,65),(2,80),(3,105),(5,90),(6,80)):self.table.setColumnWidth(column,width)
        layout.addWidget(self.table,1);self.table.itemSelectionChanged.connect(self.select_row)
        self.repair_box=QGroupBox(tr('Corriger la ligne sélectionnée'));repair=QVBoxLayout(self.repair_box);self.issue=QLabel();self.issue.setWordWrap(True);repair.addWidget(self.issue);form=QFormLayout();repair.addLayout(form)
        self.edit_source=QComboBox()
        for title,value in [('Rebrickable','RB'),('BrickLink','BL'),(tr('Catalogue alternatif'),'ALT'),('BrickArchitect','BA')]:self.edit_source.addItem(title,value)
        self.edit_kind=QComboBox()
        for title,value in [(tr('Pièce'),'part'),(tr('Set'),'set'),(tr('Mini-figurine'),'minifig')]:self.edit_kind.addItem(title,value)
        controls=QHBoxLayout();controls.addWidget(self.edit_source);controls.addWidget(self.edit_kind);form.addRow(tr('Source / type'),controls)
        self.edit_ref=QLineEdit();form.addRow(tr('Référence'),self.edit_ref)
        self.edit_color=QComboBox();self.edit_color.setEditable(True);self.edit_color.setInsertPolicy(QComboBox.InsertPolicy.NoInsert);compact_combo(self.edit_color);form.addRow(tr('Couleur'),self.edit_color)
        self.edit_quantity=QLineEdit();form.addRow(tr('Quantité'),self.edit_quantity)
        self.edit_version=QLineEdit();self.edit_version.setPlaceholderText(tr('Dernière version si vide'));form.addRow(tr('Version de l’inventaire'),self.edit_version)
        actions=FlowLayout();repair.addLayout(actions)
        self.pick_button=QPushButton(tr('Rechercher dans le catalogue…'));self.pick_button.clicked.connect(self.pick_item);actions.addWidget(self.pick_button)
        self.save_row=QPushButton(tr('Enregistrer la correction'));self.save_row.clicked.connect(self.save_correction);actions.addWidget(self.save_row)
        layout.addWidget(self.repair_box);self.repair_box.hide();self.edit_source.currentIndexChanged.connect(self.change_palette);self.edit_kind.currentIndexChanged.connect(self.change_palette)
        self.status=QLabel();self.status.setWordWrap(True);outer.addWidget(self.status)
        buttons=FlowLayout();outer.addLayout(buttons)
        self.commit=QPushButton(tr('Ajouter les lignes prêtes'));self.commit.setProperty('primary',True);self.commit.clicked.connect(self.import_selected);self.commit.setEnabled(False);buttons.addWidget(self.commit)
        recheck=QPushButton(tr('Revérifier les lignes'));recheck.clicked.connect(self.refresh);buttons.addWidget(recheck)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);buttons.addWidget(close)
        self.reload_pending();self.update_destination()

    def reload_targets(self,selected=None):
        self.target.blockSignals(True);self.target.clear();self.target.addItem(tr('Créer un inventaire personnel'),None)
        for row in self.db.rows('SELECT s.id,i.source,i.ref,i.name FROM stock_sets s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 ORDER BY i.ref'):
            self.target.addItem(row['source']+' '+row['ref']+' — '+row['name'],row['id'])
        index=self.target.findData(selected)
        if selected is not None and index<0:self.target.addItem(tr('Inventaire de destination absent'),selected);index=self.target.count()-1
        self.target.setCurrentIndex(max(0,index));self.target.blockSignals(False)

    def reload_pending(self):
        selected=self.pending.currentData();self.pending.clear();self.pending.addItem(tr('Imports en attente…'),None)
        for job in imports.jobs(self.db):self.pending.addItem(Path(job['filename']).name+' — '+tf('{0} lignes en attente',job['pending']),job['id'])
        self.pending.setCurrentIndex(max(0,self.pending.findData(selected)));self.resume_button.setEnabled(self.pending.count()>1)

    def update_destination(self,*_):
        if self.updating:return
        owned=self.destination.currentData()=='stock_sets';locked=any(row.get('imported') for row in self.rows)
        attached=any(row.get('imported') and row['kind']!='set' for row in self.rows)
        target_exists=self.target.currentData() is not None and bool(self.db.rows('SELECT 1 FROM stock_sets WHERE id=? AND quantity>0',(self.target.currentData(),)))
        target_locked=attached and target_exists
        self.destination.setEnabled(not locked);self.target.setEnabled(owned and not target_locked);self.name.setEnabled(owned and not target_locked and self.target.currentData() is None)
        if self.job_id:
            try:imports.update_destination(self.db,self.job_id,self.destination.currentData(),self.target.currentData(),self.name.text())
            except ValueError as error:self.status.setText(str(error));self.commit.setEnabled(False);return
        self.update_commit()

    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,tr('Importer une liste de pièces ou de sets'),'',tr('Listes (*.csv *.txt *.tsv *.xml);;Tous les fichiers (*)'))
        if path:self.path=path;self.load()

    def load(self,*_):
        if not self.path:return
        self.job_id=None;self.rows=[];self.resolved=[];self.table.setRowCount(0);self.repair_box.hide();self.commit.setEnabled(False);self.filename.setText(Path(self.path).name);self.filename.setToolTip(str(self.path))
        try:
            job=imports.create_job(self.db,self.path,self.source.currentData(),self.destination.currentData())
            imports.update_destination(self.db,job,self.destination.currentData(),self.target.currentData(),self.name.text());self.load_job(job)
        except Exception as error:self.status.setText(str(error))

    def resume(self):
        job=self.pending.currentData()
        if job:self.load_job(job)

    def load_job(self,job):
        details=self.db.rows('SELECT * FROM stock_import_jobs WHERE id=?',(job,))
        if not details:return
        details=details[0];self.job_id=job;self.path=details['filename'];self.filename.setText(Path(self.path).name);self.filename.setToolTip(self.path)
        self.updating=True;self.source.setCurrentIndex(max(0,self.source.findData(details['source'])));self.destination.setCurrentIndex(self.destination.findData(details['destination']));self.reload_targets(details['target_entry']);self.name.setText(details['name']);self.updating=False;self.refresh()

    def update_commit(self):
        ready=[row for row in self.resolved if not row['imported'] and not row['issue']]
        needs_name=self.destination.currentData()=='stock_sets' and self.target.currentData() is None and any(row['kind']!='set' for row in ready)
        self.commit.setEnabled(bool(ready) and (not needs_name or bool(self.name.text().strip())))

    def refresh(self,*_):
        if not self.job_id:return
        details=self.db.rows('SELECT * FROM stock_import_jobs WHERE id=?',(self.job_id,))[0]
        self.updating=True;self.destination.setCurrentIndex(self.destination.findData(details['destination']));self.reload_targets(details['target_entry']);self.name.setText(details['name']);self.updating=False
        ordinal=self.current_ordinal();self.rows=imports.job_rows(self.db,self.job_id);self.resolved=resolve_rows(self.db,self.rows)
        self.table.blockSignals(True);self.table.setSortingEnabled(False);self.table.setRowCount(len(self.resolved))
        for r,row in enumerate(self.resolved):
            state=tr('Déjà importée') if row['imported'] else row['issue'] or tr('Prête à importer')
            values=(row['ordinal'],row['source'],row['kind'],row['ref'],row['item']['name'] if row['item'] else '',row['color'],row['quantity'],state)
            for c,value in enumerate(values):
                cell=QTableWidgetItem();cell.setData(Qt.ItemDataRole.DisplayRole,value);cell.setData(Qt.ItemDataRole.UserRole,row['ordinal']);cell.setToolTip(str(row['original'])+'\n'+state);cell.setForeground(QColor('#91a4b8' if row['imported'] else '#f4aa91' if row['issue'] else '#97d6b2'));self.table.setItem(r,c,cell)
        self.table.setSortingEnabled(True);self.table.blockSignals(False)
        if not any(row['ordinal']==ordinal and not row['imported'] for row in self.resolved):
            ordinal=next((row['ordinal'] for row in self.resolved if not row['imported'] and row['issue']),next((row['ordinal'] for row in self.resolved if not row['imported']),None))
        self.table.clearSelection()
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).data(Qt.ItemDataRole.UserRole)==ordinal:self.table.selectRow(r);break
        imported=sum(row['imported'] for row in self.resolved);pending=[row for row in self.resolved if not row['imported']];ready=sum(not row['issue'] for row in pending)
        self.status.setText(tf('{0} lignes prêtes — {1} à corriger — {2} déjà importées.',ready,len(pending)-ready,imported));self.reload_pending();self.update_destination();self.select_row()

    def stock_changed(self):
        if self.job_id:self.load_job(self.job_id)
        else:self.reload_pending();self.reload_targets(self.target.currentData())

    def current_ordinal(self):
        selected=self.table.selectionModel().selectedRows()
        return self.table.item(selected[0].row(),0).data(Qt.ItemDataRole.UserRole) if selected else None

    def selected_row(self):
        ordinal=self.current_ordinal()
        return next((row for row in self.resolved if row['ordinal']==ordinal),None)

    def select_row(self):
        row=self.selected_row();self.repair_box.setVisible(bool(row and not row['imported']))
        if not row or row['imported']:return
        self.issue.setText(row['issue'] or tr('Prête à importer'))
        self.updating=True;self.edit_source.setCurrentIndex(max(0,self.edit_source.findData(row['source'])));self.edit_kind.setCurrentIndex(max(0,self.edit_kind.findData(row['kind'])));self.edit_ref.setText(row['ref']);self.edit_quantity.setText(str(row['quantity']));self.edit_version.setText(str(row.get('inventory_version') or ''));self.edit_version.setEnabled(row['kind']=='set');self.populate_palette(str(row['color']));self.updating=False

    def populate_palette(self,color=''):
        from .color_links import rb_palette,bl_palette
        source=self.edit_source.currentData();palette=bl_palette(self.db.setting) if source=='BL' else rb_palette()
        if source!='BL':palette={**palette,**{str(row['id']):row for row in self.db.rows('SELECT * FROM colors')}}
        self.edit_color.clear();self.edit_color.addItem(tr('Choisir une couleur…'),'')
        for code,entry in sorted(palette.items(),key=lambda pair:(pair[1].get('name','').lower(),pair[0])):self.edit_color.addItem(code+' — '+entry.get('name',''),code)
        index=self.edit_color.findData(color)
        if index>=0:self.edit_color.setCurrentIndex(index)
        else:self.edit_color.setCurrentIndex(-1);self.edit_color.setEditText(color)
        self.edit_color.setEnabled(self.edit_kind.currentData()=='part')

    def change_palette(self,*_):
        if not self.updating:self.populate_palette()
        self.edit_version.setEnabled(self.edit_kind.currentData()=='set')

    def pick_item(self):
        picker=ImportItemPicker(self.db,self.edit_source.currentData(),self.edit_kind.currentData(),self)
        def chosen(result):
            if result==QDialog.DialogCode.Accepted and picker.item:self.edit_ref.setText(picker.item['ref'])
        show_window(picker,self,chosen)

    def save_correction(self):
        row=self.selected_row()
        if not row or row['imported']:return
        index=self.edit_color.currentIndex();text=self.edit_color.currentText().strip()
        color=self.edit_color.currentData() if index>=0 and text==self.edit_color.itemText(index) else text
        payload={'source':self.edit_source.currentData(),'kind':self.edit_kind.currentData(),'ref':self.edit_ref.text().strip(),'color':str(color or '') if self.edit_kind.currentData()=='part' else '', 'quantity':self.edit_quantity.text().strip()}
        payload['inventory_version']=self.edit_version.text().strip() if self.edit_kind.currentData()=='set' else ''
        try:imports.update_row(self.db,self.job_id,row['ordinal'],payload);self.refresh()
        except Exception as error:QMessageBox.warning(self,tr('Correction impossible'),str(error))

    def import_selected(self):
        if not self.job_id:return
        try:
            imports.update_destination(self.db,self.job_id,self.destination.currentData(),self.target.currentData(),self.name.text());imports.import_ready(self.db,self.job_id)
            self.load_job(self.job_id);notify_changed(self)
        except Exception as error:QMessageBox.warning(self,tr('Import interrompu'),str(error))

