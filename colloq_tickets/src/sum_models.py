"""Неизменяемые узлы считающей DP и план выбора сумм."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping

from .profiles import TopicProfile


@dataclass(frozen=True)
class SumNode:
    kind: str
    table: Mapping[tuple[int, Fraction], int]
    children: tuple[SumNode, ...] = ()
    profile: int = -1
    copies: int = 1
    layers: tuple[Mapping[tuple[int, Fraction], int], ...] = ()


@dataclass(frozen=True)
class SumPlan:
    root: SumNode
    profiles: tuple[TopicProfile, ...]
    amounts: tuple[tuple[Fraction, int], ...]
    size: int
