import tempfile,unittest
from pathlib import Path
from atelier.data import Database
class CategorySearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'db.sqlite')
        for row in [(1,'Icons',None),(2,'Vehicles',1),(3,'Classic Cars',2),(4,'City',None)]:self.db.run('INSERT INTO themes VALUES(?,?,?)',row)
    def tearDown(self):self.temp.cleanup()
    def item(self,ref,source='RB',kind='set',category='Icons',category_id='1',name='Flower',year='2026'):
        return self.db.run('INSERT INTO items(source,kind,ref,name,category,category_id,year,search) VALUES(?,?,?,?,?,?,?,?)',(source,kind,ref,name,category,category_id,year,(ref+' '+name).lower()))
    def test_category_search_is_case_and_accent_insensitive_and_combines_words(self):
        self.item('10300',category='Icôns',name='Flower Garden');self.item('60000',category='City',category_id='4',name='Garden')
        rows,total,_,_=self.db.query('RB','set',search='ICONS garden');self.assertEqual(total,1);self.assertEqual(rows[0]['ref'],'10300')
    def test_parent_family_matches_descendants_without_cross_source_ids(self):
        self.item('direct');self.item('child',category='Vehicles',category_id='2');self.item('grandchild',category='Classic Cars',category_id='3')
        self.item('city',category='City',category_id='4');self.item('bricklink',source='BL',category='Different family',category_id='1')
        rows,total,_,_=self.db.query('RB','set',search='icons');self.assertEqual(total,3);self.assertEqual({r['ref'] for r in rows},{'direct','child','grandchild'})
        self.assertEqual(self.db.query('BL','set',search='icons')[1],0)
    def test_search_covers_entire_catalogue_before_pagination_and_year_filter(self):
        for n in range(126):self.item(f'set-{n:03}',category='Classic Cars',category_id='3',year='2025')
        self.item('new',year='2026')
        rows,total,pages,page=self.db.query('RB','set',search='icons',year='2025',size=50,page=3,sort='ref',descending=True)
        self.assertEqual((total,pages,page),(126,3,3));self.assertEqual(len(rows),26);self.assertEqual(rows[0]['ref'],'set-025')
    def test_categories_work_for_parts_alternatives_and_existing_stock(self):
        for source in ('BL','ALT'):
            iid=self.item(source,source=source,kind='part',category='Bricks',category_id='');self.db.add('stock',iid)
            self.assertEqual(self.db.query(source,'part',search='bricks')[1],1);self.assertEqual(self.db.query(source,'part',search='bricks',scope='stock')[1],1)
            self.db.run('UPDATE items SET category=? WHERE id=?',('Special Bricks',iid));self.assertEqual(self.db.query(source,'part',search='special')[1],1)
    def test_literal_percent_and_underscore_do_not_become_wildcards(self):
        self.item('a',category='100%_Special');self.item('b',category='100XXSpecial')
        self.assertEqual(self.db.query('RB','set',search='100%_')[1],1)
