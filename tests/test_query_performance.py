"""Correctness and bounded query counts for the accelerated read paths."""
from pathlib import Path
import sqlite3,tempfile
from unittest.mock import patch
from test_storage_and_inventory_batches import Fixture,app
from atelier.data import Database
from atelier import projects,set_allocations,inventory_batches
from atelier.query_cache import ReadCache


class QueryCacheTests(Fixture):
    def test_hidden_catalogue_defers_work_and_shows_fresh_stock_when_opened(self):
        from atelier.catalogue import Catalogue
        widget=self.keep(Catalogue(self.db,scope='stock'));before=next(r for r in widget.rows if r['id']==self.part)['chosen_quantity']
        self.db.add('stock',self.part,'4',7);widget.invalidate()
        self.assertEqual(next(r for r in widget.rows if r['id']==self.part)['chosen_quantity'],before)
        widget.show();app.processEvents()
        self.assertEqual(next(r for r in widget.rows if r['id']==self.part)['chosen_quantity'],47)
    def test_stock_cache_sees_other_database_connections_and_undo(self):
        self.assertEqual(self.db.query(scope='stock')[1],2)
        other=Database(self.db.path)
        try:other.run('UPDATE stock SET quantity=17 WHERE item_id=?',(self.part,))
        finally:other.close()
        row=next(r for r in self.db.query(scope='stock')[0] if r['id']==self.part)
        self.assertEqual(row['chosen_quantity'],17)
        self.db.add('stock',self.part,'4',3);self.assertEqual(next(r for r in self.db.query(scope='stock')[0] if r['id']==self.part)['chosen_quantity'],20)
        self.db.undo_last_action();self.assertEqual(next(r for r in self.db.query(scope='stock')[0] if r['id']==self.part)['chosen_quantity'],17)
    def test_cached_rows_are_private_and_failed_transactions_do_not_leak(self):
        rows,*_=self.db.query('RB','part');rows[0]['name']='changed only by caller';rows.clear()
        self.assertEqual(self.db.query('RB','part')[1],2)
        self.assertNotIn('changed only by caller',[r['name'] for r in self.db.query('RB','part')[0]])
        with self.assertRaises(ValueError):
            with self.db.connect() as c:c.execute("UPDATE items SET name='Rolled back' WHERE id=?",(self.part,));raise ValueError('rollback')
        self.assertNotIn('Rolled back',[r['name'] for r in self.db.query('RB','part')[0]])
    def test_nested_reads_keep_the_explicit_snapshot(self):
        self.db.query(scope='stock');other=Database(self.db.path)
        try:
            with self.db.read() as c:
                c.execute('BEGIN');self.assertEqual(c.execute('SELECT quantity FROM stock WHERE item_id=?',(self.part,)).fetchone()[0],40)
                other.run('UPDATE stock SET quantity=11 WHERE item_id=?',(self.part,))
                self.db.setting('some-key');self.assertTrue(c.in_transaction)
                row=next(r for r in self.db.query(scope='stock')[0] if r['id']==self.part)
                self.assertEqual(row['chosen_quantity'],40)
            self.assertEqual(next(r for r in self.db.query(scope='stock')[0] if r['id']==self.part)['chosen_quantity'],11)
        finally:other.close()
    def test_categories_and_years_follow_committed_catalogue_changes(self):
        self.db.categories('RB','part');self.db.years('RB','set')
        self.db.run("UPDATE items SET category='Nouvelles' WHERE id=?",(self.part,))
        self.assertIn('Nouvelles',self.db.categories('RB','part'))
        identity=self.item('set','0001-1');self.db.run("UPDATE items SET year='2026' WHERE id=?",(identity,))
        self.assertIn('2026',self.db.years('RB','set'))
    def test_repeated_pages_skip_the_expensive_sql_and_cache_stays_bounded(self):
        self.db.query('RB','part');seen=[]
        with self.db.read() as c:
            c.set_trace_callback(seen.append)
            try:self.db.query('RB','part')
            finally:c.set_trace_callback(None)
        self.assertFalse(any('FROM items i' in sql for sql in seen))
        cache=ReadCache(limit=4096,entries=3)
        for n in range(30):cache.put(n,[str(n)*30])
        self.assertLessEqual(cache.bytes,4096);self.assertLessEqual(len(cache.items),3)
        self.assertEqual(cache.get(29),(True,['29'*30]))
    def test_close_and_reopen_cannot_reuse_an_old_generation(self):
        self.db.query('RB','part');self.db.close()
        self.db.run("UPDATE items SET name='After reopening' WHERE id=?",(self.part,))
        self.assertIn('After reopening',[r['name'] for r in self.db.query('RB','part')[0]])


