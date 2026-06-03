from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Iterable, Iterator

VALID_OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}
VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


def absolute_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def has_hidden_or_system_attribute(path: Path) -> bool:
    if os.name != "nt":
        return path.name.startswith(".")
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == INVALID_FILE_ATTRIBUTES:
        return False
    return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def is_valid_office_file(path: Path) -> bool:
    path = absolute_path(path)
    if not path.is_file():
        return False
    if path.name.startswith("~$"):
        return False
    if path.suffix.lower() not in VALID_OFFICE_EXTENSIONS:
        return False
    if has_hidden_or_system_attribute(path):
        return False
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def _iter_files_under(path: Path) -> Iterator[Path]:
    try:
        if path.is_file():
            yield path
            return
        if path.is_dir():
            for root, _dirs, files in os.walk(path):
                for filename in files:
                    yield Path(root) / filename
    except OSError:
        return


def iter_valid_office_files(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []

    for input_path in paths:
        for candidate in _iter_files_under(absolute_path(input_path)):
            normalized = absolute_path(candidate)
            if not is_valid_office_file(normalized):
                continue
            key = os.path.normcase(str(normalized))
            if key in seen:
                continue
            seen.add(key)
            result.append(normalized)
    return result
