"""Catalogue-only inventory queues; load a batch or continue until paused."""
import threading
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QSpinBox,
    QCheckBox,QTableWidget,QHeaderView,QAbstractItemView,QMessageBox)
from .i18n import tr,tf
from .ui_common import async_task,FlowLayout
from .windows import notify_changed,show_window
from .result_tables import fill_table,row_index
from . import inventory_batches as batches


class InventoryBatchDialog(QDialog):
    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db;self.rows=[];self.job=None;self.busy=False;self.continuous=False;self.closed=False;self.cancel=threading.Event()
        self.page=0;self.total=0;self.log_page=0;self.log_page_size=500
        self.setWindowTitle(tr('Inventaires des sets par lots'));self.resize(1080,740)
        layout=QVBoxLayout(self);note=QLabel(tr('Charge les inventaires dans les catalogues pour les recherches de constructions. Ce chargement n’ajoute aucun set ni aucune pièce au stock. Pour une base complète Rebrickable, les fichiers CSV de Mise à jour des données restent disponibles.'));note.setWordWrap(True);layout.addWidget(note)
        bar=QHBoxLayout();self.source=QComboBox();self.source.addItem('Rebrickable','RB');self.source.addItem('BrickLink','BL');bar.addWidget(self.source)
        self.filter=QLineEdit();self.filter.setPlaceholderText(tr('Référence, nom ou thème du set'));bar.addWidget(self.filter,1)
        self.limit=QSpinBox();self.limit.setRange(10,1000);self.limit.setValue(500);bar.addWidget(QLabel(tr('Sets par page')));bar.addWidget(self.limit)
        self.list_button=QPushButton(tr('Afficher les sets'));self.list_button.clicked.connect(self.list_sets);bar.addWidget(self.list_button);layout.addLayout(bar)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Set')]);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.setColumnWidth(2,580);layout.addWidget(self.table,1)
        bar=QHBoxLayout();self.previous=QPushButton(tr('Page précédente'));self.previous.clicked.connect(lambda:self.change_page(-1));bar.addWidget(self.previous)
        self.page_label=QLabel();bar.addWidget(self.page_label,1)
        self.next=QPushButton(tr('Page suivante'));self.next.clicked.connect(lambda:self.change_page(1));bar.addWidget(self.next);layout.addLayout(bar)
        self.references=QLineEdit();self.references.setPlaceholderText(tr('Ou saisir les références de sets, séparées par espaces / virgules'));layout.addWidget(self.references)
        bar=FlowLayout();bar.addWidget(QLabel(tr('Sets par lot')));self.size=QSpinBox();self.size.setRange(10,1000);self.size.setValue(db.setting('inventory_batch_size',10));bar.addWidget(self.size)
        self.force=QCheckBox(tr('Actualiser aussi les inventaires déjà présents'));bar.addWidget(self.force)
        self.create=QPushButton(tr('Préparer la sélection'));self.create.clicked.connect(self.prepare_selection);bar.addWidget(self.create)
        self.create_all=QPushButton(tr('Préparer tous les sets trouvés'));self.create_all.clicked.connect(lambda:self.prepare_selection(True));bar.addWidget(self.create_all);layout.addLayout(bar)
        note=QLabel(tr('Sans filtre, « Préparer tous les sets trouvés » inclut tout le catalogue choisi, sans limite de nombre. La taille des pages et des lots ne limite pas la file enregistrée.'));note.setWordWrap(True);layout.addWidget(note)
        bar=QHBoxLayout();bar.addWidget(QLabel(tr('Chargements enregistrés')));self.history=QComboBox();bar.addWidget(self.history,1);self.history.currentIndexChanged.connect(self.choose_job);layout.addLayout(bar)
        self.status=QLabel(tr('Choisis les sets et prépare un chargement.'));self.status.setWordWrap(True);layout.addWidget(self.status)
        self.log=QTableWidget(0,4);self.log.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('État'),tr('Détail')]);self.log.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.log.setColumnWidth(3,510);self.log.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.log,1)
        bar=QHBoxLayout();self.log_previous=QPushButton(tr('Page précédente'));self.log_previous.clicked.connect(lambda:self.change_log_page(-1));bar.addWidget(self.log_previous)
        self.log_page_label=QLabel();bar.addWidget(self.log_page_label,1)
        self.log_next=QPushButton(tr('Page suivante'));self.log_next.clicked.connect(lambda:self.change_log_page(1));bar.addWidget(self.log_next);layout.addLayout(bar)
        bar=FlowLayout();self.run=QPushButton(tr('Charger le prochain lot'));self.run.clicked.connect(lambda:self.start(False));bar.addWidget(self.run)
        self.all=QPushButton(tr('Enchaîner les lots'));self.all.clicked.connect(lambda:self.start(True));bar.addWidget(self.all)
        self.pause=QPushButton(tr('Pause'));self.pause.clicked.connect(self.cancel.set);bar.addWidget(self.pause)
        self.retry=QPushButton(tr('Réessayer les erreurs'));self.retry.clicked.connect(self.retry_errors);bar.addWidget(self.retry)
        builds=QPushButton(tr('Chercher des constructions'));builds.clicked.connect(self.open_builds);bar.addWidget(builds)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);bar.addWidget(close);layout.addLayout(bar)
        self.refresh_history();self.controls(False)
    def controls(self,busy):
        self.busy=busy
        for w in (self.source,self.filter,self.limit,self.list_button,self.create,self.create_all,self.size,self.force,self.history,self.references,self.retry):w.setEnabled(not busy)
        self.run.setEnabled(not busy and self.job is not None);self.all.setEnabled(not busy and self.job is not None);self.pause.setEnabled(busy)
        self.previous.setEnabled(not busy and self.page>0);self.next.setEnabled(not busy and (self.page+1)*getattr(self,'page_size',self.limit.value())<self.total)
    def list_sets(self):
        if self.busy:return
        self.page=0;self.list_source=self.source.currentData();self.list_filter=self.filter.text();self.page_size=self.limit.value();self.load_page()
    def load_page(self):
        self.rows,self.total=batches.catalogue_page(self.db,self.list_source,self.list_filter,self.page,self.page_size)
        fill_table(self.table,[(r['source'],r['ref'],r['name']) for r in self.rows])
        self.page_label.setText(tf('{0}–{1} sur {2} sets',self.page*self.page_size+1 if self.total else 0,min((self.page+1)*self.page_size,self.total),self.total))
        self.previous.setEnabled(self.page>0);self.next.setEnabled((self.page+1)*self.page_size<self.total)
    def change_page(self,step):
        if self.busy or not self.total:return
        self.page=max(0,min((self.total-1)//self.page_size,self.page+step));self.load_page()
    def prepare_selection(self,all_displayed=False):
        if self.busy:return
        import re
        text=self.references.text().strip();selected=[]
        if all_displayed:
            try:job=batches.create_catalogue_job(self.db,self.source.currentData(),self.filter.text(),self.size.value(),self.force.isChecked())
            except ValueError as e:QMessageBox.warning(self,tr('Chargement impossible'),str(e));return
            self.save_job(job);return
        if text:
            for ref in dict.fromkeys(re.split(r'[\s,;]+',text)):
                found=self.db.rows("SELECT * FROM items WHERE source=? AND kind='set' AND ref=?",(self.source.currentData(),ref))
                if not found:QMessageBox.warning(self,tr('Set introuvable'),ref+tr(' : ajoute cette référence au catalogue avant le chargement.'));return
                selected.append(found[0])
        else:selected=[self.rows[row_index(self.table,index.row())] for index in self.table.selectionModel().selectedRows()]
        try:job=batches.create_job(self.db,selected,self.size.value(),self.force.isChecked())
        except ValueError as e:QMessageBox.warning(self,tr('Chargement impossible'),str(e));return
        self.save_job(job)
    def save_job(self,job):
        self.db.set_setting('inventory_batch_size',self.size.value());self.refresh_history(job)
    def refresh_history(self,preferred=None):
        current=preferred or self.job;self.history.blockSignals(True);self.history.clear()
        for job in batches.jobs(self.db):self.history.addItem(job['created']+' · '+job['name'],job['id'])
        self.history.setCurrentIndex(max(0,self.history.findData(current)));self.history.blockSignals(False);self.choose_job()
    def choose_job(self,*_):
        self.job=self.history.currentData();self.log_page=0
        if self.job is not None:
            row=self.db.rows('SELECT * FROM inventory_jobs WHERE id=?',(self.job,))[0];self.size.setValue(row['batch_size'])
        self.refresh_progress();self.controls(False)
    def refresh_progress(self):
        if self.job is None:
            self.log_previous.setEnabled(False);self.log_next.setEnabled(False);return
        s=batches.summary(self.db,self.job)
        self.status.setText(str(s['loaded'])+tr(' chargés · ')+str(s['skipped'])+tr(' déjà disponibles · ')+str(s['pending'])+tr(' en attente · ')+str(s['errors'])+tr(' erreur(s).'))
        labels={'pending':tr('En attente'),'loaded':tr('Chargé'),'skipped':tr('Déjà disponible'),'error':tr('Erreur')}
        self.log_page=max(0,min(self.log_page,max(0,(s['total']-1)//self.log_page_size)))
        rows=self.db.rows('SELECT source,ref,status,error FROM inventory_job_items WHERE job_id=? ORDER BY ordinal LIMIT ? OFFSET ?',(self.job,self.log_page_size,self.log_page*self.log_page_size))
        fill_table(self.log,[(r['source'],r['ref'],labels[r['status']],r['error']) for r in rows])
        self.log_page_label.setText(tf('{0}–{1} sur {2} sets',self.log_page*self.log_page_size+1 if s['total'] else 0,min((self.log_page+1)*self.log_page_size,s['total']),s['total']))
        self.log_previous.setEnabled(self.log_page>0);self.log_next.setEnabled((self.log_page+1)*self.log_page_size<s['total'])
    def change_log_page(self,step):
        self.log_page=max(0,self.log_page+step);self.refresh_progress()
    def start(self,continuous=False):
        if self.busy or self.job is None:return
        self.cancel.clear();self.continuous=continuous;self._next_batch()
    def _next_batch(self):
        if self.closed or self.cancel.is_set():return
        self.db.run('UPDATE inventory_jobs SET batch_size=? WHERE id=?',(self.size.value(),self.job));job=self.job;self.controls(True)
        def done(summary):
            self.controls(False);self.refresh_progress();notify_changed(self)
            if self.continuous and not self.cancel.is_set() and summary['pending']:QTimer.singleShot(0,self._next_batch)
        def fail(error):
            self.controls(False);self.refresh_progress();self.status.setText(str(error)+tr(' — le chargement reste enregistré pour une reprise.'))
        async_task(self,lambda progress:batches.run_batch(self.db,job,self.cancel,progress),done,fail,lambda text:self.status.setText(tr('Chargement : ')+str(text)))
    def retry_errors(self):
        if self.job is not None:batches.retry_errors(self.db,self.job);self.refresh_progress()
    def open_builds(self):
        from .build_stock import BuildStockDialog
        from .windows import application_owner
        owner=application_owner(self);show_window(BuildStockDialog(self.db,getattr(owner,'engine',None),self),self)
    def done(self,result):self.closed=True;self.cancel.set();super().done(result)
