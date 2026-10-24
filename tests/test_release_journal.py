"""Release safeguards protect history and prevent premature final labels."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from release_notes import prepend, section
from check_release import check, ROOT


class ReleaseJournalTests(unittest.TestCase):
    def test_new_versions_preserve_history_and_both_languages(self):
        historical = 'BrickLabo\n\n## Version 0.1.73\n\n### Français\nAncien\n### English\nPrevious\n\n## Archives antérieures à 0.1.73\nHistorique intégral\n'
        text = prepend(historical, '0.1.74', 'Ajout\nDeuxième ligne', 'Change')
        self.assertIn(historical[historical.index('## Version'):], text)
        self.assertIn('Deuxième ligne', section(text, '0.1.74'))
        self.assertNotIn('Ancien', section(text, '0.1.74'))
        self.assertNotIn('Historique intégral', section(text, '0.1.73'))
        with self.assertRaises(ValueError):
            prepend(text, '0.1.74', 'Ajout', 'Change')
        with self.assertRaises(ValueError):
            prepend(text, '0.1.75', 'Ajout', '')

    def test_packaging_rejects_split_journals_and_unproved_final_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('app/structure.json', 'app/COMPOSANTS.json', 'app/atelier/version.py', 'tools/launcher.rc',
                         'LICENSE', 'licences/BrickLabo/LICENSE', 'licences/RESOURCE_RIGHTS.json',
                         'documentation/GUIDE_DEMARRAGE.html', 'documentation/GUIDE_DEMARRAGE.en.html', 'documentation/NOUVEAUTES.txt'):
                dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
            self.assertEqual(check(root)['journal'], 'documentation/NOUVEAUTES.txt')
            split = root / 'documentation/CONTROLE_v0.1.74.txt'
            split.write_text('new duplicate', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Journal séparé'):
                check(root)
            split.unlink()
            with self.assertRaisesRegex(ValueError, 'Preuves'):
                check(root, for_final=True)
            evidence = root / 'evidence.json'
            evidence.write_text(json.dumps({'version':'0.1.73','checks':{}}))
            with self.assertRaisesRegex(ValueError, 'full_suite_windows'):
                check(root, for_final=True, evidence=evidence)


if __name__ == '__main__':
    unittest.main()
