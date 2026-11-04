"""Вспомогательные команды для расписания: нагрузка и тесты."""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('workload', add_help=False, help='Отчёт нагрузки по готовому расписанию')
    commands.add_parser('test', help='Запуск тестов распределения')
    args, remaining = parser.parse_known_args()
    if args.command == 'workload':
        from src.workload import main as report_workload
        report_workload(remaining)
    else:
        if remaining:
            parser.error('Неизвестные параметры: ' + ' '.join(remaining))
        import unittest
        root = Path(__file__).resolve().parent
        unittest.main(module=None, argv=[sys.argv[0], 'discover', '-s', str(root/'tests'), '-v'])


if __name__ == '__main__':
    main()
