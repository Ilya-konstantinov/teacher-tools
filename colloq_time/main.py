"""Единая точка входа: расписание, отчёт нагрузки и тесты."""
from pathlib import Path
import sys


def main():
    args = sys.argv[1:]
    if args in (['test'], ['--test']):
        import unittest
        root = Path(__file__).resolve().parent
        unittest.main(module=None, argv=[sys.argv[0], 'discover', '-s', str(root/'tests'), '-v'])
    elif args and args[0] == 'workload':
        from src.workload import main as workload_main
        workload_main(args[1:])
    else:
        from src.cli import main as schedule_main
        schedule_main(args[1:] if args and args[0] == 'schedule' else args)


if __name__ == '__main__':
    main()
