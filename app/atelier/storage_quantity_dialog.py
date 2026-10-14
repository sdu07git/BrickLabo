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
