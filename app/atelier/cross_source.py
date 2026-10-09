"""Resolve photo references from explicit links, never from equal IDs alone."""

from collections import defaultdict
from functools import lru_cache
from html.parser import HTMLParser
import json
import re
import urllib.error
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit

from .paths import resources_directory
from .services import API, request

KINDS = {'part': ('parts', 'P'), 'minifig': ('minifigs', 'M'), 'set': ('sets', 'S')}


def _references(values):
    if isinstance(values, str):
        values = [values]
    return list(dict.fromkeys(str(value) for value in values or [] if value))


@lru_cache(maxsize=1)
def bundled_references():
    """Reuse the checked BrickArchitect snapshot without duplicating its files."""
    root = resources_directory()
    candidates = defaultdict(set)
    path = root / 'brickarchitect.json'
    if path.is_file():
        for record in json.loads(path.read_text(encoding='utf-8')).get('records', []):
            rb = _references(record.get('RB'))
            bl = _references(record.get('BL'))
            if record.get('checked') is True and len(rb) == len(bl) == 1:
                candidates['part:' + rb[0]].add(bl[0])
    result = {key: sorted(values) for key, values in candidates.items()}
    path = root / 'verified_photo_refs.json'
    if path.is_file():
        for key, value in json.loads(path.read_text(encoding='utf-8')).items():
            result[key] = _references(value.get('BrickLink'))
    return result


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ''
        self.in_title = False
        self.links = []
        self.anchor = None
        self.rows = []
        self.cells = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        elif tag == 'a':
            self.anchor = [attrs.get('href', ''), '']
        elif tag == 'tr':
            self.cells = []
        elif tag == 'td' and self.cells is not None:
            self.cell = ['', []]

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'a' and self.anchor is not None:
            link = tuple(self.anchor)
            self.links.append(link)
            if self.cell is not None:
                self.cell[1].append(link)
            self.anchor = None
        elif tag == 'td' and self.cell is not None and self.cells is not None:
            self.cells.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.cells is not None:
            self.rows.append(self.cells)
            self.cells = None

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.anchor is not None:
            self.anchor[1] += data
        if self.cell is not None:
            self.cell[0] += data


def rebrickable_references(html, item):
    """Only the requested item's External Sites / BrickLink table is evidence."""
    kind, ref = item['kind'], item['ref']
    page = _Links()
    page.feed(html)
    label = 'Part' if kind == 'part' else 'Set'
    if not re.search(r'\bLEGO\s+' + label + r'\s+' + re.escape(ref) + r'(?![\w.-])', page.title, re.I):
        return []
    result = []
    for section in re.findall(r'<section\b[^>]*>(.*?)</section\s*>', html, re.I | re.S):
        if not re.search(r'<h[1-6]\b[^>]*>\s*External Sites\s*</h[1-6]\s*>', section, re.I):
            continue
        table = _Links()
        table.feed(section)
        for row in table.rows:
            if len(row) < 2 or row[0][0].strip().casefold() != 'bricklink':
                continue
            for href, text in row[1][1]:
                parsed = urlsplit(urljoin('https://rebrickable.com/', href))
                if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('www.bricklink.com', 'bricklink.com'):
                    continue
                query = parse_qs(parsed.query)
                if parsed.path == '/v2/catalog/catalogitem.page':
                    values = query.get(KINDS[kind][1], [])
                elif kind == 'set' and parsed.path == '/v2/search.page':
                    values = query.get('q', [])
                else:
                    continue
                if len(values) == 1 and values[0] == text.strip() and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', values[0]):
                    result.append(values[0])
    return _references(result)


def bricklink_set_reference(html, item):
    """Validate an exact set candidate through BrickLink's Other Databases link."""
    page = _Links()
    page.feed(html)
    ref = item['ref']
    if not re.search(r'\bSet\s+' + re.escape(ref) + r'(?![\w.-])', page.title, re.I):
        return None
    sections = re.split(r'Other\s+Databases\s*:', html, maxsplit=1, flags=re.I)
    if len(sections) != 2:
        return None
    links = _Links()
    links.feed(sections[1])
    for href, text in links.links:
        parsed = urlsplit(urljoin('https://www.bricklink.com/', href))
        if text.strip().casefold() == 'rebrickable' and parsed.scheme in ('http', 'https') and parsed.hostname in ('rebrickable.com', 'www.rebrickable.com'):
            parts = unquote(parsed.path).strip('/').split('/')
            if len(parts) >= 2 and parts[:2] == ['sets', ref]:
                return ref
    return None


def save_references(db, item, refs):
    refs = _references(refs)
    if refs:
        db.set_setting('rb_bricklink_refs_' + item['kind'] + '_' + item['ref'], refs)
    return refs


def bricklink_reference(db, item, download=False, attempted_pages=None):
    if item.get('source') == 'BL':
        return item['ref']
    kind = item.get('kind')
    if item.get('source') != 'RB' or kind not in KINDS:
        return None
    key = 'rb_bricklink_refs_' + kind + '_' + item['ref']
    refs = db.setting(key)
    if refs is None:
        refs = bundled_references().get(kind + ':' + item['ref'])
    if refs is None and download and kind in ('part', 'minifig') and db.setting('api_rb', ''):
        try:
            data = API(db).rb(KINDS[kind][0] + '/' + quote(item['ref'], safe='') + '/')
            refs = _references(data.get('external_ids', {}).get('BrickLink'))
            if 'external_ids' in data:
                db.set_setting(key, refs)
        except (urllib.error.URLError, ValueError):
            pass
    refs = _references(refs)
    if refs or not download or kind == 'part':
        return refs[0] if len(refs) == 1 else None

    attempts = attempted_pages if attempted_pages is not None else set()
    for source in ('RB', 'BL') if kind == 'set' else ('RB',):
        identity = (source, kind, item['ref'])
        if identity in attempts:
            continue
        attempts.add(identity)
        if source == 'RB':
            url = 'https://rebrickable.com/' + KINDS[kind][0] + '/' + quote(item['ref'], safe='') + '/'
        else:
            url = 'https://www.bricklink.com/v2/catalog/catalogitem.page?S=' + quote(item['ref'], safe='')
        try:
            html = request(url, timeout=12).decode('utf-8', 'replace')
            if source == 'RB':
                refs = rebrickable_references(html, item)
            else:
                verified = bricklink_set_reference(html, item)
                refs = [verified] if verified else []
        except (urllib.error.URLError, ValueError):
            continue
        if refs:
            save_references(db, item, refs)
            return refs[0] if len(refs) == 1 else None
    return None
