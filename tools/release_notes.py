"""Maintain the single French/English release journal; never create versioned TXT files."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
JOURNAL = Path('documentation/NOUVEAUTES.txt')
MARKER = re.compile(r'^## Version (\d+\.\d+\.\d+)\s*$', re.M)


def section(text, version):
    entries = list(MARKER.finditer(text))
    for index, entry in enumerate(entries):
        if entry.group(1) == version:
            end = entries[index + 1].start() if index + 1 < len(entries) else len(text)
            archive = text.find('\n## Archives antérieures', entry.end(), end)
            return text[entry.start():archive if archive >= 0 else end].strip() + '\n'
    raise ValueError('Version absente du journal : ' + version)


def prepend(text, version, french, english):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Version attendue : X.Y.Z')
    if version in [match.group(1) for match in MARKER.finditer(text)]:
        raise ValueError('Cette version existe déjà dans le journal')
    if not french.strip() or not english.strip():
        raise ValueError('Les deux langues sont nécessaires')
    entry = f'## Version {version}\n\n### Français\n\n{french.strip()}\n\n### English\n\n{english.strip()}\n\n'
    first = MARKER.search(text)
    position = first.start() if first else len(text)
    return text[:position] + entry + text[position:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--add', action='store_true')
    parser.add_argument('--fr', type=Path)
    parser.add_argument('--en', type=Path)
    args = parser.parse_args()
    path = ROOT / JOURNAL
    text = path.read_text(encoding='utf-8')
    if args.add:
        if not args.fr or not args.en:
            parser.error('--add requires --fr and --en input files')
        path.write_text(prepend(text, args.version, args.fr.read_text(encoding='utf-8'), args.en.read_text(encoding='utf-8')), encoding='utf-8')
    else:
        print(section(text, args.version), end='')


if __name__ == '__main__':
    main()
