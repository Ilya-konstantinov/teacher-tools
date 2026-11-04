"""Восстановление конкретных билетов из независимо вычисленного плана."""
from itertools import combinations, islice
from heapq import heapify, heappop, heappush

from .models import GenerationResult, Ticket, TicketPlan


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
            if max(len(lows), len(highs)) > 4 * len(item.members):
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
        from .sum_reconstruction import materialize_types
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
