import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from paperforge.backends import command_arguments, output_format, subprocess_environment
from paperforge.cli import main as generate
from paperforge.config import load_settings
from paperforge.documents import compile_pdf, main as print_document, render_document


class BackendTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='paperforge test ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bank = self.root / 'bank.json'
        self.bank.write_text(json.dumps([
            {'text': 'Question #strong[not markup] \\ " &', 'answers': 'Answer #1'},
            {'text': 'Another question', 'answers': 'Answer #2'},
            {'text': 'Third question', 'answers': 'Answer #3'},
        ]))

    def test_typst_pipeline_and_inline_data(self):
        output = self.root / 'papers.json'
        with contextlib.redirect_stdout(io.StringIO()):
            generate(['--questions', str(self.bank), '-n', '2', '--tickets', '3',
                      '--output', str(output), '--answers', '--format', 'typst', '--no-pdf'], pipeline=True)
        for suffix, mode in (('.typ', 'tickets'), ('_answers.typ', 'answers')):
            source = output.with_suffix('.typ') if suffix == '.typ' else output.with_name('papers_answers.typ')
            line = source.read_text().splitlines()[0]
            encoded = line.removeprefix('#let document = json(bytes(').removesuffix('))')
            payload = json.loads(json.loads(encoded))
            self.assertEqual(payload['mode'], mode)
            self.assertEqual(payload['schema_version'], 1)
            self.assertEqual(len(payload['tickets']), 3)
            if mode == 'answers':
                self.assertIn('answer_text', payload['tickets'][0]['questions'][0])

    def test_custom_typst_template(self):
        template = self.root / 'custom.typ'
        template.write_text('#document.options.title\n')
        output = self.root / 'custom-output.typ'
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.bank), '--format', 'typ', '--template', str(template), '-o', str(output)])
        self.assertTrue(output.read_text().endswith(template.read_text()))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            print_document([str(self.bank), '--format', 'typ', '--template', str(template), '-o', str(template)])

    def test_external_renderer_contract_and_custom_extension(self):
        script = self.root / 'renderer.py'
        script.write_text('import json, sys\np = json.load(sys.stdin)\n'
                          'assert p["schema_version"] == 1\n'
                          'print("<p>" + p["mode"] + ":" + p["tickets"][0]["questions"][0]["answers"] + "</p>")\n')
        output = self.root / 'document.html'
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.bank), '--format', 'html', '--renderer-command',
                            json.dumps([sys.executable, str(script)]), '-o', str(output), '--no-pdf'], answers=True)
        self.assertEqual(output.read_text().strip(), '<p>answers:Answer #1</p>')

    def test_renderer_failure_and_empty_output_preserve_result(self):
        output = self.root / 'document.html'
        output.write_text('keep')
        for code in ('import sys; sys.exit(7)', ''):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                print_document([str(self.bank), '--format', 'html', '--renderer-command',
                                json.dumps([sys.executable, '-c', code]), '-o', str(output)])
            self.assertEqual(output.read_text(), 'keep')

    def test_generic_python_generator(self):
        plugin = self.root / 'plugin.py'
        plugin.write_text('def export_document(data, *, settings, **options):\n'
                          '    return "<h1>" + data["mode"] + "</h1>"\n')
        output = self.root / 'output.html'
        with contextlib.redirect_stdout(io.StringIO()):
            print_document([str(self.bank), '--format', 'html', '--generator', str(plugin), '-o', str(output)])
        self.assertEqual(output.read_text(), '<h1>tickets</h1>')

    def test_generic_compiler_argument_boundaries(self):
        script = self.root / 'compiler.py'
        script.write_text('import pathlib, sys\n'
                          'assert pathlib.Path(sys.argv[1]).read_text() == "SOURCE"\n'
                          'pathlib.Path(sys.argv[2]).write_bytes(b"%PDF-test")\n')
        source = self.root / 'source document.html'
        source.write_text('SOURCE')
        command = json.dumps([sys.executable, str(script), '{input}', '{output}'])
        self.assertEqual(compile_pdf(source, compiler_command=command).read_bytes(), b'%PDF-test')
        with self.assertRaisesRegex(ValueError, 'placeholders'):
            compile_pdf(source, compiler_command=json.dumps([sys.executable, str(script)]))

    def test_custom_compiler_cannot_reuse_stale_pdf(self):
        source = self.root / 'paper.html'
        source.write_text('SOURCE')
        output = source.with_suffix('.pdf')
        output.write_bytes(b'keep previous PDF')
        for code in ('pass', 'import sys; sys.exit(1)'):
            command = json.dumps([sys.executable, '-c', code, '{input}', '{output}'])
            with self.subTest(code=code), self.assertRaises(ValueError):
                compile_pdf(source, compiler_command=command)
            self.assertEqual(output.read_bytes(), b'keep previous PDF')

    def test_typst_compiler_command(self):
        source = self.root / 'paper.typ'
        source.write_text('Hello')
        source.with_suffix('.pdf').write_bytes(b'%PDF-test')
        with patch('paperforge.documents.shutil.which', return_value='/bin/typst'), \
                patch('paperforge.documents.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '')) as run:
            compile_pdf(source)
        self.assertEqual(run.call_args.args[0], ['/bin/typst', 'compile', 'paper.typ', 'paper.pdf'])
        with self.assertRaisesRegex(ValueError, 'match'):
            compile_pdf(source, engine='xelatex')

    def test_commands_and_formats_are_validated(self):
        for command in ('echo hi', '{}', '[]', '[2]', '[""]'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                command_arguments(command)
        for fmt in ('../x', 'pdf', '', 'a/b'):
            with self.subTest(fmt=fmt), self.assertRaises(ValueError):
                output_format(fmt)
        self.assertEqual(output_format('typst'), 'typ')

    def test_external_process_does_not_inherit_bundled_library_path(self):
        with patch.object(sys, 'frozen', True, create=True), \
                patch.dict('os.environ', {'LD_LIBRARY_PATH': '/bundle', 'LD_LIBRARY_PATH_ORIG': '/system'}):
            self.assertEqual(subprocess_environment()['LD_LIBRARY_PATH'], '/system')
