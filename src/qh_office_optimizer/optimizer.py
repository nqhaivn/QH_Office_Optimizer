from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from qh_office_optimizer import constants
from qh_office_optimizer.formatting import format_size
from qh_office_optimizer.models import FileOptimizationResult, OptimizationConfig
from qh_office_optimizer.office_package import (
    JPEG_EXTENSIONS,
    Replacement,
    collect_relationship_targets,
    copy_for_reading,
    has_digital_signature,
    is_jpeg_data,
    list_media_parts,
    make_temp_dir_near,
    unique_jpeg_part_name,
    write_package_with_replacements,
)
from qh_office_optimizer.output_rules import FatalOutputError, write_optimized_file

Logger = Callable[[str], None]


@dataclass
class BatchSummary:
    total: int
    success_count: int = 0
    original_total: int = 0
    optimized_total: int = 0


class CancelToken:
    def __init__(self) -> None:
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested


class MagickLaunchError(RuntimeError):
    pass


def has_enough_free_space(path: Path, required_bytes: int) -> bool:
    probe = path if path.exists() else path.parent
    try:
        return shutil.disk_usage(probe).free >= required_bytes
    except OSError:
        return False


def optimize_batch(
    config: OptimizationConfig,
    magick_path: Path,
    logger: Logger,
    update_file: Callable[[Path, int], None] | None = None,
    cancel_token: CancelToken | None = None,
) -> BatchSummary:
    summary = BatchSummary(total=len(config.files))
    logger(f"Bắt đầu tối ưu {summary.total} tệp tin.")

    for source_path in config.files:
        try:
            result = optimize_one_file(source_path, config, magick_path, logger)
        except MagickLaunchError:
            logger(constants.ERR006)
            break
        if result.success and result.new_size is not None:
            summary.success_count += 1
            summary.original_total += result.original_size
            summary.optimized_total += result.new_size
            if update_file:
                update_file(source_path, result.new_size)
        if cancel_token and cancel_token.cancel_requested:
            break

    if summary.success_count:
        logger(
            "Đã tối ưu "
            f"{summary.success_count}/{summary.total} tệp tin. "
            f"Dung lượng ban đầu {format_size(summary.original_total)}, "
            f"dung lượng sau khi tối ưu {format_size(summary.optimized_total)}"
        )
    else:
        logger("Không có tệp tin nào được tối ưu thành công.")
    return summary


