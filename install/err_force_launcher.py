"""Tiny launcher used by PyInstaller to build ERR_FORCE.exe.

It locates the bundled venv (created by eye_tracking_setup/setup_colleague.cmd)
and starts the PySide6 app with the right environment variables, so the user
just double-clicks ERR_FORCE.exe instead of fiddling with batch scripts.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import traceback
from pathlib import Path


def _show_error(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:
        sys.stderr.write(f"{title}: {message}\n")


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _repo_root() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _can_import_tobii(python: Path) -> bool:
    try:
        completed = subprocess.run(
            [
                str(python),
                "-c",
                (
                    "import sys; "
                    "sys.exit(3) if sys.version_info[:2] > (3, 10) "
                    "else None; import tobii_research"
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        return False
    return completed.returncode == 0


def _venv_python(root: Path) -> Path | None:
    for candidate in (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "pythonw.exe",
        root / ".venv-eye-tracking" / "Scripts" / "python.exe",
        root / ".venv-eye-tracking" / "Scripts" / "pythonw.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "pythonw.exe",
    ):
        if candidate.is_file() and _can_import_tobii(candidate):
            return candidate
    return None


def main() -> int:
    root = _repo_root()
    os.chdir(root)

    python = _venv_python(root)
    if python is None:
        _show_error(
            "ERR Force - setup required",
            "Could not find a Python 3.10 virtual environment with Tobii Research installed.\n\n"
            "Run eye_tracking_setup\\setup_colleague.cmd first to create\n"
            "the .venv environment, then launch ERR Force again.",
        )
        return 1

    env = os.environ.copy()
    fg_root = root / "game"
    if fg_root.is_dir():
        env.setdefault("SIVAKS_FG_ROOT", str(fg_root))
    env.setdefault("ERR_FORCE_HOME", str(root))
    env.setdefault("ER_FORCE_HOME", str(root))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    try:
        creationflags = 0
        if os.name == "nt" and python.name.lower() == "python.exe":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            [str(python), "-m", "ui.app"],
            cwd=str(root),
            env=env,
            creationflags=creationflags,
        )
        return completed.returncode
    except Exception:
        _show_error(
            "ERR Force - launch failed",
            traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
