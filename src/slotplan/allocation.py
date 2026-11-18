"""Compute a minimum-cost maximum flow using only the standard library."""
from dataclasses import dataclass
from datetime import datetime
from heapq import heappop, heappush

from .data import (Assignment, Examiner, Student, MINUTES_PER_HOUR,
                   OUTSIDE_PREFERENCE_PENALTY, UNASSIGNED_PENALTY, PRIORITY_RADIX)

# Python API compatibility defaults. The CLI reads config.json.
DEFAULT_API_CAPACITY = 2
DEFAULT_API_PREP_MINUTES = 0


@dataclass
class Edge:
    to: int
    reverse: int
    capacity: int
    cost: int


def batch_capacities(examiners: list[Examiner], capacity: int, batch_minutes: int,
                     prep_minutes: int) -> dict[int, int]:
    """Count examiners available throughout the examination interval [start, end)."""
    available_hours = {h for examiner in examiners for h in examiner.hours}
    if not available_hours:
        return {}
    result = {}
    for h in range(min(available_hours), max(available_hours) + 1):
        for batch in range(capacity):
            arrival = h * MINUTES_PER_HOUR + batch * batch_minutes
            start = arrival + prep_minutes
            end = start + batch_minutes
            needed_hours = set(range(start // MINUTES_PER_HOUR, (end - 1) // MINUTES_PER_HOUR + 1))
            count = sum(needed_hours <= set(e.hours) for e in examiners)
            if count:
                result[arrival] = count
    return result


def allocate(students: list[Student], examiners: list[Examiner], capacity: int = DEFAULT_API_CAPACITY,
             deadline: datetime | None = None, *, batch_minutes: int | None = None,
             prep_minutes: int = DEFAULT_API_PREP_MINUTES) -> list[Assignment]:
    if not 1 <= capacity <= MINUTES_PER_HOUR:
        raise ValueError("Вместимость должна быть от 1 до 60")
    if batch_minutes is None:
        batch_minutes = MINUTES_PER_HOUR // capacity
    if not 1 <= batch_minutes <= MINUTES_PER_HOUR or capacity * batch_minutes > MINUTES_PER_HOUR:
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
    # Adjacent batches have disjoint examinations, and preparation shifts all
    # of them equally. Each batch capacity can therefore be computed independently.
    capacity_by_batch = batch_capacities(examiners, capacity, batch_minutes, prep_minutes)
    arrivals = sorted(capacity_by_batch)
    source, sink = n + len(arrivals), n + len(arrivals) + 1
    graph: list[list[Edge]] = [[] for _ in range(sink + 1)]

    def add(a: int, b: int, cap: int, cost: int) -> Edge:
        edge = Edge(b, len(graph[b]), cap, cost)
        graph[a].append(edge)
        graph[b].append(Edge(a, len(graph[a]) - 1, 0, -cost))
        return edge

    # Digits in base PRIORITY_RADIX give earlier applications strict priority.
    # Unassigned students receive the worst rank, UNASSIGNED_PENALTY.
    scale = PRIORITY_RADIX ** n
    late_cost = (OUTSIDE_PREFERENCE_PENALTY * n + 1) * scale
    # Once preference criteria tie, assign earlier arrival times to earlier applicants.
    # Lower-order digits preserve the priority of all preceding criteria.
    time_base = len(arrivals) + 1
    time_scale = time_base ** n
    choices: list[list[tuple[Edge, int, int]]] = [[] for _ in students]
    for j, arrival in enumerate(arrivals):
        add(n + j, sink, capacity_by_batch[arrival], 0)
    for i, student in enumerate(students):
        add(source, i, 1, 0)
        weight = PRIORITY_RADIX ** (n - ranks[i] - 1)
        time_weight = time_base ** (n - ranks[i] - 1)
        for j, arrival in enumerate(arrivals):
            h = arrival // MINUTES_PER_HOUR
            # Students must be available from arrival through preparation and examination.
            # An unavailable hour anywhere in that interval rules out the batch.
            end = arrival + prep_minutes + batch_minutes
            attendance_hours = range(h, (end - 1) // MINUTES_PER_HOUR + 1)
            if any(hour in student.unavailable for hour in attendance_hours):
                continue
            penalty = student.priorities.index(h) if h in student.priorities and not late[i] else OUTSIDE_PREFERENCE_PENALTY
            cost = penalty * scale + (penalty - UNASSIGNED_PENALTY) * weight + (late_cost if late[i] else 0)
            cost = cost * time_scale + j * time_weight
            choices[i].append((add(i, n + j, 1, cost), arrival, penalty))

    # The initial graph is a DAG: source -> students -> batches -> sink.
    # Initializing to zero is equivalent to adding a source with zero-cost
    # edges to every vertex, including unreachable ones.
    # One pass yields feasible potentials in O(V + E).
    potentials = [0] * len(graph)
    for node in [source, *range(source), sink]:
        for edge in graph[node]:
            if edge.capacity:
                potentials[edge.to] = min(potentials[edge.to], potentials[node] + edge.cost)

    # Residual edges allow earlier assignments to be revised.
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
                # Reduced costs are nonnegative on reachable edges.
                distance = current + edge.cost + potentials[node] - potentials[edge.to]
                if distances[edge.to] is None or distance < distances[edge.to]:
                    distances[edge.to] = distance
                    previous[edge.to] = node, index
                    heappush(queue, (distance, edge.to))
        if previous[sink] is None:
            break
        # Dijkstra visits every reachable vertex, so these distances are final
        # and the updated potentials are feasible.
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
            result.append(Assignment(student, arrival // MINUTES_PER_HOUR, penalty + 1 if penalty < OUTSIDE_PREFERENCE_PENALTY else None,
                                     "После дедлайна: пожелания не учитывались" if late[i] else "",
                                     arrival))
        else:
            reason = "Нет допустимых часов приёма" if not choices[i] else "Недостаточно мест с учётом приоритетов"
            result.append(Assignment(student, None, None, reason))
    return result
