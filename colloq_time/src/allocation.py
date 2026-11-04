"""Максимальный поток минимальной стоимости без сторонних зависимостей."""
from dataclasses import dataclass
from datetime import datetime
from heapq import heappop, heappush

from .models import Assignment, Examiner, Student


@dataclass
class Edge:
    to: int
    reverse: int
    capacity: int
    cost: int


def batch_capacities(examiners: list[Examiner], capacity: int, batch_minutes: int,
                     prep_minutes: int) -> dict[int, int]:
    """Мест в батче = принимающие, доступные на всей проверке [start, end)."""
    available_hours = {h for examiner in examiners for h in examiner.hours}
    if not available_hours:
        return {}
    result = {}
    for h in range(min(available_hours), max(available_hours) + 1):
        for batch in range(capacity):
            arrival = h * 60 + batch * batch_minutes
            start = arrival + prep_minutes
            end = start + batch_minutes
            needed_hours = set(range(start // 60, (end - 1) // 60 + 1))
            count = sum(needed_hours <= set(e.hours) for e in examiners)
            if count:
                result[arrival] = count
    return result


def allocate(students: list[Student], examiners: list[Examiner], capacity: int = 2,
             deadline: datetime | None = None, *, batch_minutes: int | None = None,
             prep_minutes: int = 0) -> list[Assignment]:
    if not 1 <= capacity <= 60:
        raise ValueError("Вместимость должна быть от 1 до 60")
    if batch_minutes is None:
        batch_minutes = 60 // capacity
    if not 1 <= batch_minutes <= 60 or capacity * batch_minutes > 60:
        raise ValueError("Все проверки одного принимающего должны укладываться в час")
    if not isinstance(prep_minutes, int) or prep_minutes < 0:
        raise ValueError("Время подготовки должно быть неотрицательным целым числом")
    if any(s.submitted_at is None for s in students) and (
        deadline is not None or any(s.submitted_at is not None for s in students)
    ):
        raise ValueError("Для дедлайна и сортировки по времени нужны даты всех заявок")
    n = len(students)
    order = sorted(range(n), key=lambda i: (students[i].submitted_at or datetime.min, i))
    ranks = {index: rank for rank, index in enumerate(order)}
    late = [deadline is not None and s.submitted_at > deadline for s in students]
    # Проверки соседних батчей не пересекаются; подготовка сдвигает их все
    # одинаково. Поэтому вместимость каждого батча можно считать независимо.
    capacity_by_batch = batch_capacities(examiners, capacity, batch_minutes, prep_minutes)
    arrivals = sorted(capacity_by_batch)
    source, sink = n + len(arrivals), n + len(arrivals) + 1
    graph: list[list[Edge]] = [[] for _ in range(sink + 1)]

    def add(a: int, b: int, cap: int, cost: int) -> Edge:
        edge = Edge(b, len(graph[b]), cap, cost)
        graph[a].append(edge)
        graph[b].append(Edge(a, len(graph[a]) - 1, 0, -cost))
        return edge

    # Разряды по основанию 5 дают точное преимущество ранним заявкам,
    # а не приблизительную сумму весов. Нераспределение имеет ранг 4.
    scale = 5 ** n
    late_cost = (3 * n + 1) * scale
    # После всех критериев по приоритетам более ранние заявки получают
    # более раннее время прихода. Младшие разряды не меняют прежнюю оптимизацию.
    time_base = len(arrivals) + 1
    time_scale = time_base ** n
    choices: list[list[tuple[Edge, int, int]]] = [[] for _ in students]
    for j, arrival in enumerate(arrivals):
        add(n + j, sink, capacity_by_batch[arrival], 0)
    for i, student in enumerate(students):
        add(source, i, 1, 0)
        weight = 5 ** (n - ranks[i] - 1)
        time_weight = time_base ** (n - ranks[i] - 1)
        for j, arrival in enumerate(arrivals):
            h = arrival // 60
            # Студент присутствует от прихода до конца проверки, включая
            # подготовку. Запрет любого пересечённого часа исключает батч.
            end = arrival + prep_minutes + batch_minutes
            attendance_hours = range(h, (end - 1) // 60 + 1)
            if any(hour in student.unavailable for hour in attendance_hours):
                continue
            penalty = student.priorities.index(h) if h in student.priorities and not late[i] else 3
            cost = penalty * scale + (penalty - 4) * weight + (late_cost if late[i] else 0)
            cost = cost * time_scale + j * time_weight
            choices[i].append((add(i, n + j, 1, cost), arrival, penalty))

    # Начальный граф — DAG: источник → студенты → батчи → сток.
    # Нулевые начальные значения эквивалентны дополнительному источнику
    # с нулевыми рёбрами ко всем вершинам, включая недостижимые.
    # Один проход даёт допустимые потенциалы за O(V + E).
    potentials = [0] * len(graph)
    for node in [source, *range(source), sink]:
        for edge in graph[node]:
            if edge.capacity:
                potentials[edge.to] = min(potentials[edge.to], potentials[node] + edge.cost)

    # Остаточные рёбра позволяют пересмотреть уже сделанные назначения.
    while True:
        distances: list[int | None] = [None] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distances[source] = 0
        queue = [(0, source)]
        while queue:
            current, node = heappop(queue)
            if current != distances[node]:
                continue
            for index, edge in enumerate(graph[node]):
                if not edge.capacity:
                    continue
                # Приведённая стоимость неотрицательна для достижимых рёбер.
                distance = current + edge.cost + potentials[node] - potentials[edge.to]
                if distances[edge.to] is None or distance < distances[edge.to]:
                    distances[edge.to] = distance
                    previous[edge.to] = node, index
                    heappush(queue, (distance, edge.to))
        if previous[sink] is None:
            break
        # Дейкстра проходит все достижимые вершины, поэтому расстояния
        # здесь окончательные, а новые потенциалы снова допустимы.
        for node, distance in enumerate(distances):
            if distance is not None:
                potentials[node] += distance
        node = sink
        while node != source:
            parent, index = previous[node]
            edge = graph[parent][index]
            edge.capacity -= 1
            graph[node][edge.reverse].capacity += 1
            node = parent

    result = []
    for i, student in enumerate(students):
        selected = next((choice for choice in choices[i] if choice[0].capacity == 0), None)
        if selected:
            _, arrival, penalty = selected
            result.append(Assignment(student, arrival // 60, penalty + 1 if penalty < 3 else None,
                                     "После дедлайна: пожелания не учитывались" if late[i] else "",
                                     arrival))
        else:
            reason = "Нет допустимых часов приёма" if not choices[i] else "Недостаточно мест с учётом приоритетов"
            result.append(Assignment(student, None, None, reason))
    return result
