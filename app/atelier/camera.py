
from .paths import resources_directory

from .i18n import tr,tf
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QSlider,QDoubleSpinBox,QCheckBox,QDialogButtonBox,QPushButton,QComboBox,QInputDialog,QScrollArea,QWidget
from .viewpoint import camera_for_item,normalize_camera,DEFAULT_CAMERA
from .ui_common import async_task,scalable

class OrbitPreview(QLabel):
    dragged=Signal(float,float)
    def __init__(self):
        super().__init__();self.last=None;self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setMinimumSize(360,260);self.setCursor(Qt.CursorShape.OpenHandCursor)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.last=event.position();self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.last is not None and event.buttons()&Qt.MouseButton.LeftButton:
            delta=event.position()-self.last;self.last=event.position();self.dragged.emit(delta.x()*.5,-delta.y()*.5);event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        self.last=None;self.setCursor(Qt.CursorShape.OpenHandCursor);super().mouseReleaseEvent(event)

class CameraDialog(QDialog):
    def __init__(self,db,engine,item,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.item=dict(item);self.controls={};self.image=None;self.revision=0;self.running=False;self.dirty=False;self.closed=False
        self.setWindowTitle(tr('Angle du rendu 3D — ')+item['ref']);self.resize(900,760);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        root=QVBoxLayout(self);hint=QLabel(tr('Glisse sur la pièce pour la tourner, ou règle les angles ci-dessous.'));hint.setWordWrap(True);root.addWidget(hint)
        self.preview=OrbitPreview();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.preview);root.addWidget(scroll,1);self.preview.dragged.connect(self.orbit)
        for key,title,limit in [('yaw',tr('Rotation horizontale'),180),('pitch',tr('Inclinaison'),89),('roll',tr('Rotation dans l’image'),180)]:
            row=QHBoxLayout();label=QLabel(title);label.setMinimumWidth(160);row.addWidget(label)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(-limit,limit);row.addWidget(slider,1)
            spin=QDoubleSpinBox();spin.setRange(-limit,limit);spin.setDecimals(1);spin.setSingleStep(1);spin.setSuffix(' °');row.addWidget(spin)
            self.controls[key]=(slider,spin);slider.valueChanged.connect(lambda value,k=key:self.slider_changed(k,value));spin.valueChanged.connect(lambda value,k=key:self.spin_changed(k,value));root.addLayout(row)
        row=QHBoxLayout();reset=QPushButton(tr('Vue initiale'));reset.clicked.connect(lambda:self.set_camera(DEFAULT_CAMERA));row.addWidget(reset)
        opposite=QPushButton(tr('Tourner de 180°'));opposite.clicked.connect(self.opposite);row.addWidget(opposite);root.addLayout(row)
        row=QHBoxLayout();self.presets=QComboBox();self.presets.setMinimumWidth(220);row.addWidget(self.presets,1)
        self.save_preset_button=QPushButton(tr('Enregistrer ce point de vue…'));self.save_preset_button.clicked.connect(self.save_preset);row.addWidget(self.save_preset_button);root.addLayout(row)
        self.presets.currentIndexChanged.connect(self.load_preset);self.reload_presets()
        self.all_models=QCheckBox(tr('Appliquer cette vue à tous les modèles 3D (remplace les angles individuels)'))
        check_icon=(resources_directory()/'checkbox_check.svg').as_posix()
        self.all_models.setStyleSheet('''
            QCheckBox { color: #f5f7fa; background: #263244; padding: 12px; border-radius: 6px; spacing: 12px; font-weight: 600; }
            QCheckBox::indicator { width: 24px; height: 24px; border: 2px solid #cbd5e1; border-radius: 4px; background: #111827; }
            QCheckBox::indicator:hover { border-color: #67e8f9; }
            QCheckBox::indicator:checked { background: #67e8f9; border-color: #67e8f9; image: url("%s"); }
            QCheckBox:focus { border: 2px solid #67e8f9; }
        ''' % check_icon)
        root.addWidget(self.all_models)
        self.status=QLabel('');self.status.setWordWrap(True);root.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr('Appliquer'));self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Annuler'))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False);self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);root.addWidget(self.buttons)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.render_preview)
        self.set_camera(camera_for_item(db,item));self.timer.start(0)
    def camera(self):return normalize_camera({key:spin.value() for key,(_,spin) in self.controls.items()})
    def set_camera(self,value):
        for key,number in normalize_camera(value).items():
            slider,spin=self.controls[key];slider.blockSignals(True);spin.blockSignals(True);slider.setValue(round(number));spin.setValue(number);spin.blockSignals(False);slider.blockSignals(False)
        self.schedule()
    def schedule(self):
        self.revision+=1
        if hasattr(self,'buttons'):self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        if hasattr(self,'timer'):self.timer.start(100)
    def slider_changed(self,key,value):
        spin=self.controls[key][1];spin.blockSignals(True);spin.setValue(value);spin.blockSignals(False);self.schedule()
    def spin_changed(self,key,value):
        slider=self.controls[key][0];slider.blockSignals(True);slider.setValue(round(value));slider.blockSignals(False);self.schedule()
    def orbit(self,dx,dy):
        camera=self.camera();camera['yaw']=(camera['yaw']+dx+180)%360-180;camera['pitch']+=dy;self.set_camera(camera)
    def opposite(self):
        camera=self.camera();camera['yaw']=(camera['yaw']+360)%360-180;self.set_camera(camera)
    def reload_presets(self,selected=None):
        self.presets.blockSignals(True);self.presets.clear();self.presets.addItem(tr('Charger un point de vue…'),None)
        for name in sorted(self.db.setting('camera_presets',{})):self.presets.addItem(name,name)
        if selected:self.presets.setCurrentIndex(self.presets.findData(selected))
        self.presets.blockSignals(False)
    def save_preset(self):
        name,ok=QInputDialog.getText(self,tr('Enregistrer un point de vue'),tr('Nom du point de vue :'))
        if not ok or not name.strip():return
        self.store_preset(name.strip())
    def store_preset(self,name):
        presets=self.db.setting('camera_presets',{});presets[name]=self.camera();self.db.set_setting('camera_presets',presets);self.reload_presets(name);self.status.setText(tr('Point de vue « ')+name+tr(' » enregistré. Appliquer valide la vue pour les modèles.'))
    def load_preset(self,index):
        name=self.presets.itemData(index)
        if name:self.set_camera(self.db.setting('camera_presets',{}).get(name,{}))
    def render_preview(self):
        if self.closed:return
        if self.running:self.dirty=True;return
        self.running=True;self.dirty=False;revision=self.revision;camera=self.camera();item=dict(self.item)
        self.status.setText(tr('Rendu de l’angle choisi…'))
        def work(progress):
            renderer=self.engine.renderer()
            if not renderer:raise ValueError(tr('Importe LDraw pour régler la caméra du rendu 3D.'))
            chosen=item.get('chosen_color');color=str(chosen if chosen not in (None,'') else self.db.visual(item['id'])['color'])
            return self.engine.render_3d(item,(500,350),color,camera=camera)[0]
        def finish(image=None,error=None):
            self.running=False
            if self.closed:return
            if revision==self.revision:
                if image is not None:
                    self.image=image;scalable(self.preview,image,max(360,self.preview.width()-20),max(260,self.preview.height()-20));self.status.setText(tr('Cette vue sera utilisée pour le rendu principal de l’étiquette.'));self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
                else:self.status.setText(error or tr('Rendu indisponible.'));self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
            if self.dirty or revision!=self.revision:self.timer.start(0)
        async_task(self,work,lambda image:finish(image),lambda error:finish(error=error))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.image is not None:scalable(self.preview,self.image,max(360,self.preview.width()-20),max(260,self.preview.height()-20))
    def done(self,result):
        self.closed=True;self.timer.stop();super().done(result)
