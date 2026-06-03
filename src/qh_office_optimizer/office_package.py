from __future__ import annotations

import posixpath
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from qh_office_optimizer.file_rules import VALID_IMAGE_EXTENSIONS

CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", CONTENT_TYPES_NS)
ET.register_namespace("", RELATIONSHIPS_NS)

JPEG_EXTENSIONS = {".jpg", ".jpeg"}
JPEG_CONTENT_TYPE = "image/jpeg"


@dataclass(frozen=True)
class MediaPart:
    name: str
    size: int

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix.lower()


@dataclass(frozen=True)
class Replacement:
    old_name: str
    new_name: str
    data: bytes


def is_jpeg_data(data: bytes) -> bool:
    return len(data) >= 3 and data[0:3] == b"\xff\xd8\xff"


def list_media_parts(package_path: Path) -> list[MediaPart]:
    with zipfile.ZipFile(package_path, "r") as package:
        media: list[MediaPart] = []
        for info in package.infolist():
            if info.is_dir():
                continue
            if Path(info.filename).suffix.lower() in VALID_IMAGE_EXTENSIONS:
                media.append(MediaPart(name=info.filename, size=info.file_size))
        return media


def has_digital_signature(package_path: Path) -> bool:
    with zipfile.ZipFile(package_path, "r") as package:
        for info in package.infolist():
            name = info.filename.lower()
            if name.startswith("_xmlsignatures/"):
                return True
            if "digital-signature" in name or name.endswith("origin.sigs"):
                return True
    return False


def _normalize_part_name(name: str) -> str:
    normalized = posixpath.normpath(name.replace("\\", "/"))
    return "" if normalized == "." else normalized.lstrip("/")


def _relationship_base_dir(rels_name: str) -> str:
    rels_name = _normalize_part_name(rels_name)
    if rels_name == "_rels/.rels":
        return ""
    marker = "/_rels/"
    if marker not in rels_name:
        return posixpath.dirname(rels_name)
    prefix, rel_file = rels_name.split(marker, 1)
    source_name = rel_file.removesuffix(".rels")
    source_part = f"{prefix}/{source_name}" if prefix else source_name
    return posixpath.dirname(source_part)


def _resolve_relationship_target(base_dir: str, target: str) -> str:
    decoded = unquote(target)
    if decoded.startswith("/"):
        return _normalize_part_name(decoded)
    return _normalize_part_name(posixpath.join(base_dir, decoded))


def _relative_relationship_target(base_dir: str, new_name: str, was_absolute: bool) -> str:
    if was_absolute:
        return f"/{_normalize_part_name(new_name)}"
    if not base_dir:
        return _normalize_part_name(new_name)
    return posixpath.relpath(_normalize_part_name(new_name), start=base_dir)


def update_relationships_xml(xml_bytes: bytes, rels_name: str, name_mapping: dict[str, str]) -> tuple[bytes, int]:
    if not name_mapping:
        return xml_bytes, 0
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes, 0

    changed = 0
    base_dir = _relationship_base_dir(rels_name)
    for rel in root.findall(f".//{{{RELATIONSHIPS_NS}}}Relationship"):
        if rel.attrib.get("TargetMode", "").lower() == "external":
            continue
        target = rel.attrib.get("Target")
        if not target:
            continue
        resolved = _resolve_relationship_target(base_dir, target)
        new_name = name_mapping.get(resolved)
        if not new_name:
            continue
        rel.set("Target", _relative_relationship_target(base_dir, new_name, target.startswith("/")))
        changed += 1

    if not changed:
        return xml_bytes, 0
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), changed


def update_content_types_xml(xml_bytes: bytes, name_mapping: dict[str, str]) -> bytes:
    if not name_mapping:
        return xml_bytes
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes

    default_tag = f"{{{CONTENT_TYPES_NS}}}Default"
    override_tag = f"{{{CONTENT_TYPES_NS}}}Override"
    defaults = {
        item.attrib.get("Extension", "").lower()
        for item in root.findall(default_tag)
    }
    if "jpg" not in defaults:
        ET.SubElement(root, default_tag, {"Extension": "jpg", "ContentType": JPEG_CONTENT_TYPE})

    reverse = {f"/{old_name}": f"/{new_name}" for old_name, new_name in name_mapping.items()}
    for override in root.findall(override_tag):
        part_name = override.attrib.get("PartName")
        if part_name in reverse:
            override.set("PartName", reverse[part_name])
            override.set("ContentType", JPEG_CONTENT_TYPE)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def collect_relationship_targets(package_path: Path) -> set[str]:
    targets: set[str] = set()
    with zipfile.ZipFile(package_path, "r") as package:
        for info in package.infolist():
            if not info.filename.endswith(".rels"):
                continue
            base_dir = _relationship_base_dir(info.filename)
            try:
                root = ET.fromstring(package.read(info.filename))
            except ET.ParseError:
                continue
            for rel in root.findall(f".//{{{RELATIONSHIPS_NS}}}Relationship"):
                if rel.attrib.get("TargetMode", "").lower() == "external":
                    continue
                target = rel.attrib.get("Target")
                if not target:
                    continue
                targets.add(_resolve_relationship_target(base_dir, target))
    return targets


def unique_jpeg_part_name(old_name: str, existing_names: set[str], planned_names: set[str]) -> str:
    suffix = Path(old_name).suffix.lower()
    if suffix in JPEG_EXTENSIONS:
        return old_name

    directory = posixpath.dirname(old_name)
    stem = Path(old_name).stem
    candidate = f"{stem}.jpg"
    if directory:
        candidate = f"{directory}/{candidate}"

    used = set(existing_names) | set(planned_names)
    if candidate not in used or candidate == old_name:
        return candidate

    index = 1
    while True:
        candidate_name = f"{stem}_opt_{index}.jpg"
        candidate = f"{directory}/{candidate_name}" if directory else candidate_name
        if candidate not in used:
            return candidate
        index += 1


def write_package_with_replacements(source_path: Path, output_path: Path, replacements: list[Replacement]) -> None:
    replacement_by_old = {item.old_name: item for item in replacements}
    name_mapping = {
        item.old_name: item.new_name
        for item in replacements
        if item.old_name != item.new_name
    }
    added_names = {item.new_name for item in replacements if item.old_name != item.new_name}

    with zipfile.ZipFile(source_path, "r") as source, zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as target:
        for info in source.infolist():
            if info.is_dir():
                target.writestr(info, b"")
                continue

            replacement = replacement_by_old.get(info.filename)
            if replacement and replacement.new_name != replacement.old_name:
                continue

            data = source.read(info.filename)
            if replacement:
                data = replacement.data
            elif info.filename == "[Content_Types].xml":
                data = update_content_types_xml(data, name_mapping)
            elif info.filename.endswith(".rels"):
                data, _changed = update_relationships_xml(data, info.filename, name_mapping)

            target.writestr(info, data)

        for replacement in replacements:
            if replacement.new_name == replacement.old_name:
                continue
            if replacement.new_name in added_names:
                target.writestr(replacement.new_name, replacement.data)
                added_names.remove(replacement.new_name)


def make_temp_dir_near(source_path: Path) -> tempfile.TemporaryDirectory[str]:
    try:
        source_path.parent.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix="qh_office_optimizer_", dir=str(source_path.parent))
    except OSError:
        return tempfile.TemporaryDirectory(prefix="qh_office_optimizer_")


def copy_for_reading(source_path: Path, temp_dir: Path) -> Path:
    copy_path = temp_dir / source_path.name
    shutil.copy2(source_path, copy_path)
    return copy_path