class SearchParityTests(Fixture):
    def test_index_matches_fallback_for_literals_short_words_and_negations(self):
        for n,name in enumerate(['Brick Modular Duplo','Modulex 1 x 2','Étage carré 2 × 2','50% special_foo','quotes "and" OR NOT','日本語の部品','Bri ric ick separated','3010-1 bar']):
            self.item('part','edge-'+str(n),name)
        for query in ['brick -duplo','-modulex','-duplo -brick','1','x','%','_','"and"','OR','日本語','bri','brick','3010-1','50%','special_foo','carré']:
            with self.subTest(query=query):
                self.db.search_index_available=True;a=self.db.query('RB','part',search=query,size=200)
                self.db.search_index_available=False;b=self.db.query('RB','part',search=query,size=200)
                self.assertEqual(a,b)
        self.db.search_index_available=True
    def test_names_categories_and_relationships_refresh_derived_flags(self):
        self.db.query('RB','part',hide_decorated=True)
        self.db.run("UPDATE items SET name='Brick with Sticker',category='Éléments' WHERE id=?",(self.part,))
        self.assertNotIn(self.part,[r['id'] for r in self.db.query('RB','part',hide_decorated=True)[0]])
        self.assertIn(self.part,[r['id'] for r in self.db.query('RB','part',search='elements')[0]])
        self.db.run("UPDATE items SET name='Brick plain' WHERE id=?",(self.part,))
        self.db.run("INSERT INTO relationships VALUES('P','3005','3001')")
        self.assertNotIn(self.part,[r['id'] for r in self.db.query('RB','part',hide_decorated=True)[0]])
        self.db.run('DELETE FROM relationships')
        self.assertIn(self.part,[r['id'] for r in self.db.query('RB','part',hide_decorated=True)[0]])
    def test_old_collections_rebuild_the_accelerators_without_losing_items(self):
        expected=self.db.query('RB','part',search='brique')
        with self.db.connect() as c:
            for name in ('insert','update','delete'):c.execute('DROP TRIGGER item_decorations_'+name)
            c.execute('DROP TABLE item_decorations')
        reopened=Database(self.db.path)
        try:self.assertEqual(reopened.query('RB','part',search='brique'),expected)
        finally:reopened.close()
    def test_drawer_search_keeps_its_field_and_wildcard_semantics(self):
        from atelier.storage_assignment import catalogue_rows,stock_rows
        self.db.run("UPDATE items SET alternate='OnlyInAlternate' WHERE id=?",(self.part,))
        self.assertEqual(catalogue_rows(self.db,'OnlyInAlternate'),[])
        self.assertEqual([r['id'] for r in catalogue_rows(self.db,'300_')],[self.other,self.part])
        self.assertEqual([r['id'] for r in stock_rows(self.db,'300_')],[self.other,self.part])
        self.assertEqual(catalogue_rows(self.db,'-modulex'),[])


class ProjectAndInventoryReadsTests(Fixture):
    def test_inventory_reader_is_released_without_waiting_for_cyclic_gc(self):
        import weakref
        from atelier.build_stock import InventoryReader
        with self.db.read() as c:
            reader=InventoryReader(c);reader.canonical('RB','3005','4');reader.children('RB','set','absent')
            self.assertEqual(InventoryReader(c).canonical('RB','3005','4'),reader.canonical('RB','3005','4'))
            self.assertEqual(InventoryReader(c).children('RB','set','absent'),((),False))
            reference=weakref.ref(reader);del reader
            self.assertIsNone(reference())
    def test_batch_summary_matches_details_across_colours_claims_and_reservations(self):
        self.db.add('stock',self.part,'0',9)
        pids=[]
        for ignore in (False,True):
            for include in (False,True):
                pids.append(projects.create(self.db,'Project',[dict(item_id=self.part,color='4',quantity=57),dict(item_id=self.part,color='0',quantity=20)],ignore_colors=ignore,include_set_stock=include))
        projects.reserve(self.db,pids[0],quantity=5)
        for summary in projects.list_projects(self.db):
            detail=projects.detail(self.db,summary['id'])
            self.assertEqual(summary['missing'],sum(p['missing'] for p in detail))
            self.assertEqual(summary['required'],sum(p['required'] for p in detail))
        projects.release(self.db,pids[0])
        for summary in projects.list_projects(self.db):self.assertEqual(summary['missing'],sum(p['missing'] for p in projects.detail(self.db,summary['id'])))
    def test_cached_inventory_resolves_colours_and_missing_references_atomically(self):
        values=[dict(source='RB',ref='3005',name='Brick',color=str(n),quantity=n+1) for n in range(150)]
        inventory_batches.store_inventory(self.db,'RB','test-1',values,values)
        seen=[]
        with self.db.read() as c:
            c.set_trace_callback(seen.append)
            try:rows=inventory_batches.cached_components(self.db,'RB','test-1')
            finally:c.set_trace_callback(None)
        self.assertEqual([(r['chosen_color'],r['chosen_quantity']) for r in rows],[(str(n),n+1) for n in range(150)])
        self.assertLess(len(seen),10)
        values.append(dict(source='RB',ref='absent',color='4',quantity=1));self.db.set_setting('irrelevant',True)
        self.db.run('UPDATE catalogue_inventory SET parts=? WHERE ref=?',(__import__('json').dumps(values),'test-1'))
        with self.assertRaises(ValueError):inventory_batches.cached_components(self.db,'RB','test-1')
    def test_prefetched_builds_keep_latest_versions_and_refresh_after_changes(self):
        from atelier.build_stock import find_builds
        for n in range(130):self.item('set','bench-'+str(n))
        with self.db.connect() as c:
            for n in range(130):
                ref='bench-'+str(n)
                iid=c.execute('INSERT INTO inventories(version,set_num) VALUES(1,?)',(ref,)).lastrowid
                c.execute("INSERT INTO inventory_parts VALUES(?,'3005',4,2,0,'')",(iid,))
        result=find_builds(self.db,ignore_colors=False,minimum=100,include_set_stock=False)[0]
        self.assertEqual(len(result),130);self.assertTrue(all(r['total']==2 for r in result))
        with self.db.connect() as c:
            iid=c.execute("INSERT INTO inventories(version,set_num) VALUES(2,'bench-0')").lastrowid
            c.execute("INSERT INTO inventory_parts VALUES(?,'3005',4,41,0,'')",(iid,))
        self.assertNotIn('bench-0',[r['ref'] for r in find_builds(self.db,minimum=100,include_set_stock=False)[0]])
