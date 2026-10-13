"""A layout selector whose hover preview does not alter the editor draft."""
import copy

from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import QComboBox,QFrame,QVBoxLayout,QLabel

from .i18n import tr
from .labels import render_label,required_views
from .label_pieces import bindings
from .ui_common import async_task,label_pixmap


class ModelSelector(QComboBox):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.popup_active=False;self.revision=0;self.running=False;self.closed=False
        self.view().setMouseTracking(True);self.highlighted.connect(self.preview_model)
        self.hover=QFrame(editor,Qt.WindowType.ToolTip);self.hover.setObjectName('labelModelHover');self.hover.setFrameShape(QFrame.Shape.StyledPanel)
        self.hover.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.hover.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        box=QVBoxLayout(self.hover);self.title=QLabel();self.title.setWordWrap(True);box.addWidget(self.title)
        self.image=QLabel();self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);box.addWidget(self.image)
        self.note=QLabel();self.note.setWordWrap(True);box.addWidget(self.note);self.hover.setFixedWidth(344)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(100);self.timer.timeout.connect(self.render_hover)

    def showPopup(self):
        self.popup_active=True;super().showPopup();self.preview_model(self.currentIndex())

    def hidePopup(self):
        super().hidePopup();self.cancel_preview()

    def cancel_preview(self):
        self.popup_active=False;self.revision+=1;self.timer.stop();self.hover.hide()

    def preview_model(self,index):
        if not self.popup_active or self.closed:return
        self.revision+=1;self.pending=self.editor.model_template(self.itemData(index));self.pending_item=self.editor.preview_item()
        self.title.setText(self.itemText(index));self.draw(self.editor.visuals)
        self.note.setText(tr('Chargement de l’aperçu…'))
        popup=self.view().window();rect=popup.geometry();area=self.screen().availableGeometry()
        self.hover.adjustSize();x=rect.right()+6
        if x+self.hover.rect().width()>area.right():x=rect.left()-self.hover.rect().width()-6
        self.hover.move(max(area.left(),min(x,area.right()-self.hover.rect().width())),max(area.top(),min(rect.top(),area.bottom()-self.hover.rect().height())))
        self.hover.show()
        if set(required_views(self.pending))<=self.editor.visuals.keys() and bindings(self.pending)==bindings(self.editor.template):
            self.note.clear();self.timer.stop()
        else:self.timer.start()

    def draw(self,visuals):
        image=render_label(self.pending_item,self.editor.db,visuals,self.pending,dpi=150)
        self.image.setPixmap(label_pixmap(image).scaledToWidth(320,Qt.TransformationMode.SmoothTransformation))

    def render_hover(self):
        if self.closed or not self.popup_active or self.running:return
        revision=self.revision;template=copy.deepcopy(self.pending);item=dict(self.pending_item);self.running=True
        def work(progress):return self.editor.engine.visuals(item,item.get('chosen_color'),False,template=template,cancelled=lambda:self.closed or revision!=self.revision)
        def finish(result=None,error=None):
            self.running=False
            if self.closed or not self.popup_active:return
            if revision!=self.revision:self.timer.start(0);return
            if result:
                visuals,note=result;self.draw(visuals);self.note.setText(note)
            else:self.note.setText(tr('Aperçu indisponible : ')+str(error))
        async_task(self.editor,work,lambda result:finish(result),lambda error:finish(error=error))

    def close_preview(self):
        self.closed=True;self.cancel_preview()
