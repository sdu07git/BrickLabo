"""Cabinet layout choices and a live, read-only preview before applying."""
import math
from PySide6.QtCore import Qt,QRectF,QSize
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QFormLayout,QLabel,QComboBox,
                              QSpinBox,QDoubleSpinBox,QDialogButtonBox)
from .i18n import tr,tf
from .storage_wall import alignment_positions,extent


class AlignmentPreview(QWidget):
    def __init__(self,walls,parent=None):
        super().__init__(parent);self.walls={w['id']:w for w in walls};self.positions=[];self.hit_boxes=[];self.setMouseTracking(True)
        self.setMinimumSize(260,180);self.setAccessibleName(tr('Aperçu de la disposition des meubles'))

    def sizeHint(self):return QSize(600,300)

    def set_positions(self,positions):
        self.positions=positions;self.hit_boxes=[];self.setToolTip('');self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),self.palette().base())
        self.hit_boxes=[]
        if not self.positions:return
        boxes=[];bounds=QRectF()
        for index,(x,y,identity) in enumerate(self.positions):
            wall=self.walls[identity];width,height=extent(wall)
            box=QRectF(x*112,y*70,width*112,height*70);boxes.append((index,wall,box));bounds=bounds.united(box)
        area=QRectF(self.rect()).adjusted(12,12,-12,-12)
        scale=min(area.width()/bounds.width(),area.height()/bounds.height())
        left=area.center().x()-bounds.width()*scale/2;top=area.center().y()-bounds.height()*scale/2
        painter.setPen(QPen(QColor('#39739d'),1.2))
        for index,wall,box in boxes:
            target=QRectF(left+(box.x()-bounds.x())*scale,top+(box.y()-bounds.y())*scale,box.width()*scale,box.height()*scale)
            painter.setBrush(QColor('#dfedf7'));painter.drawRoundedRect(target,4,4)
            self.hit_boxes.append((target,tf('Meuble {0} : {1}',index+1,wall['name'])))
            text_area=target.adjusted(4,4,-4,-4)
            if text_area.width()>8 and text_area.height()>8:
                name=painter.fontMetrics().elidedText(wall['name'],Qt.TextElideMode.ElideRight,max(0,int(text_area.width())))
                text=str(index+1)+'\n'+name if text_area.height()>=2*painter.fontMetrics().height() else str(index+1)
                painter.drawText(text_area,Qt.AlignmentFlag.AlignCenter,text)

    def mouseMoveEvent(self,event):
        self.setToolTip(next((name for box,name in self.hit_boxes if box.contains(event.position())),''))
        super().mouseMoveEvent(event)

    def leaveEvent(self,event):
        self.setToolTip('');super().leaveEvent(event)


class StorageAlignmentDialog(QDialog):
    def __init__(self,walls,parent=None):
        super().__init__(parent);self.walls=walls;self.setWindowTitle(tr('Aligner les meubles'));self.resize(660,530)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.direction=QComboBox();self.direction.setObjectName('alignment_direction')
        for label,value in [(tr('En grille'),'grid'),(tr('Horizontalement'),'horizontal'),(tr('Verticalement'),'vertical')]:self.direction.addItem(label,value)
        form.addRow(tr('Disposition'),self.direction)
        self.per_row=QSpinBox();self.per_row.setObjectName('alignment_per_row');self.per_row.setRange(1,max(1,len(walls)));self.per_row.setValue(min(4,max(1,len(walls))))
        self.per_row.setToolTip(tr('Avec 8 meubles, choisir 4 crée deux rangées de 4 meubles.'))
        form.addRow(tr('Meubles par rangée'),self.per_row)
        self.gap=QDoubleSpinBox();self.gap.setObjectName('alignment_gap');self.gap.setRange(0,100);self.gap.setDecimals(1);self.gap.setSingleStep(.1);self.gap.setValue(.2)
        form.addRow(tr('Écart entre les meubles'),self.gap)
        note=QLabel(tr('L’ordre suit la disposition actuelle, de gauche à droite puis de haut en bas. En grille, les colonnes s’alignent sur le meuble le plus large et les rangées sur le plus haut. Appliquer enregistre la disposition.'));note.setWordWrap(True);layout.addWidget(note)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('alignment_summary');layout.addWidget(self.summary)
        self.preview=AlignmentPreview(walls);layout.addWidget(self.preview,1)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(self.buttons);self.buttons.rejected.connect(self.reject)
        self.direction.currentIndexChanged.connect(self.refresh_preview);self.per_row.valueChanged.connect(self.refresh_preview);self.gap.valueChanged.connect(self.refresh_preview);self.refresh_preview()

    def refresh_preview(self):
        direction=self.direction.currentData();self.per_row.setEnabled(direction=='grid')
        try:positions=alignment_positions(self.walls,direction,self.gap.value(),self.per_row.value())
        except ValueError as error:
            self.preview.set_positions([]);self.summary.setText(str(error));self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False);return
        self.preview.set_positions(positions);self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True)
        count=len(self.walls);per_row=self.per_row.value() if direction=='grid' else count if direction=='horizontal' else 1
        self.summary.setText(tf('{0} meuble(s) · {1} rangée(s) · jusqu’à {2} meuble(s) par rangée',count,math.ceil(count/max(1,per_row)),per_row))
