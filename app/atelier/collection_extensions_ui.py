"""Modeless entry points for lot analysis, MOC projects, set claims and shopping."""
from pathlib import Path
import threading

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QVBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QSpinBox,QCheckBox,
    QFormLayout,QDialogButtonBox,QTableWidgetItem,QAbstractItemView,QFileDialog,QInputDialog,QTabWidget,QSplitter)

from .i18n import tr,tf
from .ui_common import FlowLayout,async_task
from .collection_dialogs import WorkflowDialog,table,safe,export_rows
from .windows import notify_changed
from .result_tables import fill_table,row_index


def fit_window(window,width,height):
    available=window.screen().availableGeometry();window.resize(min(width,max(640,available.width()-32)),min(height,max(400,available.height()-56)))


class SetAllocationDialog(WorkflowDialog):
    def __init__(self,db,project_id,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.project_id=project_id;self.engine=engine
        from . import set_allocations as work
        self.setWindowTitle(tr('Sets affectés au projet'));fit_window(self,1050,640);layout=QVBoxLayout(self)
        note=QLabel(tr('Choisis combien d’exemplaires démonter pour ce projet. Leur inventaire est réservé à ce projet et exclu des autres recherches. Le stock en vrac reste disponible séparément. Les exemplaires d’une même ligne sont équivalents si leur inventaire suivi est divisible ; sinon le groupe entier doit être affecté.'));note.setWordWrap(True);layout.addWidget(note)
        self.all=QCheckBox(tr('Utiliser tous les sets encore libres, sans les réserver'));self.all.setChecked(not db.rows('SELECT 1 FROM project_set_sources WHERE project_id=?',(project_id,)));layout.addWidget(self.all)
        self.rows=work.choices(db,project_id);self.table=table([tr('Source'),tr('Référence'),tr('Nom'),tr('Possédés'),tr('Affectés ailleurs'),tr('Exemplaires pour ce projet'),tr('Suivi')]);layout.addWidget(self.table,1)
        fill_table(self.table,[(r['source'],r['ref'],r['name'],r['owned_copies'],r['other_copies'],'',r['error'] or (tr('Groupe entier uniquement') if r['group_only'] else tr('Inventaire du catalogue') if r['fallback'] else tr('Inventaire suivi'))) for r in self.rows],sortable=False)
        self.spins=[]
        for index,row in enumerate(self.rows):
            spin=QSpinBox();spin.setRange(0,max(0,row['owned_copies']-row['other_copies']));spin.setValue(row['selected_copies']);spin.setEnabled(not row['error']);self.table.setCellWidget(index,5,spin);self.spins.append(spin)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(self.reject)
        def save():
            def run():
                work.assign(db,project_id,{r['entry_id']:spin.value() for r,spin in zip(self.rows,self.spins)},self.all.isChecked());notify_changed(self);self.accept()
            safe(self,run)
        buttons.accepted.connect(save)


class MOCImportDialog(WorkflowDialog):
    def __init__(self,db,parent=None,created=lambda identity:None):
        super().__init__(parent);self.db=db;self.created=created;self.rows=[];self.busy=False;self.loading=False
        self.setWindowTitle(tr('Importer un inventaire MOC en projet'));fit_window(self,1100,700);layout=QVBoxLayout(self)
        note=QLabel(tr('Importe un CSV Rebrickable ou un XML BrickLink comme besoins d’un projet. Corrige les cellules Source, Type, Référence, Couleur et Quantité si nécessaire. Aucune pièce n’est ajoutée au stock.'));note.setWordWrap(True);layout.addWidget(note)
        bar=FlowLayout();self.source=QComboBox()
        for title,value in [(tr('Détection automatique'),'auto'),('Rebrickable','RB'),('BrickLink','BL')]:self.source.addItem(title,value)
        bar.addWidget(self.source);open_button=QPushButton(tr('Ouvrir un inventaire MOC…'));open_button.clicked.connect(self.load);bar.addWidget(open_button);layout.addLayout(bar)
        self.name=QLineEdit();self.name.setPlaceholderText(tr('Nom du projet'));layout.addWidget(self.name);self.ignore=QCheckBox(tr('Ignorer les couleurs'));layout.addWidget(self.ignore)
        self.table=table([tr('Source'),tr('Type'),tr('Référence'),tr('Couleur'),tr('Quantité'),tr('Nom'),tr('À corriger')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed);layout.addWidget(self.table,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.save_button=QPushButton(tr('Créer le projet depuis le fichier'));self.save_button.clicked.connect(self.save);self.save_button.setEnabled(False);layout.addWidget(self.save_button)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(350);self.timer.timeout.connect(self.validate_rows);self.table.cellChanged.connect(lambda *_:self.timer.start() if not self.loading else None)
    def display(self):
        self.loading=True;self.table.blockSignals(True)
        fill_table(self.table,[(r.get('source',''),r.get('kind',''),r.get('ref',''),r.get('color',''),r.get('quantity',''),r['item']['name'] if r.get('item') else '',r.get('issue','')) for r in self.rows])
        for row in range(self.table.rowCount()):
            for column in (5,6):self.table.item(row,column).setFlags(self.table.item(row,column).flags()&~Qt.ItemFlag.ItemIsEditable)
        self.table.blockSignals(False);self.loading=False;errors=sum(bool(r.get('issue')) for r in self.rows)
        self.save_button.setEnabled(bool(self.rows) and not errors and not self.busy);self.status.setText(tf('{0} lignes · {1} à corriger',len(self.rows),errors))
    def load(self):
        path,_=QFileDialog.getOpenFileName(self,tr('Inventaire du MOC'),'',tr('Inventaires (*.csv *.tsv *.xml *.txt)'))
        if not path or self.busy:return
        from .moc_import import preview
        self.busy=True;self.save_button.setEnabled(False);source=self.source.currentData()
        def done(rows):
            self.busy=False
            if self.closed:return
            self.rows=rows;self.name.setText(Path(path).stem);self.display()
        def failed(error):self.busy=False;self.status.setText(str(error))
        async_task(self,lambda progress:preview(self.db,path,source),done,failed)
    def validate_rows(self):
        if self.loading or self.busy or self.closed:return
        from .moc_import import resolve
        values=[None]*len(self.rows)
        for row in range(self.table.rowCount()):values[row_index(self.table,row)]={key:self.table.item(row,column).text().strip() for column,key in enumerate(('source','kind','ref','color','quantity'))}
        result=safe(self,lambda:resolve(self.db,values))
        if result is not None:self.rows=result;self.display()
    def save(self):
        self.timer.stop();self.validate_rows()
        from .moc_import import create_project
        def run():
            identity=create_project(self.db,self.name.text(),self.rows,self.ignore.isChecked());notify_changed(self);self.created(identity);self.accept()
        safe(self,run)
    def done(self,result):self.timer.stop();super().done(result)


class LotAnalysisDialog(WorkflowDialog):
    def __init__(self,db,engine=None,parent=None,lot_id=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.result=None;self.cancel=threading.Event();self.busy=False;self.generation=0
        self.setWindowTitle(tr('Analyser un lot de vrac'));fit_window(self,1150,760);layout=QVBoxLayout(self)
        note=QLabel(tr('Recherche des pistes parmi les inventaires locaux. Le score mesure une correspondance de pièces, sans prouver leur set d’origine. La combinaison proposée utilise chaque pièce du lot une seule fois ; elle peut nécessiter des achats.'));note.setWordWrap(True);layout.addWidget(note)
        bar=FlowLayout();self.lot=QComboBox()
        for r in db.rows('SELECT * FROM purchase_lots WHERE cancelled=0 ORDER BY created DESC'):self.lot.addItem(r['name'],r['id'])
        if lot_id:self.lot.setCurrentIndex(max(0,self.lot.findData(lot_id)))
        bar.addWidget(self.lot);self.ignore=QCheckBox(tr('Ignorer les couleurs'));bar.addWidget(self.ignore);self.minifigs=QCheckBox(tr('Exclure les minifigurines'));bar.addWidget(self.minifigs)
        self.free=QCheckBox(tr('Limiter au vrac actuellement libre'));self.free.setChecked(True);bar.addWidget(self.free);layout.addLayout(bar)
        options=FlowLayout();options.addWidget(QLabel(tr('Minimum possédé (%)')));self.minimum=QSpinBox();self.minimum.setRange(1,100);self.minimum.setValue(25);options.addWidget(self.minimum);options.addWidget(QLabel(tr('Nombre maximum de sets')));self.maximum=QSpinBox();self.maximum.setRange(1,20);self.maximum.setValue(6);options.addWidget(self.maximum)
        self.analyze_button=QPushButton(tr('Analyser ce lot'));self.analyze_button.clicked.connect(self.analyze);options.addWidget(self.analyze_button);layout.addLayout(options)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.suggestions=table([tr('Source'),tr('Référence'),tr('Nom'),tr('Possédé (%)'),tr('Pièces trouvées'),tr('Manquante'),tr('Pièces caractéristiques')]);self.tabs.addTab(self.suggestions,tr('Sets possibles'))
        self.combination=table([tr('Source'),tr('Référence'),tr('Exemplaires'),tr('Pièces du lot affectées'),tr('Pièces à acheter')]);self.tabs.addTab(self.combination,tr('Meilleure combinaison trouvée'))
        self.leftover=table([tr('Source'),tr('Référence'),tr('Couleur'),tr('Quantité')]);self.tabs.addTab(self.leftover,tr('Reste du lot'))
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.create_button=QPushButton(tr('Créer les projets de la combinaison'));self.create_button.setEnabled(False);self.create_button.clicked.connect(self.create);layout.addWidget(self.create_button)
        self.single_button=QPushButton(tr('Créer le projet du set sélectionné'));self.single_button.setEnabled(False);self.single_button.clicked.connect(self.create_one);layout.addWidget(self.single_button)
    def analyze(self):
        if self.busy or not self.lot.currentData():return
        from .lot_analysis import analyze
        self.busy=True;self.cancel=threading.Event();cancel=self.cancel;self.generation+=1;generation=self.generation;self.analyze_button.setEnabled(False);self.create_button.setEnabled(False)
        options=dict(ignore_colors=self.ignore.isChecked(),exclude_minifigs=self.minifigs.isChecked(),minimum=self.minimum.value(),max_sets=self.maximum.value(),cap_to_free=self.free.isChecked(),cancel=cancel);lot_id=self.lot.currentData()
        def done(result):
            self.busy=False
            if self.closed or generation!=self.generation:return
            self.analyze_button.setEnabled(True);self.result=result
            if result is None:return
            fill_table(self.suggestions,[(r['source'],r['ref'],r['name'],round(r['percent'],2),r['matched'],r['missing'],', '.join('/'.join(k) for k in r['distinctive'])) for r in result['suggestions']])
            fill_table(self.combination,[(r['source'],r['ref'],r['copies'],r['allocated'],r['combination_missing']) for r in result['choices']]);fill_table(self.leftover,[(source,ref,color,q) for (source,ref,color),q in sorted(result['remaining'].items())])
            self.create_button.setEnabled(bool(result['choices']));self.single_button.setEnabled(bool(result['suggestions']));self.status.setText(tf('{0} pistes affichées · {1} pièces du lot restantes · {2} inventaires indisponibles ou incomplets ignorés.',len(result['suggestions']),sum(result['remaining'].values()),result['excluded'])+'\n'+'\n'.join(result['warnings']))
        def failed(error):self.busy=False;self.analyze_button.setEnabled(True);self.status.setText(str(error))
        async_task(self,lambda progress:analyze(self.db,lot_id,progress=progress,**options),done,failed,lambda value:self.status.setText(str(value)))
    def create(self):
        from .lot_analysis import create_projects
        def run():
            identities=create_projects(self.db,self.result);notify_changed(self);self.status.setText(tf('{} projets créés sans modifier le stock ni réserver de pièces.',len(identities)))
        safe(self,run)
    def create_one(self):
        index=row_index(self.suggestions)
        if not self.result or not 0<=index<len(self.result['suggestions']):return
        from .lot_analysis import create_projects
        result=dict(self.result,choices=[dict(self.result['suggestions'][index],copies=1)],selected=[0])
        safe(self,lambda:(create_projects(self.db,result),notify_changed(self)))
    def done(self,result):self.cancel.set();self.generation+=1;super().done(result)


class ShoppingDialog(WorkflowDialog):
    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db;self.rows=[];self.setWindowTitle(tr('Liste d’achats commune aux projets'));fit_window(self,1120,720);layout=QVBoxLayout(self)
        note=QLabel(tr('Les besoins sont cumulés dans l’ordre des projets choisi à la création de la liste. Une pièce libre ne couvre qu’un seul besoin. Commandée ne signifie pas possédée : Réceptionner ajoute les pièces au vrac et enregistre un lot d’achat.'));note.setWordWrap(True);layout.addWidget(note)
        bar=FlowLayout();self.lists=QComboBox();bar.addWidget(self.lists)
        for title,callback in [(tr('Nouvelle liste d’achats…'),self.new),(tr('Recalculer les manquants'),self.recalculate)]:
            b=QPushButton(title);b.clicked.connect(callback);bar.addWidget(b)
        layout.addLayout(bar);self.table=table([tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('À recevoir'),tr('À commander'),tr('Commandées'),tr('Reçues'),tr('Correspondance BrickLink')]);layout.addWidget(self.table,1)
        controls=FlowLayout()
        for title,callback in [(tr('Régler la quantité commandée…'),self.order),(tr('Réceptionner la sélection…'),self.receive),(tr('Correspondance BrickLink…'),self.mapping),(tr('Exporter la liste en CSV…'),self.csv),(tr('Exporter Wanted List XML…'),self.xml)]:
            b=QPushButton(title);b.clicked.connect(callback);controls.addWidget(b)
        layout.addLayout(controls);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);self.lists.currentIndexChanged.connect(self.refresh);self.reload_lists()
    def reload_lists(self,preferred=None):
        old=preferred or self.lists.currentData();self.lists.blockSignals(True);self.lists.clear()
        for r in self.db.rows('SELECT * FROM shopping_lists ORDER BY created DESC,rowid DESC'):self.lists.addItem(r['name'],r['id'])
        self.lists.setCurrentIndex(max(0,self.lists.findData(old)));self.lists.blockSignals(False);self.refresh()
    def refresh(self):
        from . import project_shopping as work
        self.rows=work.rows(self.db,self.lists.currentData()) if self.lists.currentData() else []
        fill_table(self.table,[(r['source'],r['ref'],r['name'],tr('Toutes les couleurs') if r['color']=='*' else r['color'],r['missing'],r['to_order'],r['ordered'],r['received'],' / '.join(work.bricklink_mapping(self.db,r)[:2]) if not work.bricklink_mapping(self.db,r)[2] else tr('À renseigner')) for r in self.rows])
    def selected(self):
        index=row_index(self.table);return dict(self.rows[index]) if 0<=index<len(self.rows) else None
    def new(self):
        from . import projects,project_shopping
        from PySide6.QtWidgets import QDialog
        window=WorkflowDialog(self);window.setWindowTitle(tr('Choisir les projets pour les achats'));window.resize(700,500);layout=QVBoxLayout(window);name=QLineEdit(tr('Achats pour mes projets'));layout.addWidget(name)
        rows=[r for r in projects.list_projects(self.db) if r['status']!='completed'];choices=table([tr('Projet'),tr('Priorité')]);fill_table(choices,[(r['name'],'') for r in rows],sortable=False);spins=[]
        for index,row in enumerate(rows):
            item=choices.item(index,0);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked);spin=QSpinBox();spin.setRange(1,max(1,len(rows)));spin.setValue(index+1);spins.append(spin);choices.setCellWidget(index,1,spin)
        layout.addWidget(choices);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(window.reject)
        def save():
            def run():
                selection=sorted((spins[n].value(),n,r['id']) for n,r in enumerate(rows) if choices.item(n,0).checkState()==Qt.CheckState.Checked)
                identity=project_shopping.create(self.db,name.text(),[identity for priority,n,identity in selection]);self.reload_lists(identity);notify_changed(self);window.accept()
            safe(window,run)
        buttons.accepted.connect(save)
        from .windows import show_window
        show_window(window,self)
    def recalculate(self):
        if not self.lists.currentData():return
        from .project_shopping import recalculate
        def run():
            details,warnings=recalculate(self.db,self.lists.currentData());self.refresh();self.status.setText('\n'.join(warnings));notify_changed(self)
        safe(self,run)
    def order(self):
        row=self.selected()
        if row is None:return
        quantity,ok=QInputDialog.getInt(self,tr('Commande'),tr('Quantité totale commandée'),max(row['ordered'],row['received']),row['received'],1000000000)
        if not ok:return
        from .project_shopping import set_ordered
        safe(self,lambda:(set_ordered(self.db,row['list_id'],row['item_id'],row['color'],quantity),self.refresh(),notify_changed(self)))
    def receive(self):
        row=self.selected()
        if row is None:return
        maximum=max(row['target'],row['ordered'])-row['received']
        if maximum<=0:return
        actual=row['color']
        if actual=='*':
            from .projects_panel import color_options
            options=color_options(self.db,self.db.get_item(row['item_id']))
            if not options:self.status.setText(tr('Renseigne une couleur dans le catalogue avant la réception.'));return
            label,ok=QInputDialog.getItem(self,tr('Couleur reçue'),tr('Couleur réellement reçue'),[label for key,label in options],0,False)
            if not ok:return
            actual=next(key for key,title in options if title==label)
        quantity,ok=QInputDialog.getInt(self,tr('Réception'),tr('Quantité réellement reçue'),maximum,1,maximum)
        if not ok:return
        from .project_shopping import receive
        safe(self,lambda:(receive(self.db,row['list_id'],row['item_id'],row['color'],quantity,actual,row['received']),self.refresh(),notify_changed(self)))
    def mapping(self):
        row=self.selected()
        if row is None:return
        from .project_shopping import bricklink_mapping,set_mapping
        reference,color,issue=bricklink_mapping(self.db,row)
        reference,ok=QInputDialog.getText(self,tr('Correspondance BrickLink'),tr('Référence BrickLink vérifiée'),text=reference)
        if not ok:return
        if row['color']!='*' and row['kind']=='part':
            color,ok=QInputDialog.getText(self,tr('Correspondance BrickLink'),tr('Code couleur BrickLink vérifié'),text=color)
            if not ok:return
        safe(self,lambda:(set_mapping(self.db,row['list_id'],row['item_id'],row['color'],reference.strip(),color.strip()),self.refresh(),notify_changed(self)))
    def csv(self):export_rows(self,[tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('À recevoir'),tr('À commander'),tr('Commandées'),tr('Reçues')],[(r['source'],r['ref'],r['name'],r['color'],r['missing'],r['to_order'],r['ordered'],r['received']) for r in self.rows],'BrickLabo_achats.csv')
    def xml(self):
        if not self.lists.currentData():return
        path,_=QFileDialog.getSaveFileName(self,tr('Wanted List BrickLink'),'BrickLabo_achats.xml','XML (*.xml)')
        if path:
            from .project_shopping import wanted_xml
            safe(self,lambda:wanted_xml(self.db,self.lists.currentData(),path))
    def stock_changed(self):
        if not self.closed:self.refresh()
