"""Schedule models, application parsing, and result serialization."""
import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR
PREFERENCE_COUNT = 3
# The first three preferences have penalties 0, 1, and 2, followed by any available slot.
OUTSIDE_PREFERENCE_PENALTY = PREFERENCE_COUNT
UNASSIGNED_PENALTY = OUTSIDE_PREFERENCE_PENALTY + 1
PRIORITY_RADIX = UNASSIGNED_PENALTY + 1
CSV_SNIFF_BYTES = 8192
TIMESTAMP_FORMATS = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S",
                     "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S")


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


def read_table(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(CSV_SNIFF_BYTES)
        stream.seek(0)
        # In TSV, commas inside an hour list do not separate columns.
        delimiter = "\t" if "\t" in sample else ";" if ";" in sample else ","
        return [[cell.strip() for cell in row] for row in csv.reader(stream, delimiter=delimiter)
                if any(cell.strip() for cell in row)]


def hour(value: str) -> int:
    if not re.fullmatch(r"\d{1,2}(?::00)?", value.strip()):
        raise ValueError(f"Некорректный час: {value!r}")
    result = int(value.split(":")[0])
    if not 0 <= result < HOURS_PER_DAY:
        raise ValueError(f"Час вне диапазона 0–23: {value!r}")
    return result


def hours(value: str) -> tuple[int, ...]:
    return tuple(dict.fromkeys(hour(part.strip()) for part in value.split(","))) if value.strip() else ()


def timestamp(value: str) -> datetime:
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Некорректное время заявки: {value!r}; ожидается ДД.ММ.ГГГГ ЧЧ:ММ:СС")


def read_examiners(path: Path) -> list[Examiner]:
    rows = read_table(path)
    if not rows:
        raise ValueError("Пустая таблица принимающих")
    result = []
    names = set()
    for number, row in enumerate(rows[1:], 2):
        if len(row) != 2 or not row[0]:
            raise ValueError(f"Принимающие, строка {number}: нужны ФИО и список часов")
        if row[0] in names:
            raise ValueError(f"Повтор принимающего: {row[0]}")
        names.add(row[0])
        result.append(Examiner(row[0], hours(row[1])))
    return result


def read_students(path: Path) -> list[Student]:
    rows = read_table(path)
    if not rows:
        raise ValueError("Пустая таблица студентов")
    header = [cell.casefold() for cell in rows[0]]
    required = ["фио", "группа", *(f"приоритет {i}" for i in range(1, PREFERENCE_COUNT + 1)),
                "в какое время вы точно не сможете"]
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError("Нет колонок: " + ", ".join(missing))
    indices = [header.index(name) for name in required]
    time_index = next((header.index(name) for name in ("время заявки", "отметка времени") if name in header), None)
    result = []
    seen = set()
    for number, row in enumerate(rows[1:], 2):
        if len(row) > len(header):
            raise ValueError(f"Студенты, строка {number}: лишние колонки")
        row += [""] * (len(header) - len(row))
        name, group, *rest = [row[i] for i in indices]
        if not name or not group:
            raise ValueError(f"Студенты, строка {number}: нужны ФИО и группа")
        if (name, group) in seen:
            raise ValueError(f"Повтор студента: {name}, группа {group}")
        seen.add((name, group))
        result.append(Student(name, group, tuple(hour(v) if v else None for v in rest[:PREFERENCE_COUNT]),
                              frozenset(hours(rest[PREFERENCE_COUNT])), timestamp(row[time_index]) if time_index is not None else None))
    return result


def write_assignments(path: Path, assignments: list[Assignment]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["Время прихода", "ФИО", "Группа", "Приоритет", "Причина"])
        for item in sorted(assignments, key=lambda a: (a.start_minute if a.start_minute is not None else MINUTES_PER_DAY,
                                                       a.student.name, a.student.group)):
            student = item.student
            start = item.start_minute
            writer.writerow([f"{start // MINUTES_PER_HOUR:02d}:{start % MINUTES_PER_HOUR:02d}" if start is not None else "",
                             student.name, student.group,
                             item.priority if item.priority is not None else "", item.reason])
