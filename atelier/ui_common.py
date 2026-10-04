from __future__ import annotations

from .i18n import tr,tf

import traceback
from .fileio import error_message
from pathlib import Path
from io import BytesIO

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QScrollArea,QWidget,QLabel,QPushButton,
                              QMessageBox,QDialogButtonBox,QFormLayout,QLineEdit,QSpinBox,QComboBox)


STYLE='''
QWidget { background:#141c27; color:#e8edf5; font-family:"Segoe UI"; font-size:10pt; }
QMainWindow,QDialog { background:#141c27; }
QLabel { background:transparent; }
QPushButton { background:#243449; border:1px solid #3a4c63; border-radius:5px; padding:7px 10px; }
QPushButton:hover { background:#30465f; }
QPushButton:disabled { color:#718096; }
QPushButton[primary="true"] { background:#266cae; border-color:#4389c8; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit { background:#1a293b; border:1px solid #354963; border-radius:4px; padding:5px; }
QTableWidget { background:#172231; alternate-background-color:#1b293b; gridline-color:#2c3e54; selection-background-color:#285989; border:1px solid #2c3e54; }
QHeaderView::section { background:#223247; color:#dce6f3; border:none; border-right:1px solid #354963; padding:9px; }
QListWidget { background:#172231; border:1px solid #2c3e54; }
QListWidget::item { padding:10px 8px; }
QListWidget::item:selected { background:#285989; }
QScrollArea,QGraphicsView { border:1px solid #2c3e54; }
QGroupBox { border:1px solid #304258; border-radius:6px; margin-top:12px; padding-top:12px; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
QMenu { background:#1d2c40; border:1px solid #3a4c63; }
QMenu::item { padding:8px 16px; }
QMenu::item:selected { background:#285989; }
QScrollBar:vertical { background:#15202d; width:12px; }
QScrollBar:horizontal { background:#15202d; height:12px; }
QScrollBar::handle { background:#40546d; border-radius:5px; min-height:25px; min-width:25px; }
QToolTip { background:#30465f; color:#ffffff; border:1px solid #718096; }
'''
STYLE += '''
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 24px; height: 24px; border: 2px solid #cbd5e1; border-radius: 4px; background: #111827; }
QCheckBox::indicator:hover { border-color: #67e8f9; }
QCheckBox::indicator:checked { background: #67e8f9; border-color: #67e8f9; image: url("%s"); }
QCheckBox::indicator:disabled { border-color: #64748b; background: #334155; }
''' % (Path(__file__).resolve().parent.parent/'ressources'/'checkbox_check.svg').as_posix()


class Signals(QObject):
    result=Signal(object)
    error=Signal(str)
    progress=Signal(object)


class Task(QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=Signals()
    def run(self):
        try:self.signals.result.emit(self.fn(self.signals.progress.emit))
        except Exception as e:self.signals.error.emit(error_message(e));traceback.print_exc()


def async_task(parent,fn,done,fail=None,progress_callback=None):
    t=Task(fn)
    # Les connexions vers QObject sont mises en file vers le thread UI.
    bridge=TaskBridge(parent,done,fail,progress_callback)
    t.signals.result.connect(bridge.complete)
    t.signals.error.connect(bridge.failed)
    t.signals.progress.connect(bridge.progress)
    QThreadPool.globalInstance().start(t)
    return t


class TaskBridge(QObject):
    def __init__(self,parent,done,fail,progress_callback=None):
        super().__init__(parent);self.done=done;self.fail=fail;self.progress_callback=progress_callback
    @Slot(object)
    def complete(self,result):
        try:self.done(result)
        finally:self.deleteLater()
    @Slot(str)
    def failed(self,error):
        if self.fail:self.fail(error)
        else:QMessageBox.warning(self.parent(),tr('Opération impossible'),error)
        self.deleteLater()
    @Slot(object)
    def progress(self,text):
        if self.progress_callback:self.progress_callback(text);return
        if hasattr(self.parent(),'statusBar'):self.parent().statusBar().showMessage(text)
        elif hasattr(self.parent(),'progress_label'):self.parent().progress_label.setText(text)


def pixmap(image):
    if image is None:return QPixmap()
    image=image.convert('RGBA')
    data=image.tobytes('raw','RGBA')
    q=QImage(data,image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(q)


def scalable(label,image,width=330,height=230):
    label.setPixmap(pixmap(image).scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))


def dialog(title,parent):
    d=QDialog(parent)
    d.setWindowTitle(title)
    d.setWindowFlags(d.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowMinimizeButtonHint)
    d.resize(850,620)
    return d


def image_dialog(title,image,parent):
    d=dialog(title,parent);layout=QVBoxLayout(d);scroll=QScrollArea();scroll.setWidgetResizable(True)
    label=QLabel();label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setPixmap(pixmap(image));scroll.setWidget(label)
    layout.addWidget(scroll);close=QPushButton(tr('Fermer'));close.clicked.connect(d.accept);layout.addWidget(close);d.exec()


def edit_item(parent,db,item=None,kind='part'):
    d=dialog(tr('Modifier la référence alternative') if item else tr('Ajouter une référence alternative'),parent)
    layout=QVBoxLayout(d);form=QFormLayout();layout.addLayout(form)
    ref=QLineEdit(item['ref'] if item else '');name=QLineEdit(item['name'] if item else '')
    category=QLineEdit(item['category'] if item else '')
    types=QComboBox();types.addItem(tr('Pièce'),'part');types.addItem(tr('Set'),'set');types.addItem(tr('Mini-fig'),'minifig')
    types.setCurrentIndex(max(0,types.findData(item['kind'] if item else kind)))
    form.addRow(tr('Type'),types);form.addRow(tr('Référence'),ref);form.addRow(tr('Nom'),name);form.addRow(tr('Catégorie'),category)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(buttons);buttons.rejected.connect(d.reject)
    def save():
        try:db.alternative(types.currentData(),ref.text(),name.text(),category.text(),item.get('image','') if item else '',item['id'] if item else None);d.accept()
        except Exception as e:QMessageBox.warning(d,tr('Référence invalide'),str(e))
    buttons.accepted.connect(save)
    return d.exec()
