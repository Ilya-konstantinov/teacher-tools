import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from paperforge.cli import main as generate
from paperforge.config import load_settings
from paperforge.documents import compile_pdf, main as print_document, render_document
from paperforge.io import read_questions


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'questions.json'
        self.output = self.root / 'result.json'
        self.bank = [{'id': str(i), 'text': f'Вопрос {i}', 'answers': f'Ответ {i} & текст'} for i in range(4)]
        self.save_bank()

    def save_bank(self):
        self.source.write_text(json.dumps(self.bank), encoding='utf-8')

    def run_generation(self, *extra, pipeline=False):
        with contextlib.redirect_stdout(io.StringIO()):
            generate(['--questions', str(self.source), '-n', '2', '--tickets', '3',
                      '--output', str(self.output), *extra], pipeline=pipeline)

    def test_omitted_weights_and_inferred_target(self):
        self.run_generation()
        data = json.loads(self.output.read_text())
        self.assertEqual(data['target_weight'], 2)
        self.assertEqual(data['max_weight_deviation'], 0)
        self.assertTrue(all(q['weight'] == 1 for t in data['tickets'] for q in t['questions']))
        self.assertEqual(len({tuple(q['id'] for q in t['questions']) for t in data['tickets']}), 3)

    def test_inline_answers_from_original_bank(self):
        output = self.root / 'answers.tex'
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.source), '--no-pdf', '-o', str(output)], answers=True)
        document = output.read_text()
        for question in self.bank:
            self.assertIn(question['text'], document)
            self.assertIn(question['answers'].replace('&', r'\&'), document)
        self.run_generation('--answers', '--no-pdf', pipeline=True)
        data = json.loads(self.output.read_text())
        for ticket in data['tickets']:
            for question in ticket['questions']:
                self.assertIn('answers', question)
                self.assertNotIn('answer', question)

    def test_optional_ids_through_pipeline_and_original_bank_answers(self):
        for question in self.bank:
            question.pop('id')
        text = self.root / 'question.txt'
        text.write_text(self.bank[0].pop('text'), encoding='utf-8')
        self.bank[0]['text_file'] = text.name
        self.save_bank()
        original = self.source.read_text()
        questions = read_questions(self.source)
        self.assertEqual([q.id for q in questions], ['q1', 'q2', 'q3', 'q4'])
        self.assertEqual(questions, read_questions(self.source))
        self.run_generation('--answers', '--no-pdf', pipeline=True)
        data = json.loads(self.output.read_text())
        expected = {q.id: (q.text, q.answer) for q in questions}
        for ticket in data['tickets']:
            for question in ticket['questions']:
                self.assertEqual((question['text'], question['answers']), expected[question['id']])
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.source), '--no-pdf'], answers=True)
        self.assertEqual(self.source.read_text(), original)

    def test_optional_ids_do_not_conflict_with_explicit_ids(self):
        self.bank[0].pop('id')
        self.bank[1]['id'] = 'q1'
        self.bank[2]['id'] = 'q1_2'
        self.save_bank()
        self.assertEqual([q.id for q in read_questions(self.source)], ['q1_3', 'q1', 'q1_2', '3'])
        for invalid in ('', None, 123, 'q1'):
            self.bank[0]['id'] = invalid
            self.save_bank()
            with self.subTest(id=invalid), self.assertRaises(ValueError):
                read_questions(self.source)

    def test_legacy_answer_and_conflicting_fields(self):
        self.bank[0]['answer'] = self.bank[0].pop('answers')
        self.save_bank()
        self.run_generation('--answers', '--no-pdf', pipeline=True)
        self.bank[0]['answers'] = 'Conflicting answer'
        self.save_bank()
        with self.assertRaisesRegex(ValueError, 'противоречат'):
            read_questions(self.source)

    def test_partial_invalid_weights_and_nonuniform_target(self):
        self.bank[0]['weight'] = 2
        self.save_bank()
        with self.assertRaisesRegex(ValueError, 'всех вопросов'):
            read_questions(self.source)
        for weight in (None, 0, True, float('nan')):
            for q in self.bank:
                q['weight'] = weight
            self.save_bank()
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                read_questions(self.source)
        for i, q in enumerate(self.bank):
            q['weight'] = i + 1
        self.save_bank()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_generation()
        self.assertFalse(self.output.exists())
        self.run_generation('--target-weight', '5')

    def test_text_files_resolved_relative_to_bank_and_snapshotted(self):
        folder = self.root / 'texts'
        folder.mkdir()
        text = folder / 'question.txt'
        text.write_text('\ufeffУсловие\na. Первый\nпродолжение\nb. Второй', encoding='utf-8')
        self.bank = [{'id': 'q', 'text_file': 'texts/question.txt', 'answers': {'correct': ['a']}},
                     {'id': 'other', 'text_file': str(text), 'group': 'topic'}]
        self.save_bank()
        questions = read_questions(self.source)
        self.assertEqual([q.id for q in questions], ['q', 'other'])
        self.assertEqual(questions[0].text, 'Условие')
        self.assertEqual(questions[0].options, (('a', 'Первый\nпродолжение'), ('b', 'Второй')))
        with contextlib.redirect_stdout(io.StringIO()):
            generate(['--questions', str(self.source), '-n', '1', '--tickets', '2', '--output', str(self.output)])
        text.unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.output)])
        tex = self.output.with_suffix('.tex').read_text()
        self.assertIn('Условие', tex)
        self.assertIn('Первый', tex)
        self.assertNotIn('question.txt', tex)

    def test_text_file_errors(self):
        for entry in ({'text_file': 'missing.txt'}, {'text_file': ''}, {'text_file': None},
                      {'text_file': 'a.txt', 'text': 'ambiguous'}):
            self.source.write_text(json.dumps([{'id': 'q', **entry}]))
            with self.subTest(entry=entry), self.assertRaises((ValueError, OSError)):
                read_questions(self.source)

    def test_text_file_cannot_be_overwritten(self):
        text = self.root / 'question.tex'
        text.write_text('Keep original')
        self.bank = [{'id': str(i), 'text_file': str(text)} for i in range(4)]
        self.save_bank()
        self.output = text
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_generation()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            print_document([str(self.source), '-o', str(text)])
        self.assertEqual(text.read_text(), 'Keep original')

    def test_directory_natural_order_and_multiline_options(self):
        directory = self.root / 'bank'
        directory.mkdir()
        for name in ('10.txt', '2.txt', '1.txt'):
            (directory / name).write_text('Вопрос\na. Один\nпродолжение\nb. Два\n')
        questions = read_questions(directory)
        self.assertEqual([q.id for q in questions], ['1.txt', '2.txt', '10.txt'])
        self.assertEqual(questions[0].options[0], ('a', 'Один\nпродолжение'))
        self.assertEqual([q.weight for q in questions], [1, 1, 1])

    def test_pipeline_and_standalone_answers_same_order(self):
        self.run_generation('--no-pdf', '--answers', pipeline=True)
        data = json.loads(self.output.read_text())
        student = self.output.with_suffix('.tex').read_text()
        answers = self.output.with_name('result_answers.tex').read_text()
        self.assertNotIn('Ответ 0', student)
        previous = -1
        for ticket in data['tickets']:
            previous = answers.index('Билет № ' + str(ticket['ticket']), previous + 1)
            for question in ticket['questions']:
                previous = answers.index(question['text'], previous + 1)
                previous = answers.index(question['answers'].replace('&', r'\&'), previous + 1)
        independent = self.root / 'standalone.tex'
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.output), '--no-pdf', '-o', str(independent)], answers=True)
        self.assertEqual(answers, independent.read_text())

    def test_separate_key_requires_all_selected_answers(self):
        key = self.root / 'key.json'
        key.write_text(json.dumps({'0': 'secret'}))
        self.output.write_text('keep')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_generation('--no-pdf', '--answers-key', str(key), pipeline=True)
        self.assertEqual(self.output.read_text(), 'keep')
        key.write_text(json.dumps({**{q['id']: q['answers'] for q in self.bank}, 'unused': 'fine'}))
        self.run_generation('--no-pdf', '--answers-key', str(key), pipeline=True)
        self.assertTrue(self.root.joinpath('result_answers.tex').exists())

    def test_choice_answer_validation(self):
        data = {'tickets': [{'ticket': 1, 'questions': [
            {'id': 'q', 'text': 'Question', 'options': [['a', 'A']], 'answers': {'correct': []}}]}]}
        tex = render_document(data, settings=load_settings(), answers=True)
        self.assertIn('Пустой набор', tex)
        for correct in (['z'], ['a', 'a'], 'a', None):
            data['tickets'][0]['questions'][0]['answers'] = {'correct': correct}
            with self.subTest(correct=correct), self.assertRaises(ValueError):
                render_document(data, settings=load_settings(), answers=True)

    def test_custom_functions_are_independent(self):
        plugin = self.root / 'plugin.py'
        plugin.write_text('''from dataclasses import dataclass
@dataclass
class Marker:
    value: str

def student(data, *, settings, **options):
    return "STUDENT:" + str([t['ticket'] for t in data['tickets']])

def teacher(data, *, settings, **options):
    return "TEACHER:" + str([q['answers'] for t in data['tickets'] for q in t['questions']])
''')
        self.run_generation('--no-pdf', '--print-generator', str(plugin) + ':student',
                            '--answers-generator', str(plugin) + ':teacher', pipeline=True)
        self.assertEqual(self.output.with_suffix('.tex').read_text(), 'STUDENT:[1, 2, 3]')
        self.assertTrue(self.root.joinpath('result_answers.tex').read_text().startswith('TEACHER:'))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_generation('--no-pdf', '--print-generator', str(plugin) + ':missing', pipeline=True)

    def test_cpplyc_adapter_restarts_numbering_and_subsets_key(self):
        plugin = self.root / 'legacy.py'
        plugin.write_text('''from dataclasses import dataclass
from pathlib import Path
@dataclass
class Question:
    source: Path
    text: str
    options: list

def render(questions, template, stamp, per_column):
    return template.replace('BODY', stamp + str([(i, q.text) for i, q in enumerate(questions, 1)]))

def render_answers(questions, template, stamp, key):
    assert set(key) == {q.source.name for q in questions}
    return render(questions, template, stamp, 3)
''')
        for name in ('template.tex', 'answers-template.tex'):
            (self.root / name).write_text(r'\begin{document}BODY\end{document}')
        self.run_generation('--no-pdf', '--print-generator', str(plugin),
                            '--answers-generator', str(plugin), pipeline=True)
        tex = self.output.with_suffix('.tex').read_text()
        self.assertEqual(tex.count(r'\begin{document}'), 1)
        self.assertEqual(tex.count(r'\clearpage'), 2)
        self.assertEqual(tex.count('(1,'), 3)
        for number in range(1, 4):
            self.assertIn(f'Билет № {number}', tex)

    def test_output_collisions_preserve_files(self):
        for extra in (['--print-output', str(self.output)],
                      ['--print-output', str(self.source)],
                      ['--answers', '--answers-output', str(self.output.with_suffix('.tex'))]):
            self.output.write_text('keep')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_generation('--no-pdf', *extra, pipeline=True)
            self.assertEqual(self.output.read_text(), 'keep')

    def test_pdf_compiler_error_reports_failure(self):
        tex = self.root / 'doc.tex'
        tex.write_text('bad')
        with patch('paperforge.documents.shutil.which', return_value=None), self.assertRaisesRegex(ValueError, 'не найден'):
            compile_pdf(tex)
        failed = subprocess.CompletedProcess([], 1, 'error from engine')
        with patch('paperforge.documents.shutil.which', return_value='/fake/xelatex'), \
                patch('paperforge.documents.subprocess.run', return_value=failed) as call:
            with self.assertRaisesRegex(ValueError, 'error from engine'):
                compile_pdf(tex)
            self.assertIn('-no-shell-escape', call.call_args.args[0])

    def test_unified_cli_from_another_directory(self):
        result = subprocess.run([sys.executable, '-m', 'paperforge', 'run', '--questions', str(self.source),
                                 '-n', '2', '--tickets', '3', '--output', str(self.output),
                                 '--answers', '--no-pdf'], cwd='/', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.root.joinpath('result_answers.tex').exists())
