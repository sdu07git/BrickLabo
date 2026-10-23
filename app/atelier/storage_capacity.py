"""User-measured capacities; no volume or unit count is inferred from a photo."""
import math
import uuid
from collections import OrderedDict

from .i18n import tr

TABLES=('storage_formats','storage_wall_formats','storage_capacities')


def prepare(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS storage_formats(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS storage_wall_formats(wall_id INTEGER PRIMARY KEY REFERENCES storage_walls(id) ON DELETE CASCADE,
        format_id TEXT NOT NULL REFERENCES storage_formats(id));
        CREATE TABLE IF NOT EXISTS storage_capacities(format_id TEXT NOT NULL REFERENCES storage_formats(id),item_id INTEGER NOT NULL REFERENCES items(id),
        width INTEGER NOT NULL CHECK(width>0),height INTEGER NOT NULL CHECK(height>0),capacity INTEGER NOT NULL CHECK(capacity>0),
        PRIMARY KEY(format_id,item_id,width,height));''')


def state(c):
    return {table:[dict(r) for r in c.execute('SELECT * FROM '+table+' ORDER BY 1,2')] for table in TABLES}


def save(db,wall_id,name,rules):
    from .action_history import change
    name=name.strip()
    if not name or len(name)>120:raise ValueError(tr('Nom de format invalide.'))
    with db.connect() as c,change(c,TABLES,tr('Capacité des tiroirs')):
        if not c.execute('SELECT 1 FROM storage_walls WHERE id=?',(wall_id,)).fetchone():raise ValueError(tr('Meuble introuvable.'))
        found=c.execute('SELECT id FROM storage_formats WHERE name=?',(name,)).fetchone();format_id=found['id'] if found else uuid.uuid4().hex
        c.execute('INSERT OR IGNORE INTO storage_formats VALUES(?,?)',(format_id,name))
        c.execute('INSERT INTO storage_wall_formats VALUES(?,?) ON CONFLICT(wall_id) DO UPDATE SET format_id=excluded.format_id',(wall_id,format_id))
        for identity,width,height,capacity in rules:
            if any(type(n) is not int for n in (identity,width,height,capacity)) or not 1<=width<=100 or not 1<=height<=100 or not 0<=capacity<=1000000000:raise ValueError(tr('Capacité de tiroir invalide.'))
            if not c.execute("SELECT 1 FROM items WHERE id=? AND kind IN ('part','minifig')",(identity,)).fetchone():raise ValueError(tr('Sélection de pièces invalide.'))
            c.execute('DELETE FROM storage_capacities WHERE format_id=? AND item_id=? AND width=? AND height=?',(format_id,identity,width,height))
            if capacity:c.execute('INSERT INTO storage_capacities VALUES(?,?,?,?,?)',(format_id,identity,width,height,capacity))
    return format_id


def limits(snapshot):
    formats={r['wall_id']:r['format_id'] for r in snapshot['storage_wall_formats']}
    rules={(r['format_id'],r['item_id'],r['width'],r['height']):r['capacity'] for r in snapshot['storage_capacities']}
    return lambda drawer,identity:rules.get((formats.get(drawer['wall_id']),identity,drawer['width'],drawer['height']))


def adjust(plan,snapshot,drawer_counts):
    from .storage_draft import block
    capacity=limits(snapshot);available=plan['available'];used=set();series=OrderedDict();expanded=[]
    for group in plan['groups']:series.setdefault(tuple(group['entries']),group)
    for entries,group in series.items():
        identity=entries[0][0];free=[d for d in available if d['id'] not in used and capacity(d,identity)]
        quantities={entry:plan['quantities'].get(entry) for entry in entries}
        if any(q is None for q in quantities.values()):raise ValueError(tr('Renseigne les quantités avant d’appliquer les capacités.'))
        total=sum(quantities.values());minimum=drawer_counts.get(identity,1)
        # Prefer consecutive slots in one cabinet. A single ordered pass also
        # supports overflow into the next cabinet when no local block fits.
        chosen=[];space=0
        for drawer in free:
            chosen.append(drawer);space+=capacity(drawer,identity)
            if space>=total and len(chosen)>=minimum:break
        if space<total or len(chosen)<minimum:
            raise ValueError(tr('Capacité connue insuffisante pour ')+group['references'][0]+tr('. Ajoute des règles de capacité ou des tiroirs disponibles.'))
        nearby=block(free,len(chosen))
        lookup={d['id']:d for d in free}
        if nearby and sum(capacity(lookup[i],identity) for i in nearby)>=total:chosen=[lookup[i] for i in nearby]
        remaining=dict(quantities)
        for index,drawer in enumerate(chosen):
            room=capacity(drawer,identity);allocated={}
            for entry in entries:
                take=min(remaining[entry],room);allocated[entry]=take;remaining[entry]-=take;room-=take
            row=dict(group,drawer_id=drawer['id'],split_index=index,split_count=len(chosen),quantities=allocated,capacity=capacity(drawer,identity))
            # Remove a previous split suffix before writing the final count.
            base=group['name'];suffix=' ('+str(group['split_index']+1)+'/'+str(group['split_count'])+')'
            if group['split_count']>1 and base.endswith(suffix):base=base[:-len(suffix)]
            row['name']=base+(' ('+str(index+1)+'/'+str(len(chosen))+')' if len(chosen)>1 else '')
            expanded.append(row);used.add(drawer['id'])
    if len(expanded)>20000:raise ValueError(tr('La proposition dépasse 20 000 tiroirs. Réduis la sélection ou le nombre de tiroirs par référence.'))
    plan.update(groups=expanded,use_capacities=True,capacity_state=snapshot,shared_drawers=False)


def validate(plan,targets):
    if not plan.get('use_capacities'):return
    capacity=limits(plan['capacity_state']);drawers={d['id']:d for d in plan['available']}
    for group,target in zip(plan['groups'],targets):
        if target is None:continue
        limit=capacity(drawers[target],group['entries'][0][0])
        if limit is None or sum(group['quantities'].values())>limit:raise ValueError(tr('Ce tiroir n’a pas la capacité requise. Choisis un autre tiroir ou recalcule la proposition.'))


def edit_capacities(db,parent,changed):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QLineEdit,QTableWidget,QPushButton,QSpinBox,QAbstractItemView
    from .ui_common import FlowLayout
    from .result_tables import fill_table,row_index
    from .windows import show_window
    dialog=QDialog(parent);dialog.setWindowTitle(tr('Formats et capacités des tiroirs'));dialog.resize(900,620);layout=QVBoxLayout(dialog)
    note=QLabel(tr('Indique le nombre de pièces qui tient réellement dans ce format de tiroir. Une capacité de 0 efface la règle. Les règles sont communes aux meubles utilisant le même format.'));note.setWordWrap(True);layout.addWidget(note)
    bar=FlowLayout();walls=QComboBox()
    for r in db.rows('SELECT * FROM storage_walls ORDER BY name'):walls.addItem(r['name'],r['id'])
    bar.addWidget(walls);name=QComboBox();name.setEditable(True)
    for r in db.rows('SELECT * FROM storage_formats ORDER BY name'):name.addItem(r['name'])
    bar.addWidget(name);size=QComboBox();bar.addWidget(size);layout.addLayout(bar)
    search=QLineEdit();search.setPlaceholderText(tr('Rechercher une référence ou un nom'));layout.addWidget(search)
    table=QTableWidget(0,4);table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Nom'),tr('Capacité')]);table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);layout.addWidget(table,1);rows=[];spins=[]
    def refresh():
        from .storage_assignment import stock_rows
        rows[:]=list({r['id']:r for r in stock_rows(db,query=search.text(),limit=500)}.values());spins.clear()
        fill_table(table,[(r['source'],r['ref'],r['name'],'') for r in rows],sortable=False)
        fmt=db.rows('SELECT id FROM storage_formats WHERE name=?',(name.currentText(),));dimensions=size.currentData()
        rules={r['item_id']:r['capacity'] for r in db.rows('SELECT * FROM storage_capacities WHERE format_id=? AND width=? AND height=?',(fmt[0]['id'],*dimensions))} if fmt and dimensions else {}
        for index,row in enumerate(rows):
            spin=QSpinBox();spin.setRange(0,1000000000);spin.setValue(rules.get(row['id'],0));spin.setSpecialValueText(tr('Non définie'));table.setCellWidget(index,3,spin);spins.append(spin)
    def wall_changed():
        size.blockSignals(True);size.clear()
        for r in db.rows('SELECT DISTINCT width,height FROM storage_drawers WHERE wall_id=? ORDER BY width,height',(walls.currentData(),)):size.addItem(str(r['width'])+' × '+str(r['height']),(r['width'],r['height']))
        size.blockSignals(False);fmt=db.rows('SELECT f.name FROM storage_wall_formats w JOIN storage_formats f ON f.id=w.format_id WHERE w.wall_id=?',(walls.currentData(),))
        name.setCurrentText(fmt[0]['name'] if fmt else '');refresh()
    def apply():
        from .collection_dialogs import safe
        def run():
            dimensions=size.currentData()
            if not dimensions:return
            save(db,walls.currentData(),name.currentText(),[(r['id'],*dimensions,s.value()) for r,s in zip(rows,spins)]);refresh();changed()
        safe(dialog,run)
    button=QPushButton(tr('Enregistrer les capacités'));button.clicked.connect(apply);layout.addWidget(button)
    walls.currentIndexChanged.connect(wall_changed);size.currentIndexChanged.connect(refresh);name.activated.connect(refresh);search.textChanged.connect(refresh);wall_changed();show_window(dialog,parent);return dialog
