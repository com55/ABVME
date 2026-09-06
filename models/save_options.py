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
    "Rebuild .resS": "resource_patch",
}
CRC_LABELS = {
    "Off": "off",
    "On": "on",
    "Auto": "auto",
}
SAVE_OPTION_HELP = {
    "Compression Method": (
        "Select how to compress the bundle.\n"
        " - None: no compression.\n"
        " - LZ4: fast compression but larger size.\n"
        " - LZ4HC: better compression than LZ4.\n"
        " - LZMA: best compression but slowest.\n"
        " - Original: keeps the bundle's current compression flags."
    ),
    "Resource Patch Method": (
        "Select how to patch the resource stream.\n"
        " - Inline: stores resource data in the object.\n"
        " - Orphan cleanup: drops unused .resS entries.\n"
        " - Rebuild .resS: writes resource data back into .resS."
    ),
    "CRC Correction": (
        "Makes the CRC32 the same as the original file.\n"
        " - Auto: detects from the BuildTarget if it is Windows"
    ),
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


def parse_show_only_changed_files(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 0:
            return False
        if value == 1:
            return True
        return True
    text = _as_str(value).strip().lower()
    if text in ("0", "false"):
        return False
    if text in ("1", "true"):
        return True
    return True
