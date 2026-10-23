"""Whole-catalogue queues exceed 10,000 sets; UI pages never truncate jobs."""
from atelier import inventory_batches as batches
from atelier.inventory_batch_dialog import InventoryBatchDialog
from atelier.data import Database,normalize
from atelier.result_tables import row_index
from test_storage_and_inventory_batches import Fixture


class CatalogueQueueTests(Fixture):
    def seed(self,count,source='RB'):
        with self.db.connect() as c:
            c.executemany('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',
                ((source,'set',f'{n:05}-1','City '+str(n),normalize('City '+str(n))) for n in range(count)))

    def test_whole_catalogues_are_not_capped_and_leave_ownership_unchanged(self):
        self.seed(10017);self.seed(10019,'BL');self.item('set','extra',source='ALT')
        hidden=self.item('set','hidden');self.db.run('UPDATE items SET catalogue_hidden=1 WHERE id=?',(hidden,))
        stock=self.db.rows('SELECT * FROM stock')
        for source,total in [('RB',10017),('BL',10019)]:
            job=batches.create_catalogue_job(self.db,source,batch_size=1000,force=True)
            self.assertEqual(batches.summary(self.db,job),dict(total=total,pending=total,loaded=0,skipped=0,errors=0))
            edges=self.db.rows('SELECT MIN(ordinal) AS first,MAX(ordinal) AS last,COUNT(DISTINCT ref) AS n FROM inventory_job_items WHERE job_id=?',(job,))[0]
            self.assertEqual(edges,dict(first=0,last=total-1,n=total))
            self.assertEqual({r['source'] for r in self.db.rows('SELECT DISTINCT source FROM inventory_job_items WHERE job_id=?',(job,))},{source})
            self.assertEqual(self.db.rows('SELECT batch_size,force FROM inventory_jobs WHERE id=?',(job,))[0],dict(batch_size=1000,force=1))
        self.assertEqual(self.db.rows('SELECT * FROM stock'),stock);self.assertEqual(self.db.rows('SELECT * FROM stock_sets'),[])

    def test_browser_and_queue_share_source_text_theme_and_hidden_filters(self):
        self.seed(37);self.seed(13,'BL')
        self.db.run("INSERT INTO themes VALUES(42,'Space',NULL)")
        themed=self.item('set','space-1');self.db.run('UPDATE items SET category_id=? WHERE id=?',('42',themed))
        self.item('set','modulex-1','City Modulex')
        hidden=self.item('set','hidden-1','City');self.db.run('UPDATE items SET catalogue_hidden=1 WHERE id=?',(hidden,))
        for source,query,total in [('RB','city -modulex',37),('BL','city',13),('RB','Space',1)]:
            rows,count=batches.catalogue_page(self.db,source,query,0,10);self.assertEqual(count,total)
            job=batches.create_catalogue_job(self.db,source,query)
            queued=self.db.rows('SELECT ref FROM inventory_job_items WHERE job_id=? ORDER BY ordinal',(job,))
            self.assertEqual(len(queued),total);self.assertEqual([r['ref'] for r in rows],[r['ref'] for r in queued[:10]])

    def test_dialog_prepares_all_pages_and_displays_queue_tail_after_10000(self):
        self.seed(10005);dialog=self.keep(InventoryBatchDialog(self.db));dialog.limit.setValue(500);dialog.list_sets()
        self.assertEqual(dialog.table.rowCount(),500);self.assertIn('10005',dialog.page_label.text())
        dialog.next.click();self.assertEqual(dialog.rows[0]['ref'],'00500-1')
        dialog.create_all.click();self.assertEqual(batches.summary(self.db,dialog.job)['total'],10005)
        dialog.change_log_page(20);self.assertEqual(dialog.log.rowCount(),5)
        refs={dialog.log.item(row,1).text() for row in range(5)}
        self.assertEqual(refs,{f'{n:05}-1' for n in range(10000,10005)})
        self.assertFalse(dialog.log_next.isEnabled());self.assertTrue(dialog.log_previous.isEnabled())
        self.assertIn('10005',dialog.log_page_label.text())
        dialog.log_previous.click();self.assertEqual(dialog.log.rowCount(),500)

    def test_whole_catalogue_button_needs_no_prior_listing_and_honours_current_filter(self):
        self.seed(35);self.seed(17,'BL');dialog=self.keep(InventoryBatchDialog(self.db))
        dialog.source.setCurrentIndex(dialog.source.findData('BL'));dialog.filter.setText('City -13');dialog.create_all.click()
        expected=self.db.rows("SELECT COUNT(*) AS n FROM items WHERE source='BL' AND kind='set' AND name NOT LIKE '%13%'")[0]['n']
        self.assertEqual(batches.summary(self.db,dialog.job)['total'],expected)
        self.assertEqual(dialog.table.rowCount(),0)

    def test_single_selection_after_sort_and_page_change_queues_only_that_set(self):
        self.seed(31);dialog=self.keep(InventoryBatchDialog(self.db));dialog.limit.setValue(10);dialog.list_sets();dialog.next.click()
        dialog.table.sortItems(1);dialog.table.selectRow(3);ref=dialog.rows[row_index(dialog.table,3)]['ref'];dialog.create.click()
        self.assertEqual(self.db.rows('SELECT source,ref FROM inventory_job_items WHERE job_id=?',(dialog.job,)),[dict(source='RB',ref=ref)])

    def test_both_sources_resume_and_load_the_tail_of_a_large_saved_queue(self):
        class API:
            def __init__(self,db):pass
            def rb(self,path):
                return {'results':[{'part':{'part_num':'3005','name':'Brick'},'color':{'id':4},'quantity':2}], 'next':None}
            def bl(self,path):
                return [{'entries':[{'item':{'type':'PART','no':'3005','name':'Brick'},'color_id':5,'quantity':2}]}]
        before=self.db.rows('SELECT * FROM stock')
        for source in ('RB','BL'):
            self.seed(10005,source);job=batches.create_catalogue_job(self.db,source,force=True)
            self.db.run("UPDATE inventory_job_items SET status='skipped' WHERE job_id=? AND ordinal<10000",(job,))
            reopened=Database(self.db.path)
            try:result=batches.run_batch(reopened,job,api_factory=API)
            finally:reopened.close()
            self.assertEqual((result['total'],result['skipped'],result['loaded'],result['pending']),(10005,10000,5,0))
            self.assertEqual(len(self.db.rows('SELECT ref FROM catalogue_inventory WHERE source=?',(source,))),5)
        self.assertEqual(self.db.rows('SELECT * FROM stock'),before)

    def test_invalid_or_empty_catalogue_never_leaves_a_partial_queue(self):
        self.seed(1)
        for args in [('ALT','',10),('RB','absent',10),('RB','',True),('RB','',9),('RB','',1001)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):batches.create_catalogue_job(self.db,*args)
        self.assertEqual(batches.jobs(self.db),[]);self.assertEqual(self.db.rows('SELECT * FROM inventory_job_items'),[])
