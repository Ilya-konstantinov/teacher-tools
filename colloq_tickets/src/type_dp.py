"""Выбор количеств типов: сокращения, перебор и DP по частотам."""
from dataclasses import dataclass
from fractions import Fraction
from math import lcm
from .problem import SearchLimit, balanced_cost, priority_score


@dataclass(frozen=True)
class CountProblem:
    capacities: tuple[int, ...]
    costs: tuple[int, ...]
    count: int
    complement: bool
    baseline: tuple[int, ...]
    original_capacities: tuple[int, ...]

    def restore(self, amounts):
        if self.complement:
            return tuple(cap - amount for cap, amount in zip(self.original_capacities, amounts))
        return tuple(amounts)


def reduce_counts(classes, pool, count):
    caps = tuple(p.capacity for p in pool)
    missing = sum(caps) - count
    if missing < 0:
        raise ValueError("Недостаточная вместимость типов")
    complement = missing < count
    effective = missing if complement else count
    denominator = lcm(*(p.deviation.denominator for p in pool))
    sign = -1 if complement else 1
    costs = tuple(sign * int(p.deviation * denominator) for p in pool)
    baseline = [0] * len(classes)
    if complement:
        for pattern, cap in zip(pool, caps):
            for c, amount in pattern.composition:
                baseline[c] += cap * amount
    return CountProblem(tuple(min(cap, effective) for cap in caps), costs, effective,
                        complement, tuple(baseline), caps)


def components(pool):
    parent = {}

    def root(i):
        parent.setdefault(i, i)
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for pattern in pool:
        first = root(pattern.composition[0][0])
        for i, _ in pattern.composition[1:]:
            parent[root(i)] = root(first)
    result = {}
    for index, pattern in enumerate(pool):
        result.setdefault(root(pattern.composition[0][0]), []).append(index)
    return tuple(tuple(indices) for indices in result.values())


def enumeration_bound(problem, limit):
    """Верхняя граница числа планов с отсечением больших целых на limit+1."""
    p = len(problem.capacities)
    if problem.count == 0 or p <= 1:
        return 1
    product = 1
    for cap in problem.capacities:
        product = min(limit + 1, product * (cap + 1))
    # Число слабых композиций H по P типам: C(H+P-1,P-1).
    n = problem.count + p - 1
    k = min(problem.count, p - 1)
    combinations = 1
    for i in range(1, k + 1):
        combinations = combinations * (n - i + 1) // i
        if combinations > limit:
            combinations = limit + 1
            break
    return min(product, combinations)


@dataclass(frozen=True)
class Projection:
    active: tuple[int, ...]
    tracked: tuple[int, ...]
    vectors: tuple[tuple[int, ...], ...]
    # Для каждого активного класса: целые коэффициенты и общий знаменатель.
    expressions: tuple[tuple[tuple[int, ...], int], ...]
    state_bound: int

    def degrees(self, state):
        result = []
        for coefficients, denominator in self.expressions:
            value = sum(a * b for a, b in zip(coefficients, state))
            quotient, remainder = divmod(value, denominator)
            if remainder:
                raise RuntimeError("Нецелая частота при восстановлении проекции")
            result.append(quotient)
        return result


