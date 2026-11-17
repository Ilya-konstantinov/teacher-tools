"""Проверяемые настройки: CLI > пользовательский JSON > config.json проекта."""
import argparse
from dataclasses import dataclass, fields
import json
import math
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / 'config.json'
# Поддерживаемые границы печатного шаблона, а не значения по умолчанию.
TICKETS_PER_PAGE_RANGE = (1, 8)
MARGIN_MM_RANGE = (5, 40)
FONT_SIZE_RANGE = (8, 18)
# Параметр random_seed в OR-Tools — знаковое 32-битное целое.
MAX_RANDOM_SEED = (1 << 31) - 1


@dataclass(frozen=True)
class GenerationConfig:
    group_mode: str
    objective_mode: str
    algorithm: str
    max_search_nodes: int
    max_dp_states: int
    time_limit: float
    allow_feasible: bool
    output: str


@dataclass(frozen=True)
class SearchConfig:
    dp_work_multiplier: int
    auto_enumeration_work_limit: int
    cp_sat_workers: int
    random_seed: int


@dataclass(frozen=True)
class PrintConfig:
    tickets_per_page: int
    margin_mm: float
    font_size: float
    title: str
    institution: str
    font: str


@dataclass(frozen=True)
class Settings:
    generation: GenerationConfig
    search: SearchConfig
    printing: PrintConfig


def _read(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: ожидается JSON-объект настроек')
    return data


def _section(name, cls, values):
    expected = {f.name: f.type for f in fields(cls)}
    if not isinstance(values, dict) or set(values) != set(expected):
        raise ValueError(f'Некорректные поля секции {name}; допустимы: {", ".join(expected)}')
    for key, kind in expected.items():
        value = values[key]
        valid = type(value) is kind if kind is not float else type(value) in (int, float)
        if not valid:
            raise ValueError(f'{name}.{key}: ожидается {kind.__name__}')
        if kind in (int, float) and not math.isfinite(value):
            raise ValueError(f'{name}.{key}: нужно конечное число')
        if kind is str and not value.strip():
            raise ValueError(f'{name}.{key}: нужна непустая строка')
    return cls(**values)


def validate_printing(options):
    options = _section('printing', PrintConfig, vars(options))
    for key, limits in (('tickets_per_page', TICKETS_PER_PAGE_RANGE),
                        ('margin_mm', MARGIN_MM_RANGE), ('font_size', FONT_SIZE_RANGE)):
        if not limits[0] <= getattr(options, key) <= limits[1]:
            raise ValueError(f'printing.{key}: допустимый диапазон {limits[0]}–{limits[1]}')
    return options


def load_settings(path=None):
    from .problem import ALGORITHMS, GROUP_MODES, OBJECTIVE_MODES

    schemas = {'generation': GenerationConfig, 'search': SearchConfig, 'printing': PrintConfig}
    data = _read(DEFAULT_CONFIG_PATH)
    if set(data) != set(schemas):
        raise ValueError('В config.json нужны секции generation, search, printing')
    for name, cls in schemas.items():
        _section(name, cls, data[name])
    if path is not None and Path(path).resolve() != DEFAULT_CONFIG_PATH.resolve():
        overrides = _read(path)
        for name, values in overrides.items():
            if name not in schemas or not isinstance(values, dict):
                raise ValueError(f'Неизвестная или некорректная секция: {name}')
            data[name] = {**data[name], **values}
    settings = Settings(**{name: _section(name, cls, data[name]) for name, cls in schemas.items()})
    generation, search = settings.generation, settings.search
    for name, choices in (('group_mode', GROUP_MODES), ('objective_mode', OBJECTIVE_MODES), ('algorithm', ALGORITHMS)):
        if getattr(generation, name) not in choices:
            raise ValueError(f'generation.{name}: допустимы {", ".join(choices)}')
    for name in ('max_search_nodes', 'max_dp_states', 'time_limit'):
        if getattr(generation, name) <= 0:
            raise ValueError(f'generation.{name}: нужно положительное число')
    for name in ('dp_work_multiplier', 'auto_enumeration_work_limit', 'cp_sat_workers'):
        if getattr(search, name) <= 0:
            raise ValueError(f'search.{name}: нужно положительное число')
    if not 0 <= search.random_seed <= MAX_RANDOM_SEED:
        raise ValueError(f'search.random_seed: допустимый диапазон 0–{MAX_RANDOM_SEED}')
    validate_printing(settings.printing)
    return settings


def settings_for_cli(parser, argv):
    parser.add_argument('--config', type=Path, help='JSON с переопределениями config.json')
    probe = argparse.ArgumentParser(add_help=False)
    probe.add_argument('--config', type=Path)
    options, _ = probe.parse_known_args(argv)
    try:
        return load_settings(options.config)
    except (OSError, ValueError, OverflowError) as error:
        parser.error(f'Конфигурация: {error}')
