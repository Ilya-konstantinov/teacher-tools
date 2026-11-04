"""Публичный API: выбор плана и независимое восстановление билетов."""
from planning import ALGORITHMS, plan_tickets
from reconstruction import restore_tickets


def generate_tickets_report(*args, **kwargs):
    """Совместимый составной вызов двух этапов."""
    return restore_tickets(plan_tickets(*args, **kwargs))


def generate_tickets(*args, **kwargs):
    return generate_tickets_report(*args, **kwargs).tickets
