"""Проверка данных и правил тематических групп."""
import math

from models import Question


GROUP_MODES = ("different", "same", "ignore")


def validate_questions(questions: list[Question]) -> None:
    ids = set()
    for question in questions:
        if not isinstance(question.id, str) or not question.id.strip():
            raise ValueError("id вопроса должен быть непустой строкой")
        if question.id in ids:
            raise ValueError(f"Повтор id: {question.id}")
        ids.add(question.id)
        if not isinstance(question.text, str) or not question.text.strip():
            raise ValueError(f"Вопрос {question.id}: нужен непустой текст")
        if not isinstance(question.group, str) or not question.group.strip():
            raise ValueError(f"Вопрос {question.id}: group должен быть непустой строкой")
        if (isinstance(question.weight, bool) or not isinstance(question.weight, (int, float))
                or not math.isfinite(question.weight) or question.weight <= 0):
            raise ValueError(f"Вопрос {question.id}: вес должен быть положительным конечным числом")


def compatible(first: Question, second: Question, mode: str) -> bool:
    if mode not in GROUP_MODES:
        raise ValueError(f"Неизвестный режим групп: {mode}")
    return mode == "ignore" or ((first.group != second.group) if mode == "different"
                                else (first.group == second.group))
