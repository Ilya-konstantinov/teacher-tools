"""Восстановление разных билетов из плана типов или сумм."""
from collections import Counter
from heapq import heapify, heappop, heappush
from itertools import combinations, islice
from math import comb, prod
from random import Random
from .models import GenerationResult, Ticket, TicketPlan, TicketType


HEAP_REBUILD_FACTOR = 4  # Ограничивает накопление устаревших элементов ленивых куч.


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
    rng = Random(sum_plan.random_seed)
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


def _combinations_for_type(classes, composition):
    """Ленивое произведение combinations без материализации его факторов."""
    iterators = [iter(combinations(classes[composition[0][0]].members, composition[0][1]))]
    parts = []
    while iterators:
        part = next(iterators[-1], None)
        if part is None:
            iterators.pop()
            if parts:
                parts.pop()
            continue
        level = len(iterators)
        if level == len(composition):
            yield frozenset(i for block in (*parts, part) for i in block)
        else:
            parts.append(part)
            index, amount = composition[level]
            iterators.append(iter(combinations(classes[index].members, amount)))


def realize(questions, classes, pool, amounts):
    """Восстановить билеты и достичь точной стоимости F_s(D) каждого класса.

    Если deg(u)>deg(v)+1 внутри класса, среди билетов с u без v есть билет,
    замена u→v в котором ещё не выбрана. Иначе инъекция этих билетов в билеты
    с v без u противоречит неравенству степеней. Замена сохраняет тип и
    уникальность и уменьшает сумму квадратов. Другие классы не меняются.
    """
    if len(pool) != len(amounts):
        raise ValueError("Число типов и число количеств в плане не совпадают")
    # Стабильный ID билета позволяет при замене обновлять только два
    # вопроса, а не переписывать индексы всех неизменившихся участников.
    tickets = []
    selected = {}
    occurrences = [{} for _ in questions]  # упорядоченные множества ID
    for pattern, amount in zip(pool, amounts):
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= pattern.capacity:
            raise ValueError("Некорректное количество билетов типа")
        for ticket in islice(_combinations_for_type(classes, pattern.composition), amount):
            if ticket in selected:
                raise RuntimeError("Повтор билета при восстановлении типов")
            index = len(tickets)
            selected[ticket] = index
            tickets.append(ticket)
            for i in sorted(ticket):
                occurrences[i][index] = None
    if len(tickets) != sum(amounts):
        raise RuntimeError("Не удалось восстановить различные билеты")
    degrees = [len(items) for items in occurrences]
    for item in classes:
        lows = [(degrees[i], i) for i in item.members]
        highs = [(-degrees[i], i) for i in item.members]
        heapify(lows)
        heapify(highs)
        while True:
            while lows[0][0] != degrees[lows[0][1]]:
                heappop(lows)
            while -highs[0][0] != degrees[highs[0][1]]:
                heappop(highs)
            low, high = lows[0][1], highs[0][1]
            if degrees[high] - degrees[low] <= 1:
                break
            # Порядок dict воспроизводим, сортировка билетов на каждой замене
            # не нужна. Индексы остальных вопросов сохраняют тот же ID.
            for index in occurrences[high]:
                ticket = tickets[index]
                if low in ticket:
                    continue
                replacement = (ticket - {high}) | {low}
                if replacement not in selected:
                    break
            else:
                raise RuntimeError("Нарушен инвариант балансировки класса")
            del selected[ticket]
            selected[replacement] = index
            tickets[index] = replacement
            del occurrences[high][index]
            occurrences[low][index] = None
            degrees[high] -= 1
            degrees[low] += 1
            for i in (low, high):
                heappush(lows, (degrees[i], i))
                heappush(highs, (-degrees[i], i))
            # Ограничиваем память ленивых куч; перестроение амортизировано.
            if max(len(lows), len(highs)) > HEAP_REBUILD_FACTOR * len(item.members):
                lows = [(degrees[i], i) for i in item.members]
                highs = [(-degrees[i], i) for i in item.members]
                heapify(lows)
                heapify(highs)
    return [Ticket(tuple(questions[i] for i in indices))
            for indices in sorted(tuple(sorted(ticket)) for ticket in tickets)]


def restore_tickets(plan: TicketPlan) -> GenerationResult:
    """Подставить вопросы, сохранив количества типов и оптимальные частоты.

    Не запускает оптимизатор. Один план можно восстановить повторно.
    """
    selection = plan.selection
    if selection.sum_plan is not None:

        types, amounts = materialize_types(selection.sum_plan, plan.classes,
                                           plan.ticket_count, plan.target_weight)
    else:
        types, amounts = selection.types, selection.amounts
    if len(types) != len(amounts):
        raise ValueError("Число типов и число количеств в плане не совпадают")
    if sum(amounts) != plan.ticket_count:
        raise ValueError("Число билетов в плане не совпадает с запрошенным")
    tickets = realize(plan.questions, plan.classes, types, amounts)
    diagnostics = dict(selection.diagnostics)
    diagnostics["selected_ticket_types"] = sum(amount > 0 for amount in amounts)
    return GenerationResult(tickets, selection.algorithm, selection.optimal,
                            selection.proven_objectives,
                            weight_classes=len({c.weight for c in plan.classes}),
                            question_classes=len(plan.classes),
                            ticket_types=len(types) if selection.types_enumerated else None,
                            objective_mode=selection.objective_mode,
                            objective_count=selection.objective_count,
                            frequency_guarantee=selection.frequency_guarantee,
                            diagnostics=diagnostics)
