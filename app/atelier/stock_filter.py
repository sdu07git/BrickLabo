"""Non-destructive stock selection for build searches."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QDialogButtonBox
from .i18n import tr

class StockFilterDialog(QDialog):
    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db;self.setWindowTitle(tr('Stock utilisable pour les recherches'));self.resize(950,650)
        layout=QVBoxLayout(self)
        info=QLabel(tr('Décoche « Utiliser les pièces de Mon stock set » pour chercher uniquement avec le vrac. Sinon, décoche les sets à garder montés ou les références à exclure. Ce choix ne modifie ni le stock ni les réservations des projets.'));info.setWordWrap(True);layout.addWidget(info)
        self.include_sets=QCheckBox(tr('Utiliser les pièces de Mon stock set'))
        self.include_sets.setToolTip(tr('Inclut les composants suivis des sets possédés. Décoché : seuls les pièces et mini-figurines en vrac sont utilisables, hors réservations de projets.'))
        self.include_sets.setChecked(db.setting('build_include_set_stock',True));layout.addWidget(self.include_sets)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Filtrer par référence, nom, source ou type'));layout.addWidget(self.search)
        self.rows=db.rows('''SELECT s.id,s.color,s.quantity,i.source,i.kind,i.ref,i.name,
            COALESCE((SELECT quantity FROM stock p WHERE p.id=s.id),0) AS loose_quantity
            FROM stock_available s JOIN items i ON i.id=s.item_id
            WHERE s.quantity>0 ORDER BY i.kind DESC,i.source,i.ref,s.color''')
        self.table=QTableWidget(len(self.rows),7);self.table.setHorizontalHeaderLabels([tr('Utiliser'),tr('Type'),tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité')]);self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        excluded=set(db.setting('build_excluded_entries',[]))
        self._set_checked={row['id']:row['id'] not in excluded for row in self.rows if row['kind']=='set'}
        self._using_sets=self.include_sets.isChecked()
        for i,row in enumerate(self.rows):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Unchecked if row['id'] in excluded else Qt.CheckState.Checked);self.table.setItem(i,0,check)
            for col,key in enumerate(('kind','source','ref','name','color','quantity'),1):
                value={'part':tr('Pièce'),'set':tr('Set'),'minifig':tr('Mini-fig')}.get(row[key],row[key]) if key=='kind' else row[key]
                cell=QTableWidgetItem(str(value));cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(i,col,cell)
        self.include_sets.toggled.connect(self.refresh_mode);self.search.textChanged.connect(self.filter_rows);self.refresh_mode()
        buttons=QHBoxLayout()
        for label,state in [('Tout cocher (lignes visibles)',Qt.CheckState.Checked),('Tout décocher (lignes visibles)',Qt.CheckState.Unchecked)]:
            button=QPushButton(tr(label));button.clicked.connect(lambda _,s=state:self.set_visible(s));buttons.addWidget(button)
        layout.addLayout(buttons)
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);actions.accepted.connect(self.save);actions.rejected.connect(self.reject);layout.addWidget(actions)
    def refresh_mode(self,*_):
        enabled=self.include_sets.isChecked()
        if self._using_sets and not enabled:
            self._set_checked={row['id']:self.table.item(i,0).checkState()==Qt.CheckState.Checked for i,row in enumerate(self.rows) if row['kind']=='set'}
        self._using_sets=enabled
        for i,row in enumerate(self.rows):
            if row['kind']=='set':
                check=self.table.item(i,0)
                check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable if enabled else Qt.ItemFlag.NoItemFlags)
                check.setCheckState(Qt.CheckState.Checked if enabled and self._set_checked[row['id']] else Qt.CheckState.Unchecked)
            else:self.table.item(i,6).setText(str(row['quantity'] if enabled else row['loose_quantity']))
        self.filter_rows()
    def filter_rows(self,*_):
        text=self.search.text().casefold()
        for i,row in enumerate(self.rows):
            quantity=row['quantity'] if self.include_sets.isChecked() or row['kind']=='set' else row['loose_quantity']
            self.table.setRowHidden(i,quantity<=0 or text not in ' '.join(self.table.item(i,j).text() for j in range(1,7)).casefold())
    def set_visible(self,state):
        for i,row in enumerate(self.rows):
            if not self.table.isRowHidden(i) and (row['kind']!='set' or self.include_sets.isChecked()):self.table.item(i,0).setCheckState(state)
    def save(self):
        enabled=self.include_sets.isChecked()
        excluded=[row['id'] for i,row in enumerate(self.rows) if (not self._set_checked[row['id']] if row['kind']=='set' and not enabled else self.table.item(i,0).checkState()==Qt.CheckState.Unchecked)]
        with self.db.connect() as c:
            for key,value in [('build_include_set_stock',enabled),('build_excluded_entries',excluded)]:
                c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE settings.value<>excluded.value',(key,json.dumps(value)))
        self.accept()
