"""Точный перебор небольшого числа планов по типам, без перебора билетов."""
from objectives import priority_score
from reduction import reduce_counts
from ticket_types import SearchLimit, balanced_cost


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
