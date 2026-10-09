"""Manual GitHub Release discovery and verified portable update preparation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile

from .i18n import tr, tf
from .version import VERSION
from . import temp_area
from .update_installer import (
    DIRECTORIES, ROOT_FILES, STATE_FOLDER, JOURNAL, REPORT,
    acquire_lease, atomic_json, linked, native_path, other_instances,
    read_json, safe_relative, validate_locations, validate_plan, verify_runner, version_tuple,
)

REPOSITORY = 'sdu07git/BrickLabo'
RELEASES_URL = 'https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=100'
RELEASES_PAGE = 'https://github.com/' + REPOSITORY + '/releases'
MAX_DOWNLOAD = 1536 * 1024 * 1024
MAX_UNPACKED = 4 * 1024**3
MAX_FILES = 30000
MAX_JSON = 16 * 1024 * 1024
REQUIRED = (
    'BrickLabo.exe', 'LISEZ-MOI.txt', 'PROJET_GITHUB.url',
    'app/bootstrap.py', 'app/structure.json', 'app/COMPOSANTS.json',
    'app/atelier/version.py', 'app/python.exe', 'app/pythonw.exe',
    'app/python3.dll', 'app/_sqlite3.pyd',
    'app/lib/PySide6/QtWidgets.pyd', 'app/lib/PySide6/plugins/platforms/qwindows.dll',
    'app/lib/PIL/Image.py', 'app/lib/numpy/__init__.py',
    'ressources/BrickLabo.ico', 'ressources/complete.zip',
    'documentation/AIDE.html', 'documentation/AIDE.en.html',
)


class UpdateCancelled(Exception):
    def __str__(self):
        return tr('Téléchargement annulé. Aucun fichier du logiciel n’a été remplacé.')


def cancelled(event):
    if event is not None and event.is_set():
        raise UpdateCancelled()


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    notes: str
    page: str
    asset_name: str = ''
    asset_url: str = ''
    size: int = 0
    sha256: str = ''
    problem: str = ''

    @property
    def installable(self):
        return bool(self.asset_url and self.sha256 and not self.problem)


def select_release(entries, current=VERSION):
    if not isinstance(entries, list):
        raise ValueError(tr('Réponse GitHub invalide.'))
    candidates = []
    installed = version_tuple(current)
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('draft') or entry.get('prerelease'):
            continue
        tag = entry.get('tag_name', '')
        match = re.fullmatch(r'v?(\d{1,5}\.\d{1,5}\.\d{1,5})', tag) if isinstance(tag, str) else None
        if match and version_tuple(match[1]) > installed:
            candidates.append((version_tuple(match[1]), match[1], tag, entry))
    if not candidates:
        return None
    _, version, tag, entry = max(candidates, key=lambda row: row[0])
    page = RELEASES_PAGE + '/tag/' + quote(tag, safe='')
    notes = entry.get('body') or ''
    notes = notes[:500000] if isinstance(notes, str) else ''
    expected = 'BrickLabo_v' + version + '_Complet.zip'
    assets = entry.get('assets') or []
    if not isinstance(assets, list):
        raise ValueError(tr('Réponse GitHub invalide.'))
    matching = [a for a in assets if isinstance(a, dict) and a.get('name') == expected]
    if len(matching) != 1:
        return Release(version, tag, notes, page, problem=tr('Le ZIP complet Windows est absent de cette release.'))
    asset = matching[0]
    size = asset.get('size')
    url = asset.get('browser_download_url', '')
    expected_url = 'https://github.com/' + REPOSITORY + '/releases/download/' + quote(tag, safe='') + '/' + expected
    if asset.get('state') != 'uploaded' or type(size) is not int or not 0 < size <= MAX_DOWNLOAD or url != expected_url:
        return Release(version, tag, notes, page, problem=tr('Le fichier de mise à jour publié n’est pas reconnu.'))
    digest = asset.get('digest') or ''
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        return Release(version, tag, notes, page, problem=tr('GitHub ne fournit pas de contrôle SHA-256 pour ce ZIP. L’installation automatique est indisponible.'))
    return Release(version, tag, notes, page, expected, url, size, digest[7:].lower())


def trusted_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in (
        'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
        'objects.githubusercontent.com', 'github-releases.githubusercontent.com',
    ) and not parsed.username and not parsed.password and parsed.port in (None, 443))


class GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted_url(newurl):
            raise ValueError(tr('Redirection de téléchargement non autorisée.'))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_request(url, api=False):
    if not trusted_url(url):
        raise ValueError(tr('Adresse de téléchargement non autorisée.'))
    headers = {'User-Agent': 'BrickLabo/' + VERSION, 'Accept': 'application/octet-stream'}
    if api:
        headers.update({'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10'})
    request = Request(url, headers=headers)
    try:
        response = build_opener(GitHubRedirect()).open(request, timeout=20)
        if not trusted_url(response.geturl()):
            response.close()
            raise ValueError(tr('Adresse de téléchargement non autorisée.'))
        return response
    except HTTPError as error:
        if error.code in (403, 429):
            raise ValueError(tr('GitHub refuse la requête ou limite les téléchargements. Réessaie plus tard.')) from error
        if error.code == 404:
            raise ValueError(tr('Aucune release publique accessible sur GitHub.')) from error
        raise ValueError(tf('Erreur GitHub HTTP {0}.', error.code)) from error
    except URLError as error:
        raise ValueError(tr('Connexion à GitHub impossible. Vérifie la connexion Internet puis réessaie.')) from error


def check_updates(current=VERSION, cancel=None, opener=open_request):
    cancelled(cancel)
    with opener(RELEASES_URL, api=True) as response:
        content = response.read(MAX_JSON + 1)
    cancelled(cancel)
    if len(content) > MAX_JSON:
        raise ValueError(tr('Réponse GitHub trop volumineuse.'))
    try:
        entries = json.loads(content)
    except (ValueError, UnicodeError) as error:
        raise ValueError(tr('Réponse GitHub invalide.')) from error
    return select_release(entries, current)


class PreparedUpdate:
    """Own a leased workspace until explicitly handed to the detached installer."""
    def __init__(self, root, stage, release, lease):
        self.root, self.stage = native_path(root), native_path(stage)
        self.release, self.lease = release, lease
        self.pin = ''
        self.handed_off = False
        temp_area.register(self.stage)

    def release_lease(self):
        temp_area.release(self.stage)
        if self.lease is not None:
            self.lease.close()
            self.lease = None

    def discard(self):
        self.release_lease()
        if not self.handed_off:
            shutil.rmtree(self.stage, ignore_errors=True)

    def __del__(self):
        try:
            self.discard()
        except Exception:
            pass


def inspect_archive(archive, version):
    if len(archive.infolist()) > MAX_FILES:
        raise ValueError(tr('Le ZIP contient trop de fichiers.'))
    files, folded, directories = {}, set(), set()
    total = 0
    for info in archive.infolist():
        if info.orig_filename != info.filename:
            raise ValueError(tr('Chemin ou contenu interdit dans le ZIP de mise à jour.'))
        name = info.filename.rstrip('/') if info.is_dir() else info.filename
        if name == 'BrickLabo' and info.is_dir():
            continue
        if not name.startswith('BrickLabo/'):
            raise ValueError(tr('Ce ZIP n’est pas une distribution complète de BrickLabo.'))
        relative = name[len('BrickLabo/'):]
        try:
            safe_relative(relative)
        except ValueError as error:
            raise ValueError(tr('Chemin ou contenu interdit dans le ZIP de mise à jour.')) from error
        key = relative.casefold()
        if key in folded or info.flag_bits & 1:
            raise ValueError(tr('Fichier dupliqué ou chiffré dans le ZIP.'))
        folded.add(key)
        mode = info.external_attr >> 16
        allowed = (0, stat.S_IFDIR) if info.is_dir() else (0, stat.S_IFREG)
        if stat.S_IFMT(mode) not in allowed:
            raise ValueError(tr('Les liens et fichiers spéciaux sont interdits dans le ZIP.'))
        if info.is_dir():
            if relative in ROOT_FILES:
                raise ValueError(tr('Ce ZIP n’est pas une distribution complète de BrickLabo.'))
            directories.add(key)
            continue
        if info.file_size < 0 or info.file_size > 1024**3:
            raise ValueError(tr('Un fichier du ZIP est trop volumineux.'))
        total += info.file_size
        if total > MAX_UNPACKED:
            raise ValueError(tr('Le contenu décompressé du ZIP est trop volumineux.'))
        files[relative] = info
    spellings = {}
    for relative in files:
        path = safe_relative(relative)
        for candidate in (path, *path.parents):
            text = candidate.as_posix()
            previous = spellings.setdefault(text.casefold(), text)
            if previous != text:
                raise ValueError(tr('Des chemins du ZIP se chevauchent.'))
    file_keys = {name.casefold() for name in files}
    for relative in files:
        parents = safe_relative(relative).parents
        if any(parent.as_posix().casefold() in file_keys for parent in parents):
            raise ValueError(tr('Des chemins du ZIP se chevauchent.'))
    if file_keys & directories or not set(REQUIRED).issubset(files):
        raise ValueError(tr('Le ZIP est incomplet ou contient uniquement le code source.'))
    runtimes = [name for name in files if re.fullmatch(r'app/python\d+\.zip', name)]
    if len(runtimes) != 1 or any(runtimes[0][:-4] + extension not in files for extension in ('.dll', '._pth')):
        raise ValueError(tr('Le ZIP est incomplet ou contient uniquement le code source.'))
    for folder in DIRECTORIES:
        if not any(name.startswith(folder + '/') for name in files):
            raise ValueError(tr('Le ZIP est incomplet ou contient uniquement le code source.'))
    metadata = files['app/structure.json']
    if metadata.file_size > 65536:
        raise ValueError(tr('Manifeste de distribution invalide.'))
    try:
        structure = json.loads(archive.read(metadata))
    except (ValueError, UnicodeError) as error:
        raise ValueError(tr('Manifeste de distribution invalide.')) from error
    if (not isinstance(structure, dict) or structure.get('application') != 'BrickLabo'
            or structure.get('version') != version or structure.get('layout') != 3):
        raise ValueError(tr('La version du ZIP ne correspond pas à la release annoncée.'))
    for relative in ('BrickLabo.exe', 'app/python.exe', 'app/pythonw.exe'):
        with archive.open(files[relative]) as stream:
            header = stream.read(64)
            if len(header) != 64 or header[:2] != b'MZ':
                raise ValueError(tr('Le ZIP ne contient pas les exécutables Windows attendus.'))
            offset = int.from_bytes(header[60:64], 'little')
            if not 64 <= offset <= min(files[relative].file_size - 6, 1024 * 1024):
                raise ValueError(tr('Le ZIP ne contient pas les exécutables Windows attendus.'))
            stream.seek(offset)
            if stream.read(6) != b'PE\x00\x00\x64\x86':
                raise ValueError(tr('Le ZIP ne contient pas les exécutables Windows attendus.'))
    return files, total


def isolated_runtime(root, stage):
    """Copy only the existing embedded standard library, not Qt or application code."""
    source, target = root / 'app', stage / 'r'
    target.mkdir()
    for path in source.iterdir():
        if path.is_file() and not linked(path) and (
                path.suffix.lower() in ('.dll', '.pyd')
                or re.fullmatch(r'python\d+\.zip', path.name)
                or path.name == 'python.exe'):
            shutil.copyfile(path, target / path.name)
    libraries = list(target.glob('python*.zip'))
    if not (target / 'python.exe').is_file() or len(libraries) != 1:
        raise ValueError(tr('Le runtime Windows portable est absent. Télécharge le ZIP complet depuis GitHub.'))
    (target / (libraries[0].stem + '._pth')).write_text(libraries[0].name + '\n.\n', encoding='utf-8')
    shutil.copyfile(native_path(Path(__file__).with_name('update_installer.py')), stage / 'i.py')
    result = {}
    for path in [stage / 'i.py', *target.iterdir()]:
        with path.open('rb') as stream:
            result[path.relative_to(stage).as_posix()] = {'size': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    return result


def prepare_update(root, release, progress=lambda value: None, cancel=None, opener=open_request):
    root = native_path(root)
    if not release.installable or version_tuple(release.version) <= version_tuple(VERSION):
        raise ValueError(release.problem or tr('Cette release ne peut pas être installée.'))
    for folder in (root, root / 'Donnees', root / 'Donnees' / 'temp'):
        if linked(folder) or not folder.is_dir():
            raise ValueError(tr('Le dossier du logiciel ou des données n’est pas valide.'))
    state = root / 'Donnees' / STATE_FOLDER
    if linked(state):
        raise ValueError(tr('Le dossier de mise à jour ne doit pas être un lien.'))
    state.mkdir(exist_ok=True)
    current = read_json(root / 'app' / 'structure.json')
    if current.get('application') != 'BrickLabo' or current.get('version') != VERSION:
        raise ValueError(tr('La version installée a changé. Relance BrickLabo puis recherche à nouveau les mises à jour.'))
    if (state / JOURNAL).exists() and read_json(state / JOURNAL).get('status') in ('installing', 'rollback_failed'):
        raise ValueError(tr('Une mise à jour interrompue doit être réparée avant une nouvelle installation. Consulte Donnees/maj/transaction.json et le dossier de l’ancienne installation.'))
    if other_instances(root, own_session=temp_area.temporary_folder(root / 'Donnees' / 'temp')):
        raise ValueError(tr('Ferme les autres instances de BrickLabo avant de préparer la mise à jour.'))
    if shutil.disk_usage(root).free < release.size + 64 * 1024 * 1024:
        raise ValueError(tr('Espace disque insuffisant pour télécharger la mise à jour.'))
    stage = root / 'Donnees' / 'temp' / ('u' + uuid.uuid4().hex[:10])
    stage.mkdir()
    prepared = None
    try:
        prepared = PreparedUpdate(root, stage, release, acquire_lease(stage / 'actif'))
        validate_locations(root, stage)
        checksum, size = hashlib.sha256(), 0
        progress((tr('Téléchargement du ZIP complet…'), 0))
        with opener(release.asset_url) as response, (stage / 'a.zip').open('xb') as writer:
            length = response.headers.get('Content-Length')
            if length and (not length.isdigit() or int(length) != release.size):
                raise ValueError(tr('La taille du téléchargement ne correspond pas à la release.'))
            last = 0.0
            while True:
                cancelled(cancel)
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > release.size:
                    raise ValueError(tr('Le téléchargement dépasse la taille annoncée.'))
                checksum.update(chunk)
                writer.write(chunk)
                now = time.monotonic()
                if now - last > .1:
                    progress((tr('Téléchargement du ZIP complet…'), int(size * 60 / release.size)))
                    last = now
        cancelled(cancel)
        if size != release.size or checksum.hexdigest() != release.sha256:
            raise ValueError(tr('Le contrôle SHA-256 du ZIP a échoué. Aucun fichier du logiciel n’a été remplacé.'))
        progress((tr('Vérification et préparation des fichiers…'), 60))
        with zipfile.ZipFile(stage / 'a.zip') as archive:
            files, total = inspect_archive(archive, release.version)
            if shutil.disk_usage(root).free < total * 2 + 64 * 1024 * 1024:
                raise ValueError(tr('Espace disque insuffisant pour préparer et installer la mise à jour.'))
            destination = stage / 'n'
            destination.mkdir()
            inventory, extracted = {}, 0
            last = 0.0
            for relative, info in files.items():
                cancelled(cancel)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                checksum, count = hashlib.sha256(), 0
                with archive.open(info) as reader, target.open('xb') as writer:
                    while chunk := reader.read(1024 * 1024):
                        cancelled(cancel)
                        count += len(chunk)
                        if count > info.file_size:
                            raise ValueError(tr('Le contenu décompressé dépasse la taille annoncée.'))
                        checksum.update(chunk)
                        writer.write(chunk)
                if count != info.file_size:
                    raise ValueError(tr('Un fichier de la mise à jour est incomplet.'))
                inventory[relative] = {'size': count, 'sha256': checksum.hexdigest()}
                extracted += count
                now = time.monotonic()
                if now - last > .1:
                    progress((tr('Vérification et préparation des fichiers…'), 60 + int(35 * extracted / max(total, 1))))
                    last = now
        cancelled(cancel)
        runner = isolated_runtime(root, stage)
        plan = {'format': 1, 'application': 'BrickLabo', 'root': str(root), 'stage': str(stage),
                'from_version': VERSION, 'version': release.version, 'files': inventory, 'runner': runner}
        atomic_json(stage / 'plan.json', plan)
        prepared.pin = hashlib.sha256((stage / 'plan.json').read_bytes()).hexdigest()
        cancelled(cancel)
        progress((tr('Mise à jour prête. Clique sur Installer et redémarrer.'), 100))
        return prepared
    except BaseException:
        if prepared is not None:
            prepared.discard()
        else:
            shutil.rmtree(stage, ignore_errors=True)
        raise


def start_installer(prepared, wait_pid=None):
    """Called after workers and database close. Await the staged process lease."""
    if os.name != 'nt':
        raise ValueError(tr('L’installation automatique est disponible dans la distribution Windows complète.'))
    plan, _, stage = validate_plan(prepared.stage / 'plan.json', prepared.pin)
    verify_runner(plan, stage)
    environment = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'BRICKLABO_ROOT'):
        environment.pop(key, None)
    temporary = prepared.stage / 't'
    temporary.mkdir(exist_ok=True)
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        environment[key] = str(temporary)
    command = [str(prepared.stage / 'r' / 'python.exe'), '-I', '-B',
               'i.py', 'plan.json', prepared.pin,
               '--wait-pid', str(wait_pid or os.getpid())]
    process = subprocess.Popen(command, cwd=str(prepared.stage), env=environment,
                               creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                               close_fds=True)
    deadline = time.monotonic() + 10
    ready = prepared.stage / 'ready.json'
    while time.monotonic() < deadline:
        if ready.exists():
            value = read_json(ready)
            if value.get('pid') == process.pid and value.get('sha256') == prepared.pin:
                prepared.handed_off = True
                prepared.release_lease()
                return process
        if process.poll() is not None:
            break
        time.sleep(.05)
    # A worker that did not acknowledge ownership must never perform a later update.
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    raise RuntimeError(tr('Le programme d’installation n’a pas démarré. L’ancienne version est conservée.'))


def clean_update_workspaces(root):
    """Only inactive updater workspaces; keep interrupted transactions recoverable."""
    root = native_path(root)
    temporary = root / 'Donnees' / 'temp'
    journal_path = root / 'Donnees' / STATE_FOLDER / JOURNAL
    protected = ''
    try:
        if journal_path.exists():
            journal = read_json(journal_path)
            if journal.get('status') in ('installing', 'rollback_failed'):
                protected = journal.get('stage', '')
        if not temporary.is_dir() or linked(temporary):
            return
        for folder in temporary.iterdir():
            if (folder.is_dir() and not linked(folder) and re.fullmatch(r'u[0-9a-f]{10}', folder.name)
                    and folder.name != protected and not temp_area.is_live(folder)):
                shutil.rmtree(folder, ignore_errors=True)
    except (OSError, ValueError):
        pass


def previous_installation(root):
    state = native_path(root) / 'Donnees' / STATE_FOLDER
    try:
        report = read_json(state / REPORT)
        name = report.get('previous', '')
        path = state / name
        if (re.fullmatch(r'b[0-9a-f]{10}', name) and path.is_dir() and not linked(path)
                and (path / 'app' / 'structure.json').is_file()):
            return path
    except (OSError, ValueError, TypeError):
        pass
    return None
