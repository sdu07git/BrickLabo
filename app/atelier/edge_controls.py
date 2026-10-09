
from .i18n import tr,tf
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSlider,QDoubleSpinBox,QCheckBox,QPushButton
from .edge_style import normalize_style,default_style

class EdgeControls(QWidget):
    changed=Signal()
    def __init__(self,settings,inherit=False,parent=None):
        super().__init__(parent);self.loading=True;self.sliders={};self.spins={};self.rows=[]
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0)
        self.inherit=QCheckBox(tr('Utiliser le réglage général')) if inherit else None
        if self.inherit:root.addWidget(self.inherit);self.inherit.toggled.connect(self.inheritance_changed)
        for key,title,lo,hi,suffix in [('black',tr('Intensité du noir'),0,100,' %'),('width',tr('Épaisseur des arêtes'),.5,10,' px')]:
            root.addWidget(QLabel(title));row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0);slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(round(lo*10),round(hi*10));spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setDecimals(1);spin.setSingleStep(.1);spin.setSuffix(suffix);layout.addWidget(slider,1);layout.addWidget(spin);root.addWidget(row)
            self.rows.append(row);self.sliders[key]=slider;self.spins[key]=spin
            slider.valueChanged.connect(lambda value,k=key:self.from_slider(k,value));spin.valueChanged.connect(lambda value,k=key:self.from_spin(k,value))
        self.defaults=QPushButton(tr('Valeurs par défaut'));self.defaults.clicked.connect(self.reset_defaults);root.addWidget(self.defaults)
        self.set_settings(settings,False);self.loading=False
    def reset_defaults(self):
        self.set_settings(default_style(),False);self.changed.emit()
    def set_settings(self,value,inherit=False):
        self.loading=True
        for key,number in normalize_style(value).items():self.spins[key].setValue(number);self.sliders[key].setValue(round(number*10))
        if self.inherit:self.inherit.setChecked(inherit)
        for row in self.rows:row.setEnabled(not inherit)
        self.loading=False
    def from_slider(self,key,value):
        self.spins[key].setValue(value/10)
    def from_spin(self,key,value):
        slider=self.sliders[key];slider.blockSignals(True);slider.setValue(round(value*10));slider.blockSignals(False)
        if not self.loading:self.changed.emit()
    def inheritance_changed(self,value):
        for row in self.rows:row.setEnabled(not value)
        if not self.loading:self.changed.emit()
    def settings(self):
        if self.inherit and self.inherit.isChecked():return None
        return {key:spin.value() for key,spin in self.spins.items()}
