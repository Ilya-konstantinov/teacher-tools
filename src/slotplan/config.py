"""Schedule and workload settings share a single examination duration."""
import argparse
from dataclasses import dataclass, fields
import json
import math
from pathlib import Path
import re

from .data import MINUTES_PER_HOUR

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / 'config.json'


@dataclass(frozen=True)
class ScheduleConfig:
    minutes_per_student: int
    prep_minutes: int
    output: str


@dataclass(frozen=True)
class WorkloadConfig:
    output: str
    warning_ratio: float
    overload_color: str
    warning_color: str
    normal_color: str
    idle_color: str


@dataclass(frozen=True)
class Settings:
    schedule: ScheduleConfig
    workload: WorkloadConfig


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


def load_settings(path=None):
    schemas = {'schedule': ScheduleConfig, 'workload': WorkloadConfig}
    data = _read(DEFAULT_CONFIG_PATH)
    if set(data) != set(schemas):
        raise ValueError('В config.json нужны секции schedule, workload')
    for name, cls in schemas.items():
        _section(name, cls, data[name])
    if path is not None and Path(path).resolve() != DEFAULT_CONFIG_PATH.resolve():
        for name, values in _read(path).items():
            if name not in schemas or not isinstance(values, dict):
                raise ValueError(f'Неизвестная или некорректная секция: {name}')
            data[name] = {**data[name], **values}
    settings = Settings(**{name: _section(name, cls, data[name]) for name, cls in schemas.items()})
    if not 1 <= settings.schedule.minutes_per_student <= MINUTES_PER_HOUR:
        raise ValueError(f'schedule.minutes_per_student: допустимый диапазон 1–{MINUTES_PER_HOUR}')
    if settings.schedule.prep_minutes < 0:
        raise ValueError('schedule.prep_minutes: нужно неотрицательное число')
    if not 0 < settings.workload.warning_ratio <= 1:
        raise ValueError('workload.warning_ratio: нужно число в интервале (0, 1]')
    for name in ('overload_color', 'warning_color', 'normal_color', 'idle_color'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', getattr(settings.workload, name)):
            raise ValueError(f'workload.{name}: нужен цвет в формате #RRGGBB')
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
