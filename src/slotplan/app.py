"""Command dispatch for Slotplan."""
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="Schedule students and report examiner workload.")
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('schedule', add_help=False, help='Allocate students to arrival slots')
    commands.add_parser('workload', add_help=False, help='Report workload for a schedule')
    args, remaining = parser.parse_known_args(argv)
    if args.command == 'schedule':
        from .cli import main as schedule
        schedule(remaining)
    else:
        from .workload import main as workload
        workload(remaining)
