"""Original packaging is a separate BrickLink item type, never a set inventory."""
import urllib.parse
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QPushButton,QScrollArea,QDialogButtonBox
from .ui_common import async_task,scalable

def boxes_for_set(db,item):
    if not item or item.get('kind')!='set' or item.get('source') not in ('RB','BL'):return []
    refs=[item['ref']]
    if '-' not in item['ref']:refs.append(item['ref']+'-1')
    return db.rows("SELECT * FROM items WHERE source='BL' AND kind='box' AND ref IN ("+','.join('?' for _ in refs)+") ORDER BY ref",refs)

class BoxDialog(QDialog):
    def __init__(self,db,engine,item,parent=None):
        super().__init__(parent);self.engine=engine;self.boxes=boxes_for_set(db,item);self.token=0;self.closed=False;self.image=None
        self.setWindowTitle('Boîte d’origine — '+item['ref']);self.resize(760,620)
        self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowMinimizeButtonHint)
        layout=QVBoxLayout(self);self.choice=QComboBox()
        for box in self.boxes:self.choice.addItem(box['ref']+' — '+box['name'])
        layout.addWidget(self.choice);self.caption=QLabel();self.caption.setWordWrap(True);layout.addWidget(self.caption)
        self.preview=QLabel();self.preview.setMinimumSize(320,220);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.preview);layout.addWidget(scroll,1)
        self.link=QLabel();self.link.setOpenExternalLinks(True);layout.addWidget(self.link)
        self.reload=QPushButton('Recharger la photo');self.reload.clicked.connect(self.load);layout.addWidget(self.reload)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.choice.currentIndexChanged.connect(self.load);self.load()
    def load(self):
        self.token+=1;token=self.token;self.image=None;index=self.choice.currentIndex()
        if index<0:self.preview.setText('Aucune boîte répertoriée.');self.reload.setEnabled(False);return
        box=self.boxes[index];self.caption.setText(box['ref']+' — '+box['name']);self.preview.clear();self.preview.setText('Chargement de la photo…')
        url='https://www.bricklink.com/v2/catalog/catalogitem.page?O='+urllib.parse.quote(box['ref'],safe='')
        self.link.setText('<a href="'+url+'">Voir la boîte sur BrickLink</a>')
        def done(image):
            if self.closed or token!=self.token:return
            self.image=image
            if image is None:self.preview.setText('Photo indisponible pour cette boîte.')
            else:scalable(self.preview,image,max(320,self.preview.width()-20),max(220,self.preview.height()-20))
        def fail(error):
            if not self.closed and token==self.token:self.preview.setText('Photo inaccessible : '+error)
        async_task(self,lambda progress:self.engine.photo(box),done,fail)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.image:scalable(self.preview,self.image,max(320,self.preview.width()-20),max(220,self.preview.height()-20))
    def done(self,result):self.closed=True;self.token+=1;super().done(result)
