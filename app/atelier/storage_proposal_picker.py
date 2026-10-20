"""Searchable reference selection within a captured, uncommitted storage draft."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QTableWidget,QHeaderView,QAbstractItemView,QDialogButtonBox
from .i18n import tr
from .result_tables import fill_table,row_index
from .storage_wall import normalize
from .thumbnails import PartThumbnails
from . import storage_assignment as assignment


class ProposalReferencePicker(QDialog):
    def __init__(self,db,plan,targets,destination,engine=None,parent=None):
        super().__init__(parent);self.plan=plan;self.targets=targets;self.destination=destination;self.rows=[];self.indices=[];self.selected_index=None
        self.setWindowTitle(tr('Ajouter une autre référence au tiroir'));self.resize(900,540)
        layout=QVBoxLayout(self);note=QLabel(tr('Choisis une référence de la proposition. Elle sera déplacée de son tiroir proposé vers ce tiroir, avec ses couleurs et ses quantités. Les autres placements sont conservés.'));note.setWordWrap(True);layout.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Référence, nom ou catégorie'));layout.addWidget(self.search)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels([tr('Aperçu'),tr('Source'),tr('Référence'),tr('Pièce'),tr('Couleur'),tr('Quantité proposée'),tr('Tiroir proposé')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.ensurePolished()
        for column,width in enumerate((100,65,115,220,110,120,210)):self.table.setColumnWidth(column,max(width,self.table.fontMetrics().horizontalAdvance(self.table.horizontalHeaderItem(column).text())+28))
        layout.addWidget(self.table,1);self.thumbs=PartThumbnails(self.table,db,engine,self.visible_rows,0,self) if engine else None
        if self.thumbs:self.table.model().layoutChanged.connect(lambda *_:self.thumbs.reset())
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);self.add_button=buttons.button(QDialogButtonBox.StandardButton.Ok);self.add_button.setText(tr('Ajouter au tiroir'));buttons.accepted.connect(self.choose);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.table.itemSelectionChanged.connect(lambda:self.add_button.setEnabled(bool(self.table.selectionModel().selectedRows())));self.table.itemDoubleClicked.connect(self.choose);self.search.textChanged.connect(self.reload);self.reload()

    def visible_rows(self):return [self.rows[row_index(self.table,row)] for row in range(self.table.rowCount())]

    def reload(self,*_):
        terms=normalize(self.search.text()).split();self.indices=[];self.rows=[];values=[];drawers={drawer['id']:drawer for drawer in self.plan['available']}
        present={entry for group,target in zip(self.plan['groups'],self.targets) if target==self.destination for entry in group['entries']}
        for index,(group,target) in enumerate(zip(self.plan['groups'],self.targets)):
            if present.intersection(group['entries']):continue
            identity,color=group['entries'][0];part=self.plan['preview']['items'][identity]
            if any(term not in normalize(part['source']+' '+part['ref']+' '+part['name']+' '+part['category']) for term in terms):continue
            quantities=list(assignment.group_quantities(self.plan,group).values());quantity=sum(quantities) if quantities and all(value is not None for value in quantities) else tr('À renseigner')
            colors=' / '.join(dict.fromkeys(color or tr('Non précisée') for identity,color in group['entries']))
            ref=part['ref']+(' ('+str(group['split_index']+1)+'/'+str(group['split_count'])+')' if group['split_count']>1 else '')
            self.indices.append(index);self.rows.append(dict(part,chosen_color=color));values.append((tr('3D / photo à charger'),part['source'],ref,part['name'],colors,quantity,assignment.drawer_label(self.plan,drawers[target]) if target in drawers else tr('Laisser sans emplacement')))
        self.table.clearSelection();fill_table(self.table,values)
        for row in range(self.table.rowCount()):self.table.setRowHeight(row,72)
        self.add_button.setEnabled(False)
        if self.thumbs:self.thumbs.reset()

    def choose(self,*_):
        selected=self.table.selectionModel().selectedRows()
        if not selected:return
        self.selected_index=self.indices[row_index(self.table,selected[0].row())];self.accept()

    def done(self,result):
        if self.thumbs:self.thumbs.stop()
        super().done(result)
