import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,time,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtCore import Qt,QThreadPool,QTimer,QPoint,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from atelier.data import Database
from atelier.render import LDraw
from atelier.preview import Preview,VisualEngine
from atelier.camera import CameraDialog
from atelier.viewpoint import camera_for_item,save_camera
from atelier.catalogue import Catalogue
from atelier.labels import render_label
app=QApplication.instance() or QApplication([])

def wait(fn):
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        app.processEvents()
        if fn():return
        time.sleep(.01)
    raise AssertionError('Camera render did not complete')

class CameraTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.db=Database(self.folder/'db.sqlite');self.db.set_setting('camera_default',{});self.windows=[]
        model=self.folder/'ldraw';(model/'parts').mkdir(parents=True)
        (model/'ldconfig.ldr').write_text('0 !COLOUR Blue CODE 1 VALUE #0000FF EDGE #333333\n0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n')
        data='0 Two differently coloured opposite faces\n4 1 -20 -20 5 20 -20 5 20 20 5 -20 20 5\n4 4 -20 -20 -5 20 -20 -5 20 20 -5 -20 20 -5\n'
        for ref in ('3005','3001'):(model/'parts'/(ref+'.dat')).write_text(data)
        self.db.set_setting('ldraw',str(model));self.engine=VisualEngine(self.db);self.parts=[]
        for ref in ('3005','3001'):
            iid=self.db.run('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?)',('RB','part',ref,'Brick '+ref,'Bricks',ref));self.parts.append(self.db.get_item(iid))
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
        for window in self.windows:window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents();self.temp.cleanup()
    def keep(self,window):self.windows.append(window);return window
    def ready(self,d):wait(lambda:not d.running and d.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
    def test_rotation_reverses_visible_face_and_keeps_orthographic_views(self):
        renderer=self.engine.renderer();front,bounds=renderer.render('3005',(180,150));zero,_=renderer.render('3005',(180,150),camera={})
        self.assertEqual(front.tobytes(),zero.tobytes())
        back,new_bounds=renderer.render('3005',(180,150),camera={'yaw':180});self.assertNotEqual(front.tobytes(),back.tobytes());self.assertEqual(list(bounds),list(new_bounds))
        self.assertGreater(front.getpixel((90,75))[2],front.getpixel((90,75))[0]);self.assertGreater(back.getpixel((90,75))[0],back.getpixel((90,75))[2])
        for view in ('top','side'):
            one,_=renderer.render('3005',(180,150),view=view);two,_=renderer.render('3005',(180,150),view=view,camera={'yaw':180,'pitch':30})
            self.assertEqual(one.tobytes(),two.tobytes())
    def test_individual_global_and_persistent_named_views(self):
        a,b=self.parts;save_camera(self.db,a,{'yaw':180});self.assertEqual(camera_for_item(self.db,a)['yaw'],180);self.assertEqual(camera_for_item(self.db,b)['yaw'],0)
        save_camera(self.db,b,{'yaw':-90});save_camera(self.db,a,{'yaw':45,'pitch':20},all_models=True)
        reopened=Database(self.db.path)
        self.assertEqual(camera_for_item(reopened,a),camera_for_item(reopened,b));self.assertEqual(camera_for_item(reopened,a)['yaw'],45)
        save_camera(self.db,a,{'yaw':180});self.assertEqual(camera_for_item(self.db,b)['yaw'],45)
        d=self.keep(CameraDialog(self.db,self.engine,a));d.set_camera({'yaw':-70,'pitch':10,'roll':15});d.store_preset('Vue avant')
        d.set_camera({});d.presets.setCurrentIndex(0);d.presets.setCurrentIndex(d.presets.findData('Vue avant'));self.assertEqual(d.camera()['yaw'],-70)
        self.assertEqual(Database(self.db.path).setting('camera_presets')['Vue avant']['roll'],15);d.reject();self.assertEqual(camera_for_item(self.db,a)['yaw'],180)
    def test_mouse_drag_and_opposite_turn(self):
        d=self.keep(CameraDialog(self.db,self.engine,self.parts[0]));d.show();self.ready(d)
        center=d.preview.rect().center();QTest.mousePress(d.preview,Qt.MouseButton.LeftButton,pos=center);QTest.mouseMove(d.preview,center+QPoint(70,20),delay=20);QTest.mouseRelease(d.preview,Qt.MouseButton.LeftButton,pos=center+QPoint(70,20))
        self.assertEqual(d.camera()['yaw'],35);self.assertEqual(d.camera()['pitch'],-10)
        d.opposite();self.assertEqual(d.camera()['yaw'],-145);self.ready(d);self.assertEqual(camera_for_item(self.db,self.parts[0])['yaw'],0)
    def test_apply_via_preview_updates_item_or_all_models(self):
        p=self.keep(Preview(self.db,self.engine));p.set_item(self.parts[0]);signals=[];p.visual_changed.connect(signals.append)
        def choose(global_view):
            dialog=app.activeModalWidget()
            if not isinstance(dialog,CameraDialog):QTimer.singleShot(10,lambda:choose(global_view));return
            dialog.set_camera({'yaw':180 if not global_view else 60});dialog.all_models.setChecked(global_view)
            def apply():
                if dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled():dialog.accept()
                else:QTimer.singleShot(10,apply)
            QTimer.singleShot(10,apply)
        QTimer.singleShot(10,lambda:choose(False));p.edit_camera();self.assertEqual(camera_for_item(self.db,self.parts[0])['yaw'],180);self.assertEqual(camera_for_item(self.db,self.parts[1])['yaw'],0)
        QTimer.singleShot(10,lambda:choose(True));p.edit_camera();self.assertEqual(camera_for_item(self.db,self.parts[1])['yaw'],60);self.assertIsNone(signals[-1])
    def test_camera_is_used_in_catalogue_thumbnail_and_label(self):
        item=self.parts[0];cat=self.keep(Catalogue(self.db,'RB','part'));cat.engine=self.engine;cat.show();cat.load_thumbnails()
        row=next(i for i,r in enumerate(cat.rows) if r['id']==item['id']);col=cat.visible_columns.index('image')
        wait(lambda:not cat.table.item(row,col).icon().isNull());old=cat.table.item(row,col).icon().cacheKey()
        main1,_=self.engine.visuals(item);label1=render_label(item,self.db,main1,dpi=80)
        save_camera(self.db,item,{'yaw':180});cat.refresh_visual(item);wait(lambda:cat.table.item(row,col).icon().cacheKey()!=old)
        main2,_=self.engine.visuals(item);label2=render_label(item,self.db,main2,dpi=80)
        self.assertNotEqual(main1['main'].tobytes(),main2['main'].tobytes());self.assertNotEqual(label1.tobytes(),label2.tobytes())
        self.assertEqual(main1['top'].tobytes(),main2['top'].tobytes())
