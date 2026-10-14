"""Review the persistent undo/redo stack without confusing print history."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QSpinBox,QTableWidget,QHeaderView,QAbstractItemView
from PySide6.QtGui import QAction
from .i18n import tr
from .ui_common import FlowLayout
from .result_tables import fill_table
from . import action_history


class ActionHistoryDialog(QDialog):
    def __init__(self, db, owner):
        super().__init__(owner)
        self.db, self.owner = db, owner
        self.setWindowTitle(tr('Historique des actions'))
        self.resize(850, 520)
        layout = QVBoxLayout(self)
        hint = QLabel(tr('Les actions s’annulent dans l’ordre inverse. Une nouvelle modification après une annulation remplace les actions qui restaient à rétablir.'))
        hint.setWordWrap(True); layout.addWidget(hint)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr('Date'), tr('Action'), tr('État')])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 160); self.table.setColumnWidth(1, 480); self.table.setColumnWidth(2, 100)
        layout.addWidget(self.table, 1)
        controls = FlowLayout()
        self.undo = QPushButton(tr('Annuler')); self.undo.clicked.connect(owner.undo_stock)
        self.redo = QPushButton(tr('Rétablir')); self.redo.clicked.connect(owner.redo_stock)
        self.undo_shortcut=QAction(self);self.undo_shortcut.setShortcut('Ctrl+Z');self.undo_shortcut.triggered.connect(owner.undo_stock);self.addAction(self.undo_shortcut)
        self.redo_shortcut=QAction(self);self.redo_shortcut.setShortcut('Ctrl+Y');self.redo_shortcut.triggered.connect(owner.redo_stock);self.addAction(self.redo_shortcut)
        controls.addWidget(self.undo); controls.addWidget(self.redo)
        controls.addWidget(QLabel(tr('Actions conservées')))
        self.count = QSpinBox(); self.count.setRange(1, 500)
        with db.read() as c: self.count.setValue(action_history.limit(c))
        controls.addWidget(self.count)
        save = QPushButton(tr('Appliquer la limite')); save.clicked.connect(self.save_limit); controls.addWidget(save)
        close = QPushButton(tr('Fermer')); close.clicked.connect(self.close); controls.addWidget(close)
        layout.addLayout(controls)
        self.reload()

    def reload(self):
        fill_table(self.table, [(row['created'], tr(row['description']), tr('Appliquée') if row['applied'] else tr('Annulée')) for row in action_history.rows(self.db)])
        self.undo.setEnabled(bool(self.db.undo_description()))
        self.redo.setEnabled(bool(self.db.redo_description()))
        self.undo_shortcut.setEnabled(self.undo.isEnabled());self.redo_shortcut.setEnabled(self.redo.isEnabled())
        self.undo.setToolTip(self.db.undo_description()); self.redo.setToolTip(self.db.redo_description())

    def refresh_action_history(self): self.reload()

    def save_limit(self):
        action_history.set_limit(self.db, self.count.value())
        self.owner.update_undo()
