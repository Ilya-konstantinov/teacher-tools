"""Select an algorithm, build a plan, and expose the public generation API."""
import math
from dataclasses import replace
from fractions import Fraction
from .config import load_settings
from .cp_sat import select_direct, select_types
from .models import TicketPlan, TypeSelection
from .problem import (
    ALGORITHMS,
    GROUP_MODES,
    OBJECTIVE_MODES,
    SearchLimit,
    describe_selection,
    enumerate_types,
    group_questions,
    validate_questions,
)
from .reconstruction import restore_tickets
from .sum_dp import select_sums, select_weight_types
from .type_dp import (
    analyze_dp,
    enumeration_bound,
    reduce_counts,
    select_types_dp,
    select_types_enumeration,
)


def plan_tickets(questions, questions_per_ticket, ticket_count,
                 group_mode=None, max_search_nodes=None, *,
                 target_weight, algorithm=None, time_limit=None,
                 allow_feasible=None, max_dp_states=None,
                 objective_mode=None, settings=None) -> TicketPlan:
    """Select by difficulty (default) or strict frequencies. In weight-first mode, auto tries profile sum DP, then types, then direct CP-SAT if the budget is exceeded."""
    settings = settings if settings is not None else load_settings()
    defaults, search = settings.generation, settings.search
    group_mode = defaults.group_mode if group_mode is None else group_mode
    max_search_nodes = defaults.max_search_nodes if max_search_nodes is None else max_search_nodes
    algorithm = defaults.algorithm if algorithm is None else algorithm
    time_limit = defaults.time_limit if time_limit is None else time_limit
    allow_feasible = defaults.allow_feasible if allow_feasible is None else allow_feasible
    max_dp_states = defaults.max_dp_states if max_dp_states is None else max_dp_states
    objective_mode = defaults.objective_mode if objective_mode is None else objective_mode
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
                                    group_mode, target, time_limit, allow_feasible, objective_mode, search=search))

    if algorithm == "cp-sat":
        return direct()
    if objective_mode == "weight-first" and algorithm in ("auto", "sum-dp"):
        try:
            return report(select_sums(classes, questions_per_ticket, ticket_count,
                                      group_mode, target, max_dp_states, search=search))
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

    # Skip multidimensional DP when only a few count plans are possible.
    reduced = reduce_counts(classes, pool, ticket_count)
    plan_bound = enumeration_bound(reduced, max_search_nodes)
    if algorithm == "enumerate" or (algorithm == "auto" and
            plan_bound * max(1, len(pool)) <= min(search.auto_enumeration_work_limit, max_search_nodes)):
        try:
            return finish(select_types_enumeration(classes, pool, ticket_count, max_search_nodes, objective_mode),
                          "type-enumeration")
        except SearchLimit as error:
            if algorithm == "enumerate":
                raise ValueError(f"{error}; увеличьте --max-search-nodes или выберите auto/cp-sat-types") from error

    if algorithm in ("auto", "dp"):
        try:
            analysis = analyze_dp(classes, pool, ticket_count, max_work=search.dp_work_multiplier * max_dp_states)
            if algorithm == "dp" or analysis.state_bound <= max_dp_states:
                return finish(select_types_dp(classes, pool, ticket_count, max_dp_states, analysis, objective_mode, work_multiplier=search.dp_work_multiplier), "type-dp")
        except SearchLimit as error:
            if algorithm == "dp":
                raise ValueError(f"DP: {error}; увеличьте --max-dp-states или выберите auto/cp-sat-types") from error

    return report(select_types(questions, classes, pool, ticket_count, time_limit, allow_feasible, objective_mode, search=search))


def generate_tickets_report(*args, **kwargs):
    """Run both stages through the compatibility API."""
    return restore_tickets(plan_tickets(*args, **kwargs))


def generate_tickets(*args, **kwargs):
    return generate_tickets_report(*args, **kwargs).tickets
