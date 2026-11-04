"""Точные сокращения выбора типов: дополнение, компоненты и ранг частот."""
from dataclasses import dataclass
from fractions import Fraction
from math import lcm

from .ticket_types import SearchLimit


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
