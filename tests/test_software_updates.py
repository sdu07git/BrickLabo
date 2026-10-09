"""Updater contracts: offline GitHub fixtures, real files, failure injection and Qt."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from atelier import software_updates as updates, update_installer as installer, temp_area
from atelier.version import VERSION

FUTURE = '.'.join(map(str, (*installer.version_tuple(VERSION)[:2], installer.version_tuple(VERSION)[2] + 1)))


def pe_fixture():
    content = bytearray(512)
    content[:2] = b'MZ'
    content[60:64] = (128).to_bytes(4, 'little')
    content[128:134] = b'PE\x00\x00\x64\x86'
    return bytes(content)


def payload(version=FUTURE):
    result = {name: ('new:' + name).encode() for name in updates.REQUIRED}
    result.update({name: pe_fixture() for name in ('BrickLabo.exe', 'app/python.exe', 'app/pythonw.exe')})
    result['app/structure.json'] = json.dumps({'application': 'BrickLabo', 'version': version, 'layout': 3}).encode()
    result['app/python312.zip'] = b'embedded standard library fixture'
    result['app/python312.dll'] = b'python dll fixture'
    result['app/python312._pth'] = b'python312.zip\n.\nlib\nimport site\n'
    result['licences/LICENCE.txt'] = b'license fixture'
    return result


def archive_bytes(contents=None, additional=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in (contents or payload()).items():
            archive.writestr('BrickLabo/' + name, content)
        for name, content in additional:
            archive.writestr(name, content)
    return stream.getvalue()


def release_entry(version=FUTURE, **changes):
    name = 'BrickLabo_v' + version + '_Complet.zip'
    result = {'tag_name': 'v' + version, 'draft': False, 'prerelease': False,
              'body': 'New release notes', 'assets': [{'name': name, 'size': 1024,
              'state': 'uploaded', 'digest': 'sha256:' + 'a' * 64,
              'browser_download_url': 'https://github.com/' + updates.REPOSITORY + '/releases/download/v' + version + '/' + name}]}
    result.update(changes)
    return result


class Response(io.BytesIO):
    def __init__(self, content, length=None):
        super().__init__(content)
        self.headers = {} if length is None else {'Content-Length': str(length)}


class ReleaseTests(unittest.TestCase):
    def test_select_highest_numeric_stable_version(self):
        self.assertEqual(updates.select_release([release_entry('0.2.2'), release_entry('0.10.0'), release_entry('0.3.0')]).version, '0.10.0')

    def test_equal_older_draft_and_prerelease_ignored(self):
        for entries in ([], [release_entry(VERSION)], [release_entry('0.1.27')],
                        [release_entry(draft=True)], [release_entry(prerelease=True)],
                        [release_entry(tag_name='v0.1.999b')]):
            self.assertIsNone(updates.select_release(entries))

    def test_full_asset_and_digest_required(self):
        entry = release_entry()
        release = updates.select_release([entry])
        self.assertTrue(release.installable)
        self.assertEqual(release.sha256, 'a' * 64)
        entry['assets'][0]['name'] = 'BrickLabo_v' + FUTURE + '_Sources.zip'
        self.assertFalse(updates.select_release([entry]).installable)
        entry = release_entry()
        entry['assets'][0].pop('digest')
        self.assertFalse(updates.select_release([entry]).installable)

    def test_reject_wrong_url_size_or_upload_state(self):
        for key, value in (('browser_download_url', 'https://evil.example/a.zip'),
                           ('size', True), ('size', updates.MAX_DOWNLOAD + 1), ('state', 'new')):
            entry = release_entry()
            entry['assets'][0][key] = value
            self.assertFalse(updates.select_release([entry]).installable)

    def test_duplicate_asset_is_not_chosen_arbitrarily(self):
        entry = release_entry()
        entry['assets'].append(dict(entry['assets'][0]))
        self.assertFalse(updates.select_release([entry]).installable)

    def test_github_response_limits_and_cancel(self):
        release = updates.check_updates(opener=lambda *a, **kw: Response(json.dumps([release_entry()]).encode()))
        self.assertEqual(release.version, FUTURE)
        for content in (b'not json', b'{}'):
            with self.assertRaises(ValueError):
                updates.check_updates(opener=lambda *a, **kw: Response(content))
        event = threading.Event()
        event.set()
        with self.assertRaises(updates.UpdateCancelled):
            updates.check_updates(cancel=event, opener=lambda *a, **kw: self.fail('Cancelled request opened'))

    def test_download_redirects_are_https_on_github_hosts_only(self):
        self.assertTrue(updates.trusted_url('https://release-assets.githubusercontent.com/example'))
        for url in ('http://github.com/a', 'https://github.com.evil.example/a',
                    'https://user@github.com/a', 'file:///tmp/a', 'https://github.com:1234/a'):
            self.assertFalse(updates.trusted_url(url))
        with self.assertRaises(ValueError):
            updates.GitHubRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example/a.zip')


class ArchiveTests(unittest.TestCase):
    def inspect(self, data):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return updates.inspect_archive(archive, FUTURE)

    def test_complete_zip_and_runtime_version_change(self):
        self.assertEqual(set(self.inspect(archive_bytes())[0]), set(payload()))
        data = payload()
        for suffix in ('.zip', '.dll', '._pth'):
            data['app/python313' + suffix] = data.pop('app/python312' + suffix)
        self.assertEqual(set(self.inspect(archive_bytes(data))[0]), set(data))

    def test_source_only_or_wrong_manifest_rejected(self):
        for change in ('source', 'version', 'layout'):
            data = payload()
            if change == 'source':
                data.pop('BrickLabo.exe')
            else:
                meta = json.loads(data['app/structure.json'])
                meta[change] = '0.1.27' if change == 'version' else 999
                data['app/structure.json'] = json.dumps(meta).encode()
            with self.assertRaises(ValueError):
                self.inspect(archive_bytes(data))

    def test_traversal_windows_special_names_and_data_overwrite_rejected(self):
        for name in ('../outside', 'BrickLabo/Donnees/atelier.sqlite', 'BrickLabo/app/../x',
                     'BrickLabo/app/a\\b', 'BrickLabo/app/C:drive', 'BrickLabo/app/CON.txt',
                     'BrickLabo/app/LPT1', 'BrickLabo/app/trailing.', 'BrickLabo/app/a//b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.inspect(archive_bytes(additional=[(name, b'bad')]))
        # zipfile's writer truncates NUL names; forge the actual on-disk header
        # to test the reader against a malicious name rather than that writer.
        malformed = archive_bytes(additional=[('BrickLabo/app/aXevil', b'bad')])
        malformed = malformed.replace(b'BrickLabo/app/aXevil', b'BrickLabo/app/a\x00evil')
        with self.assertRaises(ValueError):
            self.inspect(malformed)

    def test_case_collisions_and_file_directory_overlap_rejected(self):
        for extra in ([('BrickLabo/app/BOOTSTRAP.py', b'bad')],
                      [('BrickLabo/app/same', b'a'), ('BrickLabo/app/same/x', b'b')],
                      [('BrickLabo/app/Case/a', b'a'), ('BrickLabo/app/case/b', b'b')]):
            with self.assertRaises(ValueError):
                self.inspect(archive_bytes(additional=extra))

    def test_symlink_and_wrong_executable_rejected(self):
        info = zipfile.ZipInfo('BrickLabo/app/link')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        data = io.BytesIO(archive_bytes())
        with zipfile.ZipFile(data, 'a') as archive:
            archive.writestr(info, '../../Donnees')
        with self.assertRaises(ValueError):
            self.inspect(data.getvalue())
        contents = payload()
        contents['app/python.exe'] = b'MZnot a Windows PE'
        with self.assertRaises(ValueError):
            self.inspect(archive_bytes(contents))

    def test_uncompressed_size_and_file_count_budgets(self):
        with patch.object(updates, 'MAX_UNPACKED', 64), self.assertRaises(ValueError):
            self.inspect(archive_bytes())
        with patch.object(updates, 'MAX_FILES', 3), self.assertRaises(ValueError):
            self.inspect(archive_bytes())


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'BrickLabo'
        for folder in installer.DIRECTORIES:
            (self.root / folder).mkdir(parents=True)
            (self.root / folder / 'old.txt').write_text('old ' + folder)
        for name in installer.ROOT_FILES:
            (self.root / name).write_text('old ' + name)
        (self.root / 'app' / 'structure.json').write_text(json.dumps({'application': 'BrickLabo', 'version': VERSION, 'layout': 3}))
        (self.root / 'app' / 'python.exe').write_bytes(pe_fixture())
        (self.root / 'app' / 'python312.zip').write_bytes(b'old stdlib')
        (self.root / 'app' / 'python312.dll').write_bytes(b'old dll')
        (self.root / 'Donnees' / 'temp').mkdir(parents=True)
        (self.root / 'Donnees' / 'stock.bin').write_bytes(b'private stock, settings and API keys')
        (self.root / 'personal.txt').write_bytes(b'user file outside app')
        self.contents = archive_bytes()
        entry = release_entry()
        entry['assets'][0].update(size=len(self.contents), digest='sha256:' + hashlib.sha256(self.contents).hexdigest())
        self.release = updates.select_release([entry])
        self.original = self.snapshot()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and not p.relative_to(self.root).parts[:2] == ('Donnees', 'maj')
                and not p.relative_to(self.root).parts[:2] == ('Donnees', 'temp')}

    def prepare(self, **kwargs):
        result = updates.prepare_update(self.root, self.release, opener=lambda *a, **kw: Response(self.contents), **kwargs)
        self.addCleanup(result.discard)
        return result

    def plan(self, prepared):
        plan, root, stage = installer.validate_plan(prepared.stage / 'plan.json', prepared.pin)
        return plan, root, stage

    def test_prepare_never_changes_installation_and_is_leased(self):
        prepared = self.prepare()
        self.assertEqual(self.snapshot(), self.original)
        self.assertTrue(temp_area.is_live(prepared.stage))
        self.assertTrue((prepared.stage / 'r' / 'python.exe').exists())
        self.assertFalse((prepared.stage / 'r' / 'atelier').exists())
        prepared.discard()
        self.assertFalse(prepared.stage.exists())

    def test_download_hash_size_and_cancel_leave_no_staging_files(self):
        variants = [(self.contents + b'x', None), (self.contents[:-1], None),
                    (b'x' * len(self.contents), None), (self.contents, str(len(self.contents) + 1))]
        for content, length in variants:
            with self.assertRaises(ValueError):
                updates.prepare_update(self.root, self.release, opener=lambda *a, **kw: Response(content, length))
            self.assertEqual(self.snapshot(), self.original)
            self.assertFalse(list((self.root / 'Donnees' / 'temp').iterdir()))
        event = threading.Event()
        with self.assertRaises(updates.UpdateCancelled):
            updates.prepare_update(self.root, self.release, progress=lambda p: event.set(), cancel=event,
                                   opener=lambda *a, **kw: Response(self.contents))
        self.assertFalse(list((self.root / 'Donnees' / 'temp').iterdir()))

    def test_disk_space_checked_before_download_and_extraction(self):
        usage = shutil.disk_usage(self.root)
        with patch.object(shutil, 'disk_usage', return_value=usage._replace(free=0)), self.assertRaises(ValueError):
            updates.prepare_update(self.root, self.release, opener=lambda *a, **kw: self.fail('Opened without disk space'))
        self.assertEqual(self.snapshot(), self.original)

    def test_success_keeps_exact_user_files_and_old_installation(self):
        prepared = self.prepare()
        previous = installer.deploy(*self.plan(prepared), restart=False)
        for name, content in payload().items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertEqual((self.root / 'Donnees' / 'stock.bin').read_bytes(), self.original['Donnees/stock.bin'])
        self.assertEqual((self.root / 'personal.txt').read_bytes(), self.original['personal.txt'])
        for name, content in self.original.items():
            if name.split('/')[0] in installer.MANAGED:
                self.assertEqual((previous / name).read_bytes(), content)
        self.assertFalse((prepared.stage / 'a.zip').exists())
        self.assertFalse((prepared.stage / 'n').exists())
        self.assertEqual(updates.previous_installation(self.root), previous)
        self.assertEqual(installer.read_json(self.root / 'Donnees' / 'maj' / installer.JOURNAL)['status'], 'installed')

    def test_replacement_failure_rolls_back_every_component(self):
        prepared = self.prepare()
        actual_move = installer.move
        def fail_move(source, target, **kwargs):
            if Path(source) == prepared.stage / 'c' / 'documentation':
                raise PermissionError('Simulated locked destination')
            return actual_move(source, target, seconds=0)
        with patch.object(installer, 'move', side_effect=fail_move), self.assertRaises(PermissionError):
            installer.deploy(*self.plan(prepared), restart=False)
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(installer.read_json(self.root / 'Donnees' / 'maj' / installer.JOURNAL)['status'], 'rolled_back')

    def test_failed_restart_rolls_back_before_any_new_process_starts(self):
        prepared = self.prepare()
        with patch.object(installer, 'launch_application', side_effect=OSError('Cannot launch')), self.assertRaises(OSError):
            installer.deploy(*self.plan(prepared))
        self.assertEqual(self.snapshot(), self.original)

    def test_stage_file_plan_and_inventory_tampering_rejected(self):
        for change in ('plan', 'file', 'extra', 'symlink'):
            with self.subTest(change=change):
                prepared = self.prepare()
                if change == 'plan':
                    with (prepared.stage / 'plan.json').open('ab') as stream:
                        stream.write(b' ')
                    with self.assertRaises(ValueError):
                        self.plan(prepared)
                else:
                    path = prepared.stage / 'n' / 'app' / 'bootstrap.py'
                    if change == 'file':
                        path.write_bytes(b'changed')
                    elif change == 'extra':
                        (prepared.stage / 'n' / 'app' / 'extra.py').write_text('unexpected')
                    else:
                        path.unlink()
                        path.symlink_to(self.root / 'personal.txt')
                    with self.assertRaises(ValueError):
                        installer.deploy(*self.plan(prepared), restart=False)
                self.assertEqual(self.snapshot(), self.original)
                prepared.discard()

    def test_current_version_changed_after_preparation(self):
        prepared = self.prepare()
        marker = self.root / 'app' / 'structure.json'
        marker.write_text(json.dumps({'application': 'BrickLabo', 'version': '9.9.9'}))
        with self.assertRaises(ValueError):
            installer.deploy(*self.plan(prepared), restart=False)
        self.assertEqual((self.root / 'Donnees' / 'stock.bin').read_bytes(), self.original['Donnees/stock.bin'])

    def test_live_other_instance_blocks_prepare_and_install(self):
        session = self.root / 'Donnees' / 'temp' / 's1234567890'
        session.mkdir()
        with installer.acquire_lease(session / 'actif'):
            with self.assertRaises(ValueError):
                self.prepare()
        shutil.rmtree(session)
        prepared = self.prepare()
        session.mkdir()
        with installer.acquire_lease(session / 'actif'):
            with self.assertRaises(RuntimeError):
                installer.deploy(*self.plan(prepared), restart=False)
        self.assertEqual(self.snapshot(), self.original)

    def test_startup_gate_prevents_opening_data_during_installation(self):
        state = self.root / 'Donnees' / 'maj'
        state.mkdir()
        with installer.acquire_lease(state / 'verrou'):
            with self.assertRaises(RuntimeError), installer.startup_gate(self.root, seconds=0):
                self.fail('Acquired another process gate')
        with installer.startup_gate(self.root, seconds=0):
            pass

    def test_interrupted_journal_can_restore_old_files(self):
        state = self.root / 'Donnees' / 'maj'
        previous = state / 'b1234567890'
        previous.mkdir(parents=True)
        (self.root / 'app').rename(previous / 'app')
        (self.root / 'app').mkdir()
        (self.root / 'app' / 'partial.py').write_text('partially installed')
        journal = {'previous': previous.name, 'status': 'installing',
                   'changes': [{'name': 'app', 'had_old': True, 'phase': 'installed'}]}
        installer.atomic_json(state / installer.JOURNAL, journal)
        installer.recover_transaction(self.root)
        self.assertEqual(self.snapshot(), self.original)

    def test_invalid_rollback_journal_cannot_touch_user_data(self):
        with self.assertRaises(ValueError):
            installer.rollback(self.root, {'previous': 'b1234567890', 'changes': [{'name': 'Donnees', 'had_old': True, 'phase': 'installed'}]})
        self.assertEqual(self.snapshot(), self.original)

    def test_cleanup_protects_worker_lease_and_interrupted_transaction(self):
        prepared = self.prepare()
        stage = prepared.stage
        worker = installer.acquire_lease(stage / 'maj')
        self.addCleanup(worker.close)
        prepared.handed_off = True
        prepared.release_lease()
        updates.clean_update_workspaces(self.root)
        self.assertTrue(stage.exists())
        temp_area.purge(self.root / 'Donnees' / 'temp')
        self.assertTrue((stage / 'plan.json').exists())
        worker.close()
        installer.atomic_json(self.root / 'Donnees' / 'maj' / installer.JOURNAL, {'status': 'installing', 'stage': stage.name})
        temp_area.purge(self.root / 'Donnees' / 'temp', days=0)
        self.assertTrue((stage / 'plan.json').exists())
        updates.clean_update_workspaces(self.root)
        self.assertTrue(stage.exists())
        installer.atomic_json(self.root / 'Donnees' / 'maj' / installer.JOURNAL, {'status': 'installed', 'stage': stage.name})
        updates.clean_update_workspaces(self.root)
        self.assertFalse(stage.exists())

    def test_isolated_runtime_is_verified_before_handoff(self):
        prepared = self.prepare()
        plan, _, stage = self.plan(prepared)
        installer.verify_runner(plan, stage)
        (stage / 'i.py').write_text('changed helper')
        with self.assertRaises(ValueError):
            installer.verify_runner(plan, stage)

    def test_handoff_waits_for_worker_lease_and_uses_relative_arguments(self):
        prepared = self.prepare()
        class Process:
            pid = 12345
            def poll(self):
                return None
        process = Process()
        leases = []
        def start(command, **kwargs):
            self.assertEqual(command[3:5], ['i.py', 'plan.json'])
            self.assertEqual(kwargs['cwd'], str(prepared.stage))
            self.assertEqual(kwargs['env']['TEMP'], str(prepared.stage / 't'))
            lease = installer.acquire_lease(prepared.stage / 'maj')
            leases.append(lease)
            self.addCleanup(lease.close)
            installer.atomic_json(prepared.stage / 'ready.json', {'pid': process.pid, 'sha256': prepared.pin})
            return process
        windows = SimpleNamespace(name='nt', environ=os.environ, getpid=os.getpid)
        with patch.object(updates, 'os', windows), patch.object(subprocess, 'CREATE_NO_WINDOW', 8, create=True), patch.object(subprocess, 'CREATE_NEW_PROCESS_GROUP', 16, create=True), patch.object(subprocess, 'Popen', side_effect=start):
            self.assertIs(updates.start_installer(prepared), process)
        self.assertTrue(prepared.handed_off)
        self.assertIsNone(prepared.lease)
        self.assertTrue(temp_area.is_live(prepared.stage))
        updates.clean_update_workspaces(self.root)
        self.assertTrue(prepared.stage.exists())
        leases[0].close()
        updates.clean_update_workspaces(self.root)

    def worker_process(self, prepared, arguments):
        # Execute the actual copied stdlib-only helper in a separate Linux
        # process. Stub only Windows application launching, not installation.
        code = "import runpy,sys; m=runpy.run_path('i.py'); m['main'].__globals__['launch_application']=lambda root: None; raise SystemExit(m['main'](sys.argv[1:]))"
        process = subprocess.Popen([sys.executable, '-B', '-c', code, *arguments],
                                   cwd=prepared.stage, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def stop():
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)
        self.addCleanup(stop)
        return process

    def test_real_detached_worker_waits_for_gui_process_then_installs(self):
        prepared = self.prepare()
        parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        def stop_parent():
            if parent.poll() is None:
                parent.terminate()
            parent.wait(timeout=5)
        self.addCleanup(stop_parent)
        worker = self.worker_process(prepared, ['plan.json', prepared.pin, '--wait-pid', str(parent.pid)])
        deadline = time.monotonic() + 5
        while not (prepared.stage / 'ready.json').exists() and time.monotonic() < deadline and worker.poll() is None:
            time.sleep(.02)
        self.assertTrue((prepared.stage / 'ready.json').exists())
        self.assertEqual(self.snapshot(), self.original)
        self.assertTrue(temp_area.is_live(prepared.stage))
        stop_parent()
        stdout, stderr = worker.communicate(timeout=10)
        self.assertEqual(worker.returncode, 0, stdout + stderr)
        self.assertEqual(installer.read_json(self.root / 'app' / 'structure.json')['version'], FUTURE)
        self.assertEqual((self.root / 'Donnees' / 'stock.bin').read_bytes(), self.original['Donnees/stock.bin'])

    def test_recovery_command_uses_the_retained_plan_pin(self):
        prepared = self.prepare()
        state = self.root / 'Donnees' / 'maj'
        previous = state / 'b1234567890'
        previous.mkdir()
        (self.root / 'app').rename(previous / 'app')
        (self.root / 'app').mkdir()
        (self.root / 'app' / 'partial.py').write_text('incomplete update')
        journal = {'previous': previous.name, 'status': 'installing', 'stage': prepared.stage.name,
                   'plan_sha256': prepared.pin, 'changes': [{'name': 'app', 'had_old': True, 'phase': 'installed'}]}
        installer.atomic_json(state / installer.JOURNAL, journal)
        worker = self.worker_process(prepared, ['--recover'])
        stdout, stderr = worker.communicate(timeout=10)
        self.assertEqual(worker.returncode, 0, stdout + stderr)
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(installer.read_json(state / installer.JOURNAL)['status'], 'rolled_back')

    def test_complete_backup_excludes_installation_backups(self):
        from atelier.data import Database
        from atelier.backups import create_backup
        db = Database(self.root / 'Donnees' / 'atelier.sqlite')
        self.addCleanup(db.close)
        (self.root / 'Donnees' / 'maj').mkdir()
        (self.root / 'Donnees' / 'maj' / 'old.exe').write_bytes(b'not user data')
        target = Path(self.temp.name) / 'backup.zip'
        create_backup(db, target)
        with zipfile.ZipFile(target) as archive:
            self.assertNotIn('Donnees/maj/old.exe', archive.namelist())
            self.assertIn('Donnees/stock.bin', archive.namelist())


class UpdateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_release_notes_are_plain_text_and_controls_follow_state(self):
        from atelier.software_update_dialog import SoftwareUpdateDialog
        dialog = SoftwareUpdateDialog(auto_check=False)
        dialog.automatic = True
        release = updates.select_release([release_entry(body='<script>unsafe</script> **release notes**')])
        dialog.checked(release)
        self.assertEqual(dialog.notes.toPlainText(), release.notes)
        self.assertTrue(dialog.download_button.isEnabled())
        self.assertFalse(dialog.install_button.isEnabled())
        dialog.checked(None)
        self.assertFalse(dialog.download_button.isEnabled())
        dialog.reject()

    def test_reject_cancels_and_discards_prepared_download(self):
        from atelier.software_update_dialog import SoftwareUpdateDialog
        from unittest.mock import Mock
        dialog = SoftwareUpdateDialog(auto_check=False)
        prepared = Mock()
        dialog.prepared = prepared
        dialog.reject()
        self.assertTrue(dialog.cancel_event.is_set())
        prepared.discard.assert_called_once()

    def test_install_transfers_ownership_before_closing_child(self):
        from PySide6.QtWidgets import QWidget
        from atelier.software_update_dialog import SoftwareUpdateDialog
        from unittest.mock import Mock
        class Owner(QWidget):
            def request_software_update(owner, prepared):
                self.assertIsNone(dialog.prepared)
                self.assertIs(prepared, plan)
                dialog.reject()
                return True
        owner = Owner()
        dialog = SoftwareUpdateDialog(owner, auto_check=False)
        plan = Mock()
        dialog.prepared = plan
        dialog.automatic = True
        dialog.install()
        plan.discard.assert_not_called()
        dialog.deleteLater()
        owner.deleteLater()

    def test_declined_close_keeps_prepared_update(self):
        from PySide6.QtWidgets import QWidget
        from atelier.software_update_dialog import SoftwareUpdateDialog
        from unittest.mock import Mock
        class Owner(QWidget):
            def request_software_update(owner, prepared):
                return False
        owner = Owner()
        dialog = SoftwareUpdateDialog(owner, auto_check=False)
        plan = Mock()
        dialog.prepared = plan
        dialog.automatic = True
        dialog.install()
        self.assertIs(dialog.prepared, plan)
        self.assertTrue(dialog.install_button.isEnabled())
        dialog.reject()
        owner.deleteLater()

    def test_data_update_window_contains_software_command_and_disables_during_import(self):
        from atelier.data import Database
        from atelier.dialogs import ImportDialog
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / 'atelier.sqlite')
            dialog = ImportDialog(db, None)
            self.assertIn('logiciel', dialog.software_button.text())
            dialog.busy(True)
            self.assertFalse(dialog.software_button.isEnabled())
            dialog.busy(False)
            self.assertTrue(dialog.software_button.isEnabled())
            dialog.reject()
            db.close()

    def test_main_handoff_happens_after_workers_engine_and_database_close(self):
        from unittest.mock import Mock
        from atelier import app as application
        order = []
        root = Path(tempfile.gettempdir()) / 'bricklabo-main-test'
        prepared = Mock()
        db = Mock()
        db.close.side_effect = lambda: order.append('database')
        window = Mock(catalogues=[])
        window._pending_software_update = prepared
        window.findChildren.return_value = []
        window.engine.close.side_effect = lambda: order.append('engine')
        gui = Mock()
        gui.exec.return_value = 0
        pool = Mock()
        pool.waitForDone.side_effect = lambda: order.append('workers')
        def start(value):
            self.assertIs(value, prepared)
            self.assertEqual(order, ['workers', 'engine', 'database'])
            order.append('installer')
        old_hook = sys.excepthook
        try:
            with patch('atelier.storage.prepare_portable_storage', return_value=root), patch('atelier.storage.configure_portable_database'), patch.object(application, 'setup_logging', return_value=(Mock(), root / 'logs')), patch.object(application, 'QApplication', return_value=gui), patch.object(application, 'install_qt_language'), patch.object(application, 'Database', return_value=db), patch.object(application, 'MainWindow', return_value=window), patch('PySide6.QtCore.QThreadPool.globalInstance', return_value=pool), patch.object(updates, 'start_installer', side_effect=start):
                self.assertEqual(application.main(), 0)
        finally:
            sys.excepthook = old_hook
        self.assertEqual(order[-1], 'installer')
        prepared.discard.assert_not_called()


if __name__ == '__main__':
    unittest.main()
