from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Examiner:
    name: str
    hours: tuple[int, ...]


@dataclass(frozen=True)
class Student:
    name: str
    group: str
    priorities: tuple[int | None, ...]
    unavailable: frozenset[int]
    submitted_at: datetime | None = None


@dataclass(frozen=True)
class Assignment:
    student: Student
    hour: int | None
    priority: int | None
    reason: str = ""
    start_minute: int | None = None
