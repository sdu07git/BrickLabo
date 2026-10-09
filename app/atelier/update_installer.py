"""Standalone, standard-library installer run from an isolated portable runtime.

The GUI seals a plan after checking GitHub's SHA-256 and extracting the ZIP.
This process waits for the GUI to exit, verifies files while preparing a copy,
then renames only the application roots. Donnees is never a deployment target.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time
import uuid

DIRECTORIES = ('app', 'ressources', 'documentation', 'licences')
ROOT_FILES = ('LISEZ-MOI.txt', 'PROJET_GITHUB.url', 'BrickLabo.exe')
# Replace the launcher last; leave user-created files outside these roots alone.
MANAGED = DIRECTORIES + ROOT_FILES
STATE_FOLDER = 'maj'
JOURNAL = 'transaction.json'
REPORT = 'resultat.json'
MAX_PLAN = 16 * 1024 * 1024
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', re.I)


def native_path(path):
    """Use Windows extended paths for file operations, including long UNC paths."""
    value = os.path.abspath(path)
    if os.name == 'nt' and not value.startswith('\\\\?\\'):
        value = '\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value
    return Path(value)


def display_path(path):
    """Normal spelling for shell/Qt paths; extended paths are for file I/O."""
    value = str(path)
    if value.startswith('\\\\?\\UNC\\'):
        return '\\\\' + value[8:]
    return value[4:] if value.startswith('\\\\?\\') else value


def linked(path):
    path = Path(path)
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def safe_relative(name):
    path = PurePosixPath(name)
    if (not name or path.as_posix() != name or path.is_absolute()
            or '\\' in name or len(name) > 1500):
        raise ValueError('Invalid application path: ' + name)
    for part in path.parts:
        if (part in ('.', '..', '') or part[-1:] in (' ', '.') or len(part) > 255
                or RESERVED.match(part) or any(ord(c) < 32 or c in ':<>"|?*' for c in part)):
            raise ValueError('Invalid Windows filename: ' + name)
    if path.parts[0] not in MANAGED or (path.parts[0] in ROOT_FILES and len(path.parts) != 1):
        raise ValueError('Unexpected application content: ' + name)
    return path


def atomic_json(path, value):
    path = native_path(path)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path):
    with native_path(path).open('rb') as stream:
        value = stream.read(MAX_PLAN + 1)
    if len(value) > MAX_PLAN:
        raise ValueError('Update metadata is too large')
    return json.loads(value)


def acquire_lease(path):
    stream = native_path(path).open('a+b')
    try:
        if stream.tell() == 0:
            stream.write(b'1')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except BaseException:
        stream.close()
        raise


def live_lease(path):
    if not native_path(path).exists():
        return False
    try:
        stream = acquire_lease(path)
        stream.close()
        return False
    except OSError:
        return True


@contextmanager
def startup_gate(root, seconds=10):
    """New instances cannot open SQLite while the installer owns the gate."""
    path = native_path(root) / 'Donnees' / STATE_FOLDER / 'verrou'
    lease = None
    if path.exists():
        deadline = time.monotonic() + seconds
        while True:
            try:
                lease = acquire_lease(path)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Mise à jour en cours. Attends sa fin avant de relancer BrickLabo. / Update in progress. Wait before starting BrickLabo.')
                time.sleep(.1)
    try:
        yield
    finally:
        if lease is not None:
            lease.close()


def other_instances(root, own_stage=None, own_session=None):
    temporary = native_path(root) / 'Donnees' / 'temp'
    if not temporary.is_dir():
        return False
    skipped = {native_path(p).resolve() for p in (own_stage, own_session) if p}
    for folder in temporary.iterdir():
        if linked(folder) or folder.resolve() in skipped:
            continue
        if re.fullmatch(r'[su][0-9a-f]{10}', folder.name):
            if any(live_lease(folder / name) for name in ('actif', 'maj')):
                return True
    return False


def validate_locations(root, stage):
    root, stage = native_path(root), native_path(stage)
    for folder in (root, root / 'Donnees', root / 'Donnees' / 'temp', root / 'Donnees' / STATE_FOLDER):
        if linked(folder) or not folder.is_dir():
            raise ValueError('Invalid installation folder: ' + str(folder))
    if (linked(stage) or not stage.is_dir()
            or stage.parent.resolve() != (root / 'Donnees' / 'temp').resolve()
            or not re.fullmatch(r'u[0-9a-f]{10}', stage.name)):
        raise ValueError('Invalid update workspace')
    for name in MANAGED:
        if linked(root / name):
            raise ValueError('Linked application folders cannot be updated: ' + name)
    return root, stage


def validate_plan(path, pin):
    path = native_path(path)
    if linked(path) or not isinstance(pin, str) or not re.fullmatch(r'[0-9a-f]{64}', pin):
        raise ValueError('Invalid update plan')
    if path.stat().st_size > MAX_PLAN:
        raise ValueError('Update plan is too large')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != pin:
        raise ValueError('Prepared update plan changed')
    plan = json.loads(content)
    if plan.get('format') != 1 or plan.get('application') != 'BrickLabo':
        raise ValueError('Unknown update plan')
    root, stage = validate_locations(plan['root'], path.parent)
    if native_path(plan['stage']).resolve() != stage.resolve() or path.name != 'plan.json':
        raise ValueError('Update workspace changed')
    files = plan.get('files')
    if not isinstance(files, dict) or not files or len(files) > 30000:
        raise ValueError('Invalid prepared file list')
    folded = set()
    for relative, meta in files.items():
        safe_relative(relative)
        if (relative.casefold() in folded or not isinstance(meta, dict)
                or type(meta.get('size')) is not int or not 0 <= meta['size'] <= 1024**3
                or not re.fullmatch(r'[0-9a-f]{64}', meta.get('sha256', ''))):
            raise ValueError('Invalid prepared file: ' + relative)
        folded.add(relative.casefold())
    if sum(meta['size'] for meta in files.values()) > 4 * 1024**3:
        raise ValueError('Prepared update is too large')
    return plan, root, stage


def verify_runner(plan, stage):
    """The GUI verifies its trusted helper and runtime before executing either."""
    expected = plan.get('runner')
    if not isinstance(expected, dict) or 'i.py' not in expected or 'r/python.exe' not in expected or len(expected) > 100:
        raise ValueError('Invalid isolated update runtime')
    runtime = stage / 'r'
    if linked(runtime) or not runtime.is_dir():
        raise ValueError('Invalid isolated update runtime')
    actual = {'i.py'}
    for path in runtime.iterdir():
        if linked(path) or not path.is_file():
            raise ValueError('Isolated update runtime changed')
        actual.add('r/' + path.name)
    if actual != set(expected):
        raise ValueError('Isolated update runtime changed')
    for relative, meta in expected.items():
        if relative != 'i.py' and (not relative.startswith('r/') or '/' in relative[2:] or '\\' in relative):
            raise ValueError('Invalid isolated runtime path')
        path = stage / relative
        if linked(path) or path.stat().st_size != meta['size']:
            raise ValueError('Isolated update runtime changed')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != meta['sha256']:
                raise ValueError('Isolated update runtime integrity failure')


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}', value):
        raise ValueError('Invalid software version')
    return tuple(map(int, value.split('.')))


def copy_verified(plan, stage):
    source, destination = stage / 'n', stage / 'c'
    if linked(source) or not source.is_dir() or destination.exists():
        raise ValueError('Invalid prepared application folder')
    actual = set()
    for base, dirs, names in os.walk(source, followlinks=False):
        for name in dirs + names:
            if linked(Path(base) / name):
                raise ValueError('Linked file in prepared update')
        for name in names:
            actual.add((Path(base) / name).relative_to(source).as_posix())
    if actual != set(plan['files']):
        raise ValueError('Prepared update contents changed')
    destination.mkdir()
    for relative, meta in plan['files'].items():
        path = source / relative
        if path.stat().st_size != meta['size'] or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Prepared file changed: ' + relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256()
        size = 0
        with path.open('rb') as reader, target.open('xb') as writer:
            while chunk := reader.read(1024 * 1024):
                size += len(chunk)
                if size > meta['size']:
                    raise ValueError('Prepared file grew: ' + relative)
                checksum.update(chunk)
                writer.write(chunk)
        if size != meta['size'] or checksum.hexdigest() != meta['sha256']:
            raise ValueError('Prepared file integrity failure: ' + relative)
    structure = read_json(destination / 'app' / 'structure.json')
    if structure.get('application') != 'BrickLabo' or structure.get('version') != plan['version']:
        raise ValueError('Prepared software version changed')
    return destination


def move(source, destination, seconds=30):
    """Allow the old launcher and antivirus to release files; never force locks."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.2)


