from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MagickStatus:
    path: Path | None
    valid: bool


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent


def _candidate_names() -> list[str]:
    return ["magick.exe", "magick"] if os.name == "nt" else ["magick"]


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def find_magick(app_dir: Path | None = None) -> Path | None:
    app_dir = app_dir or application_dir()
    for name in _candidate_names():
        candidate = app_dir / name
        if candidate.is_file():
            return candidate

    try:
        for root, dirs, files in os.walk(app_dir):
            dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", "build", "dist"}]
            lower_files = {file_name.lower(): file_name for file_name in files}
            for name in _candidate_names():
                real_name = lower_files.get(name.lower())
                if real_name:
                    return Path(root) / real_name
    except OSError:
        pass

    for name in _candidate_names():
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def validate_magick(path: Path | None) -> MagickStatus:
    if path is None:
        return MagickStatus(path=None, valid=False)
    try:
        completed = subprocess.run(
            [str(path), "-version"],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return MagickStatus(path=path, valid=False)
    return MagickStatus(path=path, valid=completed.returncode == 0)


def find_and_validate_magick(app_dir: Path | None = None) -> MagickStatus:
    return validate_magick(find_magick(app_dir))
