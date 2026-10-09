import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication
from atelier.cross_source import (
    API, bricklink_reference, bricklink_set_reference, bundled_references,
    rebrickable_references,
)
from atelier.data import Database
from atelier.preview import VisualEngine

app = QApplication.instance() or QApplication([])


def rb_page(kind, ref, links):
    label = 'Part' if kind == 'part' else 'Set'
    return (f'<title>LEGO {label} {ref} Example | Rebrickable</title>'
            '<section><h4>External Sites</h4><table><tr><td>BrickLink</td><td>'
            + ''.join(f'<a href="{url}">{text}</a>' for url, text in links)
            + '</td></tr></table></section>')


class CrossReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / 'db.sqlite')
        self.engine = VisualEngine(self.db)

    def tearDown(self):
        self.engine.close()
        self.db.close()
        bundled_references.cache_clear()
        self.temp.cleanup()

    def item(self, kind, ref):
        iid = self.db.run('INSERT INTO items(source,kind,ref,name,image,search) VALUES(?,?,?,?,?,?)',
                          ('RB', kind, ref, ref, 'https://cdn.rebrickable.com/missing.jpg', ref))
        return self.db.get_item(iid)

    def test_bundled_checked_photo_pair_preserves_different_ids_and_model(self):
        item = self.item('part', '14210')
        self.assertEqual(bricklink_reference(self.db, item), 'x64pb01')
        image = Image.new('RGB', (32, 32), 'red')
        def get(url, download):
            return image if url == 'https://img.bricklink.com/ItemImage/P/x64pb01.gif' else None
        with patch.object(self.engine.images, 'get', side_effect=get), patch('atelier.cross_source.request') as request:
            visuals, note = self.engine.visuals(item, download=True, mode='photo_rb', _composition=False)
            self.assertIs(visuals['main'], image)
            self.assertIn('BrickLink : x64pb01', note)
            self.assertIn('référence Rebrickable : 14210', note)
            self.assertNotIn('variante de', note)
            self.assertEqual(self.db.get_item(item['id'])['ref'], '14210')
            self.assertEqual(self.db.visual(item['id'])['image'], '')
            request.assert_not_called()

    def test_snapshot_rejects_unchecked_multiple_and_conflicting_links(self):
        records = [
            {'checked': True, 'RB': ['r1'], 'BL': ['b1']},
            {'checked': True, 'RB': ['r2'], 'BL': ['b2', 'b3']},
            {'checked': False, 'RB': ['r3'], 'BL': ['b3']},
            {'checked': True, 'RB': ['r4'], 'BL': ['b4']},
            {'checked': True, 'RB': ['r4'], 'BL': ['b5']},
        ]
        (self.root / 'brickarchitect.json').write_text(json.dumps({'records': records}))
        (self.root / 'verified_photo_refs.json').write_text(json.dumps({'set:030-2': {'BrickLink': ['030-2']}}))
        bundled_references.cache_clear()
        with patch('atelier.cross_source.resources_directory', return_value=self.root):
            self.assertEqual(bricklink_reference(self.db, self.item('part', 'r1')), 'b1')
            for ref in ('r2', 'r3', 'r4'):
                self.assertIsNone(bricklink_reference(self.db, self.item('part', ref)))
            self.assertEqual(bricklink_reference(self.db, self.item('set', '030-2')), '030-2')
            self.assertEqual(bundled_references.cache_info().misses, 1)

    def test_official_external_sites_cover_sets_and_different_minifig_ids(self):
        for kind, ref, url, target in (
            ('set', '75192-1', 'https://www.bricklink.com/v2/search.page?q=75192-1&amp;utm_source=rebrickable#T=A', '75192-1'),
            ('minifig', 'fig-012937', 'https://www.bricklink.com/v2/catalog/catalogitem.page?M=sw1222&amp;utm_source=rebrickable', 'sw1222'),
            ('part', '14210', 'https://www.bricklink.com/v2/catalog/catalogitem.page?P=x64pb01', 'x64pb01'),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(rebrickable_references(rb_page(kind, ref, [(url, target)]), {'kind': kind, 'ref': ref}), [target])

    def test_external_references_exclude_related_variants_wrong_types_and_hosts(self):
        item = {'kind': 'set', 'ref': '030-2'}
        link = ('https://www.bricklink.com/v2/catalog/catalogitem.page?S=030-2', '030-2')
        for html in (
            rb_page('set', '030-20', [link]), rb_page('set', '030-2.extra', [link]),
            rb_page('set', '030-2', [('https://www.bricklink.com/v2/catalog/catalogitem.page?P=030-2', '030-2')]),
            rb_page('set', '030-2', [('https://www.bricklink.com.evil.test/v2/catalog/catalogitem.page?S=030-2', '030-2')]),
            rb_page('set', '030-2', [link]).replace('External Sites', 'Related Sets'),
            rb_page('set', '030-2', [(link[0], '030-1')]),
        ):
            self.assertEqual(rebrickable_references(html, item), [])

    def test_set_fallback_uses_only_confirmed_bricklink_other_database_link(self):
        item = self.item('set', 'unverified-1')
        valid = '<title>Example : Set unverified-1 | BrickLink</title>Other Databases: <a href="http://www.rebrickable.com/sets/unverified-1">Rebrickable</a>'
        for html in (valid.replace('sets/unverified-1', 'sets/unverified-2'), valid.replace('Other Databases:', 'Related Sets:'), valid.replace('Set unverified-1', 'Set unverified-10')):
            self.assertIsNone(bricklink_set_reference(html, item))
        def get(url, **kwargs):
            if 'rebrickable.com' in url:
                raise urllib.error.HTTPError(url, 403, 'Unavailable', {}, None)
            return valid.encode()
        with patch('atelier.cross_source.request', side_effect=get) as request:
            self.assertIsNone(bricklink_reference(self.db, item, False))
            request.assert_not_called()
            self.assertEqual(bricklink_reference(self.db, item, True), 'unverified-1')
            self.assertEqual(bricklink_reference(self.db, item, True), 'unverified-1')
            self.assertEqual(request.call_count, 2)

    def test_minifig_uses_external_table_when_api_has_no_external_ids(self):
        item = self.item('minifig', 'fig-012937')
        self.db.set_setting('api_rb', 'fake-test-key')
        html = rb_page('minifig', item['ref'], [('https://www.bricklink.com/v2/catalog/catalogitem.page?M=sw1222', 'sw1222')])
        with patch.object(API, 'rb', return_value={'set_num': item['ref']}) as api, patch('atelier.cross_source.request', return_value=html.encode()) as request:
            self.assertEqual(bricklink_reference(self.db, item, True), 'sw1222')
            self.assertEqual(bricklink_reference(self.db, item, True), 'sw1222')
            api.assert_called_once(); request.assert_called_once()

    def test_minifig_photo_supports_normalized_small_image_and_retains_rb_id(self):
        item = self.item('minifig', 'fig-012937')
        self.db.set_setting('rb_bricklink_refs_minifig_' + item['ref'], ['sw1222'])
        image = Image.new('RGBA', (32, 32), 'red')
        def get(url, download):
            return image if url == 'https://img.bricklink.com/ItemImage/MN/0/sw1222.png' else None
        with patch.object(self.engine.images, 'get', side_effect=get):
            self.assertIs(self.engine.photo(item), image)
            self.assertEqual(image.info['bricklabo_photo_source'], {'source': 'BL', 'ref': 'sw1222'})
            self.assertEqual(self.db.get_item(item['id'])['ref'], 'fig-012937')

    def test_ambiguous_and_unavailable_pages_do_not_guess_or_repeat_requests(self):
        item = self.item('set', 'unverified-1')
        attempts = set()
        with patch('atelier.cross_source.request', side_effect=ValueError('Unavailable')) as request:
            for _ in range(3):
                self.assertIsNone(bricklink_reference(self.db, item, True, attempts))
            self.assertEqual(request.call_count, 2)
            self.assertIsNone(self.db.setting('rb_bricklink_refs_set_' + item['ref']))
        self.db.set_setting('rb_bricklink_refs_set_' + item['ref'], ['a', 'b'])
        with patch('atelier.cross_source.request') as request:
            self.assertIsNone(bricklink_reference(self.db, item, True))
            request.assert_not_called()