def remove_application(path):
    if linked(path):
        raise ValueError('Linked application target: ' + str(path))
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def rollback(root, journal):
    previous = root / 'Donnees' / STATE_FOLDER / journal['previous']
    if not re.fullmatch(r'b[0-9a-f]{10}', journal['previous']) or linked(previous):
        raise ValueError('Invalid previous installation')
    changes = journal['changes']
    if not isinstance(changes, list) or len(changes) > len(MANAGED):
        raise ValueError('Invalid update journal')
    seen = set()
    for change in changes:
        if (change.get('name') not in MANAGED or change['name'] in seen
                or type(change.get('had_old')) is not bool
                or change.get('phase') not in ('moving_old', 'old_moved', 'installing', 'installed')):
            raise ValueError('Invalid update journal entry')
        seen.add(change['name'])
    for change in reversed(changes):
        name = change['name']
        target, original = root / name, previous / name
        if linked(target) or linked(original):
            raise ValueError('Linked file in update rollback')
        if original.exists():
            remove_application(target)
            move(original, target)
        elif not change['had_old'] and change['phase'] in ('installing', 'installed'):
            remove_application(target)
        elif change['had_old'] and not target.exists():
            raise ValueError('Original installation missing: ' + name)
    journal['status'] = 'rolled_back'
    atomic_json(root / 'Donnees' / STATE_FOLDER / JOURNAL, journal)


