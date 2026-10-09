import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from atelier.data import Database
from atelier.edge_controls import EdgeControls
from atelier.edge_style import default_style, style_for_item
from atelier.edges import EdgeDialog
from atelier.editor import LabelEditor
from atelier.labels import individual_template_key
from atelier.memory_cache import MemoryCache
from atelier.preview import VisualEngine

app = QApplication.instance() or QApplication([])


class EdgePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / 'db.sqlite')
        model = self.root / 'ldraw'
        (model / 'parts').mkdir(parents=True)
        (model / 'ldconfig.ldr').write_text('0 Test palette\n')
        face = '4 16 -20 0 -20 20 0 -20 20 0 20 -20 0 20\n'
        edge = '2 24 -15 0 0 15 0 0\n'
        hidden = '2 24 0 10 -15 0 10 15\n'
        conditional = '5 24 -15 0 0 15 0 0 0 0 -10 0 0 -15\n'
        opposite = '5 24 -15 0 0 15 0 0 0 0 -10 0 0 15\n'
        for ref, lines in [('plain', ''), ('a', edge), ('hidden', edge + hidden),
                           ('double', edge * 2), ('conditional', conditional), ('opposite', opposite)]:
            (model / 'parts' / (ref + '.dat')).write_text(face + lines)
        self.db.set_setting('ldraw', str(model))
        self.db.set_setting('camera_default', {})
        iid = self.db.run('INSERT INTO items(source,kind,ref,name,search) VALUES(?,?,?,?,?)',
                          ('RB', 'part', 'a', 'Test', 'a'))
        self.item = self.db.get_item(iid)
        self.engine = VisualEngine(self.db)
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            if hasattr(widget, 'reject'):widget.reject()
            widget.deleteLater()
        app.processEvents()
        self.engine.close()
        self.db.close()
        self.temp.cleanup()

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def image(self, ref='a', black=70, width=1):
        return self.engine.renderer().render(ref, (180, 150), view='top',
                                             edge_settings={'black': black, 'width': width})[0]

    def test_defaults_reset_both_controls_once_and_disable_inheritance(self):
        for inherit in (False, True):
            controls = self.keep(EdgeControls({'black': 12, 'width': 9}, inherit=inherit))
            if inherit:controls.set_settings({'black': 12, 'width': 9}, True)
            changes = []
            controls.changed.connect(lambda: changes.append(1))
            controls.defaults.click()
            self.assertEqual(controls.settings(), default_style())
            self.assertEqual(len(changes), 1)
            self.assertTrue(all(row.isEnabled() for row in controls.rows))
            if inherit:self.assertFalse(controls.inherit.isChecked())

    def test_general_defaults_remain_a_draft_until_applied_and_cancel_keeps_presets(self):
        saved = {'black': 25, 'width': 7}
        presets = {'Impression': saved}
        self.db.set_setting('edge_settings', saved)
        self.db.set_setting('edge_presets', presets)
        dialog = self.keep(EdgeDialog(self.db, self.engine, self.item))
        dialog.timer.stop()
        dialog.controls.defaults.click()
        dialog.timer.stop()
        self.assertEqual(dialog.settings(), default_style())
        self.assertEqual(self.db.setting('edge_settings'), saved)
        dialog.reject()
        self.assertEqual(self.db.setting('edge_settings'), saved)
        self.assertEqual(self.db.setting('edge_presets'), presets)

    def test_individual_defaults_cancel_or_apply_without_changing_general_edges(self):
        saved = {'black': 25, 'width': 7}
        self.db.set_setting('edge_settings', saved)
        editor = self.keep(LabelEditor(self.db, self.engine, self.item, individual=True))
        editor.edge_controls.defaults.click()
        editor.edge_timer.stop()
        self.assertEqual(editor.template['edge_settings'], default_style())
        editor.reject()
        self.assertIsNone(self.db.setting(individual_template_key(self.item)))
        editor = self.keep(LabelEditor(self.db, self.engine, self.item, individual=True))
        editor.edge_controls.defaults.click()
        editor.edge_timer.stop()
        editor.apply()
        self.assertEqual(style_for_item(self.db, self.item), default_style())
        self.assertEqual(self.db.setting('edge_settings'), saved)

    def test_style_changes_reuse_surface_and_width_coverage_without_files_or_db_writes(self):
        renderer = self.engine.renderer()
        with patch.object(renderer, '_frame', wraps=renderer._frame) as frame, \
             patch.object(renderer, '_edge_coverage', wraps=renderer._edge_coverage) as coverage, \
             patch('PIL.Image.Image.save', side_effect=AssertionError('Render disk write')), \
             patch.object(self.db, 'connect', side_effect=AssertionError('Render database write')):
            self.image(black=20, width=1)
            self.image(black=60, width=1)
            self.image(black=60, width=10)
            self.image(black=30, width=10)
            self.assertEqual(frame.call_count, 1)
            self.assertEqual(coverage.call_count, 2)

    def test_intensity_is_monotonic_and_duplicate_edges_do_not_make_lines_darker(self):
        centre = []
        for black in (0, 25, 70, 100):
            image = self.image(black=black, width=3)
            centre.append(image.getpixel((90, 75))[0])
            duplicate = self.image('double', black=black, width=3)
            self.assertEqual(image.tobytes(), duplicate.tobytes())
        self.assertEqual(centre, sorted(centre, reverse=True))
        self.assertGreater(centre[0], centre[1])
        self.assertGreater(centre[1], centre[2])
        self.assertEqual(centre[-1], 0)

    def test_hidden_and_conditional_edges_remain_correct_at_small_and_large_widths(self):
        for width in (.5, 1, 10):
            visible = self.image(width=width)
            self.assertEqual(visible.tobytes(), self.image('hidden', width=width).tobytes())
            self.assertEqual(visible.tobytes(), self.image('conditional', width=width).tobytes())
            self.assertEqual(self.image('plain', width=width).tobytes(), self.image('opposite', width=width).tobytes())

    def test_zero_black_skips_strokes_and_does_not_change_cached_surface(self):
        renderer = self.engine.renderer()
        plain = renderer.render('a', (180, 150), view='top', outlines=False)[0]
        self.image(black=100, width=10)
        with patch.object(renderer, '_edge_coverage', side_effect=AssertionError('Invisible strokes calculated')):
            zero = self.image(black=0, width=10)
        self.assertEqual(plain.tobytes(), zero.tobytes())

    def test_cache_identity_includes_camera_color_size_and_view(self):
        renderer = self.engine.renderer()
        with patch.object(renderer, '_frame', wraps=renderer._frame) as frame:
            for values in ({}, {'camera': {'yaw': 20}}, {'color': '#e12345'},
                           {'size': (181, 150)}, {'view': 'side'}):
                options = {'size': (180, 150), 'edge_settings': default_style(), **values}
                renderer.render('a', **options)
            self.assertEqual(frame.call_count, 5)

    def test_array_cache_is_bounded_and_purge_clears_derived_render_buffers(self):
        cache = MemoryCache(5000)
        for key in range(8):
            cache.get_or_create(key, lambda: {'array': np.zeros((800,), dtype=np.float32)})
        self.assertLessEqual(cache.bytes, 5000)
        self.assertEqual(len(cache.items), 1)
        renderer = self.engine.renderer()
        self.image(width=10)
        self.assertGreater(renderer.frame_cache.bytes, 0)
        self.assertGreater(renderer.edge_cache.bytes, 0)
        renderer.clear_mesh_cache()
        self.assertEqual(renderer.frame_cache.bytes, 0)
        self.assertEqual(renderer.edge_cache.bytes, 0)
        self.image()
        renderer.close()
        self.assertEqual(renderer.frame_cache.bytes, 0)
        self.assertEqual(renderer.edge_cache.bytes, 0)

    def test_concurrent_styles_share_the_same_surface_and_coverage(self):
        renderer = self.engine.renderer()
        with patch.object(renderer, '_frame', wraps=renderer._frame) as frame, \
             patch.object(renderer, '_edge_coverage', wraps=renderer._edge_coverage) as coverage:
            with ThreadPoolExecutor(2) as workers:
                images = list(workers.map(lambda black: self.image(black=black, width=3), (25, 75)))
            self.assertEqual(frame.call_count, 1)
            self.assertEqual(coverage.call_count, 1)
            self.assertNotEqual(images[0].tobytes(), images[1].tobytes())

    def test_changed_general_settings_skip_outdated_views_and_then_render_the_latest(self):
        jobs = []
        def task(owner, work, done, failed):jobs.append((work, done))
        original = self.engine.render_3d
        def render(*args, **kwargs):
            image = original(*args, **kwargs)
            if kwargs['edge_settings']['width'] == 1:
                dialog.controls.spins['width'].setValue(3)
                dialog.timer.stop()
            return image
        with patch('atelier.edges.async_task', side_effect=task), \
             patch.object(self.engine, 'render_3d', side_effect=render) as renders:
            dialog = self.keep(EdgeDialog(self.db, self.engine, self.item))
            dialog.timer.stop()
            dialog.render_preview()
            result = jobs[0][0](lambda *_: None)
            self.assertIsNone(result)
            self.assertEqual(renders.call_count, 1)
            jobs[0][1](result)
            self.assertEqual(dialog.timer.interval(), 0)
            dialog.timer.stop()
            dialog.render_preview()
            result = jobs[1][0](lambda *_: None)
            jobs[1][1](result)
            self.assertEqual(renders.call_count, 4)
            self.assertIsNotNone(dialog.preview.pixmap())
            self.assertEqual(dialog.settings()['width'], 3)

    def test_visuals_cancel_between_views_without_composing_or_fetching_a_photo(self):
        changed = []
        original = self.engine.render_3d
        def render(*args, **kwargs):
            image = original(*args, **kwargs)
            changed.append(True)
            return image
        with patch.object(self.engine, 'render_3d', side_effect=render) as renders, \
             patch.object(self.engine, 'photo', side_effect=AssertionError('Outdated photo fetch')), \
             patch('atelier.label_pieces.enrich', side_effect=AssertionError('Outdated label composition')):
            self.assertEqual(self.engine.visuals(self.item, cancelled=lambda: bool(changed)), ({}, ''))
            self.assertEqual(renders.call_count, 1)


if __name__ == '__main__':unittest.main()
