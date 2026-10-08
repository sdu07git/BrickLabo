"""Sortable result tables retaining stable row identities."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

def row_index(table,row=None):
    row=table.currentRow() if row is None else row
    cell=table.item(row,0) if row>=0 else None
    value=cell.data(Qt.ItemDataRole.UserRole) if cell else None
    return value if isinstance(value,int) else row

def fill_table(table,records):
    table.blockSignals(True);table.setSortingEnabled(False);table.setRowCount(len(records))
    for index,values in enumerate(records):
        for column,value in enumerate(values):
            cell=QTableWidgetItem();cell.setData(Qt.ItemDataRole.DisplayRole,value if isinstance(value,(int,float)) else str(value or ''))
            cell.setData(Qt.ItemDataRole.UserRole,index);table.setItem(index,column,cell)
    table.setSortingEnabled(True);table.blockSignals(False)
