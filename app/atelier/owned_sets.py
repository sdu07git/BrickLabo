from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QSplitter,QTableWidget,QTableWidgetItem,QHeaderView,QLabel
from .catalogue import Catalogue
from .thumbnails import PartThumbnails
from .i18n import tr

class OwnedSetsPanel(QWidget):
    def __init__(self,db,engine,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.entry=None;self.parts=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split)
        self.catalogue=Catalogue(db,kind='set',scope='stock_sets');split.addWidget(self.catalogue)
        lower=QWidget();body=QVBoxLayout(lower);body.addWidget(QLabel(tr('Pièces du set sélectionné — quantités totales possédées')))
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité totale'),tr('Aperçu 3D / photo')]);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for col,width in ((0,80),(1,100),(3,100),(4,140),(5,180)):self.table.setColumnWidth(col,width)
        self.table.setSortingEnabled(True);body.addWidget(self.table);split.addWidget(lower);split.setSizes([350,280])
        self.thumbnails=PartThumbnails(self.table,db,engine,self.ordered_parts,5,self);self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset());self.table.cellDoubleClicked.connect(self.open_part);self.catalogue.selected.connect(self.select)
    def ordered_parts(self):
        return [self.parts[self.table.item(row,0).data(Qt.ItemDataRole.UserRole)] for row in range(self.table.rowCount())]
    def select(self,item):
        self.entry=item.get('entry_id') if item else None;self.refresh()
    def refresh(self):
        if not self.entry or not self.db.rows('SELECT 1 FROM stock_sets WHERE id=?',(self.entry,)):self.entry=None;self.parts=[]
        else:self.parts=self.db.owned_components(self.entry)
        self.thumbnails.suspend();self.table.setSortingEnabled(False);self.table.setRowCount(len(self.parts))
        for row,item in enumerate(self.parts):
            for col,value in enumerate((item['source'],item['ref'],item['name'],item['chosen_color'],item['chosen_quantity'],tr('3D / photo à charger'))):
                cell=QTableWidgetItem();cell.setData(Qt.ItemDataRole.DisplayRole,value);cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable)
                if col==0:cell.setData(Qt.ItemDataRole.UserRole,row)
                self.table.setItem(row,col,cell)
        self.table.setSortingEnabled(True);self.thumbnails.reset()
    def open_part(self,row,column):
        from .dialogs import RelationsDialog
        items=self.ordered_parts()
        if 0<=row<len(items):RelationsDialog(self.db,self.engine,items[row],self).exec()
