"""Общие модели выбора билетов для OR-Tools CP-SAT, без перебора наборов."""
from fractions import Fraction
from collections import Counter
from dataclasses import replace
from math import comb, lcm, prod
from time import perf_counter

from .models import Question, TicketType, TypeSelection
from .problem import balanced_cost


def _cp_model():
    try:
        from ortools.sat.python import cp_model
    except ImportError as error:
        raise ValueError("Не удалось загрузить OR-Tools. Установите зависимости: "
                         "python3 -m venv .venv; .venv/bin/python -m pip install -r requirements.txt; "
                         "запускайте через python3 generate_tickets.py (на NixOS он также подключает системные библиотеки)") from error
    return cp_model


def _integers(values: list[Fraction], multiplier: int) -> list[int]:
    denominator = lcm(*(v.denominator for v in values))
    result = [int(v * denominator) for v in values]
    if sum(abs(v) for v in result) * max(1, multiplier) >= 2 ** 60:
        raise ValueError("Слишком большие веса или слишком много знаков после запятой для CP-SAT; "
                         "сократите точность входных весов")
    return result


def _frequency_objective(model, columns, ticket_count):
    squares = []
    counts = []
    for i, column in enumerate(columns):
        column = list(column)
        upper = min(ticket_count, len(column))
        count = model.new_int_var(0, upper, f"count_{i}")
        model.add(count == sum(column))
        square = model.new_int_var(0, upper ** 2, f"count_squared_{i}")
        # Точное выпуклое продолжение c² на целых c, с сильной LP-релаксацией.
        for degree in range(1, upper + 1):
            model.add(square >= (2 * degree - 1) * count - degree * (degree - 1))
        squares.append(square)
        counts.append(count)
    # При любом числе появлений минимальная сумма квадратов достигается
    # при различии частот максимум на 1. Эта оценка усиливает модель.
    if squares:
        total_count = model.new_int_var(0, len(squares) * ticket_count, 'total_count')
        model.add(total_count == sum(counts))
        for degree in range(1, ticket_count + 1):
            model.add(sum(squares) >= (2 * degree - 1) * total_count - len(squares) * degree * (degree - 1))
    return sum(squares)


def _solve(model, objectives, extract, time_limit, allow_feasible, proven=0):
    cp_model = _cp_model()
    objective_count = proven + len(objectives)
    deadline = perf_counter() + time_limit
    selection = None
    for objective in objectives:
        remaining = deadline - perf_counter()
        if remaining <= 0:
            break
        model.minimize(objective)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        if status == cp_model.MODEL_INVALID:
            raise ValueError("Некорректная модель CP-SAT: " + model.validate())
        if status == cp_model.INFEASIBLE:
            raise ValueError("Невозможно составить указанное число различных билетов с этими ограничениями")
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            selection = extract(solver)
        if status != cp_model.OPTIMAL:
            break
        proven += 1
        model.add(objective == solver.value(objective))
    if proven == objective_count:
        return replace(selection, proven_objectives=proven)
    if selection is not None and allow_feasible:
        return replace(selection, optimal=False, proven_objectives=proven)
    raise ValueError(f"За {time_limit:g} с CP-SAT не доказал оптимальность всех критериев "
                     f"(доказано {proven}/{objective_count}). Увеличьте --time-limit или укажите --allow-feasible, "
                     "чтобы сохранить найденный допустимый результат с отметкой optimal=false")


