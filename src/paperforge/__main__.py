"""Run Paperforge with python -m paperforge or as a bundled executable."""
from paperforge.app import main

if __name__ == '__main__':
    import sys

    if sys.platform == 'win32' and getattr(sys, 'frozen', False):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    main()
