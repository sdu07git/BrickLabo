"""Check release consistency; --for-final also requires recorded release evidence."""
import argparse
import json
from pathlib import Path
import re
from release_notes import JOURNAL, MARKER, section

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(r'^(?:NOUVEAUT[ÉE]S|CHANGELOG|CONTROLE|RELEASE[-_]NOTES)(?:[_ .-].*)?\.txt$', re.I)


def check(root=ROOT, for_final=False, evidence=None):
    root = Path(root)
    errors = []
    version = json.loads((root / 'app/structure.json').read_text(encoding='utf-8'))['version']
    journal = root / JOURNAL
    for folder in ('documentation', 'app', 'ressources'):
        for path in (root / folder).rglob('*.txt'):
            if FORBIDDEN.fullmatch(path.name) and path != journal:
                errors.append('Journal séparé interdit : ' + path.relative_to(root).as_posix())
    for path in root.glob('*.txt'):
        if FORBIDDEN.fullmatch(path.name):
            errors.append('Journal séparé interdit : ' + path.name)
    text = journal.read_text(encoding='utf-8')
    versions = [match.group(1) for match in MARKER.finditer(text)]
    if len(versions) != len(set(versions)):
        errors.append('Versions dupliquées dans le journal')
    try:
        entry = section(text, version)
        if '### Français' not in entry or '### English' not in entry:
            errors.append('La version courante doit être documentée en français et en anglais')
        if not versions or versions[0] != version:
            errors.append('La version courante doit être la première entrée du journal')
    except ValueError as exc:
        errors.append(str(exc))
    for name in ('app/COMPOSANTS.json', 'app/atelier/version.py', 'tools/launcher.rc'):
        if version not in (root / name).read_text(encoding='utf-8'):
            errors.append('Version incohérente : ' + name)
    for name in ('LICENSE', 'licences/BrickLabo/LICENSE', 'licences/RESOURCE_RIGHTS.json',
                 'documentation/GUIDE_DEMARRAGE.html', 'documentation/GUIDE_DEMARRAGE.en.html'):
        if not (root / name).is_file():
            errors.append('Fichier requis absent : ' + name)
    if for_final or int(version.split('.')[0]) >= 1:
        if not evidence:
            errors.append('Preuves de qualification finale absentes (--evidence)')
        else:
            data = json.loads(Path(evidence).read_text(encoding='utf-8'))
            if data.get('version') != version:
                errors.append('Preuves établies pour une autre version')
            required = ('full_suite_linux', 'full_suite_windows', 'native_windows_portable',
                        'windows_long_session', 'reference_sets', 'backup_restore_windows',
                        'update_windows', 'small_screen_review', 'physical_label_65x23', 'physical_cabinet_a4')
            for key in required:
                record = data.get('checks', {}).get(key, {})
                if record.get('passed') is not True or not record.get('evidence'):
                    errors.append('Qualification finale à confirmer : ' + key)
        rights_file = root / 'licences/RESOURCE_RIGHTS.json'
        if rights_file.exists():
            rights = json.loads(rights_file.read_text(encoding='utf-8'))
            for resource in rights['resources']:
                if resource.get('redistributed') and resource.get('status') not in ('licensed', 'permission_recorded'):
                    errors.append('Droits de redistribution à confirmer : ' + resource['id'])
    if errors:
        raise ValueError('\n'.join(errors))
    return {'version': version, 'journal': JOURNAL.as_posix(), 'final': bool(for_final or int(version.split('.')[0]) >= 1)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--for-final', action='store_true')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(for_final=args.for_final, evidence=args.evidence), ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
