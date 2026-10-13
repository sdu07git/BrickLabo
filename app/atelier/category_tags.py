"""Searchable category checklist and removable tags."""
from PySide6.QtCore import Qt,Signal,QPoint
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLineEdit,QListWidget,QListWidgetItem,QPushButton,QScrollArea,QLabel,QComboBox,QMenu,QWidgetAction
from .i18n import tr,tf
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
    selection_changed=Signal(list)
    def __init__(self,values,parent=None,show_tags=True):
        super().__init__(parent);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.show_tags=show_tags
        note=QLabel(tr('Cocher les catégories à afficher. Aucune catégorie cochée = toutes les catégories.'));note.setWordWrap(True);layout.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Rechercher une catégorie…'));layout.addWidget(self.search)
        self.list=QListWidget();self.list.setMinimumHeight(150);self.list.setMaximumHeight(190);layout.addWidget(self.list)
        self.bar=TagBar(self);self.bar.removed.connect(self.remove)
        if show_tags:layout.addWidget(self.bar)
        else:self.bar.hide()
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.select_all=QPushButton(tr('Sélectionner toutes les catégories'));self.select_all.clicked.connect(self.check_all);buttons.addWidget(self.select_all)
        clear=QPushButton(tr('Effacer les catégories sélectionnées'));clear.clicked.connect(lambda:self.set_values([]));buttons.addWidget(clear)
        matches=QHBoxLayout();layout.addLayout(matches)
        self.check_matches=QPushButton(tr('Cocher les résultats'));self.check_matches.setToolTip(tr('Cocher uniquement les catégories correspondant à la recherche, en conservant les autres choix.'));self.check_matches.clicked.connect(lambda:self.check_visible(True));matches.addWidget(self.check_matches)
        self.uncheck_matches=QPushButton(tr('Décocher les résultats'));self.uncheck_matches.setToolTip(tr('Décocher uniquement les catégories correspondant à la recherche, en conservant les autres choix.'));self.uncheck_matches.clicked.connect(lambda:self.check_visible(False));matches.addWidget(self.uncheck_matches)
        self.count=QLabel();layout.addWidget(self.count)
        for value in sorted(set(values),key=str.casefold):self.add(value)
        self.list.itemChanged.connect(self.update_selection)
        self.search.textChanged.connect(self.filter);self.update_selection()
    def update_selection(self,*_):
        values=self.values()
        if self.show_tags:self.bar.set_tags(values)
        self.count.setText(tf('{} / {} catégories sélectionnées',len(values),self.list.count()) if values else tr('Aucun filtre de catégorie : toutes les catégories.'))
        self.selection_changed.emit(values)
    def check_all(self):self.set_values(self.list.item(i).text() for i in range(self.list.count()))
    def check_visible(self,checked):
        blocked=self.list.blockSignals(True)
        for index in range(self.list.count()):
            item=self.list.item(index)
            if not item.isHidden():item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.blockSignals(blocked);self.update_selection()
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
        self.list.blockSignals(False);self.filter(self.search.text());self.update_selection()
    def remove(self,value):self.set_values([v for v in self.values() if v!=value])
    def filter(self,text):
        from .data import normalize
        text=normalize(text)
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(text not in normalize(item.text()))
        visible=any(not self.list.item(i).isHidden() for i in range(self.list.count()))
        self.check_matches.setEnabled(visible);self.uncheck_matches.setEnabled(visible)


class CheckableCategoryBox(QComboBox):
    """A compact category selector with a searchable multi-choice popup."""
    values_changed=Signal(list)
    def __init__(self,parent=None):
        super().__init__(parent);self._values=[];self.menu=None;self.picker=None
    def set_values(self,values):
        self._values=list(dict.fromkeys(values));blocked=self.blockSignals(True)
        index=self.findData(self._values[0]) if len(self._values)==1 else 0
        self.setItemText(0,tr('Catégories : ')+str(len(self._values)) if self._values and (len(self._values)>1 or index<0) else tr('Toutes les catégories'))
        self.setCurrentIndex(max(0,index));self.blockSignals(blocked)
        self.setToolTip(tr('Cocher ou décocher les catégories à afficher.'))
    def showPopup(self):
        if self.menu:self.menu.deleteLater()
        self.menu=QMenu(self);action=QWidgetAction(self.menu)
        values=[self.itemData(index) for index in range(self.count()) if self.itemData(index)]
        self.picker=CategoryTags(values,show_tags=False);self.picker.set_values(self._values)
        self.picker.selection_changed.connect(self.choose_values);action.setDefaultWidget(self.picker);self.menu.addAction(action)
        self.menu.aboutToHide.connect(super().hidePopup)
        self.menu.popup(self.mapToGlobal(QPoint(0,self.height())));self.picker.search.setFocus()
    def choose_values(self,values):
        self.set_values(values);self.values_changed.emit(values)
    def hidePopup(self):
        if self.menu:self.menu.hide()
        super().hidePopup()
