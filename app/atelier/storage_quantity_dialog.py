"""Edit one physical count or transfer part of it to another drawer."""
import sqlite3
from PySide6.QtWidgets import QDialog,QFormLayout,QLabel,QComboBox,QSpinBox,QDialogButtonBox,QMessageBox
from .i18n import tr,tf
from .windows import show_window,application_owner
from . import storage_wall as walls
from . import storage_quantities as quantities


def quantity_dialog(panel, row, transfer=False):
    drawer_id = panel.drawer_id
    if drawer_id is None: return
    db = panel.db
    dialog = QDialog(panel); dialog._storage_drawer_id = drawer_id
    dialog.setWindowTitle(tr('Transférer une quantité') if transfer else tr('Quantité dans ce tiroir')); dialog.resize(520,270)
    form = QFormLayout(dialog)
    name = QLabel(row['source']+' '+row['ref']+' · '+row['name']); name.setWordWrap(True); form.addRow(name)
    color = QComboBox(); current_color = row['chosen_color']
    if current_color or row.get('stored_quantity') not in (None,0):
        color.addItem(current_color or tr('Non précisée'),current_color); color.setEnabled(False)
    else:
        stock = db.rows('SELECT color,quantity FROM stock WHERE item_id=? AND quantity>0 ORDER BY color',(row['id'],))
        for part in stock: color.addItem(part['color'] or tr('Non précisée'),part['color'])
        if not stock: color.addItem(tr('Non précisée'),current_color)
        color.setCurrentIndex(max(0,color.findData(current_color)))
    form.addRow(tr('Couleur'),color)
    count = QSpinBox(); count.setRange(0,1000000000)
    note = QLabel(); note.setWordWrap(True)
    target_wall = QComboBox(); target_drawer = QComboBox()
    if transfer:
        if not row.get('stored_quantity'): return
        color.setEnabled(False); count.setRange(1,row['stored_quantity']); count.setValue(row['stored_quantity'])
        for wall in walls.walls(db): target_wall.addItem(wall['name'],wall['id'])
        def reload_drawers(*_):
            target_drawer.clear()
            for drawer in walls.drawers(db,target_wall.currentData()):
                if drawer['id']!=drawer_id: target_drawer.addItem(walls.address(drawer)+' · '+drawer['name'],drawer['id'])
        target_wall.currentIndexChanged.connect(reload_drawers); reload_drawers()
        form.addRow(tr('Meuble de destination'),target_wall); form.addRow(tr('Tiroir de destination'),target_drawer)
        note.setText(tr('Le transfert change les quantités des deux tiroirs et conserve le stock total.'))
    else:
        def maximum(*_):
            chosen = str(color.currentData() or '')
            with db.read() as c:
                remaining = quantities.available(c,row['id'],chosen)
                own = c.execute('SELECT quantity FROM storage_contents WHERE drawer_id=? AND item_id=? AND color=?',(drawer_id,row['id'],chosen)).fetchone()
            value = (own['quantity'] or 0) if own else 0
            count.setMaximum(max(0,remaining+value)); count.setValue(value)
            note.setText(tf('Maximum disponible pour ce tiroir : {0}. Les quantités du stock ne seront pas modifiées.',max(0,remaining+value)))
        color.currentIndexChanged.connect(maximum); maximum()
    form.addRow(tr('Quantité'),count); form.addRow(note)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); form.addRow(buttons); buttons.rejected.connect(dialog.reject)
    def save():
        try:
            if transfer:
                if target_drawer.currentData() is None: raise ValueError(tr('Choisis un tiroir de destination.'))
                quantities.transfer(db,drawer_id,target_drawer.currentData(),row['id'],current_color,count.value())
            else: quantities.set_quantity(db,drawer_id,row['id'],current_color,count.value(),str(color.currentData() or ''))
        except (ValueError,sqlite3.Error) as error: QMessageBox.warning(dialog,tr('Rangement'),str(error)); return
        panel.refresh(); owner = application_owner(panel)
        if hasattr(owner,'refresh_counts'): owner.refresh_counts()
        dialog.accept()
    buttons.accepted.connect(save); show_window(dialog,panel); return dialog


def drop_quantity_dialog(panel, source_drawer, target_drawer, rows):
    """A drop chooses counts without editing the stock or committing on opening."""
    from PySide6.QtWidgets import QVBoxLayout,QTableWidget,QHeaderView,QTableWidgetItem
    from .drawer_inventory import color_names,color_label
    rows=[dict(row) for row in rows]
    db=panel.db
    dialog=QDialog(panel);dialog._storage_drawer_id=source_drawer;dialog.setWindowTitle(tr('Quantités à déplacer'));dialog.resize(700,380)
    layout=QVBoxLayout(dialog)
    note=QLabel(tr('Choisis la quantité à déposer dans le tiroir de destination. Le reste demeure dans le tiroir d’origine ; le stock total est conservé. Les références sans comptage sont déplacées entièrement.'))
    note.setWordWrap(True);layout.addWidget(note)
    table=QTableWidget(len(rows),4);table.setHorizontalHeaderLabels([tr('Référence'),tr('Couleur'),tr('Dans le tiroir'),tr('À déplacer')]);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    table.setColumnWidth(1,155);table.setColumnWidth(2,110);table.setColumnWidth(3,120);layout.addWidget(table,1)
    names=color_names(db);counts=[]
    from PySide6.QtCore import Qt
    for index,row in enumerate(rows):
        color=str(row['chosen_color'] or '');quantity=row.get('stored_quantity')
        for column,value in enumerate([row['source']+' '+row['ref'],color_label(row,names),quantity if quantity is not None else tr('À renseigner')]):
            item=QTableWidgetItem(str(value));item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);table.setItem(index,column,item)
        count=QSpinBox();count.setRange(1,quantity) if quantity else count.setRange(0,0);count.setValue(quantity or 0);count.setEnabled(quantity is not None);table.setCellWidget(index,3,count);counts.append(count)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
    def save():
        entries=[(row['id'],row['chosen_color'],count.value() if row.get('stored_quantity') is not None else None,row.get('stored_quantity')) for row,count in zip(rows,counts)]
        try:quantities.transfer_entries(db,source_drawer,target_drawer,entries)
        except (ValueError,sqlite3.Error,OSError) as error:QMessageBox.warning(dialog,tr('Rangement'),str(error));return
        target=db.rows('SELECT wall_id FROM storage_drawers WHERE id=?',(target_drawer,))
        if target:panel.activate_wall(target[0]['wall_id']);panel.drawer_id=target_drawer
        panel.refresh();owner=application_owner(panel)
        if hasattr(owner,'refresh_counts'):owner.refresh_counts()
        dialog.accept()
    buttons.accepted.connect(save);show_window(dialog,panel);return dialog