def select_types(questions, classes, pool, ticket_count, time_limit, allow_feasible, objective_mode="balanced"):
    """Одна целочисленная переменная на тип (вес × тематическая группа)."""
    cp_model = _cp_model()
    model = cp_model.CpModel()
    selected = [model.new_int_var(0, min(p.capacity, ticket_count), f"type_{j}")
                for j, p in enumerate(pool)]
    model.add(sum(selected) == ticket_count)
    columns = [[] for _ in classes]
    bounds = [0] * len(classes)
    size = sum(amount for _, amount in pool[0].composition)
    if size * ticket_count ** 2 >= 2 ** 60:
        raise ValueError("Слишком большое число мест для целочисленной модели CP-SAT")
    for variable, pattern in zip(selected, pool):
        for i, amount in pattern.composition:
            columns[i].append(amount * variable)
            bounds[i] += amount * min(pattern.capacity, ticket_count)
    penalties = []
    for i, (item, column) in enumerate(zip(classes, columns)):
        if not column or objective_mode == "weight-first":
            continue
        members = len(item.members)
        upper = min(bounds[i], members * ticket_count, size * ticket_count)
        count = model.new_int_var(0, upper, f"class_count_{i}")
        model.add(count == sum(column))
        penalty = model.new_int_var(0, balanced_cost(members, upper), f"class_penalty_{i}")
        for q in range(upper // members + 1):
            model.add(penalty >= (2 * q + 1) * count - members * q * (q + 1))
        penalties.append(penalty)
    frequency = sum(penalties)
    if objective_mode == "balanced":
        model.add(frequency >= balanced_cost(len(questions), size * ticket_count))
    costs = _integers([p.deviation for p in pool], ticket_count)
    deviation_sum = sum(c * x for c, x in zip(costs, selected))

    def extract(solver):
        return TypeSelection(tuple(pool), tuple(solver.value(x) for x in selected), "cp-sat-types")

    # Минимакс уже доказан порогом; решаем оставшиеся цели выбранного режима.
    return _solve(model, [frequency, deviation_sum] if objective_mode == "balanced" else [deviation_sum],
                  extract, time_limit, allow_feasible, proven=1)


def _strict_lex_order(model, left, right, index):
    """left < right без кодирования всего билета огромным двоичным числом."""
    prefix_equal = model.new_constant(1)
    for i, (a, b) in enumerate(zip(left, right)):
        model.add(a <= b).only_enforce_if(prefix_equal)
        equal = model.new_bool_var(f"equal_{index}_{i}")
        model.add(a == b).only_enforce_if(equal)
        model.add(a != b).only_enforce_if(equal.Not())
        next_equal = model.new_bool_var(f"prefix_{index}_{i}")
        model.add(next_equal <= prefix_equal)
        model.add(next_equal <= equal)
        model.add(next_equal >= prefix_equal + equal - 1)
        prefix_equal = next_equal
    model.add(prefix_equal == 0)


def select_direct(questions: list[Question], classes, size: int, ticket_count: int, group_mode: str,
                  target: Fraction, time_limit: float, allow_feasible: bool, objective_mode="balanced"):
    """Большие банки: булевы «вопрос в билете», без перечисления сочетаний."""
    cp_model = _cp_model()
    model = cp_model.CpModel()
    weights_and_target = _integers([Fraction(str(q.weight)) for q in questions] + [target], ticket_count)
    weights, goal = weights_and_target[:-1], weights_and_target[-1]
    max_deviation = sum(weights) + goal
    rows = [[model.new_bool_var(f"ticket_{t}_question_{i}") for i in range(len(questions))]
            for t in range(ticket_count)]
    deviations = []
    groups = {}
    for i, question in enumerate(questions):
        groups.setdefault(question.group, []).append(i)
    for t, row in enumerate(rows):
        model.add(sum(row) == size)
        if group_mode == "different":
            for indices in groups.values():
                model.add(sum(row[i] for i in indices) <= 1)
        elif group_mode == "same":
            choices = [model.new_bool_var(f"group_{t}_{g}") for g in range(len(groups))]
            model.add(sum(choices) == 1)
            for choice, indices in zip(choices, groups.values()):
                model.add(sum(row[i] for i in indices) == size * choice)
        deviation = model.new_int_var(0, max_deviation, f"deviation_{t}")
        model.add_abs_equality(deviation, sum(w * x for w, x in zip(weights, row)) - goal)
        deviations.append(deviation)
    # Строгий порядок одновременно исключает дубли и симметрию перестановки билетов.
    for t in range(ticket_count - 1):
        _strict_lex_order(model, rows[t], rows[t + 1], t)
    worst = model.new_int_var(0, max_deviation, "worst_deviation")
    model.add_max_equality(worst, deviations)
    frequency = (_frequency_objective(model, zip(*rows), ticket_count)
                 if objective_mode == "balanced" else None)

    class_of = {i: c for c, item in enumerate(classes) for i in item.members}

    def extract(solver):
        # Прямой решатель использует индивидуальные переменные как свидетельство
        # допустимости. Наружу тоже возвращается только план по типам.
        amounts = Counter()
        for row in rows:
            counts = Counter(class_of[i] for i, variable in enumerate(row) if solver.value(variable))
            amounts[tuple(sorted(counts.items()))] += 1
        types = []
        for composition in sorted(amounts):
            deviation = abs(sum(classes[c].weight * amount for c, amount in composition) - target)
            capacity = min(ticket_count, prod(comb(len(classes[c].members), amount)
                                             for c, amount in composition))
            types.append(TicketType(composition, deviation, capacity))
        return TypeSelection(tuple(types), tuple(amounts[t.composition] for t in types),
                             "cp-sat-direct", types_enumerated=False)

    objectives = ([worst, frequency, sum(deviations)] if objective_mode == "balanced"
                  else [worst, sum(deviations)])
    return _solve(model, objectives, extract, time_limit, allow_feasible)
