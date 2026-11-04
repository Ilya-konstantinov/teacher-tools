"""Точная DP: независимые частоты, двоичное разложение и выбор дополнения."""
from dataclasses import dataclass

from .objectives import priority_score
from .reduction import CountProblem, Projection, components, frequency_projection, reduce_counts
from .ticket_types import SearchLimit, balanced_cost


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


def estimated_states(classes, pool, count):
    return analyze_dp(classes, pool, count).state_bound


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
        for previous, (frequency, deviation, path) in totals.items():
            for added, (local_frequency, local_deviation, trace) in table.items():
                budget.step()
                total = previous + added
                if total > problem.count:
                    continue
                score = (frequency + local_frequency, deviation + local_deviation)
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
