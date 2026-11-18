"""JSON-ввод вопросов; алгоритм работает с моделями, а не файлами."""
import json
import re
from collections import Counter
from pathlib import Path

from .models import Question, Ticket


def read_questions(path: Path, *, sources=None) -> list[Question]:
    path = Path(path).expanduser()
    if sources is not None:
        sources.append(path)
    if path.is_dir():
        paths = sorted(path.glob('*.txt'), key=lambda p: tuple(
            (0, int(s)) if s.isdigit() else (1, s.casefold())
            for s in re.split(r'(\d+)', p.name)))
        if not paths:
            raise ValueError(f'{path}: нет вопросов *.txt')
        if sources is not None:
            sources.extend(paths)
        return parse_questions([read_text_question(p) for p in paths])
    with path.open(encoding="utf-8-sig") as stream:
        data = json.load(stream)
    return parse_questions(data, base_dir=path.parent, sources=sources)


def read_text_question(path):
    """Условие до первого a.; варианты могут занимать несколько строк."""
    heading, options = [], []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^\s*(?:\d+)?([a-z])\.\s+(.*)$', line)
        if match:
            options.append([match[1], match[2]])
        elif options:
            options[-1][1] += '\n' + line
        else:
            heading.append(line)
    return {'id': path.name, 'text': '\n'.join(heading).strip(),
            'options': [[label, text.strip()] for label, text in options]}


def parse_questions(data, *, base_dir=Path('.'), sources=None) -> list[Question]:
    from .problem import validate_questions

    if not isinstance(data, list):
        raise ValueError("Ожидается JSON-массив вопросов")
    has_weights = any(isinstance(item, dict) and 'weight' in item for item in data)
    reserved_ids = {item['id'] for item in data
                    if isinstance(item, dict) and isinstance(item.get('id'), str)}
    result = []
    for number, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Вопрос {number}: ожидается объект")
        if not ({'text', 'text_file'} & item.keys()):
            raise ValueError(f"Вопрос {number}: обязателен text либо text_file")
        if 'id' not in item:
            # Номер позиции воспроизводим для одного банка; явные id сохраняются.
            identifier = base_id = f'q{number}'
            suffix = 2
            while identifier in reserved_ids:
                identifier = f'{base_id}_{suffix}'
                suffix += 1
            reserved_ids.add(identifier)
            item = {**item, 'id': identifier}
        if 'text_file' in item:
            if 'text' in item:
                raise ValueError(f'Вопрос {number}: задайте только text или text_file')
            source = source_file(item, 'text_file', base_dir, sources, number)
            content = read_text_question(source)
            item = {**content, **item}
        if 'answer_file' in item:
            if 'answer' in item or 'answers' in item:
                raise ValueError(f'Вопрос {number}: answer_file несовместим с answer и answers')
            source = source_file(item, 'answer_file', base_dir, sources, number)
            answer = source.read_text(encoding='utf-8-sig')
            if source.suffix.lower() == '.json':
                answer = json.loads(answer)
            if not isinstance(answer, (str, dict)) or not answer:
                raise ValueError(f'{source}: ожидается текст ответа или объект correct/comment')
            item = {**item, 'answers': answer}
        if has_weights and 'weight' not in item:
            raise ValueError(f"Вопрос {number}: weight должен быть задан у всех вопросов или ни у одного")
        if "related" in item:
            raise ValueError(f"Вопрос {number}: related больше не поддерживается; "
                             "задайте тематическую group и удалите related")
        options = item.get('options', [])
        if (not isinstance(options, list) or any(
                not isinstance(option, (list, tuple)) or len(option) != 2
                or any(not isinstance(s, str) or not s.strip() for s in option)
                for option in options)):
            raise ValueError(f'Вопрос {number}: options — список пар [метка, текст]')
        if len({option[0] for option in options}) != len(options):
            raise ValueError(f'Вопрос {number}: повтор метки варианта')
        result.append(Question(item['id'], item['text'], item.get('weight', 1),
                               item.get('group', 'default'), tuple(map(tuple, options)), question_answers(item)))
    validate_questions(result)
    return result


def source_file(item, field, base_dir, sources, number):
    filename = item[field]
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f'Вопрос {number}: {field} должен быть непустым путём')
    path = base_dir / Path(filename).expanduser()
    if sources is not None:
        sources.append(path)
    return path


def question_answers(item):
    """answers — основное поле; answer читается для прежних JSON."""
    if 'answers' in item and 'answer' in item and item['answers'] != item['answer']:
        raise ValueError(f"Вопрос {item.get('id')}: поля answers и answer противоречат друг другу")
    return item.get('answers', item.get('answer'))


def question_data(question):
    data = {name: getattr(question, name) for name in ('id', 'text', 'weight', 'group')}
    if question.options:
        data['options'] = [list(option) for option in question.options]
    if question.answer is not None:
        data['answers'] = question.answer
    return data


def without_answers(data):
    return {**data, 'tickets': [
        {**ticket, 'questions': [
            {k: v for k, v in question.items() if k not in ('answer', 'answers', 'answer_text', 'answer_file')}
            for question in ticket['questions']]}
        for ticket in data['tickets']]}


def tickets_data(tickets: list[Ticket], *, questions: list[Question], target_weight: float,
                  optimization: dict | None = None) -> dict:
    items = [{"ticket": number, "total_weight": ticket.total_weight,
             "weight_deviation": abs(ticket.total_weight - target_weight),
             "questions": [question_data(q) for q in ticket.questions]}
            for number, ticket in enumerate(tickets, 1)]
    usage = Counter(q.id for ticket in tickets for q in ticket.questions)
    data = {"target_weight": target_weight,
            "max_weight_deviation": max((item["weight_deviation"] for item in items), default=0),
            "question_usage": [{"id": q.id, "text": q.text, "group": q.group, "count": usage[q.id]}
                               for q in questions],
            "tickets": items}
    if optimization is not None:
        data["optimization"] = optimization
    return data


def write_tickets(path: Path, tickets: list[Ticket], *, questions: list[Question], target_weight: float,
                  optimization: dict | None = None) -> None:
    data = tickets_data(tickets, questions=questions, target_weight=target_weight, optimization=optimization)
    write_json(path, without_answers(data))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
