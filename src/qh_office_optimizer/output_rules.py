from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from qh_office_optimizer.models import OutputMode

Logger = Callable[[str], None]


class FatalOutputError(RuntimeError):
    pass


def unique_suffixed_path(parent: Path, stem: str, suffix: str, first_suffix: str = "_opt") -> Path:
    candidate = parent / f"{stem}{first_suffix}{suffix}"
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = parent / f"{stem}{first_suffix}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _desktop_output_dir() -> Path:
    return Path.home() / "Desktop" / "Office_Optimizer"


def _copy_unique(source_temp: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination = unique_suffixed_path(destination.parent, destination.stem, destination.suffix, "")
    shutil.copy2(source_temp, destination)
    return destination


def _fallback_to_desktop(source_temp: Path, intended_name: str, logger: Logger) -> Path:
    logger("Không thể ghi tệp mới vào thư mục được chỉ định. Sẽ thử ghi ra Desktop\\Office_Optimizer.")
    destination = _desktop_output_dir() / intended_name
    try:
        return _copy_unique(source_temp, destination)
    except OSError as exc:
        logger("Ghi tệp ra Desktop\\Office_Optimizer không thành công, tiến trình bị hủy bỏ.")
        raise FatalOutputError(str(exc)) from exc


def write_optimized_file(source_temp: Path, original_path: Path, output_mode: OutputMode, logger: Logger) -> Path:
    original_path = original_path.resolve(strict=False)
    if output_mode is OutputMode.FOLDER:
        output_dir = original_path.parent / f"{original_path.stem}_Optimizer"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger(f"Không thể tạo thư mục con cho tệp sau khi tối ưu tại {original_path.parent}")
            return _fallback_to_desktop(source_temp, original_path.name, logger)
        try:
            return _copy_unique(source_temp, output_dir / original_path.name)
        except OSError:
            return _fallback_to_desktop(source_temp, original_path.name, logger)

    if output_mode is OutputMode.SUFFIX:
        destination = unique_suffixed_path(original_path.parent, original_path.stem, original_path.suffix)
        try:
            return _copy_unique(source_temp, destination)
        except OSError:
            return _fallback_to_desktop(source_temp, destination.name, logger)

    return _overwrite_original(source_temp, original_path, logger)


def _overwrite_original(source_temp: Path, original_path: Path, logger: Logger) -> Path:
    backup = original_path.with_name(f"{original_path.name}.qh_backup")
    fallback = unique_suffixed_path(original_path.parent, original_path.stem, original_path.suffix)
    try:
        if backup.exists():
            backup = unique_suffixed_path(original_path.parent, original_path.name, ".qh_backup", "")
        original_path.rename(backup)
    except OSError:
        logger(f"Không thể ghi đè tệp tin {original_path}, tệp tối ưu sẽ được đổi tên thành {fallback.name}")
        try:
            return _copy_unique(source_temp, fallback)
        except OSError:
            return _fallback_to_desktop(source_temp, fallback.name, logger)

    try:
        shutil.copy2(source_temp, original_path)
        backup.unlink(missing_ok=True)
        return original_path
    except OSError:
        try:
            if original_path.exists():
                original_path.unlink()
            backup.rename(original_path)
        except OSError:
            pass
        logger("Không thể ghi tệp mới vào thư mục được chỉ định. Sẽ thử ghi ra Desktop\\Office_Optimizer.")
        try:
            return _copy_unique(source_temp, _desktop_output_dir() / fallback.name)
        except OSError as exc:
            logger("Ghi tệp ra Desktop\\Office_Optimizer không thành công, tiến trình bị hủy bỏ.")
            raise FatalOutputError(str(exc)) from exc
