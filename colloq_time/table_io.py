"""Чтение UTF-8 TSV/CSV и запись результата; алгоритм не зависит от файлов."""
import csv
import re
from datetime import datetime
from pathlib import Path

from models import Assignment, Examiner, Student


def read_table(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        # В TSV запятые внутри списка часов не являются разделителями колонок.
        delimiter = "\t" if "\t" in sample else ";" if ";" in sample else ","
        return [[cell.strip() for cell in row] for row in csv.reader(stream, delimiter=delimiter)
                if any(cell.strip() for cell in row)]


def hour(value: str) -> int:
    if not re.fullmatch(r"\d{1,2}(?::00)?", value.strip()):
        raise ValueError(f"Некорректный час: {value!r}")
    result = int(value.split(":")[0])
    if not 0 <= result <= 23:
        raise ValueError(f"Час вне диапазона 0–23: {value!r}")
    return result


def hours(value: str) -> tuple[int, ...]:
    return tuple(dict.fromkeys(hour(part.strip()) for part in value.split(","))) if value.strip() else ()


def timestamp(value: str) -> datetime:
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
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
    required = ["фио", "группа", "приоритет 1", "приоритет 2", "приоритет 3",
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
        result.append(Student(name, group, tuple(hour(v) if v else None for v in rest[:3]),
                              frozenset(hours(rest[3])), timestamp(row[time_index]) if time_index is not None else None))
    return result


def write_assignments(path: Path, assignments: list[Assignment]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["Время прихода", "ФИО", "Группа", "Приоритет", "Причина"])
        for item in sorted(assignments, key=lambda a: (a.start_minute if a.start_minute is not None else 1440,
                                                       a.student.name, a.student.group)):
            student = item.student
            start = item.start_minute
            writer.writerow([f"{start // 60:02d}:{start % 60:02d}" if start is not None else "",
                             student.name, student.group,
                             item.priority if item.priority is not None else "", item.reason])
