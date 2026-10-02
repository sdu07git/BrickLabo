import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from atelier.data import Database
from atelier.labels import page_layout,render_label,default_template,export_pdf
from PIL import Image


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name);self.db=Database(self.folder/'data.sqlite')
    def tearDown(self):self.tmp.cleanup()
    def archive(self,name,header,rows):
        content=io.StringIO();w=csv.writer(content);w.writerow(header);w.writerows(rows)
        p=self.folder/(name+'.csv.zip')
        with zipfile.ZipFile(p,'w') as z:z.writestr(name+'.csv',content.getvalue())
        self.db.import_file(p)
    def parts(self):
        self.archive('part_categories',['id','name'],[[1,'Bricks']])
        self.archive('parts',['part_num','name','part_cat_id'],[[str(i),f'Brick 1 x 1 variant {99-i:03}',1] for i in range(30)])
    def test_category_defaults_are_unique_stable_and_customizable(self):
        from atelier.labels import category_outline
        for i in range(600):
            self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part',str(i),'Part',f'Category {i}','part'))
        colors=[category_outline(f'Category {i}',self.db) for i in range(600)]
        self.assertEqual(len(set(colors)),600)
        reopened=Database(self.db.path)
        self.assertEqual(category_outline('Category 50',reopened),colors[50])
        new_color=category_outline('New category',reopened)
        self.assertNotIn(new_color,colors)
        self.assertEqual(category_outline('Category 50',reopened),colors[50])
        custom=default_template();custom['category_colors']['Category 50']='#123456'
        self.assertEqual(category_outline('Category 50',reopened,custom),'#123456')
        self.assertEqual(category_outline('Category 49',reopened,custom),colors[49])

    def test_decoration_columns_global_sort_and_filter(self):
        entries=[('3001','Brick plain'),('3001pr0001','Brick Printed'),('3001pb01','Brick with Pattern'),('3001stk01','Brick with Sticker'),('sheet','Sticker Sheet with Pattern'),('odd','Special decorated brick')]
        for source in ('RB','BL'):
            for ref,name in entries:self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',(source,'part',ref,name,name))
        self.db.run('INSERT INTO relationships VALUES(?,?,?)',('P','odd','3001'))
        for source in ('RB','BL'):
            all_rows=self.db.query(source,'part',size=100)[0];by_ref={r['ref']:r for r in all_rows}
            self.assertEqual(by_ref['3001']['has_print'],0)
            self.assertEqual(by_ref['3001pr0001']['has_print'],1)
            self.assertEqual(by_ref['3001pb01']['has_print'],1)
            self.assertEqual(by_ref['3001stk01']['has_sticker'],1)
            self.assertEqual(by_ref['sheet']['has_sticker'],1);self.assertEqual(by_ref['sheet']['has_print'],0)
            filtered,total,pages,_=self.db.query(source,'part',size=1,hide_decorated=True)
            self.assertEqual(total,1 if source=='RB' else 2)
            self.assertTrue(all(not r['has_print'] and not r['has_sticker'] for r in filtered))
            self.assertEqual(self.db.query(source,'part',size=1,sort='has_print',descending=True)[0][0]['has_print'],1)
        self.assertEqual(self.db.query('RB','part',size=100)[1],6)

    def test_stock_set_adds_components_quantities_and_colors_atomically(self):
        self.parts();self.archive('sets',['set_num','name','theme_id'],[['42-1','A set',1]])
        self.archive('inventories',['id','version','set_num'],[[7,1,'42-1']])
        self.archive('inventory_parts',['inventory_id','part_num','color_id','quantity','is_spare','img_url'],[[7,'0',4,3,'False',''],[7,'0',14,2,'False',''],[7,'1',4,1,'True','']])
        item=self.db.rows("SELECT * FROM items WHERE kind='set'")[0]
        self.db.add('stock',item['id'],quantity=2)
        rows=self.db.query(scope='stock',size=100)[0];quantities={(r['ref'],r['chosen_color']):r['chosen_quantity'] for r in rows}
        self.assertEqual(quantities[('42-1','')],2);self.assertEqual(quantities[('0','4')],6);self.assertEqual(quantities[('0','14')],4);self.assertEqual(quantities[('1','4')],2)
        self.db.add('stock',item['id']);rows=self.db.query(scope='stock',size=100)[0]
        quantities={(r['ref'],r['chosen_color']):r['chosen_quantity'] for r in rows}
        self.assertEqual(quantities[('42-1','')],3);self.assertEqual(quantities[('0','4')],9)
        # A missing inventory must not leave a set without its required component stock.
        self.archive('sets',['set_num','name','theme_id'],[['99-1','Unknown composition',1]])
        missing=self.db.rows("SELECT * FROM items WHERE ref='99-1'")[0]
        with self.assertRaises(ValueError):self.db.add('stock',missing['id'])
        self.assertFalse(self.db.rows('SELECT * FROM stock WHERE item_id=?',(missing['id'],)))
        # Force a mid-transaction error and check rollback of both the set and parts.
        before=self.db.rows('SELECT * FROM stock ORDER BY id')
        self.db.run("CREATE TRIGGER fail_stock BEFORE UPDATE ON stock WHEN NEW.color='14' BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(Exception):self.db.add('stock',item['id'])
        self.assertEqual(before,self.db.rows('SELECT * FROM stock ORDER BY id'))

    def test_search_dimensions_and_global_pagination(self):
        self.parts()
        a=self.db.query('RB','part','1x1',size=5,sort='name')
        b=self.db.query('RB','part','1 x 1',size=5,sort='name')
        self.assertEqual([x['id'] for x in a[0]],[x['id'] for x in b[0]])
        self.assertEqual(a[1],30);self.assertEqual(a[2],6)
        second=self.db.query('RB','part','1×1',page=2,size=5,sort='name')
        allrows=self.db.query('RB','part','1x1',size=100,sort='name')[0]
        self.assertEqual([x['id'] for x in second[0]],[x['id'] for x in allrows[5:10]])
    def test_sources_and_stock_survive_reimport(self):
        self.parts();item=self.db.query('RB','part')[0][0]
        self.db.add('stock',item['id'],'14',3);self.parts()
        stock=self.db.query(scope='stock')[0]
        self.assertEqual(stock[0]['chosen_quantity'],3)
        txt=self.folder/'Parts.txt';txt.write_text('Category ID\tCategory Name\tNumber\tName\n1\tBricks\t'+item['ref']+'\t'+item['name']+'\n')
        self.db.import_file(txt)
        self.assertEqual(self.db.rows('SELECT COUNT(*) AS n FROM items WHERE ref=?',(item['ref'],))[0]['n'],2)
    def test_latest_inventory_controls_both_directions(self):
        self.parts();self.archive('sets',['set_num','name','theme_id'],[['42-1','A set',1]])
        self.archive('inventories',['id','version','set_num'],[[1,1,'42-1'],[2,2,'42-1']])
        self.archive('inventory_parts',['inventory_id','part_num','color_id','quantity','is_spare','img_url'],[[1,'0',14,5,'False',''],[2,'1',4,2,'False','']])
        item=self.db.rows("SELECT * FROM items WHERE ref='42-1'")[0]
        self.assertEqual(self.db.components(item)[0]['ref'],'1')
        self.assertEqual(self.db.components(item)[0]['chosen_quantity'],2)
        old=self.db.rows("SELECT * FROM items WHERE ref='0'")[0];new=self.db.rows("SELECT * FROM items WHERE ref='1'")[0]
        self.assertEqual(self.db.containing_sets(old),[]);self.assertEqual(len(self.db.containing_sets(new)),1)
    def test_bad_import_rolls_back(self):
        self.archive('colors',['id','name','rgb','is_trans'],[[1,'Red','FF0000','False']])
        with self.assertRaises(Exception):self.archive('colors',['id','name','rgb','is_trans'],[[2,'Blue','0000FF','False'],[2,'Duplicate','0000FF','False']])
        self.assertEqual(self.db.rows('SELECT id FROM colors'),[{'id':1}])
    def test_export_dimensions_and_layers(self):
        self.parts();item=self.db.query('RB','part')[0][0];t=default_template();t['layers'].insert(0,{'type':'free','text':'Tiroir 12','x':2,'y':6,'w':20,'h':3,'font':2,'visible':True})
        im=render_label(item,self.db,{'main':Image.new('RGBA',(100,60),'red')},t)
        self.assertEqual(im.size,(768,272));self.assertEqual(len(page_layout(65,23)),22)
        p=self.folder/'labels.pdf';export_pdf([im]*34,p,65,23)
        self.assertTrue(p.read_bytes().startswith(b'%PDF'))
        with self.assertRaises(ValueError):page_layout(300,400)


if __name__=='__main__':unittest.main()
