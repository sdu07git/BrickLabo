"""Restore internal Windows paths without rewriting external files or URLs."""
from pathlib import Path
from unittest.mock import patch
import unittest
from atelier.storage import _remap


class RestorePathTests(unittest.TestCase):
    def test_extended_drive_and_unc_spellings_preserve_descendants(self):
        target=Path('restored')
        cases=[('\\\\?\\C:\\Collection\\Donnees\\Exports','C:\\Collection\\Donnees'),
               ('C:\\Collection\\Donnees\\Exports','\\\\?\\C:\\Collection\\Donnees'),
               ('\\\\?\\UNC\\server\\share\\Donnees\\Exports','\\\\server\\share\\Donnees')]
        for value,old in cases:
            with self.subTest(value=value):self.assertEqual(_remap(value,old,target),str(target/'Exports'))

    def test_short_alias_matches_canonical_root_and_does_not_match_similar_names(self):
        target=Path('restored')
        old='C:/Users/Long Name/BrickLabo/Donnees'
        short='C:/Users/LONGNA~1/BrickLabo/Donnees'
        def canonical(value):
            return str(value).replace('LONGNA~1','Long Name').replace('\\','/')
        values={'image':short+'/images/part.png','external':'D:/Photos/part.png',
                'sibling':short+'-other/part.png','url':'https://example.org/'+short,
                'nested':[short,short+'/Exports']}
        with patch('atelier.storage._windows_restore_identity',side_effect=canonical) as resolve:
            result=_remap(values,old,target)
        self.assertEqual(result['image'],str(target/'images/part.png'))
        self.assertEqual(result['nested'],[str(target),str(target/'Exports')])
        for key in ('external','sibling','url'):self.assertEqual(result[key],values[key])
        self.assertFalse(any('https:' in str(call) or 'D:/Photos' in str(call) for call in resolve.call_args_list))


if __name__=='__main__':unittest.main()
