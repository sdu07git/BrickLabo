"""Editable category sequence for a storage proposal, with portable preferences."""
import sqlite3
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QAbstractItemView,QHeaderView,
    QSpinBox,QPushButton,QCheckBox,QDialogButtonBox,QMessageBox)

from .i18n import tr,tf
from .ui_common import FlowLayout
from .result_tables import fill_table
from . import storage_order


class StorageCategoryOrderDialog(QDialog):
    def __init__(self,db,rows,preferred,parent=None):
        super().__init__(parent);self.db=db;self.rows={row['category']:row for row in rows};self.categories=storage_order.arranged(self.rows,preferred);self.positions={}
        self.setWindowTitle(tr('Ordre des catégories'));self.resize(760,560)
        layout=QVBoxLayout(self);hint=QLabel(tr('Donne une position à chaque catégorie ou utilise Monter / Descendre. Le rangement suivra cet ordre, puis triera les formats par nombre de tenons (longueur × largeur) dans chaque catégorie. Valider coche Catégorie et Taille en tenons.'));hint.setWordWrap(True);layout.addWidget(hint)
        self.table=QTableWidget(0,4);self.table.setObjectName('category_order_table');self.table.setHorizontalHeaderLabels([tr('Position'),tr('Catégorie'),tr('Références'),tr('Tiroirs nécessaires')]);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for column,width in enumerate((85,285,115,155)):self.table.setColumnWidth(column,width)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        actions=FlowLayout();self.up=QPushButton(tr('Monter'));self.down=QPushButton(tr('Descendre'));self.alphabetical=QPushButton(tr('Ordre alphabétique'))
        for button in (self.up,self.down,self.alphabetical):actions.addWidget(button)
        layout.addLayout(actions);self.up.clicked.connect(lambda:self.move_selected(-1));self.down.clicked.connect(lambda:self.move_selected(1));self.alphabetical.clicked.connect(self.reset_order)
        unknown=sum(row['unknown'] for row in rows);self.status=QLabel(tf('{0} référence(s) sans dimensions : elles restent à ranger manuellement, sauf si Référence est coché.',unknown));self.status.setWordWrap(True);self.status.setVisible(bool(unknown));layout.addWidget(self.status)
        self.retain=QCheckBox(tr('Retenir cet ordre pour les prochains rangements'));self.retain.setChecked(True);layout.addWidget(self.retain)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.table.currentCellChanged.connect(self.update_actions);self.fill()

    def order(self):return list(self.categories)

    def fill(self,selected=None):
        for spin in self.positions.values():spin.blockSignals(True);spin.hide()
        self.positions={};self.table.setRowCount(0)
        fill_table(self.table,[('',category or tr('Sans catégorie'),self.rows[category]['references'],self.rows[category]['drawers']) for category in self.categories],sortable=False)
        for row,category in enumerate(self.categories):
            spin=QSpinBox();spin.setRange(1,len(self.categories));spin.setValue(row+1);spin.setAccessibleName(tr('Position')+' — '+(category or tr('Sans catégorie')));self.positions[category]=spin;self.table.setCellWidget(row,0,spin);self.table.setRowHeight(row,max(38,spin.sizeHint().height()+4))
            spin.editingFinished.connect(lambda name=category,s=spin:self.move_category(name,s.value()-1))
        index=self.categories.index(selected) if selected in self.categories else 0
        if self.categories:self.table.setCurrentCell(index,1)
        self.update_actions()

    def update_actions(self,*_):
        row=self.table.currentRow();self.up.setEnabled(row>0);self.down.setEnabled(0<=row<len(self.categories)-1)

    def move_category(self,category,index):
        current=self.categories.index(category);index=max(0,min(len(self.categories)-1,index))
        if current==index:return
        self.categories.insert(index,self.categories.pop(current));self.fill(category)

    def move_selected(self,delta):
        row=self.table.currentRow()
        if 0<=row<len(self.categories):self.move_category(self.categories[row],row+delta)

    def reset_order(self):
        self.categories=storage_order.arranged(self.categories,[]);self.fill()

    def accept(self):
        # A number typed immediately before OK must be committed as well.
        for category,spin in list(self.positions.items()):
            if spin.hasFocus():
                spin.interpretText();self.move_category(category,spin.value()-1);break
        if self.retain.isChecked():
            try:storage_order.remember(self.db,self.order())
            except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(self,tr('Ordre non enregistré'),str(error));return
        super().accept()
