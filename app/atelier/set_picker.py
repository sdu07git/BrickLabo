"""Filtered, paginated set selection with a separately loaded photo preview."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSplitter,QDialogButtonBox,QPushButton,QSizePolicy,QAbstractItemView
from shiboken6 import isValid
from .i18n import tr
from .ui_common import async_task,scalable,FlowLayout
from .catalogue import Catalogue


class SetImagePreview(QWidget):
    def __init__(self,engine=None,parent=None):
        super().__init__(parent);self.engine=engine;self.item=None;self.image=None;self.token=0;self.running=False;self.closed=False
        layout=QVBoxLayout(self);self.title=QLabel(tr('Aperçu du set'));self.title.setWordWrap(True);layout.addWidget(self.title)
        self.photo=QLabel(tr('Sélectionne un set.'));self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter);self.photo.setWordWrap(True)
        self.photo.setMinimumHeight(130);self.photo.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding);layout.addWidget(self.photo,1)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(100);self.timer.timeout.connect(self.load)

    def set_item(self,item):
        if self.closed or not isValid(self):return
        self.token+=1;self.timer.stop();self.item=dict(item) if item else None;self.image=None;self.photo.clear()
        self.title.setText(item['source']+' '+item['ref']+' · '+item['name'] if item else tr('Aperçu du set'))
        self.photo.setText(tr('Chargement de la photo…') if item and self.engine else tr('Photo indisponible') if item else tr('Sélectionne un set.'))
        if item and self.engine:self.timer.start()

    def load(self):
        if self.closed or not isValid(self) or not self.item or not self.engine or self.running:return
        token=self.token;item=dict(self.item);engine=self.engine;self.running=True
        def finish(result=None,error=None):
            self.running=False
            if self.closed or not isValid(self):return
            if token!=self.token:
                if self.item:self.timer.start(0)
                return
            self.image=result
            if result is not None:self.resize_photo()
            else:self.photo.setText(tr('Photo indisponible'));self.photo.setToolTip(error or '')
        async_task(self,lambda _:engine.photo(item,download=True),lambda result:finish(result),lambda error:finish(error=error))

    def resize_photo(self):
        if self.image is not None:scalable(self.photo,self.image,max(1,self.photo.width()),max(1,self.photo.height()))

    def resizeEvent(self,event):
        super().resizeEvent(event);self.resize_photo()

    def stop(self):
        self.closed=True;self.token+=1
        if isValid(self):self.timer.stop()


class SetPicker(QDialog):
    def __init__(self,db,engine=None,parent=None):
        super().__init__(parent);self.chosen=None;self.closed=False;self.setWindowTitle(tr('Choisir un set'));self.resize(1080,620)
        layout=QVBoxLayout(self);hint=QLabel(tr('Recherche par référence ou nom, filtre par thème et année, ou utilise les filtres avancés.'));hint.setWordWrap(True);layout.addWidget(hint)
        split=QSplitter(Qt.Orientation.Horizontal);layout.addWidget(split,1)
        self.catalogue=Catalogue(db,kind='set',selection_only=True);self.catalogue.engine=engine;split.addWidget(self.catalogue)
        self.preview=SetImagePreview(engine,self);self.preview.setMinimumWidth(180);split.addWidget(self.preview);split.setSizes([760,300]);split.setChildrenCollapsible(False)
        footer=FlowLayout();layout.addLayout(footer)
        advanced=QPushButton(tr('Filtres avancés…'));advanced.clicked.connect(self.catalogue.advanced_filters);footer.addWidget(advanced)
        reset=QPushButton(tr('Réinitialiser les filtres'));reset.clicked.connect(lambda:self.catalogue.apply_filter_state({}));footer.addWidget(reset)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.choose_button=self.buttons.button(QDialogButtonBox.StandardButton.Ok);self.choose_button.setText(tr('Choisir ce set'))
        self.buttons.accepted.connect(self.choose);self.buttons.rejected.connect(self.reject);footer.addWidget(self.buttons)
        self.catalogue.selected.connect(self.select);self.catalogue.opened.connect(lambda *_:self.choose());self.catalogue.reloaded.connect(self.reloaded);self.reloaded()

    def reloaded(self):
        if self.closed or not isValid(self):return
        self.select(None)
        if self.catalogue.rows:self.catalogue.table.selectRow(0)

    def select(self,item):
        if self.closed or not isValid(self):return
        self.chosen=dict(item) if item else None;self.preview.set_item(item);self.choose_button.setEnabled(bool(item))

    def choose(self):
        if self.closed or not isValid(self):return
        selected=self.catalogue.selection()
        if selected:self.chosen=dict(selected[0]);self.accept()

    def done(self,result):
        if self.closed or not isValid(self):return
        self.closed=True
        self.preview.stop();self.catalogue.timer.stop();self.catalogue.thumbnail_token+=1
        if getattr(self.catalogue,'thumbnails',None):self.catalogue.thumbnails.stop()
        super().done(result)
