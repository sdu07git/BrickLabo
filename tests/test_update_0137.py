import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PIL import Image
from atelier.data import Database
from atelier.stock_import import read_list,import_rows
from atelier.preferences_backup import export_family,restore_families
from atelier.labels import default_template,render_label
from atelier.label_pieces import add_piece_layers,signature,enrich
from atelier.memory_cache import MemoryCache
from atelier.thumbnail_cache import ThumbnailCache
from atelier.temp_area import configure,close,purge,temporary_folder
from atelier.moc_search import parse_search,parse_bases,search_url,remember,local_rows

class Update37Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=Database(self.root/'Donnees'/'db.sqlite')
        self.part=self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','3001','Brick','Bricks','brick')")
        self.set=self.db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','set','100-1','Set','Sets','set')")
        self.db.run("INSERT INTO colors VALUES(4,'Red','FF0000',0)");self.db.run("INSERT INTO inventories VALUES(1,1,'100-1')");self.db.run("INSERT INTO inventory_parts VALUES(1,'3001',4,5,0,'')")
    def tearDown(self):close();self.tmp.cleanup()
    def totals(self):return [(r['ref'],r['chosen_color'],r['chosen_quantity']) for r in self.db.query(scope='stock_available',size=100)[0]]
    def piece(self,quantity=2):return {'source':'RB','kind':'part','ref':'3001','color':'4','quantity':quantity}
    def owned(self):return self.db.rows('SELECT id FROM stock_sets')[0]['id']
    def family(self,name):
        path=self.root/(name+'.json');export_family(self.db,name,path);return path

    def test_separation_undo_restart_and_set_quantity(self):
        self.db.add('stock',self.part,'4',3);self.db.add('stock',self.set,quantity=2)
        self.assertEqual(self.db.query(scope='stock')[0][0]['chosen_quantity'],3)
        self.assertEqual(self.db.owned_components(self.owned())[0]['chosen_quantity'],10)
        Database(self.db.path).undo_last_action();self.assertEqual(self.totals(),[('3001','4',3)])
        self.db.add('stock',self.set);self.db.change_entries('stock_sets',[self.owned()],'quantity',3)
        self.assertEqual(self.db.owned_components(self.owned())[0]['chosen_quantity'],15);self.db.undo_last_action();self.assertEqual(self.db.owned_components(self.owned())[0]['chosen_quantity'],5)

    def test_set_removal_moves_only_owned_parts_to_loose_and_is_undoable(self):
        self.db.add('stock',self.part,'4',3);self.db.add('stock',self.set,quantity=2);eid=self.owned()
        self.db.remove('stock_sets',[eid],False);self.assertEqual(self.totals(),[('3001','4',13)])
        self.db.undo_last_action();self.assertEqual(self.db.query(scope='stock')[0][0]['chosen_quantity'],3);self.assertEqual(self.db.owned_components(eid)[0]['chosen_quantity'],10)

    def test_loose_colour_change_does_not_move_owned_components(self):
        self.db.add('stock',self.set);self.db.add('stock',self.part,'4',3);eid=self.db.query(scope='stock')[0][0]['entry_id']
        self.db.change_entries('stock',[eid],'color','1')
        self.assertEqual(self.db.owned_components(self.owned())[0]['chosen_color'],'4')
        self.assertIn(('3001','4',5),self.totals());self.assertIn(('3001','1',3),self.totals());self.db.undo_last_action();self.assertIn(('3001','4',8),self.totals())

    def test_batch_validation_and_undo_preserve_previous_success(self):
        self.db.add('stock',self.part,'4',3)
        with self.assertRaises(ValueError):self.db.add_many([('stock',self.part,'4',9),('stock',99999,'',1)])
        self.assertEqual(self.totals(),[('3001','4',3)]);self.assertTrue(self.db.undo_last_action());self.assertEqual(self.totals(),[])

    def test_legacy_migration_preserves_totals_labels_filters_and_snapshot(self):
        self.db.run("DELETE FROM settings WHERE key='stock_layout_v37'");self.db.run("INSERT INTO stock(id,item_id,color,quantity) VALUES(10,?,'',2)",(self.set,));self.db.run("INSERT INTO stock(id,item_id,color,quantity) VALUES(11,?,'4',13)",(self.part,));self.db.run("INSERT INTO stock_set_components VALUES(10,?,'4',10)",(self.part,));self.db.set_setting('label_layout_stock_10',default_template());self.db.set_setting('build_excluded_entries',[10])
        self.db=Database(self.db.path);self.assertEqual(self.db.query(scope='stock')[0][0]['chosen_quantity'],3);self.assertIn(('3001','4',13),self.totals());self.assertEqual(self.db.setting('build_excluded_entries'),[-10]);self.assertTrue(self.db.setting('label_layout_stock_sets_10'));self.assertTrue((self.db.path.parent/'sauvegardes'/'avant_v37.sqlite').is_file())
        self.db=Database(self.db.path);self.assertEqual(self.db.query(scope='stock')[0][0]['chosen_quantity'],3)

    def test_legacy_migration_never_invents_missing_parts(self):
        self.db.run("DELETE FROM settings WHERE key='stock_layout_v37'");self.db.run("INSERT INTO stock(id,item_id,color,quantity) VALUES(10,?,'',2)",(self.set,));self.db.run("INSERT INTO stock(id,item_id,color,quantity) VALUES(11,?,'4',4)",(self.part,));self.db.run("INSERT INTO stock_set_components VALUES(10,?,'4',10)",(self.part,));self.db=Database(self.db.path)
        self.assertIn(('3001','4',4),self.totals());self.assertEqual(self.db.query(scope='stock')[1],0);self.assertTrue(self.db.setting('stock_migration_report'))

    def test_rebrickable_parts_and_sets_csv_destinations(self):
        parts=self.root/'parts.csv';parts.write_text('Part,Color,Quantity\n3001,4,2\n',encoding='utf-8');rows=read_list(parts);import_rows(self.db,rows,'stock')
        sets=self.root/'sets.csv';sets.write_text('Set,Quantity\n100-1,2\n',encoding='utf-8');import_rows(self.db,read_list(sets),'stock')
        self.assertEqual(self.totals(),[('3001','4',12)]);self.assertEqual(self.db.query(scope='stock_sets')[1],0);self.db.undo_last_action();self.assertEqual(self.totals(),[('3001','4',2)])
        import_rows(self.db,read_list(sets),'stock_sets');self.assertEqual(self.db.query(scope='stock')[0][0]['chosen_quantity'],2)

    def test_bricklink_xml_and_txt_flags_and_minifig(self):
        xml=self.root/'list.xml';xml.write_text('<INVENTORY><ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>3001</ITEMID><COLOR>5</COLOR><MINQTY>3</MINQTY></ITEM></INVENTORY>');self.assertEqual(read_list(xml)[0],{'source':'BL','kind':'part','ref':'3001','color':'5','quantity':3})
        txt=self.root/'list.txt';txt.write_text('Type\tItem No\tQty\tColor ID\tAlternate?\tCounterpart?\nP\t3001\t3\t5\tN\tN\nP\t3002\t3\t5\tY\tN\nP\t3003\t3\t5\tN\tY\nM\tsw01\t2\t0\tN\tN\n');rows=read_list(txt);self.assertEqual([r['ref'] for r in rows],['3001','sw01']);self.assertEqual(rows[1]['kind'],'minifig')

    def test_import_unknown_and_incomplete_inventory_are_atomic(self):
        before=self.totals()
        with self.assertRaises(ValueError):import_rows(self.db,[self.piece(),dict(self.piece(),ref='unknown')])
        self.assertEqual(self.totals(),before);self.db.run("INSERT INTO inventory_parts VALUES(1,'missing',4,3,0,'')")
        with self.assertRaises(ValueError):import_rows(self.db,[self.piece(),{'source':'RB','kind':'set','ref':'100-1','color':'','quantity':1}])
        self.assertEqual(self.totals(),before)

    def test_parts_import_named_inventory_then_attach_and_undo(self):
        import_rows(self.db,[self.piece(3)],'stock_sets',name='Casques');self.assertEqual(self.db.query(scope='stock')[1],0);eid=self.owned();self.assertEqual(self.db.owned_components(eid)[0]['chosen_quantity'],3)
        import_rows(self.db,[self.piece(2)],'stock_sets',target_entry=eid);self.assertEqual(self.db.owned_components(eid)[0]['chosen_quantity'],5);self.db.undo_last_action();self.assertEqual(self.db.owned_components(eid)[0]['chosen_quantity'],3)

    def test_invalid_import_rows_are_rejected(self):
        for line in ('3001,4,-1','3001,red,3','../evil,4,1'):
            file=self.root/'invalid.csv';file.write_text('Part,Color,Quantity\n'+line+'\n')
            with self.assertRaises(ValueError):read_list(file)

    def test_backup_family_restore_uses_references_not_ids(self):
        self.db.add('stock',self.part,'4',3);self.db.add('stock',self.set,quantity=2);self.db.set_setting('camera_item_'+str(self.part),{'yaw':70});self.db.set_setting('edge_presets',{'Strong':{'black':95,'width':4}})
        self.db.set_setting('api_rb','private');files=[self.family(f) for f in ('loose','sets','views')];other=Database(self.root/'other.sqlite');other.alternative('part','unrelated','Other','Other');restore_families(other,files)
        part=other.rows("SELECT id FROM items WHERE source='RB' AND ref='3001'")[0]['id'];self.assertNotEqual(part,self.part);self.assertEqual(other.setting('camera_item_'+str(part)),{'yaw':70});self.assertEqual(other.setting('edge_presets')['Strong']['width'],4);self.assertEqual(other.setting('api_rb',''),'');self.assertEqual(other.query(scope='stock')[0][0]['chosen_quantity'],3);self.assertEqual(other.owned_components(other.rows('SELECT id FROM stock_sets')[0]['id'])[0]['chosen_quantity'],10)

    def test_selective_restore_rolls_back_all_families_on_invalid_quantity(self):
        self.db.add('stock',self.part,'4',3);self.db.add('stock',self.set);loose=self.family('loose');sets=self.family('sets');payload=json.loads(sets.read_text());payload['data']['entries'][0]['quantity']=-1;sets.write_text(json.dumps(payload));self.db.change_entries('stock',[self.db.query(scope='stock')[0][0]['entry_id']],'quantity',7);before=self.totals()
        with self.assertRaises(ValueError):restore_families(self.db,[loose,sets])
        self.assertEqual(self.totals(),before)

    def test_labels_restore_preserves_category_colours(self):
        template=default_template();template['category_colors']={'Bricks':'#112233'};self.db.set_setting('template',template);labels=self.family('labels');template['category_colors']['Bricks']='#abcdef';self.db.set_setting('template',template);restore_families(self.db,[labels]);self.assertEqual(self.db.setting('template')['category_colors']['Bricks'],'#abcdef')

    def test_individual_label_restore_preserves_existing_colours(self):
        template=default_template();template['category_colors']={'Bricks':'#112233'};key='label_layout_item_'+str(self.part);self.db.set_setting(key,template);path=self.family('labels');template['category_colors']['Bricks']='#abcdef';self.db.set_setting(key,template);restore_families(self.db,[path]);self.assertEqual(self.db.setting(key)['category_colors']['Bricks'],'#abcdef')

    def test_stock_backup_does_not_duplicate_label_templates(self):
        self.db.add('stock',self.part,'4',2);eid=self.db.query(scope='stock')[0][0]['entry_id'];self.db.set_setting('label_layout_stock_'+str(eid),default_template());payload=json.loads(self.family('loose').read_text());self.assertNotIn('layers',json.dumps(payload))

    def test_named_template_colours_are_in_their_own_family(self):
        template=default_template();template['category_colors']={'Bricks':'#112233'};self.db.set_setting('templates',{'Casques':template});labels=self.family('labels');colors=self.family('colors')
        self.assertNotIn('#112233',labels.read_text());self.assertNotIn('layers',colors.read_text())
        template['category_colors']['Bricks']='#abcdef';self.db.set_setting('templates',{'Casques':template});restore_families(self.db,[labels]);self.assertEqual(self.db.setting('templates')['Casques']['category_colors']['Bricks'],'#abcdef')
        other=Database(self.root/'other.sqlite');restore_families(other,[colors]);self.assertEqual(other.setting('templates')['Casques']['category_colors']['Bricks'],'#112233');self.assertTrue(other.setting('templates')['Casques']['layers'])

    def test_owned_set_restore_rebinds_existing_layout(self):
        self.db.add('stock',self.set);path=self.family('sets');eid=self.owned();template=default_template();template['layers'][0]['x']=7;self.db.set_setting('label_layout_stock_sets_'+str(eid),template);restore_families(self.db,[path]);self.assertEqual(self.db.setting('label_layout_stock_sets_'+str(self.owned()))['layers'][0]['x'],7)

    def test_restoring_stock_retains_current_matching_label(self):
        self.db.add('stock',self.part,'4',2);path=self.family('loose');eid=self.db.query(scope='stock')[0][0]['entry_id'];template=default_template();template['layers'][0]['x']=7;self.db.set_setting('label_layout_stock_'+str(eid),template);restore_families(self.db,[path]);self.assertEqual(self.db.setting('label_layout_stock_'+str(eid))['layers'][0]['x'],7)

    def test_undo_does_not_leave_an_orphaned_new_label(self):
        self.db.add('stock',self.part,'4',2);eid=self.db.query(scope='stock')[0][0]['entry_id'];self.db.set_setting('label_layout_stock_'+str(eid),default_template())
        with self.assertRaises(ValueError):self.db.undo_last_action()
        self.assertEqual(self.totals(),[('3001','4',2)])

    def test_nested_alternative_sets_expand_and_cycles_are_atomic(self):
        self.db.alternative('set','CUSTOM','Nested','Personal');sid=self.db.rows("SELECT id FROM items WHERE ref='CUSTOM'")[0]['id'];self.db.set_setting('alt_components_'+str(sid),[{'item_id':self.set,'color':'','quantity':2}]);self.db.add('stock',sid);self.assertIn(('3001','4',10),self.totals())
        self.db.set_setting('alt_components_'+str(sid),[{'item_id':sid,'color':'','quantity':1}]);before=self.totals()
        with self.assertRaises(ValueError):self.db.add('stock',sid)
        self.assertEqual(self.totals(),before)

    def test_bad_cached_inventory_is_rejected_before_stock_changes(self):
        sid=self.db.run("INSERT INTO items(source,kind,ref,name,search) VALUES('BL','set','75192-1','Falcon','falcon')");self.db.set_setting('bl_components_75192-1',[dict(self.db.get_item(self.part),id=999999,chosen_color='4',chosen_quantity=5)])
        with self.assertRaises(ValueError):self.db.add('stock',sid)
        self.assertEqual(self.totals(),[])

    def test_colours_only_restore_creates_complete_default_template(self):
        template=default_template();template['category_colors']={'Bricks':'#112233'};self.db.set_setting('template',template);path=self.family('colors');other=Database(self.root/'other.sqlite');restore_families(other,[path]);self.assertTrue(other.setting('template')['layers']);self.assertEqual(other.setting('template')['category_colors']['Bricks'],'#112233')

    def test_other_preferences_never_back_up_keys_paths_or_moc_cache(self):
        for key in ('api_rb','ldraw','output','moc_search_records','stock_mocs_100-1'):self.db.set_setting(key,'private-or-cache')
        self.db.set_setting('thumbnail_disk_mb',0);payload=json.loads(self.family('preferences').read_text());self.assertEqual([r['target']['key'] for r in payload['data']['settings']],['thumbnail_disk_mb'])

    def test_multiple_piece_layers_keep_independent_images_and_references(self):
        item=self.db.get_item(self.part);template=default_template();layers=add_piece_layers(template,item,'4','photo');self.assertEqual(len(layers),2);self.assertEqual(layers[1]['piece']['ref'],'3001')
        layers[0].update(x=2,y=5,w=20,h=12);layers[1].update(x=2,y=18,w=20,h=2);key=signature(layers[0]['piece']);visual={'main':Image.new('RGBA',(50,40),'blue'),'pieces':{key:{'item':item,'visuals':{'main':Image.new('RGBA',(50,40),'red')}}}}
        image=render_label(item,self.db,visual,template);self.assertGreater(image.getpixel((80,110))[0],image.getpixel((80,110))[2]);path=self.family('labels');self.assertNotIn('item_id',path.read_text())

    def test_composition_resolves_current_identity_and_does_not_recurse(self):
        from types import SimpleNamespace
        template=default_template();add_piece_layers(template,self.db.get_item(self.part),'4','3d');calls=[]
        def visuals(item,*args,**kwargs):calls.append((item['id'],kwargs['_composition']));return {'main':Image.new('RGBA',(4,4),'red')},''
        result=enrich(SimpleNamespace(db=self.db,visuals=visuals),template,{})
        self.assertEqual(calls,[(self.part,False)]);self.assertEqual(len(result['pieces']),1)

    def test_render_memory_coalesces_concurrent_requests_and_is_bounded(self):
        cache=MemoryCache(30000);started=threading.Event();release=threading.Event();calls=[]
        def factory():calls.append(1);started.set();release.wait(2);return Image.new('RGBA',(50,50)),(1,2,3)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            one=pool.submit(cache.get_or_create,'same',factory);started.wait(1);two=pool.submit(cache.get_or_create,'same',factory);time.sleep(.02);release.set();self.assertIs(one.result(),two.result())
        self.assertEqual(len(calls),1)
        for i in range(5):cache.get_or_create(i,lambda:Image.new('RGBA',(50,50)))
        self.assertLessEqual(cache.bytes,cache.limit)

    def test_thumbnail_hits_do_not_rewrite_files_and_ram_only_mode(self):
        cache=ThumbnailCache(self.root/'cache');key=(1,'red');cache.get_or_create(key,lambda:Image.new('RGBA',(100,65),'red'));file=cache.path(key);stamp=file.stat().st_mtime_ns;cache.memory.clear();cache.memory_bytes=0
        with patch('atelier.thumbnail_cache.atomic_output',side_effect=AssertionError('Unexpected write')):self.assertIsNotNone(cache.get_or_create(key,lambda:None))
        self.assertEqual(file.stat().st_mtime_ns,stamp);cache.configure(32000,0);self.assertFalse(file.exists());cache.put((2,),Image.new('RGBA',(100,65)));self.assertEqual(list(cache.folder.iterdir()),[])

    def test_temp_sessions_protect_current_and_other_live_process(self):
        session=configure(self.db.path.parent);active=session/'render';active.write_text('active');old=self.db.path.parent/'temp'/'s1234567890';old.mkdir();(old/'abandoned').write_text('old')
        code="from atelier.temp_area import configure,close;import sys;print(configure(sys.argv[1]),flush=True);sys.stdin.readline();close()"
        child=subprocess.Popen([sys.executable,'-u','-c',code,str(self.db.path.parent)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            peer=Path(child.stdout.readline().strip());self.assertNotEqual(peer,session);self.assertTrue(peer.is_dir());purge(session.parent);self.assertTrue(peer.is_dir());self.assertTrue(active.exists());self.assertFalse(old.exists());self.assertEqual(Path(tempfile.gettempdir()),session)
        finally:
            child.communicate('\n',timeout=10)
        self.assertEqual(child.returncode,0);self.assertFalse(peer.exists());close();self.assertFalse(session.exists())

    def test_public_moc_parser_pagination_creator_and_origins(self):
        url=search_url('falcon');page='<div class="set-tn"><div class="js-sort-data" data-num_parts="370"></div><h5 class="js-set-name"><a href="/mocs/MOC-123/Designer/falcon/">Falcon</a></h5><a href="/users/Designer/mocs/">Designer</a><img data-src="https://cdn.rebrickable.com/photo.jpg"></div><a rel="next" href="?q=falcon&amp;page=2">Next</a>'
        rows,next_page=parse_search(page,url);self.assertEqual(rows[0]['num_parts'],370);self.assertEqual(rows[0]['designer_name'],'Designer');self.assertIn('page=2',next_page)
        bases=parse_bases('<p>Alternate Build of the following:</p><div class="row-condensed"><a href="/sets/75440-1/at-at/">Set</a></div>',rows[0]['moc_url']);self.assertEqual(bases,['75440-1']);self.assertIn('/users/Wurger%20Bricks/',search_url('falcon','Wurger Bricks'))
        with self.assertRaises(ValueError):parse_search(page.replace('?q=falcon&amp;page=2','https://evil.example/mocs/'),url)

    def test_local_moc_results_merge_origins_and_filter_words_creator(self):
        first={'set_num':'MOC-123','name':'Midi Falcon','designer_name':'Designer','bases':['100-1'],'bases_loaded':True};remember(self.db,[first]);remember(self.db,[dict(first,bases=['200-1'])]);self.assertEqual(local_rows(self.db,'falcon','design')[0]['bases'],['100-1','200-1']);self.assertEqual(local_rows(self.db,'falcon spaceship'),[])
