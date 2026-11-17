#!/usr/bin/env python3
"""Exercise native executables from a directory without their source/config files."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist-dir', type=Path, default=Path('dist'))
    args = parser.parse_args()
    suffix = '.exe' if os.name == 'nt' else ''
    paperforge = (args.dist_dir / ('paperforge' + suffix)).resolve()
    slotplan = (args.dist_dir / ('slotplan' + suffix)).resolve()
    with tempfile.TemporaryDirectory(prefix='teacher-tools-smoke-') as temporary:
        directory = Path(temporary)

        def run(executable, *arguments):
            result = subprocess.run([str(executable), *map(str, arguments)], cwd=directory,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode:
                raise RuntimeError(f'{executable.name} failed:\n{result.stdout}\n{result.stderr}')
            return result.stdout

        bank = directory / 'bank.json'
        bank.write_text(json.dumps([{'text': f'Question {i}', 'weight': i + 1,
                                     'answers': f'Answer {i}'} for i in range(5)]))
        run(paperforge, '--help')
        for algorithm in ('sum-dp', 'cp-sat', 'cp-sat-types'):
            output = directory / (algorithm + '.json')
            run(paperforge, 'generate', '--questions', bank, '-n', 2, '--tickets', 3,
                '--target-weight', 6, '--algorithm', algorithm, '--output', output)
            data = json.loads(output.read_text())
            assert len(data['tickets']) == 3 and data['optimization']['optimal'], data
        source = directory / 'sum-dp.json'
        run(paperforge, 'print', source, '--format', 'typst')
        assert source.with_suffix('.typ').read_text().startswith('#let document =')
        run(paperforge, 'answers', source, '--format', 'typst', '--no-pdf')
        assert 'Answer' in (directory / 'sum-dp_answers.typ').read_text()
        run(paperforge, 'print', source)
        assert '\\begin{document}' in source.with_suffix('.tex').read_text()
        plugin = directory / 'plugin.py'
        plugin.write_text('def export_document(data, *, settings, **options):\n'
                          '    return "PLUGIN:" + data["mode"]\n')
        run(paperforge, 'print', source, '--format', 'html', '--generator', plugin)
        assert source.with_suffix('.html').read_text() == 'PLUGIN:tickets'
        config = directory / 'custom.json'
        config.write_text(json.dumps({'printing': {'title': 'CUSTOM TITLE'}}))
        run(paperforge, 'print', source, '--config', config)
        assert 'CUSTOM TITLE' in source.with_suffix('.tex').read_text()

        examiners, students = directory / 'examiners.tsv', directory / 'students.tsv'
        examiners.write_text('ФИО\tВремя\nExaminer\t9,10\n', encoding='utf-8')
        students.write_text('ФИО\tГруппа\tПриоритет 1\tПриоритет 2\tПриоритет 3\tВ какое время вы точно не сможете\n'
                            'Student\t1\t9\t\t\t\n', encoding='utf-8')
        schedule = directory / 'schedule.tsv'
        run(slotplan, 'schedule', '--examiners', examiners, '--students', students, '--output', schedule)
        with schedule.open(encoding='utf-8-sig') as stream:
            assert next(csv.DictReader(stream, delimiter='\t'))['Время прихода']
        workload = directory / 'workload.tsv'
        run(slotplan, 'workload', '--examiners', examiners, '--schedule', schedule, '--output', workload)
        assert workload.exists() and workload.with_suffix('.html').exists()
    print('Binary smoke checks passed: Paperforge (including CP-SAT) and Slotplan.')


if __name__ == '__main__':
    main()
