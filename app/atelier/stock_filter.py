"""Non-destructive stock selection for build searches."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QDialogButtonBox
from .i18n import tr

class StockFilterDialog(QDialog):
    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db;self.setWindowTitle(tr('Stock utilisable pour les recherches'));self.resize(950,650)
        layout=QVBoxLayout(self)
        info=QLabel(tr('Décoche les sets à garder montés ou les pièces à réserver. Un set décoché réserve uniquement ses quantités suivies ; les pièces en vrac restantes restent utilisables. Une ligne de pièce décochée exclut toute sa quantité, dans cette couleur. Aucun stock n’est supprimé.'));info.setWordWrap(True);layout.addWidget(info)
        search=QLineEdit();search.setPlaceholderText(tr('Filtrer par référence, nom, source ou type'));layout.addWidget(search)
        self.rows=db.rows('SELECT s.id,s.color,s.quantity,i.source,i.kind,i.ref,i.name FROM stock_available s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 ORDER BY i.kind DESC,i.source,i.ref,s.color')
        self.table=QTableWidget(len(self.rows),7);self.table.setHorizontalHeaderLabels([tr('Utiliser'),tr('Type'),tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité')]);self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table)
        excluded=set(db.setting('build_excluded_entries',[]))
        for i,row in enumerate(self.rows):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Unchecked if row['id'] in excluded else Qt.CheckState.Checked);self.table.setItem(i,0,check)
            for col,key in enumerate(('kind','source','ref','name','color','quantity'),1):
                value={'part':tr('Pièce'),'set':tr('Set'),'minifig':tr('Mini-fig')}.get(row[key],row[key]) if key=='kind' else row[key]
                cell=QTableWidgetItem(str(value));cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(i,col,cell)
        search.textChanged.connect(lambda text:[self.table.setRowHidden(i,text.casefold() not in ' '.join(self.table.item(i,j).text() for j in range(1,7)).casefold()) for i in range(len(self.rows))])
        buttons=QHBoxLayout()
        for label,state in [('Tout cocher (lignes visibles)',Qt.CheckState.Checked),('Tout décocher (lignes visibles)',Qt.CheckState.Unchecked)]:
            button=QPushButton(tr(label));button.clicked.connect(lambda _,s=state:self.set_visible(s));buttons.addWidget(button)
        layout.addLayout(buttons)
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);actions.accepted.connect(self.save);actions.rejected.connect(self.reject);layout.addWidget(actions)
    def set_visible(self,state):
        for i in range(len(self.rows)):
            if not self.table.isRowHidden(i):self.table.item(i,0).setCheckState(state)
    def save(self):
        self.db.set_setting('build_excluded_entries',[row['id'] for i,row in enumerate(self.rows) if self.table.item(i,0).checkState()==Qt.CheckState.Unchecked]);self.accept()
