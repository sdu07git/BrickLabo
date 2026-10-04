"""Searchable category checklist and removable tags."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QLineEdit,QListWidget,QListWidgetItem,QPushButton,QScrollArea,QLabel
from .i18n import tr
class TagBar(QScrollArea):
    removed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.setWidgetResizable(True);self.setMaximumHeight(105);self.setMinimumHeight(48)
        content=QWidget();self.grid=QGridLayout(content);self.grid.setContentsMargins(3,3,3,3);self.setWidget(content)
    def set_tags(self,values):
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        for index,value in enumerate(values):
            button=QPushButton(value+'  ×');button.setToolTip(tr('Retirer cette catégorie : ')+value)
            button.clicked.connect(lambda _,v=value:self.removed.emit(v));self.grid.addWidget(button,index//3,index%3)
        self.setVisible(bool(values))
class CategoryTags(QWidget):
    def __init__(self,values,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        note=QLabel(tr('Choisir plusieurs catégories : les résultats peuvent appartenir à l’une OU l’autre. Aucun tag = toutes les catégories.'));note.setWordWrap(True);layout.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Rechercher une catégorie…'));layout.addWidget(self.search)
        self.list=QListWidget();self.list.setMinimumHeight(150);self.list.setMaximumHeight(190);layout.addWidget(self.list)
        self.bar=TagBar();self.bar.removed.connect(self.remove);layout.addWidget(self.bar)
        clear=QPushButton(tr('Effacer les catégories sélectionnées'));clear.clicked.connect(lambda:self.set_values([]));layout.addWidget(clear)
        for value in sorted(set(values),key=str.casefold):self.add(value)
        self.list.itemChanged.connect(lambda _:self.bar.set_tags(self.values()))
        self.search.textChanged.connect(self.filter);self.bar.set_tags([])
    def add(self,value):
        item=QListWidgetItem(value);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked);self.list.addItem(item)
    def values(self):
        return [self.list.item(i).text() for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]
    def set_values(self,values):
        values=set(values);self.list.blockSignals(True)
        known={self.list.item(i).text() for i in range(self.list.count())}
        for value in sorted(values-known):self.add(value)
        for i in range(self.list.count()):
            item=self.list.item(i);item.setCheckState(Qt.CheckState.Checked if item.text() in values else Qt.CheckState.Unchecked)
        self.list.blockSignals(False);self.filter(self.search.text());self.bar.set_tags(self.values())
    def remove(self,value):self.set_values([v for v in self.values() if v!=value])
    def filter(self,text):
        from .data import normalize
        text=normalize(text)
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(text not in normalize(item.text()))
