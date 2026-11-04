"""Разбор комбинаторных индексов в количества исходных типов билетов."""
from collections import Counter
from math import comb, prod
from random import Random

from models import TicketType


def unrank_composition(plan, total, rank):
    """Разобрать индекс конкретного билета до состава исходных классов.

    Индексы внутри сочетаний вопросов класса не материализуются: затем
    общий восстановитель создаст столько различных билетов данного типа.
    """
    result = Counter()
    stack = [(plan.root, plan.size, total, rank, 0)]
    while stack:
        node, taken, weight, rank, offset = stack.pop()
        if taken == 0:
            # Пустой набор единственный: не разворачиваем тысячи пропущенных
            # тем повторяющегося профиля, когда R существенно меньше T.
            if weight != 0 or rank != 0:
                raise RuntimeError('Некорректный индекс пустого набора')
            continue
        if node.kind in ('product', 'repeat'):
            left, right = node.children
            for (a, wa), ca in left.table.items():
                cb = right.table.get((taken - a, weight - wa), 0)
                block = ca * cb
                if rank >= block:
                    rank -= block
                    continue
                left_rank, right_rank = divmod(rank, cb)
                repeated = node.kind == 'repeat'
                stack.append((right, taken - a, weight - wa, right_rank,
                              offset + left.copies if repeated else 0))
                stack.append((left, a, wa, left_rank, offset if repeated else 0))
                break
            else:
                raise RuntimeError('Некорректный индекс произведения билетов')
        elif node.kind == 'choice':
            for child in node.children:
                block = child.table.get((taken, weight), 0)
                if rank < block:
                    stack.append((child, taken, weight, rank, 0))
                    break
                rank -= block
            else:
                raise RuntimeError('Некорректный индекс выбора профиля')
        elif node.kind == 'copies':
            child = node.children[0]
            topic, local_rank = divmod(rank, child.table[taken, weight])
            stack.append((child, taken, weight, local_rank, topic))
        elif node.kind == 'topic':
            if taken:
                profile = plan.profiles[node.profile]
                level = next(i for i, (w, _) in enumerate(profile.histogram) if w == weight)
                result[profile.members[offset][level]] += 1
        elif node.kind == 'subset':
            profile = plan.profiles[node.profile]
            for level in range(len(profile.histogram) - 1, -1, -1):
                w, available = profile.histogram[level]
                for amount in range(min(available, taken) + 1):
                    previous = node.layers[level].get((taken - amount, weight - amount * w), 0)
                    ways = comb(available, amount)
                    block = previous * ways
                    if rank >= block:
                        rank -= block
                        continue
                    rank //= ways
                    if amount:
                        result[profile.members[offset][level]] += amount
                    taken -= amount
                    weight -= amount * w
                    break
                else:
                    raise RuntimeError('Некорректный индекс сочетания вопросов')
        else:
            raise RuntimeError(f'Неизвестный узел плана: {node.kind}')
    return tuple(sorted(result.items()))


def materialize_types(sum_plan, classes, count, target):
    """Восстановить количества исходных типов, не меняя выбранных сумм.

    По одному случайному индексу из непересекающихся равных страт: без
    повторов, без смещения к началу банка, без материализации всего пула.
    Фиксированный seed делает повторное восстановление воспроизводимым.
    """
    rng = Random(0)
    amounts = Counter()
    for total, selected in sum_plan.amounts:
        capacity = sum_plan.root.table[sum_plan.size, total]
        for i in range(selected):
            start, end = i * capacity // selected, (i + 1) * capacity // selected
            rank = rng.randrange(start, end)
            amounts[unrank_composition(sum_plan, total, rank)] += 1
    types = []
    for composition in sorted(amounts):
        capacity = min(count, prod(comb(len(classes[c].members), a) for c, a in composition))
        deviation = abs(sum(classes[c].weight * a for c, a in composition) - target)
        if amounts[composition] > capacity:
            raise RuntimeError('Восстановление по суммам превысило вместимость типа')
        types.append(TicketType(composition, deviation, capacity))
    return tuple(types), tuple(amounts[t.composition] for t in types)
