"""Application-owned inventory loading; consultation windows only observe it."""
import threading
from PySide6.QtCore import QObject,Signal,QTimer,QCoreApplication
from shiboken6 import isValid
from .i18n import tr,tf
from . import inventory_batches as batches


class InventoryBackground(QObject):
    changed=Signal()
    progress=Signal(str)
    batch_finished=Signal()
    def __init__(self,db,parent):
        super().__init__(parent);self.db=db;self.job=None;self.busy=False;self.continuous=False
        self.cancel=threading.Event();self.message='';self.error='';self.summary=None;self._closing=False
    def start(self,job,batch_size,continuous=False):
        if self.busy or self._closing:return False
        if not self.db.rows('SELECT 1 FROM inventory_jobs WHERE id=?',(job,)):raise ValueError(tr('Chargement introuvable.'))
        batches._check_batch_size(batch_size)
        self.db.run('UPDATE inventory_jobs SET batch_size=? WHERE id=?',(batch_size,job))
        self.job=job;self.continuous=continuous;self.cancel.clear();self.error='';self.message=''
        self.summary=batches.summary(self.db,job);self.busy=True;self.changed.emit();self._next_batch();return True
    def _next_batch(self):
        from .windows import application_owner
        if self._closing or getattr(application_owner(self),'_closing',False) or self.cancel.is_set():
            self.busy=False;self.changed.emit();return
        from .ui_common import async_task
        async_task(self,lambda progress:batches.run_batch(self.db,self.job,self.cancel,progress),self._done,self._failed,self._progress)
    def _progress(self,message):
        if self._closing:return
        self.message=str(message);self.progress.emit(self.message)
    def _done(self,result):
        if self._closing:return
        self.summary=result if result is not None else batches.summary(self.db,self.job)
        again=self.continuous and not self.cancel.is_set() and self.summary['pending']>0
        self.busy=again;self.changed.emit();self.batch_finished.emit()
        if again:QTimer.singleShot(0,self._next_batch)
    def _failed(self,error):
        if self._closing:return
        self.busy=False;self.error=str(error);self.summary=batches.summary(self.db,self.job)
        self.changed.emit();self.batch_finished.emit()
    def pause(self):self.cancel.set();self.changed.emit()
    def shutdown(self):self._closing=True;self.continuous=False;self.cancel.set()


def service_for(db,parent=None):
    service=getattr(db,'_inventory_background',None)
    if service is not None and isValid(service):return service
    from .windows import application_owner
    owner=application_owner(parent) if parent is not None else None
    if owner is None or not hasattr(owner,'refresh_counts'):owner=QCoreApplication.instance()
    if owner is None:raise RuntimeError('Inventory loading needs the application event loop')
    service=InventoryBackground(db,owner);db._inventory_background=service;return service


def install(parent):
    from PySide6.QtWidgets import QPushButton
    service=service_for(parent.db,parent);button=None
    def open_window():
        from .inventory_batch_dialog import InventoryBatchDialog
        from .windows import show_window
        for window in list(getattr(parent,'_consultation_windows',[])):
            if isinstance(window,InventoryBatchDialog) and isValid(window) and not window.closed:
                window.show();window.raise_();window.activateWindow();return
        show_window(InventoryBatchDialog(parent.db,parent),parent)
    def refresh():
        nonlocal button
        if service.job is None:return
        if button is None:
            # Creating even a hidden permanent widget can enlarge QStatusBar.
            # Keep the normal workspace height until there is a job to show.
            button=QPushButton(tr('Inventaires en arrière-plan…'))
            button.setStyleSheet('QPushButton { padding:1px 6px; }')
            button.clicked.connect(open_window);parent.statusBar().addPermanentWidget(button)
        summary=service.summary or {}
        done=summary.get('loaded',0)+summary.get('skipped',0)+summary.get('errors',0)
        button.setText(tf('Inventaires : {0}/{1}',done,summary.get('total',0)))
        button.setToolTip((tr('Chargement en arrière-plan') if service.busy else tr('Chargement en pause') if summary.get('pending') else tr('Chargement terminé'))+'\n'+(service.error or service.message))
    def loaded():
        if parent._closing:return
        for catalogue in parent.catalogues:catalogue.invalidate(categories=True)
        for panel in parent.owned_panels:panel.invalidate()
        parent.projects.invalidate()
        if parent.dashboard.isVisible():parent.dashboard.refresh()
        refresh()
    progress_timer=QTimer(parent);progress_timer.setSingleShot(True);progress_timer.setInterval(500)
    def progress():
        if parent._closing or service.job is None:return
        service.summary=batches.summary(parent.db,service.job);refresh()
    progress_timer.timeout.connect(progress)
    service.progress.connect(lambda *_:progress_timer.start() if not progress_timer.isActive() else None)
    service.changed.connect(refresh);service.batch_finished.connect(loaded);refresh();return service
