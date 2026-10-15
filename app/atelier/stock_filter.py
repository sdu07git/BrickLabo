"""Non-destructive stock selection for build searches."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QDialogButtonBox
from .i18n import tr


def _save_choices(c,include_sets,excluded):
    for key,value in [('build_include_set_stock',include_sets),('build_excluded_entries',excluded)]:
        c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE settings.value<>excluded.value',(key,json.dumps(value)))


def select_all_loose_stock(db):
    """Explicitly include all loose entries, keeping owned-set choices for later."""
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT value FROM settings WHERE key='build_excluded_entries'").fetchone()
        excluded=json.loads(row['value']) if row else []
        _save_choices(c,False,[entry for entry in excluded if entry<0])


class StockFilterDialog(QDialog):
    def __init__(self,db,parent=None,engine=None):
        super().__init__(parent);self.db=db;self.engine=engine or getattr(parent,'engine',None);self.setWindowTitle(tr('Stock utilisable pour les recherches'));self.resize(1050,650)
        layout=QVBoxLayout(self)
        info=QLabel(tr('Coche les pièces en vrac et/ou les sets dont tu souhaites utiliser les inventaires. Les deux sélections sont indépendantes : un set coché reste utilisable même si son vrac est décoché. Le stock n’est pas modifié et aucun démontage n’est enregistré.'));info.setWordWrap(True);layout.addWidget(info)
        self.include_sets=QCheckBox(tr('Utiliser les pièces de Mon stock set'))
        self.include_sets.setToolTip(tr('Inclut les inventaires des sets cochés, sans les transférer au vrac. Décoché : seul le vrac coché est utilisable, hors réservations de projets.'))
        self.include_sets.setChecked(db.setting('build_include_set_stock',True))
        from .ui_common import FlowLayout
        mode=FlowLayout();mode.addWidget(self.include_sets)
        self.loose_only=QPushButton(tr('Utiliser uniquement le stock en vrac'));self.loose_only.clicked.connect(self.select_all_loose)
        mode.addWidget(self.loose_only)
        self.sets_only=QPushButton(tr('Sets cochés uniquement'));self.sets_only.clicked.connect(self.select_sets_only);mode.addWidget(self.sets_only);layout.addLayout(mode)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Filtrer par référence, nom, source ou type'));layout.addWidget(self.search)
        self.rows=db.rows("""SELECT i.*,s.id AS entry_id,s.color,s.quantity AS entry_quantity,
            CASE WHEN i.kind='set' THEN 0 ELSE s.quantity END AS loose_quantity
            FROM (SELECT id,item_id,color,quantity FROM stock WHERE quantity>0
            UNION ALL SELECT -id,item_id,color,quantity FROM stock_sets WHERE quantity>0) s
            JOIN items i ON i.id=s.item_id ORDER BY i.kind DESC,i.source,i.ref,s.color""")
        for row in self.rows:row['item_id']=row['id'];row['id']=row.pop('entry_id');row['quantity']=row.pop('entry_quantity')
        self.table=QTableWidget(len(self.rows),8);self.table.setHorizontalHeaderLabels([tr('Utiliser'),tr('Type'),tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité'),tr('Aperçu 3D / photo')]);self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        for column,width in ((0,65),(1,65),(2,65),(3,100),(5,70),(6,75),(7,145)):self.table.setColumnWidth(column,width)
        excluded=set(db.setting('build_excluded_entries',[]))
        self._set_checked={row['id']:row['id'] not in excluded for row in self.rows if row['kind']=='set'}
        self._using_sets=self.include_sets.isChecked()
        for i,row in enumerate(self.rows):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Unchecked if row['id'] in excluded else Qt.CheckState.Checked);self.table.setItem(i,0,check)
            for col,key in enumerate(('kind','source','ref','name','color','quantity'),1):
                value={'part':tr('Pièce'),'set':tr('Set'),'minifig':tr('Mini-fig')}.get(row[key],row[key]) if key=='kind' else row[key]
                cell=QTableWidgetItem(str(value));cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(i,col,cell)
        for i in range(len(self.rows)):
            cell=QTableWidgetItem('');cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(i,7,cell)
        self.thumbnails=None
        if self.engine:
            from .thumbnails import PartThumbnails
            self.thumbnails=PartThumbnails(self.table,self.db,self.engine,self.visible_items,7,self)
            self.finished.connect(lambda *_:self.thumbnails.stop())
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
            self.table.setRowHidden(i,quantity<=0 or text not in ' '.join(self.table.item(i,j).text() for j in range(1,7)).casefold()+' '+str(row.get('comment','')).casefold())
        if self.thumbnails:self.thumbnails.reset()
    def set_visible(self,state):
        for i,row in enumerate(self.rows):
            if not self.table.isRowHidden(i) and (row['kind']!='set' or self.include_sets.isChecked()):self.table.item(i,0).setCheckState(state)
    def visible_items(self):
        return [None if self.table.isRowHidden(i) else dict(row,id=row['item_id'],chosen_color=row['color']) for i,row in enumerate(self.rows)]
    def closeEvent(self,event):
        if self.thumbnails:self.thumbnails.stop()
        super().closeEvent(event)
    def select_sets_only(self):
        self.include_sets.setChecked(True);self.search.clear()
        for i,row in enumerate(self.rows):
            if row['kind']!='set':self.table.item(i,0).setCheckState(Qt.CheckState.Unchecked)
    def select_all_loose(self):
        self.include_sets.setChecked(False);self.search.clear()
        for i,row in enumerate(self.rows):
            if row['kind']!='set':self.table.item(i,0).setCheckState(Qt.CheckState.Checked)
    def save(self):
        enabled=self.include_sets.isChecked()
        excluded=[row['id'] for i,row in enumerate(self.rows) if (not self._set_checked[row['id']] if row['kind']=='set' and not enabled else self.table.item(i,0).checkState()==Qt.CheckState.Unchecked)]
        with self.db.connect() as c:
            _save_choices(c,enabled,excluded)
        self.accept()
