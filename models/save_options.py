"""Save-option enums, QSettings parse helpers, and UI label maps."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from models.packers import PackerName

PACKER_LABELS = {
    "None": "none",
    "LZ4": "lz4",
    "LZ4HC": "lz4hc",
    "LZMA": "lzma",
    "Original": "original",
}
RESOURCE_LABELS = {
    "Inline": "inline",
    "Orphan cleanup": "orphan_cleanup",
    "Resource patch": "resource_patch",
}
CRC_LABELS = {
    "Off": "off",
    "On": "on",
    "Auto": "auto",
}

_PACKER_VALUES = frozenset(PACKER_LABELS.values())
DEFAULT_PACKER: PackerName = "original"


class ResourcePatchMode(str, Enum):
    INLINE = "inline"
    ORPHAN_CLEANUP = "orphan_cleanup"
    RESOURCE_PATCH = "resource_patch"


class CrcMode(str, Enum):
    OFF = "off"
    ON = "on"
    AUTO = "auto"


@dataclass(frozen=True)
class StreamCapture:
    path: str
    offset: int
    size: int
    image_bytes: bytes = b""


def _as_str(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def parse_packer(value: object) -> PackerName:
    text = _as_str(value)
    if text in _PACKER_VALUES:
        return text  # type: ignore[return-value]
    return DEFAULT_PACKER


def parse_resource_patch_mode(value: object) -> ResourcePatchMode:
    try:
        return ResourcePatchMode(_as_str(value))
    except ValueError:
        return ResourcePatchMode.RESOURCE_PATCH


def parse_crc_mode(value: object) -> CrcMode:
    try:
        return CrcMode(_as_str(value))
    except ValueError:
        return CrcMode.AUTO
