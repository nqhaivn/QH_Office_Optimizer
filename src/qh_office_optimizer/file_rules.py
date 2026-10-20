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


def file_identity_key(path: Path) -> str:
    return os.path.normcase(str(absolute_path(path)))


def has_hidden_or_system_attribute(path: Path) -> bool:
    if os.name != "nt":
        return path.name.startswith(".")
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == INVALID_FILE_ATTRIBUTES:
        return False
    return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def _valid_office_file_size(path: Path, known_file: bool = False) -> int | None:
    if path.name.startswith("~$"):
        return None
    if path.suffix.lower() not in VALID_OFFICE_EXTENSIONS:
        return None
    if not known_file and not path.is_file():
        return None
    if has_hidden_or_system_attribute(path):
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return size if size > 0 else None


def is_valid_office_file(path: Path) -> bool:
    return _valid_office_file_size(absolute_path(path)) is not None


def _iter_files_under(path: Path) -> Iterator[tuple[Path, bool]]:
    try:
        if path.is_file():
            yield path, True
            return
        if path.is_dir():
            for root, _dirs, files in os.walk(path):
                for filename in files:
                    yield Path(root) / filename, True
    except OSError:
        return


def iter_valid_office_file_records(
    paths: Iterable[Path],
    excluded_keys: set[str] | None = None,
) -> list[tuple[Path, int]]:
    seen: set[str] = set(excluded_keys or set())
    result: list[tuple[Path, int]] = []

    for input_path in paths:
        for candidate, known_file in _iter_files_under(absolute_path(input_path)):
            normalized = absolute_path(candidate)
            size = _valid_office_file_size(normalized, known_file)
            if size is None:
                continue
            key = file_identity_key(normalized)
            if key in seen:
                continue
            seen.add(key)
            result.append((normalized, size))
    return result


def iter_valid_office_files(paths: Iterable[Path]) -> list[Path]:
    return [path for path, _size in iter_valid_office_file_records(paths)]
