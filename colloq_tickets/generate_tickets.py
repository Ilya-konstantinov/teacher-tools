"""Генерация билетов коллоквиума."""
from pathlib import Path

from src.cli import bootstrap, main


if __name__ == '__main__':
    bootstrap(Path(__file__).resolve())
    main()
