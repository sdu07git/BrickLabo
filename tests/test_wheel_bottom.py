"""Wheel underside shows the back face along its axle, including old aliases."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from atelier.data import Database
from atelier.labels import preset_template, render_label, export_pdf
from atelier.preview import VisualEngine
from atelier.render import LDraw


class WheelBottomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root/'parts').mkdir()
        (self.root/'ldconfig.ldr').write_text('0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333\n0 !COLOUR Blue CODE 1 VALUE #0000FF EDGE #333333\n0 !COLOUR Green CODE 2 VALUE #00FF00 EDGE #333333\n')
        self.write_wheel('wheel', depth=5)
        self.renderer = LDraw(self.root)

    def tearDown(self):
        self.renderer.close(); self.temp.cleanup()

    def write_wheel(self, ref, depth=5, matrix=None, description='Wheel Rim test'):
        matrix = np.eye(3) if matrix is None else np.array(matrix)
        faces = [(4, [[-20,-20,-depth],[20,-20,-depth],[20,20,-depth],[-20,20,-depth]]),
                 (1, [[-20,-20,depth],[20,-20,depth],[20,20,depth],[-20,20,depth]]),
                 (2, [[10,-20,depth+.1],[20,-20,depth+.1],[20,-10,depth+.1],[10,-10,depth+.1]])]
        lines = ['0 '+description]
        for color, points in faces:
            xyz = np.array(points)@matrix.T
            lines.append('4 '+str(color)+' '+' '.join(str(float(n)) for n in xyz.flat))
        (self.root/'parts'/f'{ref}.dat').write_text('\n'.join(lines)+'\n')

    def test_standard_wheel_back_face_and_correct_mirrored_marker(self):
        front, bounds = self.renderer.render('wheel', (240,180), view='side', outlines=False)
        bottom, other = self.renderer.render('wheel', (240,180), view='bottom', outlines=False)
        np.testing.assert_array_equal(bounds, other)
        self.assertGreater(front.getpixel((120,90))[0], 150)
        self.assertGreater(bottom.getpixel((120,90))[2], 150)
        # The rear face reverses left/right, while retaining vertical orientation.
        self.assertGreater(bottom.getpixel((63,33))[1], 150)
        self.assertEqual(bottom.getpixel((177,33))[1], 0)
        self.assertNotEqual(front.tobytes(), bottom.tobytes())

    def test_wheels_on_all_three_axes_and_with_width_larger_than_diameter(self):
        for axis, matrix in [('z', np.eye(3)), ('x', [[0,0,1],[0,1,0],[-1,0,0]]), ('y', [[1,0,0],[0,0,1],[0,-1,0]])]:
            for depth in (5,30):
                with self.subTest(axis=axis,depth=depth):
                    ref = axis+str(depth); self.write_wheel(ref,depth,matrix)
                    image,_ = self.renderer.render(ref,(180,150),view='bottom',outlines=False)
                    self.assertGreater(image.getpixel((90,75))[2],150)
                    alpha = np.asarray(image)[:,:,3]
                    yy,xx = np.where(alpha>200)
                    self.assertAlmostEqual((xx.max()-xx.min())/(yy.max()-yy.min()),1,delta=.03)

    def test_rotated_and_chained_moved_to_aliases_preserve_signed_axle(self):
        self.write_wheel('cube',20)
        (self.root/'parts/old.dat').write_text('0 ~Moved to cube\n1 16 5 0 0 0 0 -1 0 1 0 1 0 0 cube.dat\n')
        (self.root/'parts/older.dat').write_text('0 ~Moved to old\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 old.dat\n')
        for ref in ('old','older'):
            with self.subTest(ref=ref):
                axis = self.renderer._wheel_axis(ref+'.dat',self.renderer.mesh(ref)[3])
                np.testing.assert_array_equal(axis,[-1,0,0])
                image,_ = self.renderer.render(ref,(180,150),view='bottom',outlines=False)
                self.assertGreater(image.getpixel((90,75))[2],150)

    def test_non_wheels_and_wheel_holders_retain_vertical_underside(self):
        for description in ('Brick 2 x 2','Wheel Holder 2 x 2','Train Wheel Holder'):
            self.write_wheel('other',description=description)
            self.renderer.clear_mesh_cache()
            self.assertIsNone(self.renderer._wheel_axis('other.dat',self.renderer.mesh('other')[3]))

    def test_wheel_rims_for_holding_pins_and_technic_belt_wheels_are_recognized(self):
        for description in ('Wheel Rim 8 x 8 Round Hole, for Wheel Holding Pin','Technic Wedge Belt Wheel - Not Reinforced','Train Wheel test','Tyre test'):
            with self.subTest(description=description):
                self.write_wheel('other',description=description); self.renderer.clear_mesh_cache()
                image,_ = self.renderer.render('other',(180,150),view='bottom',outlines=False)
                self.assertGreater(image.getpixel((90,75))[2],150)

    def test_main_top_and_side_views_are_unchanged_and_bottom_ignores_main_rotation(self):
        for view in ('perspective','top','side'):
            with self.subTest(view=view), patch.object(self.renderer,'_wheel_axis',return_value=None):
                before,_ = self.renderer.render('wheel',(180,150),view=view)
            self.renderer.frame_cache.clear()
            after,_ = self.renderer.render('wheel',(180,150),view=view)
            self.assertEqual(before.tobytes(),after.tobytes())
        bottom,_ = self.renderer.render('wheel',(180,150),view='bottom')
        turned,_ = self.renderer.render('wheel',(180,150),view='bottom',camera={'yaw':90,'pitch':45})
        self.assertEqual(bottom.tobytes(),turned.tobytes())

    def test_wheel_bottom_reaches_label_png_and_pdf(self):
        db = Database(self.root/'db.sqlite'); db.set_setting('ldraw',str(self.root))
        iid = db.run("INSERT INTO items(source,kind,ref,name,category,search) VALUES('RB','part','wheel','Wheel Rim test','Wheels','wheel')")
        item = db.get_item(iid); engine = VisualEngine(db); template = preset_template('main_bottom')
        try:
            visuals,note = engine.visuals(item,template=template)
            self.assertIn('bottom',visuals); self.assertNotIn('indisponible',note)
            layer = next(l for l in template['layers'] if l['type']=='bottom')
            label = render_label(item,db,visuals,template,dpi=254)
            center = tuple(round((layer[k]+layer[s]/2)*10) for k,s in [('x','w'),('y','h')])
            self.assertGreater(label.getpixel(center)[2],150)
            png = self.root/'label.png'; label.save(png); self.assertTrue(png.is_file())
            pdf = self.root/'label.pdf'; export_pdf([label],pdf,template['width'],template['height'])
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
        finally: engine.close(); db.close()
