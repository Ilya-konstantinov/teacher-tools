"""Правила задачи, цели, классы вопросов и типы билетов."""
import math
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from math import comb
from types import MappingProxyType
from .models import Question, QuestionClass, TicketType, TopicProfile


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


OBJECTIVES = MappingProxyType({
    'weight-first': ('max_weight_deviation', 'total_weight_deviation'),
    'balanced': ('max_weight_deviation', 'frequency_squares', 'total_weight_deviation'),
})
OBJECTIVE_MODES = tuple(OBJECTIVES)


def priority_score(mode, frequency, deviation):
    """Порядок оставшихся целей после фиксации минимакса.

    В weight-first точные решатели могут использовать частоты лишь для
    разрешения равенства по сложности; публичная гарантия — две цели.
    """
    return (frequency, deviation) if mode == 'balanced' else (deviation, frequency)


def describe_selection(selection, mode):
    count = len(OBJECTIVES[mode])
    proven = count if selection.optimal else min(selection.proven_objectives, count)
    frequency = ('global-optimum' if mode == 'balanced' and proven >= 2 else 'within-class')
    return replace(selection, objective_mode=mode, objective_count=count,
                   proven_objectives=proven, frequency_guarantee=frequency)


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


def group_profiles(classes):
    topics = defaultdict(list)
    for index, item in enumerate(classes):
        topics[item.group].append(index)
    profiles = {}
    for indices in topics.values():
        indices.sort(key=lambda c: classes[c].weight)
        histogram = tuple((classes[c].weight, len(classes[c].members)) for c in indices)
        profiles.setdefault(histogram, []).append(tuple(indices))
    return tuple(TopicProfile(histogram, tuple(members)) for histogram, members in profiles.items())
