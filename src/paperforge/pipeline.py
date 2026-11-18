"""Подготовка всех документов до записи результатов пайплайна."""
from pathlib import Path

from .answers import read_key
from .generators import generator_sources
from .documents import check_outputs, render_document, render_options


def prepare_exports(args, settings, data, *, source_paths=()):
    output = args.print_output or args.output.with_suffix('.' + args.format)
    want_answers = args.answers or args.answers_key or args.answers_output or args.answers_generator or args.answers_renderer_command
    answers_output = args.answers_output or args.output.with_name(args.output.stem + '_answers.' + args.format)
    sources = [args.questions, args.answers_key, args.template, args.answers_template, args.config]
    sources.extend(source_paths)
    for generator in (args.print_generator, args.answers_generator):
        sources.extend(generator_sources(generator))
    if args.questions.is_dir():
        sources.extend(args.questions.glob('*.txt'))
    if args.output.resolve() in {Path(p).expanduser().resolve() for p in sources
                               if p is not None}:
        raise ValueError('JSON результата не должен совпадать с исходными файлами')
    sources.append(args.output)
    check_outputs([output, answers_output] if want_answers else [output], sources, pdf=args.pdf, format=args.format)
    options = render_options(args)
    documents = [(output, render_document(data, settings=settings, generator=args.print_generator, renderer_command=args.print_renderer_command, **options))]
    if want_answers:
        key = read_key(args.answers_key) if args.answers_key else None
        options['template'] = args.answers_template
        documents.append((answers_output, render_document(data, settings=settings,
                          generator=args.answers_generator, renderer_command=args.answers_renderer_command, answers=True, key=key, **options)))
    return documents
