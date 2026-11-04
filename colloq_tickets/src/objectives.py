"""Единые определения строгих целей и гарантий результата."""
from dataclasses import replace
from types import MappingProxyType


OBJECTIVES = MappingProxyType({
    'weight-first': ('max_weight_deviation', 'total_weight_deviation'),
    'balanced': ('max_weight_deviation', 'frequency_squares', 'total_weight_deviation'),
})
OBJECTIVE_MODES = tuple(OBJECTIVES)


def priority_score(mode, frequency, deviation):
    """Порядок оставшихся целей после фиксации минимакса.

    В weight-first точные решатели могут использовать частоты лишь для
    разрешения равенства по сложности; публичная гарантия — две цели.
    """
    return (frequency, deviation) if mode == 'balanced' else (deviation, frequency)


def describe_selection(selection, mode):
    count = len(OBJECTIVES[mode])
    proven = count if selection.optimal else min(selection.proven_objectives, count)
    frequency = ('global-optimum' if mode == 'balanced' and proven >= 2 else 'within-class')
    return replace(selection, objective_mode=mode, objective_count=count,
                   proven_objectives=proven, frequency_guarantee=frequency)
