"""Qualify a release using real bundled inventories and disposable data only."""
import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import gc
from io import TextIOWrapper
from io import BytesIO
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import monotonic
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
os.environ['QT_QPA_PLATFORM'] = 'windows' if sys.platform == 'win32' else os.environ.get('QT_QPA_PLATFORM', 'offscreen')
REFERENCES = ('10696-1', '10698-1', '30363-1')


def rows(name):
    with ZipFile(ROOT / 'ressources' / (name + '.csv.zip')) as archive:
        with archive.open(name + '.csv') as stream:
            yield from csv.DictReader(TextIOWrapper(stream, encoding='utf-8-sig', newline=''))


def catalogue(db, folder):
    inventories = list(rows('inventories'))
    latest = {}
    for row in inventories:
        key = (int(row['version']), int(row['id']))
        if key > latest.get(row['set_num'], (-1, -1)):
            latest[row['set_num']] = key
    nested = {name: list(rows(name)) for name in ('inventory_sets', 'inventory_minifigs')}
    refs = set(REFERENCES)
    while True:
        ids = {str(latest[ref][1]) for ref in refs}
        added = {row.get('set_num', row.get('fig_num')) for values in nested.values() for row in values if row['inventory_id'] in ids}
        if added <= refs:
            break
        refs |= added
    parts = [row for row in rows('inventory_parts') if row['inventory_id'] in ids]
    part_refs = {row['part_num'] for row in parts}
    selected = {
        'inventories': [row for row in inventories if row['id'] in ids],
        'inventory_parts': parts,
        'inventory_sets': [row for row in nested['inventory_sets'] if row['inventory_id'] in ids],
        'inventory_minifigs': [row for row in nested['inventory_minifigs'] if row['inventory_id'] in ids],
        'parts': [row for row in rows('parts') if row['part_num'] in part_refs],
        'sets': [row for row in rows('sets') if row['set_num'] in refs],
        'minifigs': [row for row in rows('minifigs') if row['fig_num'] in refs],
    }
    for name in ('part_categories', 'colors', 'themes'):
        db.import_file(ROOT / 'ressources' / (name + '.csv.zip'))
    for name in ('parts', 'sets', 'minifigs', 'inventories', 'inventory_parts', 'inventory_sets', 'inventory_minifigs'):
        values = selected[name]
        if not values:
            continue
        path = folder / (name + '.csv')
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader(); writer.writerows(values)
        db.import_file(path)
    return {ref: latest[ref][1] for ref in REFERENCES}


def ledger(db):
    tables = ('stock', 'stock_sets', 'stock_set_components', 'construction_projects', 'project_parts',
              'project_color_reservations', 'storage_walls', 'storage_drawers', 'storage_contents')
    return {table: db.rows('SELECT * FROM ' + table + ' ORDER BY rowid') for table in tables}


