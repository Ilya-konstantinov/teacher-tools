#!/usr/bin/env python3
"""Build native, single-file Paperforge and Slotplan executables with PyInstaller."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', choices=('all', 'paperforge', 'slotplan'), default='all')
    parser.add_argument('--dist-dir', type=Path, default=root / 'dist')
    parser.add_argument('--work-dir', type=Path, default=root / 'build')
    parser.add_argument('--hidden-import', action='append', default=[], help='Extra import used by a runtime Python plugin')
    args = parser.parse_args()
    projects = ('paperforge', 'slotplan') if args.project == 'all' else (args.project,)
    for project in projects:
        source = root / 'src' / project
        work = args.work_dir.resolve() / project
        work.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
                   '--name', project, '--distpath', str(args.dist_dir.resolve()),
                   '--workpath', str(work / 'work'), '--specpath', str(work),
                   '--paths', str(root / 'src'), '--add-data', str(source / 'config.json') + ':' + project]
        if project == 'paperforge':
            command += ['--add-data', str(source / 'templates') + ':paperforge/templates', '--collect-all', 'ortools']
        for name in args.hidden_import:
            command += ['--hidden-import', name]
        subprocess.run(command + [str(source / '__main__.py')], cwd=source, check=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