def frequency_projection(classes, pool, capacities, count, work_limit):
    """Выбрать независимые строки [число билетов; частоты] точно над Q.

    Сначала сохраняется строка числа билетов, затем частоты с малыми границами.
    Ранг R не превосходит min(C,P). Зависимые частоты выражаются через R
    координат. Ни округления весов, ни приближённого исключения строк нет.
    """
    columns = [dict(p.composition) for p in pool]
    active = tuple(sorted({c for p in pool for c, _ in p.composition}))
    bounds = {c: min(len(classes[c].members) * count,
                     sum(col.get(c, 0) * cap for col, cap in zip(columns, capacities)))
              for c in active}
    if len(active) * len(pool) > work_limit:
        raise SearchLimit("Превышен бюджет построения проекции частот")
    candidates = [(-1, [1] * len(pool))]
    candidates += [(c, [col.get(c, 0) for col in columns])
                   for c in sorted(active, key=lambda c: (bounds[c], c))]
    basis = []  # pivot, нормализованная строка, выражение через исходные строки
    chosen = []
    expressions = {}
    work = 0
    for row_id, values in candidates:
        row = [Fraction(value) for value in values]
        expression = [Fraction(0)] * len(chosen)
        for pivot, base, representation in basis:
            factor = row[pivot]
            if not factor:
                continue
            work += len(row) + len(representation)
            if work > work_limit:
                raise SearchLimit("Превышен бюджет исключения зависимых частот")
            row = [a - factor * b for a, b in zip(row, base)]
            for i, coefficient in enumerate(representation):
                expression[i] += factor * coefficient
        pivot = next((i for i, value in enumerate(row) if value), None)
        if pivot is None:
            expressions[row_id] = tuple(expression)
            continue
        factor = row[pivot]
        chosen.append(row_id)
        representation = tuple(-coefficient / factor for coefficient in expression) + (1 / factor,)
        basis.append((pivot, tuple(value / factor for value in row), representation))
        expressions[row_id] = (Fraction(0),) * (len(chosen) - 1) + (Fraction(1),)
    tracked = tuple(chosen[1:])
    encoded = []
    for c in active:
        expression = expressions[c]
        denominator = lcm(*(value.denominator for value in expression))
        coefficients = tuple(int(value * denominator) for value in expression)
        encoded.append((coefficients, denominator))
    vectors = tuple((1, *(col.get(c, 0) for c in tracked)) for col in columns)
    estimate = count + 1
    for c in tracked:
        estimate *= bounds[c] + 1
    return Projection(active, tracked, vectors, tuple(encoded), estimate)


@dataclass(frozen=True)
class Component:
    indices: tuple[int, ...]
    projection: Projection
    count: int


@dataclass(frozen=True)
class DPAnalysis:
    problem: CountProblem
    components: tuple[Component, ...]
    state_bound: int

    @property
    def max_rank(self):
        return max((1 + len(c.projection.tracked) for c in self.components), default=0)


def analyze_dp(classes, pool, count, max_work=1_000_000):
    problem = reduce_counts(classes, pool, count)
    result = []
    for indices in components(pool):
        local = [pool[i] for i in indices]
        capacities = [problem.capacities[i] for i in indices]
        limit = min(problem.count, sum(capacities))
        projection = frequency_projection(classes, local, capacities, limit, max_work)
        result.append(Component(indices, projection, limit))
    return DPAnalysis(problem, tuple(result), sum(c.projection.state_bound for c in result))


class _Budget:
    def __init__(self, max_states):
        self.max_states = max_states
        self.transitions = 0

    def step(self):
        self.transitions += 1
        if self.transitions > 10 * self.max_states:
            raise SearchLimit("Превышен бюджет переходов DP (10 × max_dp_states)")

    def check(self, states):
        if len(states) > self.max_states:
            raise SearchLimit("Превышен лимит состояний DP")


@dataclass(frozen=True, slots=True)
class _Trace:
    previous: object
    index: int
    amount: int


def _decode(trace, length):
    amounts = [0] * length
    while trace is not None:
        amounts[trace.index] += trace.amount
        trace = trace.previous
    return amounts


def _table(classes, component, problem, budget, require_all, objective_mode):
    projection = component.projection
    count = component.count
    # Вместимость u заменяется O(log(u+1)) пакетами 1,2,4,...,остаток.
    chunks = []
    for local_index, global_index in enumerate(component.indices):
        remaining = min(problem.capacities[global_index], count)
        power = 1
        while remaining:
            amount = min(power, remaining)
            chunks.append((local_index, amount,
                           tuple(amount * v for v in projection.vectors[local_index]),
                           amount * problem.costs[global_index]))
            remaining -= amount
            power *= 2
            budget.step()
    remaining_capacity = sum(amount for _, amount, _, _ in chunks)
    states = {(0,) * (len(projection.tracked) + 1): (0, None)}
    for index, amount, vector, delta_cost in chunks:
        remaining_capacity -= amount
        next_states = {}
        for state, (cost, trace) in states.items():
            budget.step()
            if not require_all or state[0] + remaining_capacity >= count:
                old = next_states.get(state)
                if old is None or cost < old[0]:
                    next_states[state] = (cost, trace)
            if state[0] + amount <= count:
                candidate = tuple(a + b for a, b in zip(state, vector))
                if not require_all or candidate[0] + remaining_capacity >= count:
                    new_cost = cost + delta_cost
                    old = next_states.get(candidate)
                    if old is None or new_cost < old[0]:
                        next_states[candidate] = (new_cost, _Trace(trace, index, amount))
            budget.check(next_states)
        states = next_states
    table = {}
    sign = -1 if problem.complement else 1
    for state, (cost, trace) in states.items():
        degrees = projection.degrees(state)
        frequency = sum(balanced_cost(len(classes[c].members), problem.baseline[c] + sign * degree)
                        for c, degree in zip(projection.active, degrees))
        value = (*priority_score(objective_mode, frequency, cost), trace)
        if state[0] not in table or value[:2] < table[state[0]][:2]:
            table[state[0]] = value
    return table


