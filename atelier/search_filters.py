"""Composable catalogue filters and portable named presets."""
from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QComboBox,QLineEdit,QPushButton,QDialogButtonBox,QMessageBox,QInputDialog,QScrollArea,QWidget)
from .i18n import tr

class FilterDialog(QDialog):
    def __init__(self,catalogue):
        super().__init__(catalogue);self.catalogue=catalogue;self.db=catalogue.db
        self.setWindowTitle(tr('Recherche et filtres avancés'));self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint);self.resize(630,610)
        self.preset_key='search_presets_'+catalogue.key;self.presets=self.db.setting(self.preset_key,{})
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();scroll.setWidget(content);outer.addWidget(scroll);layout=QVBoxLayout(content);info=QLabel(tr('Les filtres se combinent sur tout le catalogue, avant le tri et la pagination.'));info.setWordWrap(True);layout.addWidget(info)
        status=QLabel(tr('Recherche locale indexée : SQLite FTS5') if self.db.search_index_available else tr('Recherche compatible : index FTS5 indisponible'));layout.addWidget(status)
        row=QHBoxLayout();self.presets_combo=QComboBox();row.addWidget(self.presets_combo,1)
        for label,func in [(tr('Charger'),self.load_preset),(tr('Enregistrer…'),self.save_preset),(tr('Supprimer'),self.delete_preset)]:
            b=QPushButton(label);b.clicked.connect(func);row.addWidget(b)
        layout.addLayout(row);self.refresh_presets()
        form=QFormLayout();layout.addLayout(form);self.fields={}
        self.search=QLineEdit();form.addRow(tr('Recherche'),self.search)
        from .category_tags import CategoryTags
        self.categories=CategoryTags([catalogue.category.itemData(i) for i in range(catalogue.category.count()) if catalogue.category.itemData(i)])
        form.addRow(tr('Catégories (tags)'),self.categories)
        if catalogue.source is None:
            combo=QComboBox();combo.addItem(tr('Toutes les sources'),'')
            for source in ('RB','BL','BA','ALT'):combo.addItem(source,source)
            self.fields['source']=combo;form.addRow(tr('Source'),combo)
        for key,label in [('stock',tr('Présence dans Mon stock')),('photo',tr('Adresse de photo renseignée')),('printed',tr('Sérigraphie')),('sticker',tr('Sticker'))]:
            combo=QComboBox()
            for name,value in [(tr('Indifférent'),''),(tr('Oui'),'yes'),(tr('Non'),'no')]:combo.addItem(name,value)
            self.fields[key]=combo;form.addRow(label,combo)
        for key,label,placeholder in [('year_min',tr('Année minimale'),'1990'),('year_max',tr('Année maximale'),'2026'),('import_from',tr('Importé à partir du'),'YYYY-MM-DD'),('import_to',tr('Importé jusqu’au'),'YYYY-MM-DD')]:
            field=QLineEdit();field.setPlaceholderText(placeholder);self.fields[key]=field;form.addRow(label,field)
        if catalogue.scope in ('stock','queue','history'):
            field=QLineEdit();field.setPlaceholderText(tr('Identifiant exact de couleur'));self.fields['color']=field;form.addRow(tr('Couleur'),field)
        note=QLabel(tr('Une adresse de photo ne garantit pas que le site est accessible. Les dates d’import anciennes non renseignées sont exclues des filtres par date.'));note.setWordWrap(True);layout.addWidget(note)
        reset=QPushButton(tr('Réinitialiser tous les filtres'));reset.clicked.connect(lambda:self.set_state({}));layout.addWidget(reset)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);outer.addWidget(buttons)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply);buttons.rejected.connect(self.reject)
        self.set_state(catalogue.filter_state())

    def refresh_presets(self):
        self.presets_combo.clear();self.presets_combo.addItems(sorted(self.presets))

    def state(self):
        advanced={}
        for key,field in self.fields.items():
            value=field.currentData() if isinstance(field,QComboBox) else field.text().strip()
            if value:
                if key=='source':advanced['sources']=[value]
                else:advanced[key]=value
        if self.categories.values():advanced['categories']=self.categories.values()
        return {'search':self.search.text(),'category':'',
                'year':self.exact_year,'hide_decorated':self.hide_decorated,'advanced':advanced}

    def set_state(self,state):
        self.search.setText(state.get('search',''))
        self.categories.set_values(state.get('advanced',{}).get('categories') or ([state['category']] if state.get('category') else []))
        self.exact_year=state.get('year','');self.hide_decorated=bool(state.get('hide_decorated',False))
        advanced=state.get('advanced',{})
        for key,field in self.fields.items():
            value=(advanced.get('sources') or [''])[0] if key=='source' else advanced.get(key,'')
            if isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
            else:field.setText(str(value))

    def validate(self):
        state=self.state();f=state['advanced']
        for key in ('year_min','year_max'):
            if f.get(key) and (len(f[key])!=4 or not f[key].isdigit()):
                QMessageBox.warning(self,tr('Filtres'),tr('Saisis une année à quatre chiffres.'));return False
        for key in ('import_from','import_to'):
            if f.get(key):
                try:
                    if date.fromisoformat(f[key]).isoformat()!=f[key]:raise ValueError()
                except ValueError:
                    QMessageBox.warning(self,tr('Filtres'),tr('Saisis les dates au format AAAA-MM-JJ.'));return False
        if (f.get('year_min') and f.get('year_max') and f['year_min']>f['year_max']) or (f.get('import_from') and f.get('import_to') and f['import_from']>f['import_to']):
            QMessageBox.warning(self,tr('Filtres'),tr('La borne minimale doit précéder la borne maximale.'));return False
        return True

    def apply(self):
        if self.validate():self.accept()

    def load_preset(self):
        state=self.presets.get(self.presets_combo.currentText())
        if state is not None:self.set_state(state)

    def save_preset(self):
        if not self.validate():return
        name,ok=QInputDialog.getText(self,tr('Enregistrer les filtres'),tr('Nom du réglage :'))
        name=name.strip()
        if ok and name:
            self.presets[name]=self.state();self.db.set_setting(self.preset_key,self.presets);self.refresh_presets();self.presets_combo.setCurrentText(name)

    def delete_preset(self):
        name=self.presets_combo.currentText()
        if name in self.presets:
            if QMessageBox.question(self,tr('Supprimer'),tr('Supprimer ce réglage enregistré ?'))!=QMessageBox.StandardButton.Yes:return
            del self.presets[name];self.db.set_setting(self.preset_key,self.presets);self.refresh_presets()
