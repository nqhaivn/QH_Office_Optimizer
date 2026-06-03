from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from qh_office_optimizer import constants


class OutputMode(Enum):
    OVERWRITE = constants.OUTPUT_OVERWRITE
    FOLDER = constants.OUTPUT_FOLDER
    SUFFIX = constants.OUTPUT_SUFFIX

    @classmethod
    def from_label(cls, label: str) -> "OutputMode":
        for mode in cls:
            if mode.value == label:
                return mode
        raise ValueError(f"Unsupported output mode: {label}")


@dataclass(frozen=True)
class FileItem:
    path: Path
    old_size: int
    new_size: int | None = None


@dataclass(frozen=True)
class OptimizationConfig:
    files: list[Path]
    max_edge: int
    output_mode: OutputMode


@dataclass(frozen=True)
class FileOptimizationResult:
    source_path: Path
    output_path: Path | None
    original_size: int
    new_size: int | None
    success: bool
