"""Единая точка входа: генерация, печать и тесты."""
from pathlib import Path
import sys


def main():
    from src.runtime import bootstrap

    root = Path(__file__).resolve().parent
    bootstrap(root)
    args = sys.argv[1:]
    if args in (['test'], ['--test']):
        import unittest
        unittest.main(module=None, argv=[sys.argv[0], 'discover', '-s', str(root/'tests'), '-v'])
    elif args and args[0] == 'print':
        from src.print_tickets import main as print_main
        print_main(args[1:])
    else:
        from src.cli import main as generate_main
        generate_main(args[1:] if args and args[0] == 'generate' else args)


if __name__ == '__main__':
    main()
