"""CRC32 helpers: append corrector and bundle metadata utilities."""

from __future__ import annotations

import binascii
import struct


def compute_crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def _gf2_solve(columns: list[int], target: int) -> int:
    """Return x such that XOR of columns[i] for set bits i in x equals target."""
    size = 32
    mat = [[0] * (size + 1) for _ in range(size)]
    for col_idx in range(size):
        effect = columns[col_idx]
        for row in range(size):
            mat[row][col_idx] = (effect >> row) & 1
    for row in range(size):
        mat[row][size] = (target >> row) & 1

    pivot_row = 0
    for col in range(size):
        swap_row = None
        for row in range(pivot_row, size):
            if mat[row][col]:
                swap_row = row
                break
        if swap_row is None:
            continue
        mat[pivot_row], mat[swap_row] = mat[swap_row], mat[pivot_row]
        for row in range(size):
            if row != pivot_row and mat[row][col]:
                for c in range(size + 1):
                    mat[row][c] ^= mat[pivot_row][c]
        pivot_row += 1

    solution = 0
    for row in range(size):
        pivot_col = next((c for c in range(size) if mat[row][c]), None)
        if pivot_col is None:
            continue
        if mat[row][size]:
            solution |= 1 << pivot_col
    return solution


def _append_bit_effects(prefix: bytes) -> list[int]:
    """CRC XOR effect for each bit of a little-endian 32-bit dword appended after prefix."""
    baseline = compute_crc32(prefix + b"\x00\x00\x00\x00")
    effects: list[int] = []
    for bit in range(32):
        append = bytearray(4)
        append[bit // 8] = 1 << (bit % 8)
        toggled = compute_crc32(prefix + bytes(append))
        effects.append(baseline ^ toggled)
    return effects


def crc_corrector(data: bytes, desired_crc: int, *, append: bool = True) -> bytes:
    if not isinstance(desired_crc, int):
        raise TypeError("desired_crc must be int, not str")

    if append:
        prefix = data
        buf = bytearray(data + b"\x00\x00\x00\x00")
    else:
        if len(data) < 4:
            raise ValueError("data must be at least 4 bytes when append=False")
        prefix = data[:-4]
        buf = bytearray(data)
        buf[-4:] = b"\x00\x00\x00\x00"

    effects = _append_bit_effects(prefix)
    current = compute_crc32(bytes(buf))
    diff = current ^ desired_crc
    fix = _gf2_solve(effects, diff)
    struct.pack_into("<I", buf, len(buf) - 4, fix)
    return bytes(buf)


def decimal_crc_from_stem(stem: str) -> int | None:
    if "_" not in stem:
        return None
    tail = stem.rsplit("_", 1)[-1]
    if not tail.isdigit():
        return None
    return int(tail, 10)


def get_build_target_name(file_obj: object) -> str | None:
    from UnityPy.enums import BuildTarget
    from UnityPy.files import SerializedFile

    def _platform_name_from_serialized(entry: SerializedFile) -> str | None:
        platform = entry.target_platform
        if platform == BuildTarget.UnknownPlatform:
            return None
        name = platform.name
        if "unknown" in name.lower():
            return None
        return name

    def _scan_container(obj: object) -> str | None:
        if isinstance(obj, SerializedFile):
            return _platform_name_from_serialized(obj)

        files = getattr(obj, "files", None)
        if files is None:
            return None

        for entry in files.values():
            if isinstance(entry, SerializedFile):
                name = _platform_name_from_serialized(entry)
                if name is not None:
                    return name
                continue
            nested_files = getattr(entry, "files", None)
            if nested_files is not None:
                name = _scan_container(entry)
                if name is not None:
                    return name
        return None

    return _scan_container(file_obj)


def crc_should_run(crc_mode: str, file_obj: object) -> bool:
    if crc_mode == "off":
        return False
    if crc_mode == "on":
        return True
    if crc_mode == "auto":
        name = get_build_target_name(file_obj) or ""
        return "windows" in name.lower()
    return False
