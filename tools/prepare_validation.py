"""Recover the pinned previous Windows runtime and LDraw archive for disposable validation."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
NAME = 'BrickLabo_v0.1.72_Complet.zip'
SHA = '0bd8b946dc785d2c0c23ea87e3fdcde4f4257b075b0850d193afb345af3c1470'
URL = 'https://github.com/sdu07git/BrickLabo/releases/download/v0.1.72/' + NAME


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    archive = output / NAME
    if not archive.exists() or digest(archive) != SHA:
        partial = archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(URL, timeout=120) as source, partial.open('wb') as target:
                shutil.copyfileobj(source, target)
            if digest(partial) != SHA:
                raise ValueError('Runtime SHA-256 mismatch')
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    target = ROOT / 'ressources/complete.zip'
    if not target.exists():
        with ZipFile(archive) as source, source.open('BrickLabo/ressources/complete.zip') as reader, target.open('wb') as writer:
            shutil.copyfileobj(reader, writer)
    print(archive)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)