def select_types_dp(classes, pool, count, max_states, analysis=None, objective_mode="balanced"):
    analysis = analysis or analyze_dp(classes, pool, count, max_work=10 * max_states)
    problem = analysis.problem
    if problem.count == 0:
        return problem.restore([0] * len(pool))
    budget = _Budget(max_states)
    if len(analysis.components) == 1:
        component = analysis.components[0]
        table = _table(classes, component, problem, budget, require_all=True, objective_mode=objective_mode)
        if problem.count not in table:
            raise ValueError("Невозможно выбрать нужное количество билетов")
        local = _decode(table[problem.count][2], len(component.indices))
        amounts = [0] * len(pool)
        for index, amount in zip(component.indices, local):
            amounts[index] = amount
        return problem.restore(amounts)
    # Аддитивные стоимости независимых компонент объединяются рюкзаком.
    # Путь хранится связным списком, не копируется на каждом переходе.
    totals = {0: (0, 0, None)}
    for component in analysis.components:
        table = _table(classes, component, problem, budget, require_all=False, objective_mode=objective_mode)
        next_totals = {}
        for previous, (primary, secondary, path) in totals.items():
            for added, (local_primary, local_secondary, trace) in table.items():
                budget.step()
                total = previous + added
                if total > problem.count:
                    continue
                score = (primary + local_primary, secondary + local_secondary)
                if total not in next_totals or score < next_totals[total][:2]:
                    next_totals[total] = (*score, (path, trace))
                budget.check(next_totals)
        totals = next_totals
    if problem.count not in totals:
        raise ValueError("Невозможно выбрать нужное количество билетов")
    result = [0] * len(pool)
    path = totals[problem.count][2]
    for component in reversed(analysis.components):
        path, trace = path
        for index, amount in zip(component.indices, _decode(trace, len(component.indices))):
            result[index] = amount
    return problem.restore(result)


def select_types_enumeration(classes, pool, count, max_nodes, objective_mode="balanced"):
    problem = reduce_counts(classes, pool, count)
    if problem.count == 0:
        return problem.restore([0] * len(pool))
    suffix = [0] * (len(pool) + 1)
    for i in range(len(pool) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + problem.capacities[i]
    active = tuple(sorted({c for p in pool for c, _ in p.composition}))
    position = {c: i for i, c in enumerate(active)}
    vectors = [tuple((position[c], amount) for c, amount in p.composition) for p in pool]
    stack = [(0, problem.count, (0,) * len(active), 0, ())]
    best = None
    visited = 0
    while stack:
        index, remaining, degrees, cost, path = stack.pop()
        visited += 1
        if visited > max_nodes:
            raise SearchLimit("Превышен лимит перебора планов по типам")
        if index == len(pool):
            sign = -1 if problem.complement else 1
            frequency = sum(balanced_cost(len(classes[c].members), problem.baseline[c] + sign * d)
                            for c, d in zip(active, degrees))
            score = priority_score(objective_mode, frequency, cost)
            if best is None or score < best[:2]:
                best = (*score, path)
            continue
        lower = max(0, remaining - suffix[index + 1])
        upper = min(problem.capacities[index], remaining)
        for amount in range(lower, upper + 1):
            new_degrees = list(degrees)
            for c, coefficient in vectors[index]:
                new_degrees[c] += amount * coefficient
            stack.append((index + 1, remaining - amount, tuple(new_degrees),
                          cost + amount * problem.costs[index], path + (amount,)))
            if visited + len(stack) > max_nodes:
                raise SearchLimit("Превышен лимит перебора планов по типам")
    if best is None:
        raise ValueError("Невозможно выбрать нужное количество билетов")
    return problem.restore(best[2])
