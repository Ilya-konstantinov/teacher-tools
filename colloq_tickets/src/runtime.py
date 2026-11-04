"""Запуск в локальном venv и подключение системных библиотек NixOS."""
import os
from pathlib import Path
import sys


def bootstrap(root: Path):
    marker = 'TEACHER_TOOLS_RUNTIME'
    if os.environ.get(marker) == str(root):
        return
    executable = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not executable.exists():
        executable = Path(sys.executable)
    environment = os.environ.copy()
    store = Path('/nix/store')
    if sys.platform == 'linux' and store.is_dir():
        libraries = [environment.get('LD_LIBRARY_PATH', '')]
        for pattern in ('*-gcc-*-lib/lib/libstdc++.so.6', '*-zlib-*/lib/libz.so.1'):
            found = sorted(store.glob(pattern))
            if found:
                libraries.append(str(found[0].parent))
        environment['LD_LIBRARY_PATH'] = ':'.join(p for p in libraries if p)
    environment[marker] = str(root)
    os.execve(str(executable), [str(executable), str(root/'main.py'), *sys.argv[1:]], environment)
