"""Tiny launcher used by PyInstaller to build ER_FORCE.exe.

It locates the bundled venv (created by eye_tracking_setup/setup_colleague.cmd)
and starts the PySide6 app with the right environment variables, so the user
just double-clicks ER_FORCE.exe instead of fiddling with batch scripts.
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


def _venv_python(root: Path) -> Path | None:
    for candidate in (
        root / ".venv-eye-tracking" / "Scripts" / "pythonw.exe",
        root / ".venv-eye-tracking" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "pythonw.exe",
        root / "venv" / "Scripts" / "python.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    root = _repo_root()
    os.chdir(root)

    python = _venv_python(root)
    if python is None:
        _show_error(
            "ER Force - setup required",
            "Could not find a Python virtual environment.\n\n"
            "Run eye_tracking_setup\\setup_colleague.cmd first to create\n"
            "the .venv-eye-tracking environment, then launch ER Force again.",
        )
        return 1

    env = os.environ.copy()
    fg_root = root / "game" / "sivaks_logging_version"
    if fg_root.is_dir():
        env.setdefault("SIVAKS_FG_ROOT", str(fg_root))
    env.setdefault("ER_FORCE_HOME", str(root))
    tobii_sdk = root / "TobiiPro_SDK"
    if tobii_sdk.is_dir():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{tobii_sdk};{existing}" if existing else str(tobii_sdk)
        )

    try:
        completed = subprocess.run(
            [str(python), "-m", "UI.app"],
            cwd=str(root),
            env=env,
        )
        return completed.returncode
    except Exception:
        _show_error(
            "ER Force - launch failed",
            traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
