"""JSON-ввод вопросов; алгоритм работает с моделями, а не файлами."""
import json
from collections import Counter
from pathlib import Path

from models import Question, Ticket


def read_questions(path: Path) -> list[Question]:
    with path.open(encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if not isinstance(data, list):
        raise ValueError("Ожидается JSON-массив вопросов")
    result = []
    for number, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Вопрос {number}: ожидается объект")
        if not {"id", "text", "weight"} <= item.keys():
            raise ValueError(f"Вопрос {number}: обязательны id, text, weight")
        if "related" in item:
            raise ValueError(f"Вопрос {number}: related больше не поддерживается; "
                             "задайте тематическую group и удалите related")
        result.append(Question(item["id"], item["text"], item["weight"], item.get("group", "default")))
    return result


def write_tickets(path: Path, tickets: list[Ticket], *, questions: list[Question], target_weight: float,
                  optimization: dict | None = None) -> None:
    items = [{"ticket": number, "total_weight": ticket.total_weight,
             "weight_deviation": abs(ticket.total_weight - target_weight),
             "questions": [{"id": q.id, "text": q.text, "weight": q.weight, "group": q.group}
                           for q in ticket.questions]}
            for number, ticket in enumerate(tickets, 1)]
    usage = Counter(q.id for ticket in tickets for q in ticket.questions)
    data = {"target_weight": target_weight,
            "max_weight_deviation": max((item["weight_deviation"] for item in items), default=0),
            "question_usage": [{"id": q.id, "text": q.text, "group": q.group, "count": usage[q.id]}
                               for q in questions],
            "tickets": items}
    if optimization is not None:
        data["optimization"] = optimization
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
