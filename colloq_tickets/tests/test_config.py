import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.cli import main as generate
from src.config import load_settings
from src.models import Question
from src.planning import plan_tickets
from src.printing import main as print_tickets, tex_escape
from src.reconstruction import restore_tickets


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
        settings = self.configure({'printing': {'title': 'Другой курс'}, 'search': {'random_seed': 42}})
        base = load_settings()
        self.assertEqual(settings.generation, base.generation)
        self.assertEqual(settings.printing.font, base.printing.font)
        self.assertEqual(settings.printing.title, 'Другой курс')
        for data in ([], {'unknown': {}}, {'search': []}, {'generation': {'typo': 1}},
                     {'generation': {'max_dp_states': True}}, {'generation': {'time_limit': 0}},
                     {'generation': {'time_limit': float('nan')}}, {'generation': {'algorithm': 'bad'}},
                     {'search': {'random_seed': -1}}, {'search': {'cp_sat_workers': 0}},
                     {'search': {'dp_work_multiplier': 0}}, {'printing': {'margin_mm': True}},
                     {'printing': {'tickets_per_page': 9}}, {'printing': {'font': ''}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.configure(data)

    def test_cli_overrides_config_and_printing_preserves_labels(self):
        source, output = self.directory / 'questions.json', self.directory / 'tickets.json'
        source.write_text(json.dumps([{'id': str(i), 'text': str(i), 'weight': i + 1}
                                      for i in range(5)]))
        label = 'FONT TITLE $SIZE & курс'
        self.configure({'generation': {'algorithm': 'cp-sat', 'allow_feasible': True,
                                       'output': str(output)},
                        'printing': {'title': label, 'tickets_per_page': 1, 'font_size': 11}})
        from src.planning import generate_tickets_report
        with patch('src.planning.generate_tickets_report', wraps=generate_tickets_report) as call:
            with contextlib.redirect_stdout(io.StringIO()):
                generate(['--config', str(self.config), '--questions', str(source), '-n', '2',
                          '--tickets', '3', '--target-weight', '6', '--algorithm', 'sum-dp',
                          '--no-allow-feasible'])
            self.assertFalse(call.call_args.kwargs['allow_feasible'])
        self.assertEqual(json.loads(output.read_text())['optimization']['algorithm'], 'profile-sum-dp')
        with contextlib.redirect_stdout(io.StringIO()):
            print_tickets([str(output), '--config', str(self.config), '--tickets-per-page', '2'])
        document = output.with_suffix('.tex').read_text()
        self.assertEqual(document.count(r'\newpage'), 1)
        self.assertIn(tex_escape(label), document)
        self.assertIn(r'\fontsize{11}{13.2}', document)

    def test_bad_config_does_not_overwrite_output(self):
        output = self.directory / 'tickets.json'
        output.write_text('keep')
        self.config.write_text('{"generation": {"max_dp_states": false}}')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            generate(['--config', str(self.config), '--questions', 'missing.json', '-n', '2',
                      '--tickets', '3', '--target-weight', '6', '--output', str(output)])
        self.assertEqual(output.read_text(), 'keep')

    def test_search_budget_switches_algorithm_without_changing_optimum(self):
        questions = [Question(f'{g}_{i}', str(i), i + 1, str(g))
                     for g in range(8) for i in range(3)]
        strict = self.configure({'generation': {'max_dp_states': 100},
                                 'search': {'dp_work_multiplier': 1, 'random_seed': 17}})
        relaxed = self.configure({'generation': {'max_dp_states': 100},
                                  'search': {'dp_work_multiplier': 10, 'random_seed': 17}})
        a = plan_tickets(questions, 3, 5, 'different', target_weight=6, settings=strict)
        b = plan_tickets(questions, 3, 5, 'different', target_weight=6, settings=relaxed)
        self.assertEqual(a.selection.algorithm, 'weight-types')
        self.assertEqual(b.selection.algorithm, 'profile-sum-dp')
        self.assertEqual(b.selection.sum_plan.random_seed, 17)
        self.assertEqual(restore_tickets(b), restore_tickets(b))
        for plan in (a, b):
            self.assertTrue(plan.selection.optimal)
            self.assertEqual([t.total_weight for t in restore_tickets(plan).tickets], [6] * 5)

    def test_cp_sat_receives_search_settings(self):
        from ortools.sat.python import cp_model
        settings = self.configure({'search': {'cp_sat_workers': 2, 'random_seed': 19}})
        questions = [Question(str(i), str(i), i + 1) for i in range(5)]
        solver = cp_model.CpSolver()
        for algorithm in ('cp-sat', 'cp-sat-types'):
            with self.subTest(algorithm=algorithm), patch.object(cp_model, 'CpSolver', return_value=solver):
                plan = plan_tickets(questions, 2, 3, target_weight=6, algorithm=algorithm, settings=settings)
                self.assertTrue(plan.selection.optimal)
                self.assertEqual(solver.parameters.num_search_workers, 2)
                self.assertEqual(solver.parameters.random_seed, 19)
