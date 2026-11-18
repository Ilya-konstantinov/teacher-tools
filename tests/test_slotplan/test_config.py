import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from slotplan.cli import main as schedule
from slotplan.config import load_settings
from slotplan.workload import main as workload


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.config = self.directory / 'custom.json'

    def configure(self, data):
        self.config.write_text(json.dumps(data), encoding='utf-8')
        return load_settings(self.config)

    def test_partial_overrides_and_validation(self):
        settings = self.configure({'schedule': {'prep_minutes': 20}})
        self.assertEqual(settings.schedule.prep_minutes, 20)
        self.assertEqual(settings.workload, load_settings().workload)
        for data in ([], {'unknown': {}}, {'schedule': []}, {'workload': {'typo': 1}},
                     {'schedule': {'prep_minutes': True}}, {'schedule': {'prep_minutes': -1}},
                     {'schedule': {'minutes_per_student': 0}}, {'schedule': {'minutes_per_student': 61}},
                     {'workload': {'warning_ratio': float('inf')}}, {'workload': {'warning_ratio': 1.1}},
                     {'workload': {'normal_color': 'red'}}, {'workload': {'output': ''}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.configure(data)

    def test_schedule_and_report_share_timing_and_cli_can_override(self):
        examiners, students = self.directory / 'examiners.tsv', self.directory / 'students.tsv'
        output, report = self.directory / 'schedule.tsv', self.directory / 'workload.tsv'
        examiners.write_text('ФИО\tВремя\nПринимающий\t9\n', encoding='utf-8')
        students.write_text('ФИО\tГруппа\tПриоритет 1\tПриоритет 2\tПриоритет 3\tВ какое время вы точно не сможете\n'
                            'Студент\t1\t9\t9\t9\t\n', encoding='utf-8')
        self.configure({'schedule': {'prep_minutes': 10, 'minutes_per_student': 20, 'output': str(output)},
                        'workload': {'output': str(report), 'warning_color': '#123abc'}})
        with contextlib.redirect_stdout(io.StringIO()):
            schedule(['--config', str(self.config), '--examiners', str(examiners), '--students', str(students)])
            workload(['--config', str(self.config), '--examiners', str(examiners), '--schedule', str(output)])
        with report.open(encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        busy = [row for row in rows if row['Одновременно проверок'] == '1']
        self.assertEqual([(row['С'], row['До']) for row in busy], [('09:10', '09:30')])
        self.assertIn('#123abc', report.with_suffix('.html').read_text())
        # CLI overrides the config: 50 minutes of preparation + 20 minutes of
        # examination cannot fit this examiner's single hour of availability.
        with contextlib.redirect_stdout(io.StringIO()):
            schedule(['--config', str(self.config), '--examiners', str(examiners),
                      '--students', str(students), '--prep-minutes', '50'])
        with output.open(encoding='utf-8-sig') as stream:
            self.assertEqual(next(csv.DictReader(stream, delimiter='\t'))['Время прихода'], '')

    def test_default_config_is_found_outside_project_directory(self):
        root = Path(__file__).resolve().parents[2] / 'examples' / 'slotplan'
        output = self.directory / 'schedule.tsv'
        result = subprocess.run([sys.executable, '-m', 'slotplan', 'schedule',
                                 '--examiners', str(root / 'examiners.tsv'),
                                 '--students', str(root / 'students.tsv'), '--output', str(output)],
                                cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.exists())

    def test_invalid_config_preserves_existing_output(self):
        output = self.directory / 'schedule.tsv'
        output.write_text('keep')
        self.config.write_text('{"schedule": {"prep_minutes": -1}}')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            schedule(['--config', str(self.config), '--examiners', 'missing.tsv',
                      '--students', 'missing.tsv', '--output', str(output)])
        self.assertEqual(output.read_text(), 'keep')
