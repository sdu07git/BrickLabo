"""Storage families describe footprint/shape, independently of catalogue categories."""
import re

from .data import normalize
from .i18n import tr


def prepare(c):
    c.execute('''CREATE TABLE IF NOT EXISTS storage_shape_overrides(
        item_id INTEGER PRIMARY KEY REFERENCES items(id),family TEXT NOT NULL)''')


def automatic(item):
    from .storage_assignment import stud_dimensions
    text=normalize(item.get('name',''));dimensions=stud_dimensions(text)
    # Explicit shape words take priority over a rectangular bounding footprint.
    families=(('wheel|tyre|tire|roue|pneu','Roues et pneus'),
              ('round|circular|cylinder|cone|rond|cylindre','Rondes et cylindriques'),
              ('slope|roof|pente|toit','Pentes'),('arch|arche','Arches'),
              ('wedge|wing|aile','Biseautées et ailes'),
              ('curved|courbe','Courbes'),('hinge|charniere','Charnières'))
    for words,label in families:
        if re.search(r'\b(?:'+words+r')\b',text):return tr(label)
    if dimensions:
        width=dimensions[0]
        if width==1:return tr('Étroites : 1 × N')
        if width==2:return tr('Larges : 2 × N')
        return tr('Grands formats : 3 tenons et plus') if width>=3 else tr('Formats fractionnaires')
    return tr('Forme non déterminée')


def family(item,overrides):
    return overrides.get(item['id']) or automatic(item)


def sort_key(label):
    standard=[tr(value) for value in ('Étroites : 1 × N','Larges : 2 × N','Grands formats : 3 tenons et plus','Formats fractionnaires','Rondes et cylindriques','Pentes','Arches','Biseautées et ailes','Courbes','Charnières','Roues et pneus','Forme non déterminée')]
    return (standard.index(label) if label in standard else len(standard)-1,normalize(label))


def set_family(db,identities,label=None):
    from .action_history import change
    identities=list(dict.fromkeys(identities))
    if not identities or len(identities)>5000 or any(type(i) is not int or i<=0 for i in identities):raise ValueError(tr('Sélection de pièces invalide.'))
    if label is not None:
        label=str(label).strip()
        if not label or len(label)>120:raise ValueError(tr('Indique une famille de rangement de 1 à 120 caractères.'))
    with db.connect() as c,change(c,('storage_shape_overrides',),tr('Famille de rangement des pièces')):
        for identity in identities:
            if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig')",(identity,)).fetchone():raise ValueError(tr('Sélection de pièces invalide.'))
            if label is None:c.execute('DELETE FROM storage_shape_overrides WHERE item_id=?',(identity,))
            else:c.execute('INSERT INTO storage_shape_overrides VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET family=excluded.family',(identity,label))


def edit_families(db,parent,changed):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLineEdit,QComboBox,QPushButton,QTableWidget,QAbstractItemView,QLabel
    from .ui_common import FlowLayout
    from .result_tables import fill_table,row_index
    from .windows import show_window
    dialog=QDialog(parent);dialog.setWindowTitle(tr('Familles de rangement'));dialog.resize(900,620)
    layout=QVBoxLayout(dialog);hint=QLabel(tr('La famille sert au rangement. Elle ne modifie pas la catégorie officielle du catalogue.'));hint.setWordWrap(True);layout.addWidget(hint)
    query=QLineEdit();query.setPlaceholderText(tr('Rechercher une référence ou un nom'));layout.addWidget(query)
    table=QTableWidget(0,5);table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Nom'),tr('Famille automatique'),tr('Forme / famille')]);table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(table,1)
    rows=[]
    def refresh():
        from .storage_assignment import catalogue_rows
        rows[:]=catalogue_rows(db,query.text(),limit=500)
        overrides={r['item_id']:r['family'] for r in db.rows('SELECT * FROM storage_shape_overrides')}
        fill_table(table,[(r['source'],r['ref'],r['name'],automatic(r),family(r,overrides)) for r in rows])
    controls=FlowLayout();combo=QComboBox();combo.setEditable(True)
    for label in ('Étroites : 1 × N','Larges : 2 × N','Grands formats : 3 tenons et plus','Rondes et cylindriques','Pentes','Arches','Biseautées et ailes','Courbes','Charnières','Roues et pneus'):combo.addItem(tr(label))
    controls.addWidget(combo)
    def apply(reset=False):
        from .collection_dialogs import safe
        selected=sorted({row_index(table,index.row()) for index in table.selectionModel().selectedRows()})
        if not selected:return
        def run():set_family(db,[rows[index]['id'] for index in selected],None if reset else combo.currentText());refresh();changed()
        safe(dialog,run)
    for text,callback in [(tr('Appliquer la famille à la sélection'),lambda:apply()),(tr('Rétablir la famille automatique'),lambda:apply(True))]:
        button=QPushButton(text);button.clicked.connect(callback);controls.addWidget(button)
    layout.addLayout(controls);query.textChanged.connect(refresh);refresh();show_window(dialog,parent)
    return dialog
