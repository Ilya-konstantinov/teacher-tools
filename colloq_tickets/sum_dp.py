"""Построение ограниченных по ресурсам таблиц способов, без выбора билетов."""
from collections import defaultdict
from fractions import Fraction
from types import MappingProxyType

from profiles import group_profiles
from sum_models import SumNode
from ticket_types import SearchLimit


class SumTableBuilder:
    def __init__(self, size, budget):
        self.size = size
        self.budget = budget
        self.states = 0
        self.transitions = 0
        self.products = {}

    def step(self):
        self.transitions += 1
        if self.transitions > 10 * self.budget:
            raise SearchLimit('Превышен бюджет переходов DP по суммам')

    def freeze(self, table):
        self.states += len(table)
        if self.states > self.budget:
            raise SearchLimit('Превышен лимит сохранённых состояний DP по суммам')
        return MappingProxyType(dict(table))

    def check(self, table):
        # Проверяем и временную таблицу, не только завершённые слои.
        if self.states + len(table) > self.budget:
            raise SearchLimit('Превышен лимит сохранённых состояний DP по суммам')

    def topic(self, index, profile, mode, mandatory):
        if mode == 'different':
            table = {(1, weight): count for weight, count in profile.histogram}
            if not mandatory:
                table[(0, Fraction(0))] = 1
            return SumNode('topic', self.freeze(table), profile=index)
        layers = [self.freeze({(0, Fraction(0)): 1})]
        for weight, count in profile.histogram:
            table = defaultdict(int)
            maximum = min(count, self.size)
            if self.states + maximum + 1 > self.budget:
                raise SearchLimit('Превышен лимит сохранённых состояний DP по суммам')
            choices = [(0, 1)]
            capacity = 1
            for amount in range(1, maximum + 1):
                capacity = capacity * (count - amount + 1) // amount
                choices.append((amount, capacity))
            for (taken, total), ways in layers[-1].items():
                for amount, capacity in choices:
                    self.step()
                    if taken + amount > self.size:
                        break
                    table[taken + amount, total + amount * weight] += ways * capacity
                    self.check(table)
            layers.append(self.freeze(table))
        # Слои нужны для восстановления; последняя таблица не копируется.
        return SumNode('subset', layers[-1], profile=index, layers=tuple(layers))

    def product(self, left, right, repeated=False):
        key = (id(left), id(right), repeated)
        if key in self.products:
            return self.products[key]
        table = defaultdict(int)
        for (a, wa), ca in left.table.items():
            for (b, wb), cb in right.table.items():
                self.step()
                if a + b <= self.size:
                    table[a + b, wa + wb] += ca * cb
                    self.check(table)
        result = SumNode('repeat' if repeated else 'product', self.freeze(table),
                         (left, right), copies=left.copies + right.copies)
        self.products[key] = result
        return result

    def power(self, leaf, copies):
        # Один и тот же узел степени переиспользуется: число копий не означает
        # столько же одинаковых таблиц. Двоичное возведение в степень.
        cache = {1: leaf}
        def build(count):
            if count in cache:
                return cache[count]
            half = build(count // 2)
            value = self.product(half, half, repeated=True)
            if count % 2:
                value = self.product(value, leaf, repeated=True)
            cache[count] = value
            return value
        return build(copies)


def build_sum_table(classes, size, mode, max_states):
    profiles = group_profiles(classes)
    builder = SumTableBuilder(size, max_states)
    topic_count = sum(len(p.members) for p in profiles)
    mandatory = mode == 'different' and size == topic_count
    nodes = []
    for index, profile in enumerate(profiles):
        if mode == 'same' and sum(c for _, c in profile.histogram) < size:
            continue
        leaf = builder.topic(index, profile, mode, mandatory)
        copies = len(profile.members)
        if mode == 'different':
            nodes.append(builder.power(leaf, copies))
        elif mode == 'same':
            table = {key: value * copies for key, value in leaf.table.items() if key[0] == size}
            nodes.append(SumNode('copies', builder.freeze(table), (leaf,), copies=copies))
        else:
            nodes.append(leaf)
    if not nodes:
        raise ValueError('Нельзя составить билет указанного размера с этими группами')
    if mode == 'same':
        table = defaultdict(int)
        for node in nodes:
            for key, value in node.table.items():
                builder.step()
                table[key] += value
                builder.check(table)
        root = SumNode('choice', builder.freeze(table), tuple(nodes))
    else:
        # Соединяем соседние блоки сбалансированным деревом: восстановление
        # не упирается в рекурсивную глубину по числу исходных тем.
        while len(nodes) > 1:
            nodes = [builder.product(nodes[i], nodes[i + 1]) if i + 1 < len(nodes) else nodes[i]
                     for i in range(0, len(nodes), 2)]
        root = nodes[0]
    diagnostics = {"topic_profiles": len(profiles), "effective_topics": topic_count,
                   "sum_states": builder.states, "sum_transitions": builder.transitions}
    return root, profiles, diagnostics
