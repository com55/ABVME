"""UnityPy BundleFile.save packer values.

Tuple order is (data_flag, block_info_flag) as passed to
BundleFile.save_fs(writer, data_flag, block_info_flag).
UnityPy's packer-tuple docstring swaps those names — do not "fix" the constants.
"""

from __future__ import annotations

from typing import Literal

PackerName = Literal["none", "lz4", "lz4hc", "lzma", "original"]
PackerValue = str | tuple[int, int]

BLOCKS_INFO_AT_THE_END = 0x80

_PACKERS: dict[str, PackerValue] = {
    "none": "none",
    "lzma": "lzma",
    "original": "original",
    # 0x42 = DirectoryInfo | LZ4 (no BlocksInfoAtTheEnd)
    "lz4": (0x42, 2),
    # 0x243 = padding | DirectoryInfo | LZ4HC
    "lz4hc": (0x243, 3),
}


def resolve_packer(packer: str) -> PackerValue:
    try:
        return _PACKERS[packer]
    except KeyError as exc:
        raise ValueError(f"Unsupported packer: {packer!r}") from exc


def data_flag_has_blocks_info_at_end(file_obj: object, resolved: PackerValue) -> bool:
    if isinstance(resolved, tuple):
        data_flag = resolved[0]
    elif resolved == "original":
        data_flag = int(getattr(file_obj, "dataflags", 0))
    else:
        data_flag = 0
    return bool(data_flag & BLOCKS_INFO_AT_THE_END)
