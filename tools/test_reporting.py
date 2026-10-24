"""Machine-readable unittest evidence, without changing Qt lifetime handling."""
import json
from pathlib import Path
import platform
from time import perf_counter
import unittest
import xml.etree.ElementTree as ET


class ReportResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []
        self.started = perf_counter()

    def startTest(self, test):
        super().startTest(test)
        self.current = {'id': test.id(), 'status': 'passed', 'details': ''}
        self.case_started = perf_counter()

    def stopTest(self, test):
        self.current['seconds'] = perf_counter() - self.case_started
        self.cases.append(self.current)
        super().stopTest(test)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.current.update(status='failed', details=self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.current.update(status='error', details=self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.current.update(status='skipped', details=reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.current.update(status='expected_failure', details=self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.current.update(status='unexpected_success')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.current.update(status='failed', details=self.current['details'] + self._exc_info_to_string(err, test))

    def save(self, json_path, xml_path, shutdown_ok):
        from atelier.version import VERSION
        import PySide6
        data = dict(version=VERSION, system=platform.system(), python=platform.python_version(),
                    pyside=PySide6.__version__, tests=self.testsRun, failures=len(self.failures),
                    errors=len(self.errors), skipped=len(self.skipped),
                    seconds=perf_counter() - self.started,
                    success=bool(self.wasSuccessful() and shutdown_ok), qt_shutdown=shutdown_ok, cases=self.cases)
        if json_path:
            path = Path(json_path); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if xml_path:
            suite = ET.Element('testsuite', name='BrickLabo', tests=str(self.testsRun),
                               failures=str(len(self.failures)), errors=str(len(self.errors)),
                               skipped=str(len(self.skipped)), time=str(data['seconds']))
            for row in self.cases:
                case = ET.SubElement(suite, 'testcase', name=row['id'], time=str(row['seconds']))
                tag = {'failed': 'failure', 'error': 'error', 'skipped': 'skipped',
                       'expected_failure': 'skipped', 'unexpected_success': 'failure'}.get(row['status'])
                if tag:
                    ET.SubElement(case, tag).text = row['details'] or row['status']
            if not shutdown_ok:
                ET.SubElement(ET.SubElement(suite, 'testcase', name='Qt shutdown'), 'error').text = 'Tasks did not stop cleanly'
            path = Path(xml_path); path.parent.mkdir(parents=True, exist_ok=True)
            ET.ElementTree(suite).write(path, encoding='utf-8', xml_declaration=True)
        return data
