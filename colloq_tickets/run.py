"""Запуск с локальным venv и системными библиотеками NixOS, если они нужны."""
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    python = root / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)
    environment = os.environ.copy()
    # Бинарные колёса OR-Tools/NumPy ищут стандартные libstdc++ и zlib.
    # NixOS хранит их в store, а не в /usr/lib. На обычном Linux это не нужно.
    store = Path("/nix/store")
    if sys.platform == "linux" and store.is_dir():
        libraries = [environment.get("LD_LIBRARY_PATH", "")]
        for pattern in ("*-gcc-*-lib/lib/libstdc++.so.6", "*-zlib-*/lib/libz.so.1"):
            found = sorted(store.glob(pattern))
            if found:
                libraries.append(str(found[0].parent))
        environment["LD_LIBRARY_PATH"] = ":".join(p for p in libraries if p)
    args = sys.argv[1:]
    command = [str(python), "-m", "unittest", "-v"] if args == ["--test"] else [str(python), str(root / "main.py"), *args]
    os.execve(str(python), command, environment)


if __name__ == "__main__":
    main()
