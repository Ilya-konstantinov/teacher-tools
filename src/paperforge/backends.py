"""Backend-neutral document contract and external renderer/compiler commands."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def command_arguments(value):
    try:
        command = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError('Command must be a JSON array of arguments') from error
    if not isinstance(command, list) or not command or any(not isinstance(s, str) or not s for s in command):
        raise ValueError('Command must be a nonempty JSON array of nonempty strings')
    return command


def subprocess_environment():
    # PyInstaller modifies the library search path for bundled extensions.
    # System renderers must use their own libraries instead.
    environment = os.environ.copy()
    if getattr(sys, 'frozen', False):
        original = environment.get('LD_LIBRARY_PATH_ORIG')
        if original is None:
            environment.pop('LD_LIBRARY_PATH', None)
        else:
            environment['LD_LIBRARY_PATH'] = original
    return environment


def run_command(command, *, input=None, cwd=None):
    result = subprocess.run(command, input=input, cwd=cwd, capture_output=True,
                            text=True, encoding='utf-8', errors='replace',
                            env=subprocess_environment(), check=False)
    if result.returncode:
        raise ValueError(f'{command[0]} exited with {result.returncode}:\n'
                         + '\n'.join((result.stderr or result.stdout).splitlines()[-30:]))
    return result


def document_payload(data, *, settings, answers, options):
    return {**data, 'schema_version': 1, 'mode': 'answers' if answers else 'tickets',
            'settings': asdict(settings),
            'options': {key: str(value.expanduser().resolve()) if isinstance(value, Path) else value
                        for key, value in options.items()}}


def render_external(command, payload):
    return run_command(command_arguments(command), input=json.dumps(payload, ensure_ascii=False)).stdout


def render_typst(payload, template=None):
    """A template consumes `document`; all user text is embedded as JSON data."""
    path = Path(template).expanduser() if template else Path(__file__).resolve().parent / 'templates' / (
        'answers.typ' if payload['mode'] == 'answers' else 'tickets.typ')
    template_text = path.read_text(encoding='utf-8')
    encoded = json.dumps(json.dumps(payload, ensure_ascii=False), ensure_ascii=False)
    return '#let document = json(bytes(' + encoded + '))\n' + template_text


def output_format(value):
    value = value.lower().lstrip('.')
    if value == 'typst':
        value = 'typ'
    if not value.isascii() or not value.isalnum() or value == 'pdf':
        raise ValueError('--format must be a source extension, for example tex, typ, html')
    return value


def compile_external(path, command_spec):
    command = command_arguments(command_spec)
    if not any('{input}' in s for s in command) or not any('{output}' in s for s in command):
        raise ValueError('--compiler-command requires {input} and {output} placeholders')
    destination = path.with_suffix('.pdf')
    with tempfile.TemporaryDirectory(prefix='.paperforge-', dir=path.parent) as temporary:
        output = Path(temporary) / destination.name
        command = [s.replace('{input}', str(path)).replace('{output}', str(output)) for s in command]
        run_command(command, cwd=path.parent)
        if not output.is_file():
            raise ValueError(f'{command[0]} did not create the requested PDF')
        output.replace(destination)
    return destination
