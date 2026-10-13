"""Set catalogue actions preserve destinations, quantities and atomic undo."""
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPushButton
from atelier.catalogue import Catalogue
from test_storage_and_inventory_batches import Fixture,app


class SetStockChoiceTests(Fixture):
    def seed(self):
        parent=self.item('set','1000-1');child=self.item('set','1001-1');fig=self.item('minifig','fig-1000')
        self.db.run('INSERT INTO inventories VALUES(?,?,?)',(91,1,'1000-1'))
        self.db.run('INSERT INTO inventories VALUES(?,?,?)',(92,1,'1001-1'))
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(91,'3005',4,2,0,''))
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(91,'3005',4,1,1,''))
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(92,'3001',4,3,0,''))
        self.db.run('INSERT INTO inventory_sets VALUES(?,?,?)',(91,'1001-1',2))
        self.db.run('INSERT INTO inventory_minifigs VALUES(?,?,?)',(91,'fig-1000',1))
        return parent,child,fig
    def quantity(self,item,color='4'):
        rows=self.db.rows('SELECT quantity FROM stock WHERE item_id=? AND color=?',(item,color));return rows[0]['quantity'] if rows else 0
    def snapshot(self):
        return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','queue','stock_undo')}
    def catalogue(self,source='RB'):
        widget=self.keep(Catalogue(self.db,source,'set'));widget.resize(650,650);widget.show();app.processEvents();return widget
    def choose_context(self,cat,caption):
        captured=[]
        def execute():
            menu=app.activePopupWidget()
            actions={action.text():action for action in menu.actions()};captured.extend(actions)
            try:actions[caption].trigger()
            finally:menu.close()
        point=cat.table.visualRect(cat.table.model().index(0,0)).center()
        QTimer.singleShot(30,execute)
        with patch('atelier.catalogue.QMessageBox.warning') as warning:
            cat.context_menu(point)
        self.assertFalse(warning.called,warning.call_args)
        self.assertIn('Ajouter l’inventaire à Mon stock',captured)
        self.assertIn('Ajouter le set à Mon stock set',captured)
        self.assertNotIn('Ajouter au stock',captured)
    def test_right_click_adds_loose_parts_spares_figures_and_nested_sets_only(self):
        parent,child,fig=self.seed();cat=self.catalogue();before=self.snapshot()
        self.choose_context(cat,'Ajouter l’inventaire à Mon stock')
        self.assertEqual(self.quantity(self.part),43);self.assertEqual(self.quantity(self.other),18);self.assertEqual(self.quantity(fig,''),1)
        self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),before['stock_sets'])
        self.assertEqual(self.db.rows('SELECT * FROM stock_set_components'),before['stock_set_components'])
        self.assertEqual(self.db.rows('SELECT * FROM queue'),before['queue'])
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT * FROM stock'),before['stock'])
    def test_right_click_adds_owned_set_with_followed_inventory_and_keeps_loose_quantities(self):
        parent,child,fig=self.seed();cat=self.catalogue();self.choose_context(cat,'Ajouter le set à Mon stock set')
        self.assertEqual(self.quantity(self.part),40);self.assertEqual(self.quantity(self.other),12)
        sets=self.db.rows('SELECT * FROM stock_sets');self.assertEqual(len(sets),1);self.assertEqual((sets[0]['item_id'],sets[0]['quantity']),(parent,1))
        components=self.db.rows('SELECT * FROM stock_set_components')
        self.assertEqual({(p['item_id'],p['color']):p['quantity'] for p in components},{(self.part,'4'):3,(self.other,'4'):6,(fig,''):1})
    def test_sorted_right_click_targets_clicked_reference(self):
        parent,child,fig=self.seed();cat=self.catalogue();cat.sort='ref';cat.desc=True;cat.reload()
        self.assertEqual(cat.rows[0]['id'],child);self.choose_context(cat,'Ajouter l’inventaire à Mon stock')
        self.assertEqual(self.quantity(self.other),15);self.assertEqual(self.quantity(self.part),40)
    def test_multiple_sets_and_multiplier_are_one_undoable_stock_addition(self):
        parent,child,fig=self.seed();cat=self.catalogue();before=self.snapshot()
        selected=[dict(self.db.get_item(parent),chosen_quantity=2),self.db.get_item(child)]
        with patch.object(cat,'selection',return_value=selected):cat.add_selected('set_parts_stock')
        self.assertEqual(self.quantity(self.part),46);self.assertEqual(self.quantity(self.other),27);self.assertEqual(self.quantity(fig,''),2)
        self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
        self.db.undo_last_action();self.assertEqual(self.db.rows('SELECT * FROM stock'),before['stock'])
    def test_missing_inventory_or_unresolved_part_rejects_the_entire_selection(self):
        parent,child,fig=self.seed();missing=self.item('set','9999-1');cat=self.catalogue();before=self.snapshot()
        for target in ('set_parts_stock','stock_sets'):
            with patch.object(cat,'selection',return_value=[self.db.get_item(parent),self.db.get_item(missing)]),patch('atelier.catalogue.QMessageBox.warning') as warning:
                cat.add_selected(target);warning.assert_called_once()
            self.assertEqual(self.snapshot(),before)
        self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(91,'unresolved',4,2,0,''))
        with patch.object(cat,'selection',return_value=[self.db.get_item(parent)]),patch('atelier.catalogue.QMessageBox.warning') as warning:
            cat.add_selected('set_parts_stock');warning.assert_called_once()
        self.assertEqual(self.snapshot(),before)
    def test_bricklink_and_alternative_inventories_keep_native_parts_and_colours(self):
        bl_part=self.item('part','bl-part','BrickLink part','BL');bl_set=self.item('set','bl-set','BrickLink set','BL')
        self.db.set_setting('bl_components_bl-set',[dict(self.db.get_item(bl_part),chosen_color='11',chosen_quantity=5)])
        cat=self.catalogue('BL')
        with patch.object(cat,'selection',return_value=[self.db.get_item(bl_set)]):cat.add_selected('set_parts_stock')
        self.assertEqual(self.quantity(bl_part,'11'),5);self.assertEqual(self.quantity(self.part),40)
        alt=self.item('set','alt-set','Alternative set','ALT');self.db.add_alt_component(alt,self.part,'4',7)
        cat=self.catalogue('ALT')
        with patch.object(cat,'selection',return_value=[self.db.get_item(alt)]):cat.add_selected('set_parts_stock')
        self.assertEqual(self.quantity(self.part),47);self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])
    def test_bottom_button_offers_both_destinations_without_adding_more_buttons(self):
        self.seed();cat=self.catalogue();buttons=[button for button in cat.findChildren(QPushButton) if button.text()=='Ajouter au stock…']
        self.assertEqual(len(buttons),1)
        self.assertEqual([a.text() for a in buttons[0].menu().actions()],['Ajouter l’inventaire à Mon stock','Ajouter le set à Mon stock set'])


if __name__=='__main__':
    import unittest
    unittest.main()
