from test_storage_and_inventory_batches import Fixture
from atelier import storage_wall as walls
from atelier.storage_presence import locations,describe
from atelier.catalogue import Catalogue


class PresenceTests(Fixture):
    def cabinet(self):
        wall=walls.create_wall(self.db,'Atelier',2,3)
        drawer=walls.drawers(self.db,wall)[0]['id']
        walls.assign(self.db,drawer,[(self.part,'4')]);return drawer

    def test_missing_and_multiple_addresses_preserve_stock(self):
        self.assertEqual(describe(self.db.get_item(self.part),[],'catalogue'),'Aucun tiroir')
        first=self.cabinet();wall=walls.create_wall(self.db,'Second meuble',1,1)
        second=walls.drawers(self.db,wall)[0]['id'];walls.assign(self.db,second,[(self.part,'4')])
        entries=locations(self.db,[self.part,self.other]);text=describe(self.db.get_item(self.part),entries[self.part],'catalogue')
        self.assertIn('Déjà rangée',text);self.assertIn('Atelier',text);self.assertIn('Second meuble',text)
        self.assertNotIn(self.other,entries)
        self.assertEqual(self.db.rows('SELECT quantity FROM stock WHERE item_id=?',(self.part,))[0]['quantity'],40)
        walls.unassign(self.db,first);walls.unassign(self.db,second)
        self.assertEqual(locations(self.db,[self.part]),{})

    def test_colour_and_source_are_not_conflated(self):
        self.cabinet();item=dict(self.db.get_item(self.part));item['chosen_color']='1'
        self.assertIn('autre couleur',describe(item,locations(self.db,[self.part])[self.part],'stock'))
        other_source=self.item('part','3005',source='BL')
        self.assertEqual(locations(self.db,[other_source]),{})

    def test_catalogue_column_updates_and_can_stay_hidden(self):
        cat=self.keep(Catalogue(self.db,'RB','part'))
        col=cat.visible_columns.index('storage_location')
        row=next(i for i,r in enumerate(cat.rows) if r['id']==self.part)
        self.assertEqual(cat.table.item(row,col).text(),'Aucun tiroir')
        self.cabinet();cat.reload()
        self.assertIn('Atelier',cat.table.item(row,col).text())
        cat.toggle_column('storage_location',False)
        second=self.keep(Catalogue(self.db,'RB','part'))
        self.assertNotIn('storage_location',second.visible_columns)

    def test_two_references_in_one_drawer_are_both_found(self):
        drawer=self.cabinet();walls.assign(self.db,drawer,[(self.other,'4')])
        entries=locations(self.db,[self.part,self.other])
        for identity in (self.part,self.other):
            text=describe(self.db.get_item(identity),entries[identity],'catalogue')
            self.assertIn('Déjà rangée',text);self.assertIn('Atelier',text)
        self.assertEqual(entries[self.part][0]['col'],entries[self.other][0]['col'])
        self.assertEqual(entries[self.part][0]['row'],entries[self.other][0]['row'])

    def test_hidden_catalogue_rereads_addresses_when_shown(self):
        cat=self.keep(Catalogue(self.db,'RB','part'));cat.show();cat.hide()
        self.cabinet();cat.show()
        row=next(i for i,r in enumerate(cat.rows) if r['id']==self.part)
        cell=cat.table.item(row,cat.visible_columns.index('storage_location'))
        self.assertIn('Atelier',cell.text());self.assertEqual(cell.toolTip(),cell.text())

    def test_numeric_zero_colour_is_a_real_colour(self):
        self.cabinet();item=dict(self.db.get_item(self.part));item['chosen_color']=0
        self.assertIn('autre couleur',describe(item,locations(self.db,[self.part])[self.part],'stock'))
