"""Точное сжатие по весам и группам и вместимости типов билетов."""
from collections import defaultdict
from fractions import Fraction
from math import comb

from .models import Question, QuestionClass, TicketType


class SearchLimit(Exception):
    """Исчерпан бюджет точного перечисления/динамики; частичный ответ запрещён."""


def group_questions(questions: list[Question], mode: str) -> list[QuestionClass]:
    buckets = defaultdict(list)
    for i, question in enumerate(questions):
        key = (Fraction(str(question.weight)), question.group if mode != "ignore" else "")
        buckets[key].append(i)
    return [QuestionClass(tuple(indices), weight, group)
            for (weight, group), indices in buckets.items()]


def enumerate_types(classes, size, count, mode, target, limit):
    """Перечислять составы классов, не конкретные подмножества вопросов.

    Вместимость обрезается на count: большие значения эквивалентны для выбора.
    """
    patterns = []
    stack = [(size, 0, (), Fraction(0), 1, frozenset())]
    visited = 0
    while stack:
        remaining, start, composition, weight, capacity, used = stack.pop()
        visited += 1
        if visited > limit:
            raise SearchLimit("Превышен лимит перечисления типов")
        if remaining == 0:
            patterns.append(TicketType(composition, abs(weight - target), capacity))
            continue
        for index in range(start, len(classes)):
            item = classes[index]
            if mode == "different" and item.group in used:
                continue
            if mode == "same" and used and item.group not in used:
                continue
            maximum = min(remaining, len(item.members), 1 if mode == "different" else size)
            for amount in range(1, maximum + 1):
                stack.append((remaining - amount, index + 1, composition + ((index, amount),),
                              weight + amount * item.weight,
                              min(count, capacity * comb(len(item.members), amount)), used | {item.group}))
                if visited + len(stack) > limit:
                    raise SearchLimit("Превышен лимит перечисления типов")
    patterns.sort(key=lambda p: (p.deviation, p.composition))
    total = 0
    threshold = None
    for pattern in patterns:
        total += pattern.capacity
        if total >= count:
            threshold = pattern.deviation
            break
    if threshold is None:
        raise ValueError(f"Нужно {count} различных билетов, но допустимых только {total} "
                         f"(режим групп {mode}, вопросов в билете {size})")
    return [pattern for pattern in patterns if pattern.deviation <= threshold]


def balanced_cost(size, total):
    quotient, remainder = divmod(total, size)
    return (size - remainder) * quotient ** 2 + remainder * (quotient + 1) ** 2
