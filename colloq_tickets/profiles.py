"""Профили тем: одинаковые гистограммы весов с сохранением исходных классов."""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class TopicProfile:
    histogram: tuple[tuple[Fraction, int], ...]
    # Одна строка на исходную тему; классы в порядке весов гистограммы.
    members: tuple[tuple[int, ...], ...]


def group_profiles(classes):
    topics = defaultdict(list)
    for index, item in enumerate(classes):
        topics[item.group].append(index)
    profiles = {}
    for indices in topics.values():
        indices.sort(key=lambda c: classes[c].weight)
        histogram = tuple((classes[c].weight, len(classes[c].members)) for c in indices)
        profiles.setdefault(histogram, []).append(tuple(indices))
    return tuple(TopicProfile(histogram, tuple(members)) for histogram, members in profiles.items())
