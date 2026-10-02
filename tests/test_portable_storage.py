import json,os,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from atelier.data import Database
from atelier.storage import application_directory,prepare_portable_storage,migrate_legacy,configure_portable_database
from atelier.viewpoint import DEFAULT_CAMERA,camera_for_item,save_camera

class PortableStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.app=self.folder/'BrickLabo';self.app.mkdir();self.target=self.app/'Donnees';self.profile=self.folder/'Profile';self.source=self.profile/'LEGOAtelier'
    def tearDown(self):self.temp.cleanup()
    def legacy(self):
        db=Database(self.source/'atelier.sqlite');db.set_setting('api_rb','test-key');db.set_setting('camera_presets',{'Avant':{'yaw':180,'pitch':-23,'roll':-3}})
        image=self.source/'images'/'import.png';image.parent.mkdir();image.write_bytes(b'image')
        db.set_setting('ldraw',str(self.source/'ldraw.zip'));(self.source/'ldraw.zip').write_bytes(b'models')
        db.set_setting('output',str(self.source/'Exports'));db.set_setting('notice_links_2160-1',[{'url':str(self.source/'Notices'/'book.pdf')}])
        db.run('INSERT INTO visual(item_id,image) VALUES(?,?)',(42,str(image)))
        db.run('INSERT INTO stock(item_id,color,quantity) VALUES(?,?,?)',(42,'4',7))
        return db
    def test_executable_directory_independent_of_working_directory(self):
        with patch.object(sys,'executable',str(self.app/'BrickLabo.exe')):self.assertEqual(application_directory(),self.app)
    def test_migration_preserves_stock_keys_and_images_and_removes_old_folder(self):
        self.legacy();self.assertTrue(migrate_legacy(self.source,self.target));self.assertFalse(self.source.exists())
        db=Database(self.target/'atelier.sqlite');self.assertEqual(db.setting('api_rb'),'test-key');self.assertEqual(db.rows('SELECT quantity FROM stock')[0]['quantity'],7)
        self.assertEqual(db.rows('SELECT image FROM visual')[0]['image'],str(self.target/'images'/'import.png'));self.assertEqual((self.target/'images'/'import.png').read_bytes(),b'image')
        self.assertEqual(db.setting('ldraw'),str(self.target/'ldraw.zip'));self.assertEqual(db.setting('notice_links_2160-1')[0]['url'],str(self.target/'Notices'/'book.pdf'))
    def test_existing_portable_data_is_never_overwritten(self):
        self.legacy();db=Database(self.target/'atelier.sqlite');db.set_setting('api_rb','portable-key');self.assertFalse(migrate_legacy(self.source,self.target));self.assertEqual(db.setting('api_rb'),'portable-key');self.assertFalse(self.source.exists())
        archives=list(self.target.glob('Ancien_profil_*'));self.assertEqual(len(archives),1);self.assertEqual(Database(archives[0]/'atelier.sqlite').setting('api_rb'),'test-key')
    def test_copy_failure_preserves_original_and_removes_staging(self):
        self.legacy()
        with patch('atelier.storage.relocate_database',side_effect=ValueError('incomplete')):
            with self.assertRaises(ValueError):migrate_legacy(self.source,self.target)
        self.assertTrue((self.source/'atelier.sqlite').exists());self.assertFalse(self.target.exists());self.assertEqual(list(self.app.glob('.migration-*')),[])
    def test_nested_destination_cannot_delete_or_recursively_copy_the_application(self):
        self.legacy()
        with self.assertRaises(ValueError):migrate_legacy(self.source,self.source/'Donnees')
        self.assertTrue((self.source/'atelier.sqlite').exists());self.assertFalse((self.source/'Donnees').exists())
    def test_first_launch_paths_temp_and_relocation_after_moving_folder(self):
        self.legacy()
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.profile)}),patch('atelier.storage.application_directory',return_value=self.app),patch.object(tempfile,'tempdir',tempfile.tempdir):
            root=prepare_portable_storage();self.assertEqual(root,self.target);self.assertEqual(os.environ['TEMP'],str(root/'temp'));self.assertEqual(tempfile.gettempdir(),str(root/'temp'))
            db=Database(root/'atelier.sqlite');configure_portable_database(db)
        moved=self.folder/'Moved';shutil.move(self.app,moved)
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.profile)}),patch('atelier.storage.application_directory',return_value=moved),patch.object(tempfile,'tempdir',tempfile.tempdir):
            root=prepare_portable_storage();db=Database(root/'atelier.sqlite');configure_portable_database(db)
            self.assertEqual(db.setting('ldraw'),str(root/'ldraw.zip'));self.assertEqual(db.setting('output'),str(root/'Exports'));self.assertEqual(db.rows('SELECT image FROM visual')[0]['image'],str(root/'images'/'import.png'))
            self.assertFalse(self.source.exists())
    def test_external_output_is_reset_to_portable_exports(self):
        db=Database(self.target/'atelier.sqlite');db.set_setting('output',str(self.profile/'Exports'))
        with patch('atelier.storage.application_directory',return_value=self.app):configure_portable_database(db)
        self.assertEqual(db.setting('output'),str(self.target/'Exports'));self.assertFalse((self.profile/'Exports').exists())
    def test_new_default_and_individual_views(self):
        db=Database(self.target/'atelier.sqlite');item={'id':1}
        self.assertEqual(DEFAULT_CAMERA,{'yaw':180,'pitch':-23,'roll':-3});self.assertEqual(camera_for_item(db,item),DEFAULT_CAMERA)
        save_camera(db,item,{'yaw':70,'pitch':5,'roll':0});self.assertEqual(camera_for_item(db,item)['yaw'],70)