def optimize_one_file(
    source_path: Path,
    config: OptimizationConfig,
    magick_path: Path,
    logger: Logger,
) -> FileOptimizationResult:
    source_path = source_path.resolve(strict=False)
    if not source_path.exists():
        logger(f"Tệp tin không còn tồn tại: {source_path}")
        return FileOptimizationResult(source_path, None, 0, None, False)
    try:
        original_size = source_path.stat().st_size
    except OSError:
        logger(f"Không thể đọc được tệp tin: {source_path}")
        return FileOptimizationResult(source_path, None, 0, None, False)

    if len(str(source_path)) >= 260:
        logger(f"Không thể xử lý {source_path} vì đường dẫn tệp tin quá dài.")
        return FileOptimizationResult(source_path, None, original_size, None, False)

    with make_temp_dir_near(source_path) as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        temp_package = temp_dir / source_path.name
        optimized_package = temp_dir / f"{source_path.stem}_optimized{source_path.suffix}"

        readable_path = source_path
        try:
            if has_digital_signature(readable_path):
                logger(f"Bỏ qua {source_path} vì có chữ ký số.")
                return FileOptimizationResult(source_path, None, original_size, None, False)
            media_parts = list_media_parts(readable_path)
        except (OSError, zipfile.BadZipFile):
            try:
                readable_path = copy_for_reading(source_path, temp_dir)
                if has_digital_signature(readable_path):
                    logger(f"Bỏ qua {source_path} vì có chữ ký số.")
                    return FileOptimizationResult(source_path, None, original_size, None, False)
                media_parts = list_media_parts(readable_path)
            except (OSError, zipfile.BadZipFile):
                logger(f"Không thể đọc được tệp tin: {source_path}")
                return FileOptimizationResult(source_path, None, original_size, None, False)

        required_free_space = original_size * 3
        if not has_enough_free_space(temp_dir, required_free_space) or not has_enough_free_space(source_path.parent, required_free_space):
            logger(f"Không thể xử lý {source_path} vì ổ đĩa đã đầy")
            return FileOptimizationResult(source_path, None, original_size, None, False)

        if not media_parts:
            logger(f"Bỏ qua tệp không có ảnh: {source_path}")
            return FileOptimizationResult(source_path, None, original_size, None, False)

        replacements = _optimize_media_parts(readable_path, temp_dir, media_parts, config.max_edge, magick_path)
        if not replacements:
            logger(f"{source_path} Không cần tối ưu vì đã có dung lượng nhỏ nhất")
            return FileOptimizationResult(source_path, None, original_size, None, False)

        try:
            write_package_with_replacements(readable_path, optimized_package, replacements)
        except (OSError, zipfile.BadZipFile):
            return FileOptimizationResult(source_path, None, original_size, None, False)

        try:
            optimized_size = optimized_package.stat().st_size
        except OSError:
            return FileOptimizationResult(source_path, None, original_size, None, False)

        if optimized_size >= original_size:
            logger(f"{source_path} Không cần tối ưu vì đã có dung lượng nhỏ nhất")
            return FileOptimizationResult(source_path, None, original_size, None, False)

        try:
            output_path = write_optimized_file(optimized_package, source_path, config.output_mode, logger)
        except FatalOutputError:
            raise

        try:
            new_size = output_path.stat().st_size
        except OSError:
            new_size = optimized_size
        return FileOptimizationResult(source_path, output_path, original_size, new_size, True)


def _optimize_media_parts(
    package_path: Path,
    temp_dir: Path,
    media_parts: list,
    max_edge: int,
    magick_path: Path,
) -> list[Replacement]:
    replacements: list[Replacement] = []
    existing_names = {part.name for part in media_parts}
    planned_names: set[str] = set()
    referenced_parts = collect_relationship_targets(package_path)

    with zipfile.ZipFile(package_path, "r") as package:
        for index, part in enumerate(media_parts):
            try:
                original_data = package.read(part.name)
            except OSError:
                continue

            original_suffix = Path(part.name).suffix.lower()
            if original_suffix not in JPEG_EXTENSIONS and part.name not in referenced_parts:
                continue

            input_path = temp_dir / f"image_{index}{original_suffix}"
            output_path = temp_dir / f"image_{index}.jpg"
            try:
                input_path.write_bytes(original_data)
            except OSError:
                continue

            if not _run_magick(magick_path, input_path, output_path, max_edge):
                continue

            try:
                optimized_data = output_path.read_bytes()
            except OSError:
                continue

            if len(optimized_data) >= len(original_data):
                continue
            if not is_jpeg_data(optimized_data):
                continue

            new_name = unique_jpeg_part_name(part.name, existing_names, planned_names)
            planned_names.add(new_name)
            replacements.append(Replacement(old_name=part.name, new_name=new_name, data=optimized_data))
    return replacements


def _run_magick(magick_path: Path, input_path: Path, output_path: Path, max_edge: int) -> bool:
    args = [
        str(magick_path),
        str(input_path),
        "-auto-orient",
        "-resize",
        f"{max_edge}x{max_edge}>",
        "-background",
        "white",
        "-alpha",
        "remove",
        "-alpha",
        "off",
        "-strip",
        "-sampling-factor",
        "4:2:0",
        "-interlace",
        "JPEG",
        "-quality",
        "75",
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            args,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except OSError as exc:
        raise MagickLaunchError(str(exc)) from exc
    except subprocess.SubprocessError:
        return False
    return completed.returncode == 0 and output_path.exists()
