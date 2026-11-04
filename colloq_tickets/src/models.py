"""Модели вопросов, типов, профилей и планов билетов."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Mapping


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    weight: float
    group: str = "default"


@dataclass(frozen=True)
class Ticket:
    questions: tuple[Question, ...]

    @property
    def total_weight(self) -> float:
        return sum(question.weight for question in self.questions)


@dataclass(frozen=True)
class QuestionClass:
    members: tuple[int, ...]
    weight: Fraction
    group: str


@dataclass(frozen=True)
class TicketType:
    composition: tuple[tuple[int, int], ...]
    deviation: Fraction
    capacity: int


@dataclass(frozen=True)
class TypeSelection:
    types: tuple[TicketType, ...]
    amounts: tuple[int, ...]
    algorithm: str
    optimal: bool = True
    proven_objectives: int = 3
    types_enumerated: bool = True
    objective_mode: str = "balanced"
    objective_count: int = 3
    frequency_guarantee: str = "global-optimum"
    diagnostics: dict = field(default_factory=dict)
    sum_plan: SumPlan | None = None


@dataclass(frozen=True)
class TicketPlan:
    """Снимок входа и результат выбора типов, без конкретных билетов."""
    questions: tuple[Question, ...]
    classes: tuple[QuestionClass, ...]
    selection: TypeSelection
    questions_per_ticket: int
    ticket_count: int
    group_mode: str
    target_weight: Fraction


@dataclass(frozen=True)
class GenerationResult:
    tickets: list[Ticket]
    algorithm: str
    optimal: bool = True
    proven_objectives: int = 3
    weight_classes: int = 0
    question_classes: int = 0
    ticket_types: int | None = None
    objective_mode: str = "balanced"
    objective_count: int = 3
    frequency_guarantee: str = "global-optimum"
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TopicProfile:
    histogram: tuple[tuple[Fraction, int], ...]
    # Одна строка на исходную тему; классы в порядке весов гистограммы.
    members: tuple[tuple[int, ...], ...]


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
