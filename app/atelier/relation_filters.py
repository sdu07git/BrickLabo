"""Piece and independent optional colour criteria for containing-set searches."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QDialogButtonBox,
    QAbstractItemView)
from .i18n import tr
from .ui_common import FlowLayout
from .windows import show_window


class PartPicker(QDialog):
    def __init__(self, db, source, engine, parent):
        super().__init__(parent)
        from .catalogue import Catalogue
        self.chosen = []
        self.setWindowTitle(tr('Ajouter des pièces à la recherche'))
        self.resize(850, 540)
        layout = QVBoxLayout(self)
        hint = QLabel(tr('Recherche une référence ou un nom. Ctrl ou Maj permet de sélectionner plusieurs pièces sur cette page.'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.catalogue = Catalogue(db, source=source, kind='part', selection_only=True)
        self.catalogue.key += '_relations'
        self.catalogue.visible_columns = db.setting(self.catalogue.key, ['ref','name','image'])
        self.catalogue.engine = engine
        self.catalogue.reload()
        self.catalogue.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.catalogue, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('Ajouter la sélection'))
        buttons.accepted.connect(self.choose)
        buttons.rejected.connect(self.reject)
        self.catalogue.opened.connect(lambda *_: self.choose())
        layout.addWidget(buttons)

    def choose(self):
        self.chosen = [dict(self.catalogue.rows[index.row()]) for index in self.catalogue.table.selectionModel().selectedRows()]
        if self.chosen:
            self.accept()

    def done(self, result):
        self.catalogue.timer.stop()
        self.catalogue.thumbnail_token += 1
        if getattr(self.catalogue, 'thumbnails', None):
            self.catalogue.thumbnails.stop()
        super().done(result)


class RelationFilters(QWidget):
    search_requested = Signal()

    def __init__(self, db, engine, initial, parent=None):
        super().__init__(parent)
        self.db, self.engine, self.initial = db, engine, dict(initial)
        self.items = []
        self.picker = None
        self.closed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        note = QLabel(tr('Chercher les sets contenant toutes ces pièces. Chaque couleur est facultative.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr('Référence'), tr('Pièce'), tr('Couleur')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(2, 200)
        self.table.setMinimumHeight(72)
        self.table.setMaximumHeight(132)
        layout.addWidget(self.table)
        buttons = FlowLayout()
        self.add_button = QPushButton(tr('Ajouter une pièce…'))
        self.add_button.clicked.connect(self.choose_parts)
        self.remove_button = QPushButton(tr('Retirer la sélection'))
        self.remove_button.clicked.connect(self.remove_selected)
        self.reset_button = QPushButton(tr('Revenir à cette pièce'))
        self.reset_button.clicked.connect(self.reset)
        self.search_button = QPushButton(tr('Rechercher'))
        self.search_button.clicked.connect(self.search_requested)
        for button in (self.add_button, self.remove_button, self.reset_button, self.search_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.add_items([initial])

    def add_items(self, items):
        from .projects_panel import color_options
        for item in items:
            row = len(self.items)
            self.items.append(dict(item))
            self.table.insertRow(row)
            for column, text in enumerate((item['ref'], item['name'])):
                self.table.setItem(row, column, QTableWidgetItem(text))
            choice = QComboBox()
            choice.setAccessibleName(tr('Couleur recherchée pour ') + item['ref'])
            choice.addItem(tr('Toutes les couleurs'), None)
            native = item
            if item['source'] == 'BA':
                from .brickarchitect import native_item
                native = native_item(self.db, item, 'RB') or item
            for code, label in color_options(self.db, native):
                if code:
                    choice.addItem(label, code)
            self.table.setCellWidget(row, 2, choice)
        self.search_button.setEnabled(bool(self.items))

    def criteria(self):
        return [(dict(item), self.table.cellWidget(row, 2).currentData()) for row, item in enumerate(self.items)]

    def remove_selected(self):
        for row in sorted((index.row() for index in self.table.selectionModel().selectedRows()), reverse=True):
            self.items.pop(row)
            self.table.removeRow(row)
        self.search_button.setEnabled(bool(self.items))

    def reset(self):
        self.items.clear()
        self.table.setRowCount(0)
        self.add_items([self.initial])

    def choose_parts(self):
        if self.picker is not None:
            self.picker.show()
            self.picker.raise_()
            return
        picker = PartPicker(self.db, self.initial['source'], self.engine, self)
        self.picker = picker

        def chosen(result):
            self.picker = None
            if not self.closed and result == QDialog.DialogCode.Accepted:
                self.add_items(picker.chosen)
        show_window(picker, self, chosen, refresh_counts=False)

    def set_busy(self, busy):
        self.setEnabled(not busy)
        if self.picker is not None:self.picker.setEnabled(not busy)
        if not busy:self.search_button.setEnabled(bool(self.items))

    def stop(self):
        self.closed = True
        if self.picker is not None:
            self.picker.reject()
