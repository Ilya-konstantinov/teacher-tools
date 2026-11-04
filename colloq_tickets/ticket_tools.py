"""Вспомогательные команды для билетов: печать и тесты."""
import argparse
from pathlib import Path
import sys

from src.cli import bootstrap


def main():
    entry = Path(__file__).resolve()
    bootstrap(entry)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('print', add_help=False, help='Экспорт готовых билетов в TeX')
    commands.add_parser('test', help='Запуск тестов генератора и печати')
    args, remaining = parser.parse_known_args()
    if args.command == 'print':
        from src.printing import main as print_tickets
        print_tickets(remaining)
    else:
        if remaining:
            parser.error('Неизвестные параметры: ' + ' '.join(remaining))
        import unittest
        unittest.main(module=None, argv=[sys.argv[0], 'discover', '-s', str(entry.parent/'tests'), '-v'])


if __name__ == '__main__':
    main()