def recover_transaction(root):
    path = root / 'Donnees' / STATE_FOLDER / JOURNAL
    if not path.exists():
        return
    journal = read_json(path)
    if journal.get('status') in ('installing', 'rollback_failed'):
        rollback(root, journal)


def deploy(plan, root, stage, restart=True):
    """Call only after holding the installation lock and waiting for all GUIs."""
    current = read_json(root / 'app' / 'structure.json')
    if (current.get('application') != 'BrickLabo' or current.get('version') != plan['from_version']
            or version_tuple(plan['version']) <= version_tuple(current['version'])):
        raise ValueError('The installed version changed; check for updates again')
    needed = sum(meta['size'] for meta in plan['files'].values()) + 64 * 1024 * 1024
    if shutil.disk_usage(root).free < needed:
        raise OSError('Not enough disk space to install safely')
    prepared = copy_verified(plan, stage)
    if other_instances(root, own_stage=stage):
        raise RuntimeError('Another BrickLabo instance is open; no files were replaced')
    state = root / 'Donnees' / STATE_FOLDER
    previous = state / ('b' + uuid.uuid4().hex[:10])
    previous.mkdir()
    journal = {'format': 1, 'status': 'installing', 'previous': previous.name,
               'stage': stage.name, 'from_version': plan['from_version'],
               'version': plan['version'], 'changes': [],
               'plan_sha256': hashlib.sha256((stage / 'plan.json').read_bytes()).hexdigest()}
    atomic_json(state / JOURNAL, journal)
    try:
        for name in MANAGED:
            old, new = root / name, prepared / name
            if not new.exists():
                raise ValueError('Missing application component: ' + name)
            change = {'name': name, 'had_old': old.exists(), 'phase': 'moving_old'}
            journal['changes'].append(change)
            atomic_json(state / JOURNAL, journal)
            if change['had_old']:
                move(old, previous / name)
            change['phase'] = 'old_moved'
            atomic_json(state / JOURNAL, journal)
            change['phase'] = 'installing'
            atomic_json(state / JOURNAL, journal)
            move(new, old)
            change['phase'] = 'installed'
            atomic_json(state / JOURNAL, journal)
        journal['status'] = 'installed'
        atomic_json(state / JOURNAL, journal)
        atomic_json(state / REPORT, {'success': True, 'version': plan['version'],
                                    'previous': previous.name, 'from_version': plan['from_version'], 'stage': stage.name})
        if restart:
            launch_application(root)
        # Release the large download and unpacked copy immediately. The tiny
        # running interpreter is purged when it is no longer leased.
        for name in ('n', 'c'):
            shutil.rmtree(stage / name, ignore_errors=True)
        try:
            (stage / 'a.zip').unlink(missing_ok=True)
        except OSError:
            pass
        return previous
    except BaseException as error:
        try:
            rollback(root, journal)
            code = 'rolled_back'
        except Exception as failure:
            journal['status'] = 'rollback_failed'
            atomic_json(state / JOURNAL, journal)
            code = 'rollback_failed'
            error = RuntimeError(str(error) + '\nRollback: ' + str(failure))
        atomic_json(state / REPORT, {'success': False, 'code': code, 'error': str(error),
                                    'previous': previous.name, 'from_version': plan['from_version'], 'stage': stage.name})
        raise