def qualify(output, duration):
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication
    from atelier.data import Database
    from atelier import projects, storage_wall
    from atelier.build_stock import find_builds
    from atelier.backups import create_backup, queue_restore, apply_pending, REPORT
    from atelier.gui_gc import GuiGarbageCollector
    from atelier.task_lifetime import drain_tasks
    from atelier.render import LDraw
    from atelier.labels import default_template, render_label, export_pdf
    from atelier.version import VERSION

    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be a new empty validation directory')
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    from atelier.ui_common import STYLE, pixmap
    app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    collector = GuiGarbageCollector(app); collector.timer.stop()
    report = dict(version=VERSION, system=platform.system(), python=platform.python_version(),
                  checks=[], manual_physical_print_confirmed=False, manual_long_term_windows_pc_confirmed=False)
    windows = []; databases = []; renderer = None
    with tempfile.TemporaryDirectory(prefix='bricklabo-qualification-') as disposable:
        folder = Path(disposable)
        try:
            template = Database(folder / 'fixture.sqlite'); databases.append(template)
            report['inventory_ids'] = catalogue(template, folder)
            for ref in REFERENCES:
                path = folder / ref / 'Donnees' / 'atelier.sqlite'
                db = Database(path); databases.append(db)
                with template.connect() as source, db.connect() as target:
                    source.backup(target)
                item = db.rows("SELECT id FROM items WHERE source='RB' AND kind='set' AND ref=?", (ref,))[0]['id']
                db.add('stock_sets', item, quantity=1)
                entry = db.rows('SELECT id FROM stock_sets')[0]['id']
                project = projects.from_set(db, item, include_set_stock=True)
                state = lambda pid: next(row for row in projects.list_projects(db) if row['id'] == pid)
                summary = state(project)
                assert summary['required'] > 0 and summary['missing'] == 0, (ref, summary)
                assert not db.rows('SELECT 1 FROM stock WHERE quantity>0'), ref
                projects.set_include_set_stock(db, project, False)
                assert state(project)['missing'] == summary['required'], ref
                projects.delete(db, project)
                db.remove('stock_sets', [entry])
                for ignore in (False, True):
                    found = [row for row in find_builds(db, text=ref, minimum=100, ignore_colors=ignore, include_set_stock=False)[0] if row['ref'] == ref]
                    assert len(found) == 1 and found[0]['percent'] == 100 and found[0]['missing'] == 0, (ref, ignore, found)
                project = projects.from_set(db, item)
                before = db.rows('SELECT item_id,color,quantity FROM stock ORDER BY item_id,color')
                projects.reserve(db, project)
                details = projects.detail(db, project)
                assert sum(row['reserved'] for row in details) == summary['required'], (ref, state(project))
                other = projects.from_set(db, item)
                owned = {(row['item_id'], row['color']): row['quantity'] for row in before}
                used = {(row['id'], row['chosen_color']): row['reserved'] for row in details}
                expected_missing = sum(max(0, row['required'] - max(0, owned.get((row['id'], row['chosen_color']), 0) - used.get((row['id'], row['chosen_color']), 0))) for row in projects.detail(db, other))
                assert state(other)['missing'] == expected_missing, (ref, state(other), expected_missing)
                projects.release(db, project)
                assert state(other)['missing'] == 0
                assert before == db.rows('SELECT item_id,color,quantity FROM stock ORDER BY item_id,color')
                snapshot = ledger(db)
                backup = folder / (ref + '-backup.zip')
                create_backup(db, backup)
                first = before[0]; db.add('stock', first['item_id'], first['color'], 9)
                queue_restore(db, backup); db.close(); apply_pending(path.parent)
                restored = Database(path); databases.append(restored)
                assert ledger(restored) == snapshot, ref
                assert json.loads((path.parent / REPORT).read_text(encoding='utf-8'))['success']
                report['checks'].append(dict(case='reference_set', ref=ref, required=summary['required'], owned_set_missing=0, loose_percent=100, color_ignored_percent=100, reservation_missing=expected_missing, backup_restored=True))
                print('Reference verified', ref, summary['required'], flush=True)

            demo = Database(folder / 'demo' / 'Donnees' / 'atelier.sqlite'); databases.append(demo)
            with template.connect() as source, demo.connect() as target:
                source.backup(target)
            wall = storage_wall.create_wall(demo, 'Meuble de démonstration — 33 tiroirs', 3, 11)
            demo.set_setting('ldraw', str(ROOT / 'ressources/complete.zip'))
            renderer = LDraw(ROOT / 'ressources/complete.zip')
            refs = ('3005', '3004', '3622', '3010', '3003', '3002', '3001')
            images = {}; start = monotonic(); count = 0
            while count < len(refs) or monotonic() - start < duration:
                ref = refs[count % len(refs)]
                image, bounds = renderer.render(ref + '.dat', size=(256, 190), color='#C91A09', camera={'yaw':(count * .37) % 360 - 180, 'pitch':24})
                assert image.getbbox(), ref
                images[ref] = image; count += 1
                app.processEvents()
                if count % 25 == 0:
                    collector.collect_if_idle(force=True)
            report['checks'].append(dict(case='3d_rendering', count=count, seconds=monotonic()-start))
            for drawer, ref in zip(storage_wall.drawers(demo, wall), refs):
                matches = demo.rows("SELECT id FROM items WHERE source='RB' AND kind='part' AND ref=?", (ref,))
                if not matches:
                    continue
                identity = matches[0]['id']; demo.add('stock', identity, '4', 40)
                from atelier.storage_quantities import put_entry
                put_entry(demo, drawer['id'], identity, '4', 40)
            item = demo.rows("SELECT * FROM items WHERE source='RB' AND kind='part' AND ref='3005'")[0]
            visual = {'main': images['3005']}
            for view in ('top','side','bottom'):
                visual[view], visual['bounds'] = renderer.render('3005.dat', size=(256,190), color='#C91A09', view=view)
            label = render_label(item, demo, visual, default_template())
            label.save(output / 'etiquette-65x23.png')
            export_pdf([label], output / 'etiquettes-a4.pdf', 65, 23)
            from atelier.storage_printing import StoragePrintPreview
            with patch.object(StoragePrintPreview, 'prepare_images'):
                preview = StoragePrintPreview(demo, None, wall); windows.append(preview)
                for part in preview.snapshot['parts']:
                    if part['ref'] in images:
                        buffer = BytesIO(); images[part['ref']].save(buffer, format='PNG')
                        preview.images[(part['id'], str(part['chosen_color']))] = buffer.getvalue()
                preview.export_pdf(output / 'meuble-a4.pdf')
                preview.show(); app.processEvents(); preview.grab().save(str(output / 'apercu-meuble-a4.png'))
                preview.close()
            import atelier.app as application
            from atelier.i18n import set_language
            with ExitStack() as stack:
                for name in ('atelier.catalogue.Catalogue.load_thumbnails',
                             'atelier.thumbnails.PartThumbnails.load', 'atelier.storage_panel.StoragePanel.load_icons'):
                    stack.enter_context(patch(name))
                stack.enter_context(patch('atelier.services.request', side_effect=OSError('Offline qualification')))
                stack.enter_context(patch('atelier.preview.request', side_effect=OSError('Offline qualification')))
                for language in ('fr', 'en'):
                    set_language(language)
                    application = importlib.reload(application)
                    window = application.MainWindow(demo); windows.append(window); window.startup_timer.stop()
                    window.nav.setCurrentRow(next(i for i, row in enumerate(application.NAV) if row[3]=='stock'))
                    window.item_selected(dict(item, chosen_color='4'))
                    QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); drain_tasks()
                    for width, height in ((1366, 768), (800, 600)):
                        window.resize(width, height); window.show(); app.processEvents()
                        assert window.workspace_splitter.sizes()[1] >= 200
                        window.grab().save(str(output / f'interface-{language}-{width}.png'))
                    for part in storage_wall.wall_contents(demo):
                        if part['ref'] in images:
                            window.storage.icons[(part['id'], str(part['chosen_color']))] = pixmap(images[part['ref']])
                    window.nav.setCurrentRow(next(i for i, row in enumerate(application.NAV) if row[3]=='storage'))
                    window.resize(1366, 850); app.processEvents(); window.storage.fit_all(); app.processEvents()
                    window.grab().save(str(output / f'rangement-{language}.png'))
                    window.close(); app.processEvents()
            report['checks'].append(dict(case='ui_and_exports', languages=['fr', 'en'], sizes=[[1366,768],[800,600]], label_mm=[65,23], paper='A4', physical_print=False))
            report['success'] = True
        finally:
            for window in reversed(windows):
                window.close()
            joined = QThreadPool.globalInstance().waitForDone(10000)
            app.processEvents(); drain_tasks(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            if renderer:
                renderer.close()
            for db in reversed(databases):
                db.close()
            report['qt_shutdown'] = bool(joined and collector.stop())
            report['success'] = bool(report.get('success') and report['qt_shutdown'])
            (output / 'qualification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert report['success']
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=int, default=120, choices=range(0,86401), metavar='SECONDS')
    args = parser.parse_args()
    qualify(args.output, args.duration)
