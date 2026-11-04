import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from src.print_tickets import export_tex, tex_escape


class PrintingTests(unittest.TestCase):
    def setUp(self):
        self.data = {'optimization': {'method': 'any'}, 'tickets': [
            {'ticket': i, 'total_weight': 999, 'weight_deviation': 999,
             'questions': [{'id': 'secret_id', 'text': 'Кольца σ и δ; β(Rⁿ).', 'weight': 999},
                           {'text': 'Теорема Дынкина.', 'weight': 999}]}
            for i in range(1, 6)]}

    def test_plain_text_escaping_and_math(self):
        self.assertEqual(tex_escape('\\&%$#_{}~^'),
                         r'\textbackslash{}\&\%\$\#\_\{\}\textasciitilde{}\textasciicircum{}')
        self.assertEqual(tex_escape('σ δ β Rⁿ'),
                         r'\ensuremath{\sigma} \ensuremath{\delta} \ensuremath{\beta} R\ensuremath{^{n}}')
        self.assertEqual(tex_escape('x\ny\tz'), 'x y z')

    def test_pagination_and_private_fields(self):
        original = copy.deepcopy(self.data)
        document = export_tex(self.data, tickets_per_page=2)
        self.assertEqual(document.count(r'\newpage'), 2)
        self.assertEqual(document.count(r'\Ticket{'), 5)
        for private in ('999', 'secret_id', 'optimization', 'weight'):
            self.assertNotIn(private, document)
        self.assertEqual(original, self.data)
        self.assertIn(r'\CutLine', document)
        self.assertIn('a4paper', document)

    def test_configuration_and_label_escaping(self):
        document = export_tex(self.data, margin_mm=15, font_size=11, title='A&B')
        self.assertIn('margin=15mm', document)
        self.assertIn(r'\fontsize{11}{13.2}', document)
        self.assertIn(r'A\&B', document)

    def test_arbitrary_question_count(self):
        for count in (1, 3):
            with self.subTest(count=count):
                questions = [{'text': f'Вопрос {i} & σ', 'weight': 999}
                             for i in range(1, count + 1)]
                document = export_tex({'tickets': [{'ticket': 1, 'questions': questions}]})
                for i, question in enumerate(questions, 1):
                    self.assertIn(str(i) + r'.\enspace ' + tex_escape(question['text']), document)
                self.assertEqual(document.count(r'\vskip2mm'), count - 1)
                self.assertNotIn(str(count + 1) + r'.\enspace', document)
                self.assertNotIn('999', document)

    def test_invalid_input(self):
        for data in ({}, {'tickets': []}, {'tickets': [None]},
                     {'tickets': [{'ticket': 1, 'questions': []}]},
                     {'tickets': [{'ticket': '1', 'questions': []}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                export_tex(data)
        for kwargs in ({'tickets_per_page': 0}, {'tickets_per_page': True},
                       {'margin_mm': float('nan')}, {'font_size': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                export_tex(self.data, **kwargs)

    def test_print_command_through_main(self):
        entry = Path(__file__).resolve().parents[1] / 'main.py'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'tickets.json'
            output = Path(directory) / 'printed.tex'
            source.write_text(json.dumps(self.data), encoding='utf-8')
            result = subprocess.run([sys.executable, str(entry), 'print', str(source),
                                     '-o', str(output), '--tickets-per-page', '2'],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), export_tex(self.data, tickets_per_page=2))

    def test_real_bank_export(self):
        from src.generation import generate_tickets
        from src.table_io import read_questions

        questions = read_questions(Path(__file__).resolve().parents[1] / 'examples' / 'questions_ma2.json')
        tickets = generate_tickets(questions, 2, 100, 'different', target_weight=6)
        data = {'tickets': [{'ticket': i, 'questions': [{'text': q.text} for q in t.questions]}
                            for i, t in enumerate(tickets, 1)]}
        document = export_tex(data)
        self.assertEqual(document.count(r'\Ticket{'), len(data['tickets']))
        self.assertEqual(document.count(r'\newpage'), (len(data['tickets']) - 1) // 4)
        for t in data['tickets']:
            for q in t['questions']:
                self.assertIn(tex_escape(q['text']), document)


if __name__ == '__main__':
    unittest.main()
