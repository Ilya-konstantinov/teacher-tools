"""Load external Python renderers and adapt CppLyc generators."""
from datetime import date
import importlib.util
from pathlib import Path
import sys
import uuid


def parse_generator(spec):
    filename, separator, function = str(spec).rpartition(':')
    if separator and function.isidentifier():
        return Path(filename).expanduser(), function
    return Path(spec).expanduser(), None


def generator_sources(spec):
    if not spec:
        return ()
    path, _ = parse_generator(spec)
    return path, path.with_name('template.tex'), path.with_name('answers-template.tex')


def load_generator(spec, answers=False):
    path, function = parse_generator(spec)
    path = path.resolve()
    name = '_ticket_generator_' + uuid.uuid4().hex
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f'Невозможно загрузить генератор {path}')
    module = importlib.util.module_from_spec(module_spec)
    # Dataclasses resolve annotations through sys.modules during import.
    sys.modules[name] = module
    try:
        module_spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    explicit_function = function is not None
    function = function or ('export_document' if callable(getattr(module, 'export_document', None))
                                           else ('export_answers_tex' if answers else 'export_tex'))
    renderer = getattr(module, function, None)
    if callable(renderer):
        return renderer
    if not explicit_function and all(callable(getattr(module, member, None)) for member in
                             ('Question', 'render_answers' if answers else 'render')):
        return lambda data, **options: render_cpplyc(module, data, answers=answers, **options)
    raise ValueError(f'{path}: не найдена функция {function}')


def render_cpplyc(module, data, *, answers=False, settings=None, **options):
    """Preserve paper contents and order, starting each paper on a new page."""
    template_path = options.get('template') or Path(module.__file__).with_name(
        'answers-template.tex' if answers else 'template.tex')
    template = Path(template_path).expanduser().read_text(encoding='utf-8')
    stamp = options.get('date') or date.today().strftime('%d.%m.%Y')
    bodies, prefix, suffix = [], None, None
    for ticket in data['tickets']:
        ticket_stamp = stamp + ' · Билет № ' + str(ticket['ticket'])
        questions = [module.Question(Path(q['id']), q['text'], list(map(tuple, q.get('options', []))))
                     for q in ticket['questions']]
        if answers:
            key = {q.source.name: original['answers'] for q, original in zip(questions, ticket['questions'])}
            document = module.render_answers(questions, template, ticket_stamp, key)
        else:
            document = module.render(questions, template, ticket_stamp, options.get('per_column', 3))
        head, begin, rest = document.partition(r'\begin{document}')
        body, end, tail = rest.rpartition(r'\end{document}')
        if not begin or not end:
            raise ValueError('Генератор CppLyc должен возвращать полный LaTeX-документ')
        if prefix is None:
            prefix, suffix = head + begin, end + tail
        # TeX groups allow each paper to reuse local template definitions.
        bodies.append('\n\\begingroup\n' + body + '\n\\endgroup\n')
    return prefix + '\n\\clearpage\n'.join(bodies) + suffix
