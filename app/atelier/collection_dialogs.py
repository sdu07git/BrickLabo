"""Small, modeless entry points for the persistent collection workflows."""
import csv
import json
import sqlite3
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTableWidget,QHeaderView,QAbstractItemView,
    QDialogButtonBox,QMessageBox,QFileDialog,QInputDialog,QScrollArea,QWidget)
from .i18n import tr,tf
from .ui_common import FlowLayout,async_task
from .result_tables import fill_table,row_index
from .windows import show_window as show_managed,notify_changed
from .fileio import atomic_output
from . import collection_workflows as work
from .drawer_inventory import color_names,color_label


def close_children(parent):
    from shiboken6 import isValid
    for child in list(getattr(parent,'_workflow_children',[])):
        if isValid(child):child.reject()


def show_window(window,parent=None,on_finished=None,**kwargs):
    if parent is None:return show_managed(window,parent,on_finished,**kwargs)
    if not hasattr(parent,'_workflow_children'):parent._workflow_children=[]
    parent._workflow_children.append(window)
    def finished(result):
        if window in parent._workflow_children:parent._workflow_children.remove(window)
        if not getattr(parent,'closed',False) and on_finished:on_finished(result)
    return show_managed(window,parent,finished,**kwargs)


class WorkflowDialog(QDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.closed=False
    def done(self,result):
        self.closed=True;close_children(self);super().done(result)


def safe(parent,callback):
    try:return callback()
    except (ValueError,sqlite3.Error,OSError,KeyError,TypeError) as error:
        QMessageBox.warning(parent,tr('Outils de collection'),str(error));return None


def table(headers):
    widget=QTableWidget(0,len(headers));widget.setHorizontalHeaderLabels(headers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    widget.setSortingEnabled(True);widget.verticalHeader().setDefaultSectionSize(36)
    return widget


def preview_item(db,identity,color,expected=None):
    item=db.get_item(identity)
    if not item or expected and any(item[k]!=expected[k] for k in ('source','kind','ref')):return None
    return dict(item,chosen_color=color)


def export_rows(parent,headers,rows,name):
    path,_=QFileDialog.getSaveFileName(parent,tr('Exporter le tableau'),name,'CSV (*.csv)')
    if not path:return
    def write():
        with atomic_output(path) as temp:
            with temp.open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(headers);writer.writerows(rows)
    safe(parent,write)


class SessionPicker(WorkflowDialog):
    def __init__(self,db,kind,parent,chosen):
        super().__init__(parent);self.setWindowTitle(tr('Reprendre une session'));self.resize(740,440)
        self.rows=work.sessions(db,kind);self.chosen=chosen
        layout=QVBoxLayout(self);self.table=table([tr('Nom'),tr('Création'),tr('Dernière modification')]);layout.addWidget(self.table)
        fill_table(self.table,[(r['name'],r['created'],r['updated']) for r in self.rows])
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Open|QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons);buttons.accepted.connect(self.open);buttons.rejected.connect(self.reject);self.table.itemDoubleClicked.connect(self.open)
        if self.rows:self.table.selectRow(0)
    def open(self,*_):
        index=row_index(self.table)
        if 0<=index<len(self.rows):
            if self.chosen(self.rows[index]['id']) is not False:self.accept()


class CountDialog(WorkflowDialog):
    def __init__(self,db,identity,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.identity=identity;self.engine=engine
        self.record=work.session(db,identity,'count');self.rows=self.record['data']['rows'];self.spins=[];self.closed=False;self.dirty=False;self.palette=color_names(db)
        self.setWindowTitle(tr('Inventaire guidé')+' · '+self.record['name']);self.resize(1120,680)
        layout=QVBoxLayout(self);note=QLabel(tr('Compte les pièces réellement présentes. Les observations sont sauvegardées ; le stock et les tiroirs ne sont pas modifiés. « Non compté » est différent de zéro.'));note.setWordWrap(True);layout.addWidget(note)
        controls=FlowLayout();self.filter=QComboBox()
        for caption,key in [(tr('Toutes les lignes'),'all'),(tr('À compter'),'pending'),(tr('Pièces manquantes'),'missing'),(tr('Pièces en surplus'),'surplus')]:self.filter.addItem(caption,key)
        controls.addWidget(self.filter)
        save=QPushButton(tr('Enregistrer le comptage'));save.clicked.connect(self.save);controls.addWidget(save)
        export=QPushButton(tr('Exporter le comptage…'));export.clicked.connect(self.export);controls.addWidget(export);layout.addLayout(controls)
        self.table=table([tr('Source'),tr('Référence'),tr('Pièce'),tr('Couleur'),tr('Tiroir'),tr('Attendu'),tr('Compté'),tr('Manquante'),tr('Surplus'),tr('Aperçu')]);layout.addWidget(self.table,1)
        fill_table(self.table,[(r['source'],r['ref'],r['name'],color_label(dict(r,chosen_color=r['color']),self.palette),str(r.get('col',''))+'/'+str(r.get('row','')) if r.get('drawer_id') else '',r['expected'] if r['expected'] is not None else '?','','','',tr('3D / photo à charger')) for r in self.rows])
        self.table.setSortingEnabled(False)
        for physical in range(self.table.rowCount()):
            index=row_index(self.table,physical);row=self.rows[index];spin=QSpinBox();spin.setRange(-1,1000000000);spin.setSpecialValueText(tr('Non compté'));spin.setValue(row['counted'] if row['counted'] is not None else -1)
            self.table.setCellWidget(physical,6,spin);self.spins.append((index,spin));spin.valueChanged.connect(self.edited)
        self.table.setSortingEnabled(True)
        for column,width in enumerate((60,90,230,105,65,75,115,85,75,110)):self.table.setColumnWidth(column,width)
        header=self.table.horizontalHeader()
        for position,column in enumerate((0,1,3,4,5,6,7,8,9,2)):header.moveSection(header.visualIndex(column),position)
        from .thumbnails import PartThumbnails
        self.thumbs=PartThumbnails(self.table,db,engine,self.visible_parts,9,self) if engine else None
        if self.thumbs:self.table.model().layoutChanged.connect(self.thumbs.reset)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(450);self.timer.timeout.connect(self.save)
        self.filter.currentIndexChanged.connect(self.update_rows);self.update_rows()
    def visible_parts(self):
        return [preview_item(self.db,self.rows[row_index(self.table,n)]['item_id'],self.rows[row_index(self.table,n)]['color'],self.rows[row_index(self.table,n)]) for n in range(self.table.rowCount())]
    def counts(self):return {index:None if spin.value()<0 else spin.value() for index,spin in self.spins}
    def edited(self,*_):self.dirty=True;self.timer.start();self.update_rows()
    def update_rows(self,*_):
        from PySide6.QtWidgets import QTableWidgetItem
        counts=self.counts();mode=self.filter.currentData();self.table.setSortingEnabled(False)
        for physical in range(self.table.rowCount()):
            index=row_index(self.table,physical);row=self.rows[index];count=counts[index];expected=row['expected']
            missing=max(0,expected-count) if count is not None and expected is not None else None
            surplus=max(0,count-expected) if count is not None and expected is not None else None
            for col,val in [(6,count),(7,missing),(8,surplus)]:
                cell=QTableWidgetItem();cell.setData(Qt.ItemDataRole.DisplayRole,val if val is not None else '');self.table.setItem(physical,col,cell)
            show=mode=='all' or mode=='pending' and count is None or mode=='missing' and bool(missing) or mode=='surplus' and bool(surplus)
            self.table.setRowHidden(physical,not show)
        self.table.setSortingEnabled(True)
        body={'rows':[dict(r,counted=counts[n]) for n,r in enumerate(self.rows)]};total=work.count_totals(body)
        self.status.setText(tf('{0} à compter · {1} pièce(s) comptée(s) · {2} manquante(s) · {3} en surplus',total['remaining'],total['counted'],total['missing'],total['surplus']))
    def save(self,*_):
        self.timer.stop()
        if not self.dirty:return True
        try:
            counts=self.counts();self.record=work.save_count(self.db,self.identity,[counts[n] for n in range(len(self.rows))],self.record['body']);self.dirty=False;return True
        except (ValueError,sqlite3.Error,OSError) as error:
            self.status.setText(str(error));return False
    def export(self):
        counts=self.counts();export_rows(self,[tr('Source'),tr('Référence'),tr('Couleur'),tr('Tiroir'),tr('Attendu'),tr('Compté'),tr('Manquante'),tr('Surplus')],
            [(r['source'],r['ref'],r['color'],str(r.get('col',''))+'/'+str(r.get('row','')) if r.get('drawer_id') else '',r['expected'],counts[n],max(0,r['expected']-counts[n]) if r['expected'] is not None and counts[n] is not None else '',max(0,counts[n]-r['expected']) if r['expected'] is not None and counts[n] is not None else '') for n,r in enumerate(self.rows)],'BrickLabo_comptage.csv')
    def done(self,result):
        if not self.save():
            if QMessageBox.question(self,tr('Inventaire guidé'),tr('Le comptage n’a pas pu être enregistré. Fermer sans conserver les dernières modifications ? Exporte-les avant de confirmer.'))!=QMessageBox.StandardButton.Yes:return
        self.closed=True;self.timer.stop()
        if self.thumbs:self.thumbs.stop()
        super().done(result)


class InventoryHub(WorkflowDialog):
    def __init__(self,db,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.setWindowTitle(tr('Inventaire guidé'));self.resize(520,280)
        layout=QVBoxLayout(self);self.cabinet=QComboBox()
        for wall in db.rows('SELECT id,name FROM storage_walls ORDER BY y,x,id'):self.cabinet.addItem(wall['name'],wall['id'])
        layout.addWidget(self.cabinet)
        for label,callback in [(tr('Compter le meuble sélectionné'),self.new_cabinet),(tr('Compter un set…'),self.new_set),(tr('Reprendre un comptage…'),self.resume)]:
            button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button)
    def open_count(self,identity):
        result=safe(self,lambda:CountDialog(self.db,identity,self.engine,self))
        if result:show_window(result,self)
        return result is not None
    def new_cabinet(self):
        identity=safe(self,lambda:work.start_count(self.db,'cabinet',self.cabinet.currentData()))
        if identity:self.open_count(identity)
    def new_set(self):
        from .set_picker import SetPicker
        from .projects_panel import ReferencePicker
        picker=SetPicker(self.db,self.engine,self) if self.engine else ReferencePicker(self.db,'set',self)
        def chosen(result):
            if result and picker.chosen:
                identity=safe(self,lambda:work.start_count(self.db,'set',picker.chosen['id']))
                if identity:self.open_count(identity)
        show_window(picker,self,chosen)
    def resume(self):show_window(SessionPicker(self.db,'count',self,self.open_count),self)


class LotsDialog(WorkflowDialog):
    def __init__(self,db,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.rows=[];self.identity=None
        self.setWindowTitle(tr('Lots d’achat et d’import'));self.resize(950,650);layout=QVBoxLayout(self)
        self.table=table([tr('Nom'),tr('Provenance'),tr('Prix'),tr('Date'),tr('État')]);layout.addWidget(self.table,1)
        for col,width in enumerate((220,125,90,185,90)):self.table.setColumnWidth(col,width)
        form=QFormLayout();self.name=QLineEdit();self.provenance=QLineEdit();self.price=QDoubleSpinBox();self.price.setRange(0,10000000);self.price.setDecimals(2);self.price.setSuffix(' €');self.comment=QLineEdit()
        for title,widget in [(tr('Nom'),self.name),(tr('Provenance'),self.provenance),(tr('Prix'),self.price),(tr('Commentaire'),self.comment)]:form.addRow(title,widget)
        layout.addLayout(form);bar=FlowLayout()
        for title,callback in [(tr('Nouveau lot'),self.new),(tr('Enregistrer le lot'),self.save),(tr('Ajouter au lot…'),self.add),(tr('Annuler les apports du lot…'),self.cancel),(tr('Actualiser'),self.refresh)]:
            button=QPushButton(title);button.clicked.connect(callback);bar.addWidget(button)
        layout.addLayout(bar);correction=QPushButton(tr('Corriger la quantité du lot…'));correction.clicked.connect(self.correct);layout.addWidget(correction);self.detail=table([tr('Source'),tr('Référence'),tr('Couleur'),tr('Quantité'),tr('Destination')]);layout.addWidget(self.detail,1)
        note=QLabel(tr('Les nouveaux imports sont suivis automatiquement par lot. Les anciens ajouts ne sont pas reconstitués. L’annulation retire seulement les apports suivis ; elle est refusée si le stock restant ne couvre plus les tiroirs ou les réservations.'));note.setWordWrap(True);layout.addWidget(note)
        self.table.itemSelectionChanged.connect(self.select);self.refresh()
    def refresh(self):
        wanted=self.identity;self.rows=self.db.rows('SELECT * FROM purchase_lots ORDER BY created DESC,rowid DESC')
        self.table.blockSignals(True);fill_table(self.table,[(r['name'],r['provenance'],f"{r['price_cents']/100:.2f} €",r['created'],tr('Annulé') if r['cancelled'] else tr('Actif')) for r in self.rows]);self.table.blockSignals(False)
        index=next((n for n,r in enumerate(self.rows) if r['id']==wanted),0)
        if self.rows:self.table.selectRow(next(n for n in range(self.table.rowCount()) if row_index(self.table,n)==index))
        self.select()
    def select(self):
        index=row_index(self.table);row=self.rows[index] if 0<=index<len(self.rows) else None;self.identity=row['id'] if row else None
        for key,widget in [('name',self.name),('provenance',self.provenance),('comment',self.comment)]:widget.setText(row[key] if row else '')
        self.price.setValue(row['price_cents']/100 if row else 0)
        parts=self.db.rows('SELECT e.*,i.source,i.ref FROM purchase_lot_entries e JOIN items i ON i.id=e.item_id WHERE lot_id=?',(self.identity,))
        self.parts=parts
        fill_table(self.detail,[(r['source'],r['ref'],r['color'],r['quantity'],tr('Mon stock set') if r['scope']=='stock_sets' else tr('Mon stock')) for r in parts])
    def new(self):self.identity=None;self.table.clearSelection();self.name.clear();self.provenance.clear();self.comment.clear();self.price.setValue(0);self.name.setFocus()
    def save(self):
        def write():
            if not self.identity:self.identity=work.create_lot(self.db,self.name.text(),self.provenance.text(),round(self.price.value()*100),self.comment.text())
            else:
                if not self.name.text().strip():raise ValueError(tr('Nom du lot obligatoire.'))
                self.db.run('UPDATE purchase_lots SET name=?,provenance=?,price_cents=?,comment=? WHERE id=?',(self.name.text().strip(),self.provenance.text().strip(),round(self.price.value()*100),self.comment.text().strip(),self.identity))
            self.refresh();return True
        return safe(self,write)
    def add(self):
        if not self.identity and not self.save():return
        captured=self.identity
        from .projects_panel import ReferencePicker,color_options
        picker=ReferencePicker(self.db,('part','minifig','set'),self)
        def chosen(result):
            if not result or not picker.chosen:return
            item=dict(picker.chosen);dialog=QDialog(self);dialog.setWindowTitle(tr('Ajouter au lot'));form=QFormLayout(dialog)
            form.addRow(QLabel(item['source']+' '+item['ref']+' · '+item['name']));color=QComboBox();color.addItem(tr('Non précisée'),'')
            for key,label in color_options(self.db,item):color.addItem(label,key)
            form.addRow(tr('Couleur'),color);quantity=QSpinBox();quantity.setRange(1,1000000000);form.addRow(tr('Quantité'),quantity)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
            def save():
                if safe(dialog,lambda:work.add_to_lot(self.db,captured,item['id'],color.currentData(),quantity.value())):
                    notify_changed(self);self.refresh();dialog.accept()
            buttons.accepted.connect(save);show_window(dialog,self)
        show_window(picker,self,chosen)
    def correct(self):
        index=row_index(self.detail)
        if not 0<=index<len(self.parts):return
        row=dict(self.parts[index]);captured=self.identity
        qty,ok=QInputDialog.getInt(self,tr('Corriger le lot'),tr('Quantité de cette référence apportée par le lot'),row['quantity'],0,1000000000)
        if not ok:return
        def run():
            work.correct_lot_quantity(self.db,captured,row['scope'],row['item_id'],row['color'],qty);self.refresh();notify_changed(self)
        safe(self,run)
    def cancel(self):
        captured=self.identity
        if not captured:return
        if QMessageBox.question(self,tr('Annuler le lot'),tr('Retirer du stock les quantités ajoutées par ce lot ? Cette action peut être annulée.'))!=QMessageBox.StandardButton.Yes:return
        def run():work.cancel_lot(self.db,captured);self.refresh();notify_changed(self)
        safe(self,run)


class PickListDialog(WorkflowDialog):
    def __init__(self,db,project_id,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.project_id=project_id;self.rows=[];self.palette=color_names(db);self.setWindowTitle(tr('Liste de prélèvement'));self.resize(1050,640)
        layout=QVBoxLayout(self);note=QLabel(tr('Prélève les quantités réellement prises dans les tiroirs. Elles restent possédées et sont réservées au projet. Retourne les prélèvements avant de supprimer le projet ou de libérer ces réservations.'));note.setWordWrap(True);layout.addWidget(note)
        self.table=table([tr('Meuble'),tr('Tiroir'),tr('Source'),tr('Référence'),tr('Couleur'),tr('À prendre'),tr('Déjà prélevée'),tr('Aperçu')]);layout.addWidget(self.table,1)
        self.taken_table=table([tr('Meuble'),tr('Tiroir'),tr('Source'),tr('Référence'),tr('Couleur'),tr('Déjà prélevée')])
        from PySide6.QtWidgets import QTabWidget
        tabs=QTabWidget();layout.removeWidget(self.table);tabs.addTab(self.table,tr('À prélever'));tabs.addTab(self.taken_table,tr('Déjà prélevées'));layout.addWidget(tabs,1)
        self.engine=engine
        from .thumbnails import PartThumbnails
        self.thumbs=PartThumbnails(self.table,db,engine,self.visible_parts,7,self) if engine else None
        if self.thumbs:self.table.model().layoutChanged.connect(self.thumbs.reset)
        bar=FlowLayout()
        for label,callback in [(tr('Prélever la ligne…'),self.take),(tr('Retourner tous les prélèvements'),self.return_all),(tr('Exporter la liste…'),self.export),(tr('Actualiser'),self.refresh)]:
            button=QPushButton(label);button.clicked.connect(callback);bar.addWidget(button)
        layout.addLayout(bar);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);self.refresh()
    def visible_parts(self):return [preview_item(self.db,self.rows[row_index(self.table,n)]['item_id'],self.rows[row_index(self.table,n)]['color']) for n in range(self.table.rowCount())]
    def refresh(self):
        self.rows=work.pick_list(self.db,self.project_id)
        fill_table(self.table,[(r['cabinet'],str(r['col'])+'/'+str(r['row']) if r['drawer_id'] else '',r['source'],r['ref'],tr('Toutes les couleurs') if r.get('ignore_colors') and not r['drawer_id'] else color_label(dict(r,chosen_color=r['color']),self.palette),r['suggested'],r['taken'],tr('3D / photo à charger')) for r in self.rows])
        self.taken_rows=self.db.rows('''SELECT w.name AS cabinet,d.col,d.row,i.source,i.ref,p.color,p.quantity
          FROM project_physical_picks p JOIN storage_drawers d ON d.id=p.drawer_id JOIN storage_walls w ON w.id=d.wall_id
          JOIN items i ON i.id=p.item_id WHERE p.project_id=? ORDER BY w.y,w.x,d.row,d.col,i.ref,p.color''',(self.project_id,))
        fill_table(self.taken_table,[(r['cabinet'],str(r['col'])+'/'+str(r['row']),r['source'],r['ref'],color_label(dict(r,chosen_color=r['color']),self.palette),r['quantity']) for r in self.taken_rows])
        total=self.db.rows('SELECT COALESCE(SUM(quantity),0) AS n FROM project_physical_picks WHERE project_id=?',(self.project_id,))[0]['n']
        self.status.setText(tf('{0} pièce(s) prélevée(s) pour ce projet. Les lignes sans emplacement compté ne peuvent pas être prélevées ici.',total))
        if self.thumbs:self.thumbs.reset()
    def take(self):
        index=row_index(self.table)
        if not 0<=index<len(self.rows):return
        row=dict(self.rows[index])
        if not row['drawer_id']:return
        qty,ok=QInputDialog.getInt(self,tr('Prélèvement'),tr('Quantité réellement prise'),row['suggested'],1,row['suggested'])
        if not ok:return
        def run():
            work.pick(self.db,self.project_id,row['item_id'],row['color'],row['drawer_id'],qty,row['quantity'],need_color=row.get('need_color',row['color']));self.refresh();notify_changed(self)
        safe(self,run)
    def return_all(self):
        if QMessageBox.question(self,tr('Retour des pièces'),tr('Confirme que toutes les pièces prélevées ont été remises dans leurs tiroirs d’origine.'))!=QMessageBox.StandardButton.Yes:return
        def run():work.return_picks(self.db,self.project_id);self.refresh();notify_changed(self)
        safe(self,run)
    def export(self):
        rows=[(r['cabinet'],str(r['col'])+'/'+str(r['row']) if r['drawer_id'] else '',r['source'],r['ref'],'*' if r.get('ignore_colors') and not r['drawer_id'] else r['color'],r['suggested'],r['taken']) for r in self.rows]
        rows.extend((r['cabinet'],str(r['col'])+'/'+str(r['row']),r['source'],r['ref'],r['color'],0,r['quantity']) for r in self.taken_rows)
        export_rows(self,[tr('Meuble'),tr('Tiroir'),tr('Source'),tr('Référence'),tr('Couleur'),tr('À prendre'),tr('Déjà prélevée')],rows,'BrickLabo_prelevements.csv')
    def done(self,result):
        if self.thumbs:self.thumbs.stop()
        super().done(result)


class BuildComparisonDialog(WorkflowDialog):
    def __init__(self,db,engine=None,parent=None,options=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.candidates=[];self.result=None;self.busy=False;self.closed=False;self.generation=0
        self.setWindowTitle(tr('Comparer plusieurs reconstructions'));self.resize(1000,650)
        layout=QVBoxLayout(self);note=QLabel(tr('Choisis jusqu’à 16 sets. La comparaison cherche le plus grand nombre de sets entièrement réalisables ensemble, sans réutiliser une même pièce. Elle ne modifie pas le stock.'));note.setWordWrap(True);layout.addWidget(note)
        bar=FlowLayout()
        self.buttons=[]
        for label,callback in [(tr('Ajouter un set…'),self.add),(tr('Retirer le set sélectionné'),self.remove),(tr('Comparer les reconstructions'),self.compare),(tr('Créer les projets retenus…'),self.create_projects)]:
            button=QPushButton(label);button.clicked.connect(callback);bar.addWidget(button);self.buttons.append(button)
        self.stock_button=QPushButton(tr('Choisir le stock utilisable…'));self.stock_button.clicked.connect(self.choose_stock);bar.addWidget(self.stock_button)
        layout.addLayout(bar)
        from PySide6.QtWidgets import QCheckBox
        self.ignore=QCheckBox(tr('Ignorer les couleurs'));self.exclude=QCheckBox(tr('Exclure les minifigurines'));self.sets=QCheckBox(tr('Utiliser les pièces de mon stock set'));self.alternatives=QCheckBox(tr('Autoriser les briques alternatives équivalentes'))
        options=options or dict(exclude_minifigs=db.setting('build_exclude_minifigs',False),include_set_stock=db.setting('build_include_set_stock',True),allow_alternatives=db.setting('build_allow_alternatives',False),excluded_entries=db.setting('build_excluded_entries',[]));self.options=dict(options)
        for widget,key,default in [(self.ignore,'ignore_colors',False),(self.exclude,'exclude_minifigs',False),(self.sets,'include_set_stock',True),(self.alternatives,'allow_alternatives',False)]:
            widget.setChecked(options.get(key,default));layout.addWidget(widget);widget.toggled.connect(self.invalidate)
        self.scope=QLabel(tr('La sélection du stock utilisable est reprise de la recherche. Les projets déjà réservés sont déduits.'));self.scope.setWordWrap(True);layout.addWidget(self.scope)
        self.table=table([tr('Source'),tr('Référence'),tr('Nom'),tr('Exemplaires'),tr('Résultat')]);layout.addWidget(self.table,1)
        for col,width in enumerate((60,90,260,100,260)):self.table.setColumnWidth(col,width)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);self.refresh()
    def choose_stock(self):
        from .stock_filter import StockFilterDialog
        def saved(result):
            if not result:return
            self.options['excluded_entries']=self.db.setting('build_excluded_entries',[])
            self.sets.setChecked(self.db.setting('build_include_set_stock',True));self.invalidate()
        show_window(StockFilterDialog(self.db,self,self.engine),self,saved)
    def stock_changed(self):
        if self.result and self.result['stock_revision']!=self.db.stock_revision():
            self.invalidate();self.status.setText(tr('Le stock a changé. Relance la comparaison.'))
    def invalidate(self,*_):self.generation+=1;self.result=None;self.refresh()
    def refresh(self):
        selected=set(self.result['selected']) if self.result else set()
        labels=[]
        for n,row in enumerate(self.candidates):
            if not self.result:label=''
            elif n in selected:label=tr('Retenu')
            else:
                required=self.result['choices'][n]['required'];remaining=self.result['remaining']
                missing=sum(max(0,v-remaining[k]) for k,v in required.items())
                label=tf('Non retenu : {0} pièce(s) manquante(s)',missing)
            labels.append((row['source'],row['ref'],row['name'],row['copies'],label))
        fill_table(self.table,labels)
        self.buttons[3].setEnabled(bool(selected) and not self.busy)
    def add(self):
        if len(self.candidates)>=16:return
        from .set_picker import SetPicker
        from .projects_panel import ReferencePicker
        picker=SetPicker(self.db,self.engine,self) if self.engine else ReferencePicker(self.db,'set',self)
        def chosen(result):
            if result and picker.chosen and not self.busy and len(self.candidates)<16:
                item=dict(picker.chosen)
                if any(r['id']==item['id'] for r in self.candidates):return
                copies,ok=QInputDialog.getInt(self,tr('Exemplaires'),tr('Nombre d’exemplaires de ce set'),1,1,10000)
                if ok:self.candidates.append(dict(item,copies=copies));self.invalidate()
        show_window(picker,self,chosen)
    def remove(self):
        index=row_index(self.table)
        if 0<=index<len(self.candidates):self.candidates.pop(index);self.invalidate()
    def compare(self):
        if self.busy or not self.candidates:return
        generation=self.generation
        choices=[(r['id'],r['copies']) for r in self.candidates]
        options=dict(ignore_colors=self.ignore.isChecked(),exclude_minifigs=self.exclude.isChecked(),include_set_stock=self.sets.isChecked(),allow_alternatives=self.alternatives.isChecked(),excluded_entries=self.options.get('excluded_entries'))
        self.busy=True
        for widget in self.buttons+[self.stock_button,self.ignore,self.exclude,self.sets,self.alternatives]:widget.setEnabled(False)
        self.status.setText(tr('Comparaison en cours…'))
        def done(result):
            self.busy=False
            if self.closed:return
            self.result=result if result['stock_revision']==self.db.stock_revision() and generation==self.generation else None
            for widget in self.buttons+[self.stock_button,self.ignore,self.exclude,self.sets,self.alternatives]:widget.setEnabled(True)
            self.refresh()
            if self.result is None:self.status.setText(tr('Le stock a changé. Relance la comparaison.'));return
            self.status.setText(tf('{0} set(s) retenu(s) sur {1} ; {2} pièce(s) restent disponibles.',sum(result['choices'][n]['copies'] for n in result['selected']),sum(r['copies'] for r in result['choices']),sum(result['remaining'].values())))
        def failed(error):
            self.busy=False
            if self.closed:return
            for widget in self.buttons+[self.stock_button,self.ignore,self.exclude,self.sets,self.alternatives]:widget.setEnabled(True)
            self.status.setText(error);self.refresh()
        async_task(self,lambda progress:work.compare_builds(self.db,choices,**options),done,failed)
    def create_projects(self):
        if not self.result:return
        if self.result['stock_revision']!=self.db.stock_revision():self.stock_changed();return
        if self.ignore.isChecked():
            QMessageBox.information(self,tr('Projets'),tr('Relance la comparaison avec les couleurs respectées avant de créer les projets.'));return
        # Projects store requirements, without silently reserving set stock.
        if QMessageBox.question(self,tr('Projets'),tr('Créer les projets retenus sans réserver ni déplacer les pièces ?'))!=QMessageBox.StandardButton.Yes:return
        def run():
            work.create_comparison_projects(self.db,self.result,self.exclude.isChecked(),self.alternatives.isChecked(),ignore_colors=self.ignore.isChecked())
            notify_changed(self);self.buttons[3].setEnabled(False)
        safe(self,run)
    def done(self,result):self.closed=True;super().done(result)


class StartAssistant(WorkflowDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.db=owner.db
        saved=self.db.setting('start_assistant_page',0);self.page=saved if type(saved) is int and 0<=saved<=3 else 0
        self.setWindowTitle(tr('Bien démarrer avec BrickLabo'));self.resize(650,440);layout=QVBoxLayout(self)
        self.title=QLabel();self.title.setWordWrap(True);layout.addWidget(self.title);self.text=QLabel();self.text.setWordWrap(True);layout.addWidget(self.text,1)
        self.action=QPushButton();self.action.clicked.connect(self.run_action);layout.addWidget(self.action)
        row=QHBoxLayout();self.back=QPushButton(tr('Précédent'));self.back.clicked.connect(lambda:self.move(-1));row.addWidget(self.back)
        self.next=QPushButton(tr('Suivant'));self.next.clicked.connect(lambda:self.move(1));row.addWidget(self.next);layout.addLayout(row)
        later=QPushButton(tr('Reprendre plus tard'));later.clicked.connect(self.reject);layout.addWidget(later);self.update_page()
    def update_page(self):
        pages=[(tr('1. Les catalogues'),tr('Importe les catalogues et les inventaires Rebrickable ou BrickLink depuis Mise à jour des données. Les clés API sont facultatives pour les fichiers locaux.'),tr('Ouvrir les données')),
               (tr('2. Les rendus LDraw'),tr('Choisis ou mets à jour complete.zip depuis la fenêtre des données pour disposer des rendus 3D. Les photographies restent utilisables sans LDraw.'),tr('Ouvrir les données')),
               (tr('3. Ton stock'),tr('Importe tes pièces en vrac ou tes sets. Les deux stocks restent séparés. Chaque nouvel import est suivi dans Lots d’achat et d’import.'),tr('Importer mon stock')),
               (tr('4. Tes meubles'),tr('Crée tes meubles et tes tiroirs dans Mon rangement. Tu peux ensuite ranger les pièces, compter leur contenu et préparer les prélèvements des projets.'),tr('Ouvrir Mon rangement'))]
        title,text,action=pages[self.page];self.title.setText(title);self.text.setText(text);self.action.setText(action);self.back.setEnabled(self.page>0);self.next.setText(tr('Terminer') if self.page==3 else tr('Suivant'))
    def move(self,amount):
        if self.page==3 and amount>0:self.db.set_setting('start_assistant_completed',True);self.db.set_setting('start_assistant_page',0);self.accept();return
        self.page=max(0,min(3,self.page+amount));self.db.set_setting('start_assistant_page',self.page);self.update_page()
    def run_action(self):
        if self.page in (0,1):self.owner.imports()
        elif self.page==2:self.owner.import_stock('stock')
        else:
            from .app import NAV
            self.owner.nav.setCurrentRow(next(n for n,row in enumerate(NAV) if row[3]=='storage'))
            self.owner.storage.new_wall()
