"""Keep large cabinets interactive while reusing unchanged scene objects."""
from unittest.mock import patch
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QStyleOptionGraphicsItem
from atelier import storage_wall as walls
from atelier.storage_panel import StoragePanel
from atelier.storage_quantities import put_entry
from test_storage_and_inventory_batches import Fixture,app


class LargeCabinetTests(Fixture):
    def panel(self,columns=30,rows=30):
        identity=walls.create_wall(self.db,'Grand meuble',columns,rows)
        panel=self.keep(StoragePanel(self.db,None));panel.resize(1100,850);panel.show();app.processEvents()
        return panel,identity

    def test_10000_drawers_are_created_once_and_retained_across_show_and_refresh(self):
        panel,identity=self.panel(100,100);items=dict(panel.items);cabinet=panel.cabinets[identity]
        self.assertEqual(len(items),10000)
        with patch('atelier.storage_panel.DrawerItem',side_effect=AssertionError('Unchanged drawers rebuilt')):
            panel.redraw();panel.refresh();panel.hide();panel.show();app.processEvents()
        self.assertIs(panel.cabinets[identity],cabinet)
        self.assertTrue(all(panel.items[key] is item for key,item in items.items()))
        self.assertEqual(len(panel.scene.items()),10001)
        self.assertEqual(len(walls.drawers(self.db,identity)),10000)

    def test_new_cabinet_preserves_existing_drawer_objects_in_overview(self):
        panel,first=self.panel();panel.all_walls.setChecked(True);old=dict(panel.items)
        second=walls.create_wall(self.db,'Autre meuble',30,30);panel.reload_walls(second)
        self.assertEqual(set(panel.cabinets),{first,second});self.assertEqual(len(panel.items),1800)
        self.assertTrue(all(panel.items[key] is item for key,item in old.items()))

    def test_changed_stock_contents_and_tooltip_refresh_without_rebuilding_cabinet(self):
        panel,identity=self.panel();drawer=walls.drawers(self.db,identity)[0]['id'];item=panel.items[drawer]
        before=self.db.rows('SELECT * FROM stock');put_entry(self.db,drawer,self.part,'4',20);panel.refresh()
        self.assertIs(panel.items[drawer],item);self.assertEqual(item.parts[0]['stored_quantity'],20);self.assertIn('3005',item.toolTip())
        self.assertIn('20',item.toolTip());self.assertEqual(self.db.rows('SELECT * FROM stock'),before)
        put_entry(self.db,drawer,self.part,'4',12,previous=item.parts[0]);panel.refresh()
        self.assertIs(panel.items[drawer],item);self.assertEqual(item.parts[0]['stored_quantity'],12)
        panel.choose_drawer(drawer);self.assertEqual(panel.rows[0]['stored_quantity'],12)

    def test_only_changed_cabinet_is_rebuilt_after_drawer_geometry_edit(self):
        panel,first=self.panel(4,4);second=walls.create_wall(self.db,'Autre meuble',4,4);panel.reload_walls(first)
        panel.all_walls.setChecked(True);unchanged={key:item for key,item in panel.items.items() if item.drawer['wall_id']==second}
        first_drawer=walls.drawers(self.db,first)[0];walls.save_drawer(self.db,first,1,1,2,1,'Large',first_drawer['id']);panel.refresh();app.processEvents()
        self.assertEqual(len(panel.items),31);self.assertEqual(panel.items[first_drawer['id']].drawer['width'],2)
        self.assertTrue(all(panel.items[key] is item for key,item in unchanged.items()))
        self.assertEqual(len(panel.scene.items()),33)

    def test_10000_drawer_overview_keeps_last_drawer_selection_inventory_and_zoom(self):
        panel,identity=self.panel(100,100);drawer=walls.drawers(self.db,identity)[-1]['id']
        put_entry(self.db,drawer,self.part,'4',20);panel.refresh();panel.choose_drawer(drawer)
        self.assertEqual(panel.drawer_id,drawer);self.assertEqual(panel.table.rowCount(),1)
        self.assertIn('20',panel.items[drawer].toolTip());self.assertTrue(panel.items[drawer].selected)
        item=panel.items[drawer];panel.view.zoom(20);self.assertIs(panel.items[drawer],item)
        panel.view.ensureVisible(item);app.processEvents()
        self.assertTrue(panel.view.mapToScene(panel.view.viewport().rect()).boundingRect().intersects(item.sceneBoundingRect()))

    def test_small_drawer_face_is_simplified_but_normal_zoom_draws_details(self):
        panel,_=self.panel(1,1);item=next(iter(panel.items.values()))
        image=QImage(300,180,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image);painter.scale(.1,.1)
        with patch.object(type(item),'thumbnail_boxes',side_effect=AssertionError('Sub-pixel thumbnails drawn')):
            item.paint(painter,QStyleOptionGraphicsItem())
        painter.end();self.assertNotEqual(image.pixelColor(3,3).alpha(),0)
        painter=QPainter(image)
        with patch.object(type(item),'thumbnail_boxes',wraps=item.thumbnail_boxes) as thumbnails:
            item.paint(painter,QStyleOptionGraphicsItem());self.assertTrue(thumbnails.called)
        painter.end()
