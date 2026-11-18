"""Read answer keys and render question-and-answer documents."""
import json
from pathlib import Path

from .config import load_settings
from .io import question_answers
from .printing import tex_escape


def read_key(path):
    key = json.loads(Path(path).expanduser().read_text(encoding='utf-8-sig'))
    if not isinstance(key, dict):
        raise ValueError('Ключ ответов должен быть JSON-объектом по id вопросов')
    return key


def answer_text(question, entry):
    if isinstance(entry, str) and entry.strip():
        return entry
    if not isinstance(entry, dict):
        raise ValueError(f"Вопрос {question.get('id')}: нужен непустой ответ или объект correct/comment")
    correct, comment = entry.get('correct'), entry.get('comment', '')
    allowed = {label for label, _ in question.get('options', [])}
    if (not isinstance(correct, list) or any(not isinstance(label, str) for label in correct)
            or len(set(correct)) != len(correct) or not set(correct) <= allowed):
        raise ValueError(f"Вопрос {question.get('id')}: неверные метки correct")
    if not isinstance(comment, str):
        raise ValueError(f"Вопрос {question.get('id')}: comment должен быть строкой")
    return (', '.join(correct) if correct else 'Пустой набор') + ('\n' + comment if comment else '')


def with_answers(data, key=None):
    """Copy the document with answers attached. The bank key may include unselected questions."""
    tickets = []
    for ticket in data['tickets']:
        questions = []
        for question in ticket['questions']:
            entry = key.get(question.get('id')) if key is not None else question_answers(question)
            answer_text(question, entry)
            normalized = {k: v for k, v in question.items() if k != 'answer'}
            questions.append({**normalized, 'answers': entry})
        tickets.append({**ticket, 'questions': questions})
    return {**data, 'tickets': tickets}


def export_answers_tex(data, *, settings=None, **options):
    settings = settings or load_settings()
    style = settings.printing
    title = options.get('title', style.title)
    font = options.get('font', style.font)
    margin = options.get('margin_mm', style.margin_mm)
    size = options.get('font_size', style.font_size)
    institution = options.get('institution', style.institution)
    lines = [r'\documentclass[a4paper]{article}', r'\usepackage{fontspec}',
             r'\setmainfont{' + tex_escape(font) + '}', r'\usepackage[russian]{babel}',
             rf'\usepackage[margin={margin:g}mm]{{geometry}}', r'\setlength{\parindent}{0pt}',
             r'\begin{document}', rf'\fontsize{{{size:g}}}{{{size * 1.2:g}}}\selectfont',
             tex_escape(institution), r'\section*{' + tex_escape(title) + ': ответы}']
    for ticket in data['tickets']:
        lines.append(r'\subsection*{Билет № ' + str(ticket['ticket']) + '}')
        for number, question in enumerate(ticket['questions'], 1):
            lines.append(r'\par\medskip\textbf{' + str(number) + '. '
                         + tex_escape(question['text']) + r'}\par')
            for label, text in question.get('options', []):
                lines.append(tex_escape(label + '. ' + text) + r'\par')
            lines.append(r'\textbf{Ответ:} ' + r'\par '.join(
                tex_escape(line) for line in answer_text(question, question_answers(question)).splitlines()) + r'\par')
    return '\n'.join(lines) + '\n\\end{document}\n'
