"""Запуск: slotplan schedule --help."""
import argparse
from pathlib import Path

from .allocation import allocate
from .config import settings_for_cli
from .data import MINUTES_PER_HOUR, read_examiners, read_students, timestamp, write_assignments


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(epilog='Другие команды: slotplan workload --help.', description="Распределение студентов на коллоквиум")
    settings = settings_for_cli(parser, argv)
    defaults = settings.schedule
    parser.add_argument("--examiners", type=Path, required=True, help="TSV/CSV с принимающими")
    parser.add_argument("--students", type=Path, required=True, help="TSV/CSV с заявками")
    parser.add_argument("--output", type=Path, default=Path(defaults.output))
    timing = parser.add_mutually_exclusive_group()
    timing.add_argument("--minutes-per-student", type=int, default=defaults.minutes_per_student,
                        help="Минут на проверку одного студента, от 1 до 60")
    timing.add_argument("--capacity", type=int, help="Задать число мест на принимающего в час вручную вместо длительности")
    parser.add_argument("--prep-minutes", type=int, default=defaults.prep_minutes,
                        help="Подготовка между приходом и проверкой")
    parser.add_argument("--deadline", help="Дедлайн в формате 'ДД.ММ.ГГГГ ЧЧ:ММ:СС'; все даты в одном часовом поясе")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.minutes_per_student <= MINUTES_PER_HOUR:
            raise ValueError("Длительность проверки должна быть от 1 до 60 минут")
        capacity = args.capacity if args.capacity is not None else MINUTES_PER_HOUR // args.minutes_per_student
        if args.output.resolve() in (args.examiners.resolve(), args.students.resolve()):
            raise ValueError("Результат нельзя записывать поверх входной таблицы")
        result = allocate(read_students(args.students), read_examiners(args.examiners),
                          capacity, timestamp(args.deadline) if args.deadline else None,
                          batch_minutes=args.minutes_per_student if args.capacity is None else None,
                          prep_minutes=args.prep_minutes)
        write_assignments(args.output, result)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    assigned = sum(item.hour is not None for item in result)
    print(f"Распределено: {assigned}/{len(result)}. Не распределено: {len(result) - assigned}. Файл: {args.output}")


if __name__ == "__main__":
    main()
