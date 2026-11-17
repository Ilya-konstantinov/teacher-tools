"""Command dispatch for Paperforge."""
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate question papers and answer documents.")
    commands = parser.add_subparsers(dest='command', required=True)
    for name, description in (
        ('generate', 'Select question papers and write JSON'),
        ('print', 'Render existing papers'),
        ('answers', 'Render answer documents'),
        ('run', 'Select and render papers'),
    ):
        commands.add_parser(name, add_help=False, help=description)
    args, remaining = parser.parse_known_args(argv)
    if args.command in ('generate', 'run'):
        from .cli import main as generate
        generate(remaining, pipeline=args.command == 'run')
    else:
        from .documents import main as render
        render(remaining, answers=args.command == 'answers')