def launch_application(root):
    root = Path(display_path(root))
    environment = dict(os.environ)
    environment.pop('BRICKLABO_ROOT', None)
    for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'PYTHONHOME', 'PYTHONPATH'):
        environment.pop(key, None)
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        environment[key] = str(root / 'Donnees' / 'temp')
    return subprocess.Popen([str(root / 'BrickLabo.exe')], cwd=str(root), env=environment, close_fds=True)


def wait_for_process(pid, seconds=120):
    if pid <= 0:
        raise ValueError('Invalid application process')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            result = kernel.WaitForSingleObject(handle, int(seconds * 1000))
            if result != 0:
                raise TimeoutError('BrickLabo did not close; no files were replaced')
        finally:
            kernel.CloseHandle(handle)
    else:
        deadline = time.monotonic() + seconds
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError('BrickLabo did not close')
            time.sleep(.1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', nargs='?', default='plan.json')
    parser.add_argument('sha256', nargs='?')
    parser.add_argument('--wait-pid', type=int)
    parser.add_argument('--recover', action='store_true', help='Restore an interrupted transaction after all application instances close')
    args = parser.parse_args(argv)
    if args.recover and args.sha256 is None:
        unverified = read_json(args.plan)
        journal = read_json(native_path(unverified['root']) / 'Donnees' / STATE_FOLDER / JOURNAL)
        args.sha256 = journal.get('plan_sha256', '')
    plan, root, stage = validate_plan(args.plan, args.sha256)
    if not args.recover and not args.wait_pid:
        raise ValueError('The application process is required')
    with acquire_lease(stage / 'maj'):
        atomic_json(stage / 'ready.json', {'pid': os.getpid(), 'sha256': args.sha256})
        try:
            if args.wait_pid:
                wait_for_process(args.wait_pid)
            if other_instances(root, own_stage=stage):
                raise RuntimeError('Another BrickLabo instance is open; no files were replaced')
            with acquire_lease(root / 'Donnees' / STATE_FOLDER / 'verrou'):
                if other_instances(root, own_stage=stage):
                    raise RuntimeError('Another BrickLabo instance is open; no files were replaced')
                if args.recover:
                    journal = read_json(root / 'Donnees' / STATE_FOLDER / JOURNAL)
                    if journal.get('stage') != stage.name or journal.get('status') not in ('installing', 'rollback_failed'):
                        raise ValueError('No interrupted update matches this workspace')
                recover_transaction(root)
                if args.recover:
                    atomic_json(root / 'Donnees' / STATE_FOLDER / REPORT,
                                {'success': False, 'code': 'rolled_back', 'error': 'Interrupted update recovered', 'stage': stage.name})
                    launch_application(root)
                else:
                    deploy(plan, root, stage)
            return 0
        except Exception as error:
            state = root / 'Donnees' / STATE_FOLDER
            if not (state / REPORT).exists() or read_json(state / REPORT).get('stage') != stage.name:
                atomic_json(state / REPORT, {'success': False, 'code': 'not_installed', 'error': str(error), 'stage': stage.name})
            if os.name == 'nt':
                import ctypes
                message = ('Mise à jour interrompue. / Update interrupted.\n\n' + str(error)
                           + '\n\n' + str(state / REPORT))
                ctypes.windll.user32.MessageBoxW(None, message, 'BrickLabo', 0x10)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
