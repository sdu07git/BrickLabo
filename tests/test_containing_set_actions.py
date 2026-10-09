"""Set actions retain row identity and navigate the real main catalogue."""
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from atelier.app import MainWindow,NAV
from atelier.dialogs import RelationsDialog
from atelier.windows import show_window
from test_storage_and_inventory_batches import Fixture,app


class ContainingSetActionsTests(Fixture):
    def setUp(self):
        super().setUp()
        for target in ('atelier.catalogue.Catalogue.load_thumbnails','atelier.preview.Preview.refresh','atelier.dialogs.RelationsDialog.show_set_image','atelier.thumbnails.PartThumbnails.load'):
            started=patch(target);started.start();self.addCleanup(started.stop)
        self.rb=self.item('set','75192-1','Falcon',source='RB');self.bl=self.item('set','75192','Falcon BrickLink',source='BL');self.alt=self.item('set','ALT-Falcon','My Falcon',source='ALT')
        self.second=self.item('set','10001-1','Autre set',source='RB')
        for n,iid in enumerate((self.rb,self.second),1):
            item=self.db.get_item(iid);self.db.run('INSERT INTO inventories VALUES(?,?,?)',(n,1,item['ref']));self.db.run('INSERT INTO inventory_parts VALUES(?,?,?,?,?,?)',(n,'3005',4,2,0,''))
        self.owner=self.keep(MainWindow(self.db));self.owner.startup_timer.stop();self.owner.show();app.processEvents()
        self.dialog=RelationsDialog(self.db,self.owner.engine,self.db.get_item(self.part),self.owner);show_window(self.dialog,self.owner);app.processEvents()
    def test_right_click_after_sort_targets_the_clicked_set_and_offers_three_actions(self):
        self.dialog.set_table.sortItems(1,Qt.SortOrder.DescendingOrder)
        row=next(r for r in range(self.dialog.set_table.rowCount()) if self.dialog.set_table.item(r,0).text()=='75192-1')
        pos=self.dialog.set_table.visualItemRect(self.dialog.set_table.item(row,0)).center();actions=[]
        class TestMenu(QMenu):
            def exec(menu,*args):
                actions.extend(a.text() for a in menu.actions());next(a for a in menu.actions() if a.text()=='Voir les constructions alternatives').trigger()
        with patch('atelier.dialogs.QMenu',TestMenu),patch.object(self.dialog,'show_alternates') as opened:
            self.dialog.set_context_menu(pos);self.assertEqual(opened.call_args.args[0]['id'],self.rb)
        self.assertEqual(actions,['Afficher la boîte d’origine','Voir les constructions alternatives','Afficher dans le catalogue de sets']);self.assertEqual(self.dialog.active_set['id'],self.rb)
    def test_catalogue_action_resets_only_target_filters_and_selects_exact_set(self):
        for n in range(110):self.item('set',f'similar-{n}','75192-1 Falcon variant',source='RB')
        target=next(c for c in self.owner.catalogues if c.source=='RB' and c.kind=='set' and c.scope=='catalogue')
        unrelated=next(c for c in self.owner.catalogues if c.source=='RB' and c.kind=='part' and c.scope=='catalogue');unrelated.search.setText('3001');unrelated.timer.stop();unrelated.reset();previous=unrelated.filter_state()
        target.search.setText('unfindable');target.timer.stop();target.advanced={'stock':'yes','categories':['unfindable']};target.reload();self.assertEqual(target.total,0)
        target.page=3;target.year.addItem('1999','1999');target.year.setCurrentIndex(target.year.findData('1999'))
        before=self.db.rows('SELECT * FROM stock')
        menu=self.dialog.containing_set_menu(self.db.get_item(self.rb));action=next(a for a in menu.actions() if a.text()=='Afficher dans le catalogue de sets');action.trigger();app.processEvents()
        self.assertEqual(NAV[self.owner.nav.currentRow()][1:3],('RB','set'));self.assertEqual((target.total,target.page),(1,1));self.assertEqual(target.rows[0]['id'],self.rb)
        self.assertEqual(target.selection()[0]['id'],self.rb);self.assertEqual(self.owner.current_item['id'],self.rb);self.assertEqual(unrelated.filter_state(),previous)
        self.assertTrue(self.dialog.isVisible());self.assertFalse(self.dialog.isModal());self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
        target.reference_tag.click();self.assertIsNone(target.reference_filter);self.assertEqual(target.total,111)
    def test_navigation_selects_each_source_catalogue_and_hidden_sets_are_not_restored(self):
        for source,iid in [('RB',self.rb),('BL',self.bl),('ALT',self.alt)]:
            self.assertTrue(self.owner.show_catalogue_item(iid));self.assertEqual(NAV[self.owner.nav.currentRow()][1:3],(source,'set'));self.assertEqual(self.owner.current_item['id'],iid)
        before=self.owner.nav.currentRow();self.db.run('UPDATE items SET catalogue_hidden=1 WHERE id=?',(self.alt,));self.assertFalse(self.owner.show_catalogue_item(self.alt));self.assertEqual(self.owner.nav.currentRow(),before)
        self.db.run('DELETE FROM items WHERE id=?',(self.bl,))
        with patch('atelier.dialogs.QMessageBox.information') as note:
            self.dialog.show_in_catalogue({'id':self.bl});note.assert_called_once()
    def test_alternates_action_opens_modeless_window_using_existing_rebrickable_search(self):
        with patch('atelier.alternates.AlternatesDialog.load') as load:
            window=self.dialog.show_alternates(self.db.get_item(self.bl));self.assertEqual(window.reference.text(),'75192-1');load.assert_called_once_with(True)
        self.assertIs(window.parent(),self.owner);self.assertFalse(window.isModal());self.assertTrue(window.isVisible());self.assertTrue(self.dialog.isVisible());self.assertTrue(self.owner.isEnabled());window.reject()
