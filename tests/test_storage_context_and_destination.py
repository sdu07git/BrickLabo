"""The chosen cabinet controls drops and sorted proposals; removal is local."""
from unittest.mock import patch
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtWidgets import QMessageBox
from atelier import storage_assignment as assignment,storage_wall as walls
from atelier.storage_panel import StoragePanel
from test_storage_and_inventory_batches import Fixture,app


class DestinationTests(Fixture):
    def panel(self):
        self.db.run("UPDATE items SET category='Bricks'")
        a=walls.create_wall(self.db,'Premier meuble',5,6);b=walls.create_wall(self.db,'Autre meuble',5,6)
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1200,850);panel.show();panel.front.setChecked(True)
        panel.details_tabs.setCurrentWidget(panel.stock_browser)
        for _ in range(4):app.processEvents()
        return panel,a,b
    def snapshot(self):
        return {table:self.db.rows('SELECT * FROM '+table) for table in ('stock','stock_sets','stock_set_components','stock_undo')}
    def test_destination_selector_focuses_cabinet_for_drop_and_both_plan_buttons(self):
        panel,a,b=self.panel();before=self.snapshot()
        panel.stock_browser.target_wall.setCurrentIndex(panel.stock_browser.target_wall.findData(b));app.processEvents()
        self.assertEqual(panel.wall_id,b);self.assertEqual(set(panel.cabinets),{b});self.assertFalse(panel.all_walls.isChecked())
        window=panel.plan_storage(True);self.windows.append(window);self.assertEqual(window.plan['wall_id'],b)
        self.assertEqual({d['wall_id'] for d in window.plan['available']},{b})
        other=panel.plan_storage();self.windows.append(other);self.assertEqual(other.plan['wall_id'],b)
        chosen=walls.drawers(self.db,b)[0];panel.choose_drawer(chosen['id'])
        self.assertTrue(panel.place_selected({'entries':[(self.part,'4')],'origin':None,'catalogue':False}))
        self.assertEqual([p['id'] for p in walls.contents(self.db,chosen['id'])],[self.part]);self.assertEqual(walls.wall_contents(self.db,a),[])
        self.assertEqual(self.snapshot(),before)
    def test_parts_tab_auto_button_captures_filtered_or_selected_refs(self):
        panel,a,b=self.panel();panel.stock_browser.query.setText('3005');panel.stock_browser.timer.stop();panel.stock_browser.reload()
        captured=[]
        with patch('atelier.storage_panel.show_window',side_effect=lambda window,*args,**kwargs:captured.append(window)):
            panel.stock_browser.auto_sort.click()
        self.assertEqual(len(captured),1);window=captured[0];self.windows.append(window)
        self.assertEqual({entry for group in window.plan['groups'] for entry in group['entries']},{(self.part,'4')})
    def test_thirty_drawers_fill_by_category_and_size_from_top_to_bottom(self):
        panel,a,b=self.panel()
        for ref,name in [('10','Brick 1 x 2'),('11','Brick 2 x 2'),('12','Brick 2 x 6'),('13','Brick 1 x 8'),('14','Brick 2 x 8')]:
            iid=self.item('part',ref,name);self.db.run("UPDATE items SET category='Bricks' WHERE id=?",(iid,));self.db.add('stock',iid,'4',2)
        plan=assignment.propose(self.db,a,'Bricks');positions={d['id']:(d['row'],d['col']) for d in plan['available']}
        self.assertEqual([positions[group['drawer_id']] for group in plan['groups']],sorted(positions[group['drawer_id']] for group in plan['groups']))
        self.assertEqual(plan['groups'][0]['dimensions'],(1.,1.));self.assertEqual(positions[plan['groups'][0]['drawer_id']],(1,1))
        self.assertGreater(positions[plan['groups'][-1]['drawer_id']][0],1)
        before=self.snapshot();assignment.apply_proposal(self.db,plan);self.assertEqual(self.snapshot(),before)
    def test_catalogue_only_proposal_keeps_stock_and_rejects_stale_geometry(self):
        panel,a,b=self.panel();unowned=self.item('part','unowned','Brick 1 x 2');self.db.run("UPDATE items SET category='Bricks' WHERE id=?",(unowned,))
        before=self.snapshot();plan=assignment.propose(self.db,b,entries=[(unowned,'')],from_catalogue=True)
        self.assertEqual(plan['groups'][0]['entries'],[(unowned,'')])
        self.db.run("UPDATE items SET name='Brick 2 x 4' WHERE id=?",(unowned,))
        storage=walls.print_snapshot(self.db)
        with self.assertRaises(ValueError):assignment.apply_proposal(self.db,plan)
        self.assertEqual(walls.print_snapshot(self.db),storage)
        plan=assignment.propose(self.db,b,entries=[(unowned,'')],from_catalogue=True);assignment.apply_proposal(self.db,plan)
        self.assertEqual(self.snapshot(),before);self.assertEqual(walls.wall_contents(self.db,a),[])
    def context(self,panel,drawer,choose):
        panel.all_walls.setChecked(True);panel.redraw();panel.fit();app.processEvents();item=panel.items[drawer['id']]
        point=panel.view.mapFromScene(item.mapToScene(item.transform_face.map(QPointF(45,35))))
        def execute():
            menu=app.activePopupWidget()
            try:choose(menu)
            finally:menu.close()
        QTimer.singleShot(30,execute);panel.drawer_context_menu(point)
    def test_right_click_removes_only_the_chosen_reference_from_clicked_drawer(self):
        panel,a,b=self.panel();da=walls.drawers(self.db,a)[0];db=walls.drawers(self.db,b)[0]
        self.db.add('stock',self.part,'1',3)
        walls.assign(self.db,da['id'],[(self.part,'4'),(self.part,'1'),(self.other,'4')]);walls.assign(self.db,db['id'],[(self.part,'4')]);panel.refresh();panel.choose_drawer(db['id']);before=self.snapshot()
        def choose(menu):
            submenu=next(action.menu() for action in menu.actions() if action.menu())
            action=next(action for action in submenu.actions() if 'RB 3005 ' in action.text() and action.text().endswith(' · 4'));action.trigger()
        self.context(panel,da,choose)
        self.assertEqual({(p['id'],p['chosen_color']) for p in walls.contents(self.db,da['id'])},{(self.part,'1'),(self.other,'4')})
        self.assertEqual([p['id'] for p in walls.contents(self.db,db['id'])],[self.part]);self.assertEqual(self.snapshot(),before)
    def test_cancelled_remove_all_and_empty_drawer_menu_preserve_contents(self):
        panel,a,b=self.panel();drawer=walls.drawers(self.db,a)[0];empty=walls.drawers(self.db,a)[1]
        walls.assign(self.db,drawer['id'],[(self.part,'4')]);panel.refresh();before=walls.print_snapshot(self.db)
        with patch('atelier.storage_panel.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
            self.context(panel,drawer,lambda menu:next(action for action in menu.actions() if action.text()=='Retirer toutes les références du tiroir…').trigger())
        self.assertEqual(walls.print_snapshot(self.db),before)
        def empty_menu(menu):
            self.assertTrue(menu.actions()[0].isEnabled()) # Empty drawers can still be edited.
            self.assertTrue(all(not action.isEnabled() for action in menu.actions()[1:]))
        self.context(panel,empty,empty_menu);self.assertEqual(walls.print_snapshot(self.db),before)
    def test_destination_list_refreshes_after_rename_and_removal(self):
        panel,a,b=self.panel();panel.stock_browser.target_wall.setCurrentIndex(panel.stock_browser.target_wall.findData(b))
        walls.rename_wall(self.db,b,'Briques');panel.reload_walls();self.assertEqual(panel.stock_browser.target_wall.currentText(),'Briques')
        walls.delete_wall(self.db,b);panel.reload_walls();self.assertEqual(panel.stock_browser.target_wall.currentData(),a)


if __name__=='__main__':
    import unittest
    unittest.main()
