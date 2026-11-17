"""Общий путь JSON → выбранная функция печати → TeX → PDF."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .answers import answer_text, export_answers_tex, read_key, with_answers
from .backends import (compile_external, document_payload, output_format, render_external,
                       render_typst, subprocess_environment)
from .config import settings_for_cli, validate_printing
from .generators import load_generator
from .io import question_data, read_questions
from .printing import export_tex


def read_document(path, *, sources=None):
    path = Path(path).expanduser()
    if path.is_dir():
        data = [question_data(q) for q in read_questions(path, sources=sources)]
    else:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(data, list):
            data = [question_data(q) for q in read_questions(path, sources=sources)]
    if isinstance(data, list):
        data = {'tickets': [{'ticket': 1, 'questions': data}]}
    validate_document(data)
    return data


def validate_document(data):
    tickets = data.get('tickets') if isinstance(data, dict) else None
    if not isinstance(tickets, list) or not tickets:
        raise ValueError('Нужен непустой список tickets или вопросов')
    numbers = set()
    for ticket in tickets:
        if not isinstance(ticket, dict):
            raise ValueError('Билет должен быть объектом')
        number = ticket.get('ticket')
        if type(number) is not int or number < 1 or number in numbers:
            raise ValueError('Номера билетов должны быть различными положительными целыми')
        numbers.add(number)
        questions = ticket.get('questions')
        if not isinstance(questions, list) or not questions:
            raise ValueError(f'Билет {number}: нужен непустой список вопросов')
        for q in questions:
            if not isinstance(q, dict) or not isinstance(q.get('text'), str) or not q['text'].strip():
                raise ValueError(f'Билет {number}: нужен непустой текст вопроса')
            choices = q.get('options', [])
            if not isinstance(choices, list) or any(
                    not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(not isinstance(s, str) or not s.strip() for s in pair) for pair in choices):
                raise ValueError(f'Билет {number}: options — список пар [метка, текст]')


def add_render_arguments(parser, settings, *, pipeline=False, answers=False):
    defaults = settings.printing
    for name, kind in (('tickets_per_page', int), ('margin_mm', float), ('font_size', float),
                       ('title', str), ('institution', str), ('font', str)):
        parser.add_argument('--' + name.replace('_', '-'), type=kind, default=getattr(defaults, name))
    parser.add_argument('--pdf', action=argparse.BooleanOptionalAction, default=pipeline or answers,
                        help='Собрать PDF (run/answers: включено; print: выключено)')
    parser.add_argument('--format', type=output_format, default='tex',
                        help='Document source format: tex (default), typ/typst, or a custom extension')
    parser.add_argument('--engine', choices=('lualatex', 'xelatex', 'typst'),
                        help='PDF compiler; inferred from --format if omitted')
    parser.add_argument('--compiler-command', help='JSON argv with {input} and {output}; no shell')
    parser.add_argument('--template', type=Path, help='Шаблон внешнего генератора')
    parser.add_argument('--date', help='Дата для внешнего генератора')
    parser.add_argument('--per-column', type=int, choices=(1, 2, 3), default=3)
    if pipeline:
        parser.add_argument('--print-renderer-command', help='External renderer JSON argv; reads contract JSON on stdin')
        parser.add_argument('--answers-renderer-command', help='External answers renderer JSON argv')
        parser.add_argument('--print-generator', help='Python-файл[:функция] печати билетов')
        parser.add_argument('--answers-generator', help='Python-файл[:функция] печати ответов')
        parser.add_argument('--print-output', type=Path, help='Document source path (defaults to a sibling of the JSON)')
        parser.add_argument('--answers', action='store_true', help='Также собрать ответы')
        parser.add_argument('--answers-key', type=Path, help='JSON-ключ по id; включает сборку ответов')
        parser.add_argument('--answers-output', type=Path, help='Answers source path; enables answers')
        parser.add_argument('--answers-template', type=Path)
    else:
        parser.add_argument('--renderer-command', help='External renderer JSON argv; reads contract JSON on stdin')
        parser.add_argument('--generator', help='Python-файл[:функция] вместо стандартного генератора')
        if answers:
            parser.add_argument('--key', type=Path, help='JSON-ключ по id; иначе поле answers вопроса')


def render_options(args):
    return {name: getattr(args, name) for name in ('tickets_per_page', 'margin_mm', 'font_size',
            'title', 'institution', 'font', 'template', 'date', 'per_column', 'format')}


def render_document(data, *, settings, generator=None, renderer_command=None,
                    answers=False, key=None, **options):
    validate_document(data)
    validate_printing(replace(settings.printing, **{k: options[k] for k in vars(settings.printing)
                                                  if k in options}))
    if generator and renderer_command:
        raise ValueError('Choose either a Python generator or an external renderer command')
    if answers:
        data = with_answers(data, key)
        data = {**data, 'tickets': [{**t, 'questions': [
            {**q, 'answer_text': answer_text(q, q['answers'])} for q in t['questions']
        ]} for t in data['tickets']]}
    fmt = options.pop('format', 'tex')
    options = {**vars(settings.printing), **options}
    payload = document_payload(data, settings=settings, answers=answers, options=options)
    if renderer_command:
        document = render_external(renderer_command, payload)
    elif generator:
        document = load_generator(generator, answers)(payload, settings=settings, **options)
    elif fmt == 'typ':
        document = render_typst(payload, options.get('template'))
    elif fmt == 'tex':
        renderer = export_answers_tex if answers else export_tex
        document = renderer(data, settings=settings, **{k: options[k] for k in vars(settings.printing)})
    else:
        raise ValueError(f'Format {fmt!r} requires --generator or --renderer-command')
    if not isinstance(document, str) or not document.strip():
        raise ValueError('Renderer must return nonempty document source text')
    return document


def check_outputs(outputs, sources, *, pdf=False, format='tex'):
    protected = {Path(p).expanduser().resolve() for p in sources if p is not None}
    destinations = set()
    for path in outputs:
        path = Path(path).expanduser().resolve()
        if path.suffix.lower() != '.' + format:
            raise ValueError(f'Output source must have extension .{format}')
        generated = [path]
        if pdf:
            generated += [path.with_suffix(ext) for ext in ('.pdf', '.aux', '.log', '.out')]
        if any(p in protected or p in destinations for p in generated):
            raise ValueError('Выходные файлы должны различаться и не совпадать с исходными')
        destinations.update(generated)


def compile_pdf(path, engine=None, compiler_command=None):
    path = Path(path).resolve()
    output = path.with_suffix('.pdf')
    if compiler_command:
        return compile_external(path, compiler_command)
    else:
        engine = engine or {'.tex': 'xelatex', '.typ': 'typst'}.get(path.suffix.lower())
        if engine is None:
            raise ValueError('This format requires --compiler-command to produce PDF')
        if (engine == 'typst') != (path.suffix.lower() == '.typ'):
            raise ValueError('Compiler does not match the source format')
        executable = shutil.which(engine)
        if executable is None:
            raise ValueError(f'{engine} не найден; source saved to {path}')
        command = ([executable, 'compile', path.name, output.name] if engine == 'typst' else
                   [executable, '-interaction=nonstopmode', '-halt-on-error', '-no-shell-escape', path.name])
    result = subprocess.run(command, cwd=path.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', check=False,
                            env=subprocess_environment())
    if result.returncode:
        raise ValueError(f'Ошибка {engine}:\n' + '\n'.join(result.stdout.splitlines()[-30:]))
    if not output.is_file():
        raise ValueError(f'{engine} did not create {output}')
    warnings = [line for line in result.stdout.splitlines() if 'Overfull' in line or 'Missing character' in line]
    if warnings:
        print('Layout warnings:\n' + '\n'.join(warnings), file=sys.stderr)
    return output


def write_document(path, document, *, pdf=False, engine=None, compiler_command=None):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding='utf-8')
    print(path)
    if pdf:
        print(compile_pdf(path, engine, compiler_command))


def main(argv=None, *, answers=False):
    parser = argparse.ArgumentParser(description='Ответы: вопрос и ответ' if answers else 'Печать билетов')
    settings = settings_for_cli(parser, argv)
    parser.add_argument('input', type=Path, help='JSON билетов/банка или каталог *.txt')
    parser.add_argument('-o', '--output', type=Path)
    add_render_arguments(parser, settings, answers=answers)
    args = parser.parse_args(argv)
    source = args.input.expanduser()
    base = source / 'tickets.json' if source.is_dir() else source
    output = args.output or base.with_name(base.stem + ('_answers' if answers else '') + '.' + args.format)
    try:
        sources = [source, args.template, getattr(args, 'key', None), args.config]
        if args.generator:
            generator_path = Path(args.generator.split(':')[0]).expanduser()
            sources.extend([generator_path, generator_path.with_name('template.tex'),
                            generator_path.with_name('answers-template.tex')])
        data = read_document(source, sources=sources)
        check_outputs([output], sources, pdf=args.pdf, format=args.format)
        key = read_key(args.key) if answers and args.key else None
        document = render_document(data, settings=settings, generator=args.generator, renderer_command=args.renderer_command,
                                   answers=answers, key=key, **render_options(args))
        write_document(output, document, pdf=args.pdf, engine=args.engine, compiler_command=args.compiler_command)
    except (OSError, ValueError, OverflowError, ImportError, TypeError, AttributeError, KeyError) as exc:
        parser.exit(2, f'Ошибка: {exc}\n')
