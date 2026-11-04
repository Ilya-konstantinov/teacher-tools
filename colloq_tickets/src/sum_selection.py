"""Выбор оптимальных сумм либо количеств типов по сложности билета."""
from collections import defaultdict

from .models import TypeSelection
from .sum_dp import build_sum_table
from .sum_models import SumPlan


def proportional_counts(capacities, count):
    """Детерминированное распределение без превышения вместимостей."""
    total = sum(capacities)
    if count > total:
        raise ValueError('Недостаточно различных билетов')
    values = [count * capacity // total for capacity in capacities]
    remaining = count - sum(values)
    order = sorted(range(len(values)), key=lambda i: (-(count * capacities[i] % total), i))
    for i in order[:remaining]:
        values[i] += 1
    return values


def choose_sums(table, size, count, target):
    buckets = defaultdict(list)
    for (taken, total), capacity in table.items():
        if taken == size:
            buckets[abs(total - target)].append((total, capacity))
    amounts = []
    remaining = count
    for deviation in sorted(buckets):
        bucket = sorted(buckets[deviation])
        take = min(remaining, sum(cap for _, cap in bucket))
        for (total, _), amount in zip(bucket, proportional_counts([cap for _, cap in bucket], take)):
            if amount:
                amounts.append((total, amount))
        remaining -= take
        if remaining == 0:
            return tuple(amounts)
    raise ValueError(f'Нужно {count} различных билетов, но допустимых только {count - remaining}')



def select_sums(classes, size, count, mode, target, max_states):
    root, profiles, diagnostics = build_sum_table(classes, size, mode, max_states)
    amounts = choose_sums(root.table, size, count, target)
    return TypeSelection((), (), "profile-sum-dp", proven_objectives=2, types_enumerated=False,
                         objective_mode="weight-first", objective_count=2,
                         frequency_guarantee="within-class", diagnostics=diagnostics,
                         sum_plan=SumPlan(root, profiles, amounts, size))


def select_weight_types(pool, count):
    """Точный выбор первых двух целей из уже перечисленных типов."""
    buckets = defaultdict(list)
    for i, pattern in enumerate(pool):
        buckets[pattern.deviation].append(i)
    amounts = [0] * len(pool)
    remaining = count
    for deviation in sorted(buckets):
        indices = buckets[deviation]
        caps = [pool[i].capacity for i in indices]
        take = min(remaining, sum(caps))
        for i, amount in zip(indices, proportional_counts(caps, take)):
            amounts[i] = amount
        remaining -= take
        if not remaining:
            return amounts
    raise ValueError('Недостаточно различных билетов')
