"""Точный выбор билетов через классы весов и тематические группы."""
from fractions import Fraction
from dataclasses import replace
import math

from .constraints import GROUP_MODES, validate_questions
from .models import TicketPlan, TypeSelection
from .objectives import OBJECTIVE_MODES, describe_selection
from .cp_selection import select_types, select_direct
from .dp_selection import analyze_dp, select_types_dp
from .enumeration_selection import select_types_enumeration
from .reduction import enumeration_bound, reduce_counts
from .ticket_types import SearchLimit, enumerate_types, group_questions
from .sum_selection import select_sums, select_weight_types


ALGORITHMS = ("auto", "sum-dp", "enumerate", "dp", "cp-sat-types", "cp-sat")


def plan_tickets(questions, questions_per_ticket, ticket_count,
                 group_mode="ignore", max_search_nodes=100_000, *,
                 target_weight, algorithm="auto", time_limit=30,
                 allow_feasible=False, max_dp_states=100_000,
                 objective_mode="weight-first") -> TicketPlan:
    """Выбор плана: по сложности (по умолчанию) либо со строгими частотами.

    auto пробует профильную DP по суммам для weight-first. При превышении
    бюджета переходит к типам, затем к прямой CP-SAT-модели.
    """
    validate_questions(questions)
    if objective_mode not in OBJECTIVE_MODES:
        raise ValueError(f"Неизвестный режим целей: {objective_mode}")
    if algorithm == "sum-dp" and objective_mode != "weight-first":
        raise ValueError("sum-dp требует --objective-mode weight-first: глобальные частоты не оптимизируются")
    if (isinstance(target_weight, bool) or not isinstance(target_weight, (int, float))
            or not math.isfinite(target_weight) or target_weight <= 0):
        raise ValueError("Целевой вес должен быть положительным конечным числом")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Неизвестный алгоритм: {algorithm}")
    if group_mode not in GROUP_MODES:
        raise ValueError(f"Неизвестный режим групп: {group_mode}")
    if (isinstance(time_limit, bool) or not isinstance(time_limit, (int, float))
            or not math.isfinite(time_limit) or time_limit <= 0):
        raise ValueError("Лимит времени должен быть положительным конечным числом")
    for name, value in (("Размер билета", questions_per_ticket), ("Число билетов", ticket_count),
                        ("Лимит типов", max_search_nodes), ("Лимит DP", max_dp_states)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} должен быть положительным целым числом")
    if questions_per_ticket > len(questions):
        raise ValueError("Вопросов в банке меньше, чем требуется для одного билета")
    if ticket_count > math.comb(len(questions), questions_per_ticket):
        raise ValueError("Нужно больше различных билетов, чем существует сочетаний вопросов")
    if group_mode == "different" and questions_per_ticket > len({q.group for q in questions}):
        raise ValueError("Для режима different недостаточно различных тематических групп")

    target = Fraction(str(target_weight))
    questions = tuple(questions)
    classes = tuple(group_questions(questions, group_mode))

    fallback = {}

    def report(selection):
        selection = describe_selection(selection, objective_mode)
        selection = replace(selection, diagnostics={"topics": len({q.group for q in questions}),
                                                     **fallback, **selection.diagnostics})
        return TicketPlan(questions, classes, selection, questions_per_ticket,
                          ticket_count, group_mode, target)

    def direct():
        return report(select_direct(questions, classes, questions_per_ticket, ticket_count,
                                    group_mode, target, time_limit, allow_feasible, objective_mode))

    if algorithm == "cp-sat":
        return direct()
    if objective_mode == "weight-first" and algorithm in ("auto", "sum-dp"):
        try:
            return report(select_sums(classes, questions_per_ticket, ticket_count,
                                      group_mode, target, max_dp_states))
        except SearchLimit as error:
            if algorithm == "sum-dp":
                raise ValueError(f"DP: {error}; увеличьте --max-dp-states или выберите auto") from error
            fallback["sum_dp_fallback"] = str(error)
    try:
        pool = enumerate_types(classes, questions_per_ticket, ticket_count, group_mode,
                               target, max_search_nodes)
    except SearchLimit as error:
        if algorithm == "auto":
            fallback["type_enumeration_fallback"] = str(error)
            return direct()
        raise ValueError(f"{error}; увеличьте --max-search-nodes или выберите auto/cp-sat") from error

    def finish(amounts, name):
        return report(TypeSelection(tuple(pool), tuple(amounts), name, diagnostics=fallback))

    if algorithm == "auto" and objective_mode == "weight-first":
        return finish(select_weight_types(pool, ticket_count), "weight-types")

    if algorithm == "auto":
        if ticket_count == 1:
            return finish([1] + [0] * (len(pool) - 1), "fixed-types")
        if len(pool) == 1:
            return finish([ticket_count], "fixed-types")
        if sum(p.capacity for p in pool) == ticket_count:
            return finish([p.capacity for p in pool], "fixed-types")

    # Если возможных количественных планов мало, не строим многомерную DP.
    reduced = reduce_counts(classes, pool, ticket_count)
    plan_bound = enumeration_bound(reduced, max_search_nodes)
    if algorithm == "enumerate" or (algorithm == "auto" and
            plan_bound * max(1, len(pool)) <= min(10_000, max_search_nodes)):
        try:
            return finish(select_types_enumeration(classes, pool, ticket_count, max_search_nodes, objective_mode),
                          "type-enumeration")
        except SearchLimit as error:
            if algorithm == "enumerate":
                raise ValueError(f"{error}; увеличьте --max-search-nodes или выберите auto/cp-sat-types") from error

    if algorithm in ("auto", "dp"):
        try:
            analysis = analyze_dp(classes, pool, ticket_count, max_work=10 * max_dp_states)
            if algorithm == "dp" or analysis.state_bound <= max_dp_states:
                return finish(select_types_dp(classes, pool, ticket_count, max_dp_states, analysis, objective_mode), "type-dp")
        except SearchLimit as error:
            if algorithm == "dp":
                raise ValueError(f"DP: {error}; увеличьте --max-dp-states или выберите auto/cp-sat-types") from error

    return report(select_types(questions, classes, pool, ticket_count, time_limit, allow_feasible, objective_mode))
