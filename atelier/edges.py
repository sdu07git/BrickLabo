
from .i18n import tr,tf
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QDialogButtonBox,QScrollArea,QWidget,QHBoxLayout,QPushButton,QInputDialog,QMessageBox
from .ui_common import async_task,scalable
from .labels import render_label
from .edge_controls import EdgeControls
from .edge_style import general_style,normalize_style

class EdgeDialog(QDialog):
    def __init__(self,db,engine,item=None,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.revision=0;self.running=False;self.closed=False
        if item is None or item['kind']=='set':
            rows=db.rows("SELECT * FROM items WHERE kind='part' ORDER BY CASE WHEN ref='3001' THEN 0 ELSE 1 END LIMIT 1");item=rows[0] if rows else None
        self.item=dict(item) if item else None
        self.setWindowTitle(tr('Arêtes 3D — réglage général'));self.resize(740,780);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        root=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize);scroll.setWidget(body);root.addWidget(scroll)
        hint=QLabel(tr('Ces valeurs s’appliquent aux étiquettes qui utilisent le réglage général. Les réglages individuels restent conservés. Intensité 0 % : traits masqués ; 100 % : noir maximal.'));hint.setWordWrap(True);layout.addWidget(hint)
        self.controls=EdgeControls(general_style(db));layout.addWidget(self.controls)
        layout.addWidget(QLabel(tr('Réglages enregistrés')));self.presets=QComboBox();self.presets.currentIndexChanged.connect(self.load_preset);layout.addWidget(self.presets)
        row=QHBoxLayout()
        for title,method in [(tr('Enregistrer sous…'),self.save_preset),(tr('Renommer…'),self.rename_preset),(tr('Supprimer'),self.remove_preset)]:
            b=QPushButton(title);b.clicked.connect(method);row.addWidget(b)
        layout.addLayout(row);self.reload_presets()
        self.preview=QLabel();self.preview.setMinimumHeight(250);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.preview)
        self.label=QLabel();self.label.setMinimumHeight(140);self.label.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.label)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr('Appliquer comme réglage général'));buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Annuler'));buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(140);self.timer.timeout.connect(self.render_preview);self.controls.changed.connect(self.refresh);self.refresh()
    def settings(self):return self.controls.settings()
    def refresh(self):self.revision+=1;self.timer.start()
    def render_preview(self):
        if self.closed or self.running:return
        revision=self.revision;settings=self.settings()
        if not self.item:self.status.setText(tr('Importe un catalogue et LDraw pour visualiser une pièce.'));return
        self.running=True;self.status.setText(tr('Calcul de l’aperçu 3D…'))
        def work(progress):
            visuals={}
            for view,key,size in [('perspective','main',(620,420)),('top','top',(240,180)),('side','side',(240,160))]:
                visuals[key],visuals['bounds']=self.engine.render_3d(self.item,size,self.item.get('chosen_color') or '',view,edge_settings=settings)
            return visuals['main'],render_label(self.item,self.db,visuals)
        def finish(result=None,error=None):
            self.running=False
            if self.closed:return
            if revision==self.revision:
                if result:scalable(self.preview,result[0],560,350);scalable(self.label,result[1],560,200);self.status.setText(tr('Aperçu : ')+self.item['ref'])
                else:self.preview.clear();self.label.clear();self.status.setText(tr('Aperçu 3D indisponible : ')+str(error))
            else:self.timer.start()
        async_task(self,work,lambda result:finish(result),lambda error:finish(error=error))
    def reload_presets(self,selected=None):
        self.presets.blockSignals(True);self.presets.clear();self.presets.addItem(tr('Charger un réglage…'),None)
        for name in sorted(self.db.setting('edge_presets',{})):self.presets.addItem(name,name)
        if selected:self.presets.setCurrentIndex(self.presets.findData(selected))
        self.presets.blockSignals(False)
    def load_preset(self,*_):
        name=self.presets.currentData();value=self.db.setting('edge_presets',{}).get(name)
        if value:self.controls.set_settings(value);self.refresh()
    def store_preset(self,name,overwrite=False):
        name=name.strip()
        if not name:raise ValueError(tr('Le nom ne peut pas être vide.'))
        saved=self.db.setting('edge_presets',{})
        if name in saved and not overwrite:raise ValueError(tr('Un réglage porte déjà ce nom.'))
        saved[name]=normalize_style(self.settings());self.db.set_setting('edge_presets',saved);self.reload_presets(name)
    def rename_saved(self,old,new):
        saved=self.db.setting('edge_presets',{});new=new.strip()
        if old not in saved or not new or (new!=old and new in saved):raise ValueError(tr('Nom absent, vide ou déjà utilisé.'))
        saved[new]=saved.pop(old);self.db.set_setting('edge_presets',saved);self.reload_presets(new)
    def delete_saved(self,name):
        saved=self.db.setting('edge_presets',{});saved.pop(name,None);self.db.set_setting('edge_presets',saved);self.reload_presets()
    def save_preset(self):
        name,ok=QInputDialog.getText(self,tr('Enregistrer les arêtes'),tr('Nom du réglage :'))
        if not ok:return
        overwrite=False
        if name.strip() in self.db.setting('edge_presets',{}):
            overwrite=QMessageBox.question(self,tr('Remplacer le réglage'),tr('Remplacer les valeurs enregistrées sous ce nom ?'))==QMessageBox.StandardButton.Yes
            if not overwrite:return
        try:self.store_preset(name,overwrite)
        except ValueError as error:QMessageBox.warning(self,tr('Réglage'),str(error))
    def rename_preset(self):
        old=self.presets.currentData()
        if not old:return
        new,ok=QInputDialog.getText(self,tr('Renommer le réglage'),tr('Nouveau nom :'),text=old)
        if ok:
            try:self.rename_saved(old,new)
            except ValueError as error:QMessageBox.warning(self,tr('Réglage'),str(error))
    def remove_preset(self):
        name=self.presets.currentData()
        if name:self.delete_saved(name)
    def done(self,result):self.closed=True;self.revision+=1;self.timer.stop();super().done(result)
