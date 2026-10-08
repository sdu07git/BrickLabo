from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QFileDialog,QMessageBox
from .i18n import tr
from .stock_import import read_list,resolve_rows,import_rows

class StockImportDialog(QDialog):
    def __init__(self,db,parent=None,destination='stock'):
        super().__init__(parent);self.db=db;self.path=None;self.rows=[]
        self.setWindowTitle(tr('Importer une collection'));self.resize(1050,660)
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.source=QComboBox()
        for text,value in [(tr('Détection automatique'),'auto'),('Rebrickable','RB'),('BrickLink','BL')]:self.source.addItem(text,value)
        row.addWidget(self.source);choose=QPushButton(tr('Ouvrir un fichier…'));choose.clicked.connect(self.choose);row.addWidget(choose)
        self.filename=QLabel();row.addWidget(self.filename,1);self.source.currentIndexChanged.connect(self.load)
        choices=QHBoxLayout();layout.addLayout(choices);choices.addWidget(QLabel(tr('Ajouter à :')))
        self.destination=QComboBox();self.destination.addItem(tr('Mon stock — pièces en vrac'),'stock');self.destination.addItem(tr('Mon stock set — sets et leurs pièces'),'stock_sets');self.destination.setCurrentIndex(1 if destination=='stock_sets' else 0);choices.addWidget(self.destination)
        self.target=QComboBox();self.target.addItem(tr('Créer un inventaire personnel'),None)
        for s in db.rows('SELECT s.id,i.source,i.ref,i.name FROM stock_sets s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 ORDER BY i.ref'):self.target.addItem(s['source']+' '+s['ref']+' — '+s['name'],s['id'])
        choices.addWidget(self.target,1);self.name=QLineEdit();self.name.setPlaceholderText(tr('Nom du nouvel inventaire'));choices.addWidget(self.name)
        self.destination.currentIndexChanged.connect(self.update_destination);self.target.currentIndexChanged.connect(self.update_destination)
        info=QLabel(tr('Les sets ajoutés au stock de pièces sont décomposés selon leur inventaire. Les pièces ajoutées au stock de sets sont rattachées au set choisi ou à un nouvel inventaire. Les références et inventaires doivent être présents localement. Un import forme une seule action annulable.'));info.setWordWrap(True);layout.addWidget(info)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Type'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité'),tr('Vérification')]);self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.ResizeMode.Stretch);self.table.setSortingEnabled(True);layout.addWidget(self.table,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons);self.commit=QPushButton(tr('Ajouter au stock'));self.commit.clicked.connect(self.import_selected);self.commit.setEnabled(False);buttons.addWidget(self.commit);close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);buttons.addWidget(close);self.update_destination()
    def update_destination(self,*_):
        owned=self.destination.currentData()=='stock_sets';self.target.setEnabled(owned);self.name.setEnabled(owned and self.target.currentData() is None)
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,tr('Importer une liste de pièces ou de sets'),'',tr('Listes (*.csv *.txt *.tsv *.xml);;Tous les fichiers (*)'))
        if path:self.path=path;self.filename.setText(path);self.load()
    def load(self,*_):
        if not self.path:return
        self.commit.setEnabled(False);self.rows=[];self.table.setSortingEnabled(False);self.table.setRowCount(0)
        try:
            self.rows=read_list(self.path,self.source.currentData());resolved=resolve_rows(self.db,self.rows);self.table.setRowCount(len(resolved))
            for r,row in enumerate(resolved):
                for c,value in enumerate((row['source'],row['kind'],row['ref'],row['item']['name'] if row['item'] else '',row['color'],row['quantity'],row['issue'] or tr('Référence trouvée'))):
                    cell=QTableWidgetItem();cell.setData(Qt.ItemDataRole.DisplayRole,value);cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(r,c,cell)
            missing=sum(bool(r['issue']) for r in resolved);self.status.setText(str(len(resolved))+tr(' lignes — références absentes : ')+str(missing));self.commit.setEnabled(not missing)
        except Exception as error:self.status.setText(str(error))
        finally:self.table.setSortingEnabled(True)
    def import_selected(self):
        try:import_rows(self.db,self.rows,self.destination.currentData(),self.target.currentData(),self.name.text())
        except Exception as error:QMessageBox.warning(self,tr('Import interrompu'),str(error));return
        self.accept()
