
from .i18n import tr,tf
from copy import deepcopy
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QColorDialog,QDialogButtonBox,QSplitter,QWidget,QScrollArea,QSizePolicy
from .labels import default_template,category_outline,render_label
from .ui_common import scalable,async_task

class ContourDialog(QDialog):
    def __init__(self,db,engine,current_item=None,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.current_item=current_item
        self.template=deepcopy(db.setting('template',default_template()));self.template.setdefault('category_colors',{})
        self.visual={};self.preview_item=None;self.label_image=None;self.token=0;self.switching=False
        self.setWindowTitle(tr('Couleurs des contours — aperçu de l’étiquette'));self.resize(1060,630)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        root=QVBoxLayout(self);split=QSplitter();root.addWidget(split,1)
        left=QWidget();layout=QVBoxLayout(left);layout.addWidget(QLabel(tr('Catégorie')))
        self.category=QComboBox();self.category.setEditable(False);self.category.setMinimumWidth(180);self.category.setMaximumWidth(300);self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.category.setMinimumContentsLength(20);self.category.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        categories=[r['category'] for r in db.rows("SELECT DISTINCT category FROM items WHERE kind='part' AND category<>'' ORDER BY category")]
        self.category.addItems(categories or ['Brick']);layout.addWidget(self.category)
        self.picker=QColorDialog(left);self.picker.setOptions(QColorDialog.ColorDialogOption.NoButtons|QColorDialog.ColorDialogOption.DontUseNativeDialog)
        self.picker.setWindowFlags(Qt.WindowType.Widget);layout.addWidget(self.picker,1);split.addWidget(left)
        right=QWidget();preview=QVBoxLayout(right);preview.addWidget(QLabel(tr('Aperçu du modèle général')))
        self.image=QLabel();self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.image.setMinimumSize(300,140);self.image.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.image);self.scroll=scroll;preview.addWidget(scroll,1)
        self.caption=QLabel();self.caption.setWordWrap(True);preview.addWidget(self.caption)
        self.swatch=QLabel();preview.addWidget(self.swatch);split.addWidget(right);split.setSizes([440,600]);split.setChildrenCollapsible(False)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.render_preview);self.scroll.viewport().installEventFilter(self);split.splitterMoved.connect(lambda *_:self.timer.start(35))
        self.category.currentTextChanged.connect(self.select_category);self.picker.currentColorChanged.connect(self.change_color)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr('Appliquer'));buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Annuler'));buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        if current_item and current_item.get('kind')=='part' and current_item.get('category') in categories:self.category.setCurrentText(current_item['category'])
        self.select_category(self.category.currentText())
    def select_category(self,category):
        self.category.setToolTip(category)
        if not category.strip():return
        self.token+=1;token=self.token;self.switching=True
        self.picker.setCurrentColor(QColor(category_outline(category,self.db,self.template)));self.switching=False
        if self.current_item and self.current_item.get('category')==category and self.current_item['kind']=='part':item=dict(self.current_item)
        else:
            rows=self.db.rows("SELECT * FROM items WHERE category=? AND kind='part' ORDER BY source='RB' DESC,id LIMIT 1",(category,))
            item=rows[0] if rows else {'id':-1,'source':'ALT','kind':'part','ref':'','name':tr('Aperçu'),'category':category}
        self.preview_item=item;self.visual={};self.render_preview()
        if item['id']==-1:return
        self.caption.setText(tr('Chargement de l’aperçu — ')+item['ref'])
        def done(result):
            if token!=self.token:return
            self.visual=result[0];self.caption.setText(item['ref']+' — '+item['name']);self.render_preview()
        async_task(self,lambda progress:self.engine.visuals(item,item.get('chosen_color'),download=False),done,lambda error:self.caption.setText(tr('Visuel de la pièce indisponible : ')+error) if token==self.token else None)
    def change_color(self,color):
        if self.switching or not color.isValid():return
        category=self.category.currentText().strip()
        if category:self.template['category_colors'][category]=color.name();self.timer.start(35)
    def render_preview(self):
        if not self.preview_item:return
        self.label_image=render_label(self.preview_item,self.db,self.visual,self.template,dpi=160)
        scalable(self.image,self.label_image,max(1,self.scroll.viewport().width()-20),max(1,self.scroll.viewport().height()-20),show_transparency=True)
        self.swatch.setText(tr('Contour : ')+category_outline(self.category.currentText(),self.db,self.template))
    def eventFilter(self,watched,event):
        if watched is self.scroll.viewport() and event.type()==QEvent.Type.Resize:self.timer.start(35)
        return super().eventFilter(watched,event)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'timer'):self.timer.start(35)
    def done(self,result):
        self.token+=1;self.timer.stop();super().done(result)
