"""Bundle-scoped Inline / Orphan cleanup / Resource patch for streamed Texture2D."""

from __future__ import annotations

import logging
import ntpath
from dataclasses import dataclass

from models.save_options import (
    ResourcePatchMode,
    StreamCapture,
    parse_resource_patch_mode,
)

log = logging.getLogger("ABVME")

_BC_DXT_FORMATS = frozenset({10, 11, 12, 24, 25, 26, 27})


@dataclass
class _Member:
    obj: object
    data: object
    stream_path: str
    orig_offset: int
    orig_size: int
    patched: bool
    image_bytes: bytes
    force_inline: bool = False


def _note(warnings: list[str], message: str) -> None:
    log.warning(message)
    warnings.append(message)


def apply_resource_patch(
    *,
    file_obj,
    source_path: str,
    captures: dict[tuple[str, int], StreamCapture],
    mode: ResourcePatchMode,
    env,
    patched_data: dict[tuple[str, int], object] | None = None,
) -> list[str]:
    """Mutate file_obj in place. Return warnings. Caller consumes captures after RESOURCE_PATCH / ORPHAN_CLEANUP.

    patched_data maps (source_path, path_id) to the Texture2D instance from Replace
    (AssetInfo._readed_data). UnityPy 1.23 ObjectReader.read() does not return
    post-save_typetree pixels; do not take image_data from a second read().
    """
    relevant = {key: cap for key, cap in captures.items() if key[0] == source_path}
    if not relevant:
        return []

    parsed = parse_resource_patch_mode(mode)
    if parsed is ResourcePatchMode.INLINE:
        return []

    objects = list(_iter_bundle_objects(file_obj, env, source_path))
    patched_ids = {path_id for (_src, path_id) in relevant}

    if parsed is ResourcePatchMode.ORPHAN_CLEANUP:
        _orphan_cleanup(file_obj, objects, patched_ids)
        return []

    return _resource_patch(file_obj, objects, source_path, relevant, env, patched_data)


def _iter_bundle_objects(file_obj, env, source_path: str):
    raw = getattr(env, "objects", None) if env is not None else None
    if raw:
        for obj in raw:
            if _belongs_to_bundle(obj, file_obj, env, source_path):
                yield obj
        return
    files = getattr(file_obj, "files", None)
    if not files or not hasattr(files, "items"):
        return
    for item in files.values():
        objects = getattr(item, "objects", None)
        if isinstance(objects, dict):
            yield from objects.values()
        elif objects:
            try:
                yield from objects
            except TypeError:
                continue


def _belongs_to_bundle(obj, file_obj, env, source_path: str) -> bool:
    assets_file = getattr(obj, "assets_file", None)
    parent = getattr(assets_file, "parent", None)
    if parent is file_obj or assets_file is file_obj:
        return True
    if env is None or not source_path:
        return False
    files = getattr(env, "files", None) or {}
    env_file = files.get(source_path) if hasattr(files, "get") else None
    return env_file is not None and (parent is env_file or assets_file is env_file)


def _is_texture2d(obj) -> bool:
    from UnityPy.enums import ClassIDType

    return getattr(obj, "type", None) == ClassIDType.Texture2D


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _stream_keys_from_data(data) -> list[str]:
    keys: list[str] = []
    stream = getattr(data, "m_StreamData", None)
    path = getattr(stream, "path", "") if stream is not None else ""
    if path:
        keys.append(str(path))
    resource = getattr(data, "m_Resource", None)
    source = getattr(resource, "m_Source", "") if resource is not None else ""
    if source:
        keys.append(str(source))
    return keys


def _basename_key(stream_path: str) -> str:
    return ntpath.basename(stream_path)


def _resolve_ress_entry(file_obj, key: str) -> tuple[str | None, object | None]:
    files = getattr(file_obj, "files", None)
    if not files or not hasattr(files, "items"):
        return None, None
    want = ntpath.basename(key).lower()
    for name, item in files.items():
        if ntpath.basename(str(name)).lower() == want:
            return str(name), item
    return None, None


def _read_slice(reader, offset: int, size: int) -> bytes:
    view = getattr(reader, "view", None)
    if view is not None:
        return bytes(view[offset : offset + size])
    position = getattr(reader, "Position", None)
    try:
        reader.Position = offset
        read_bytes = getattr(reader, "read_bytes", None)
        if callable(read_bytes):
            return bytes(read_bytes(size))
        return b""
    finally:
        if position is not None:
            reader.Position = position


def _image_bytes(data) -> bytes:
    raw = getattr(data, "image_data", b"") or b""
    try:
        return bytes(raw)
    except (TypeError, ValueError):
        return b""


def _inline_texture(data) -> None:
    stream = getattr(data, "m_StreamData", None)
    if stream is not None:
        stream.path = ""
        stream.offset = 0
        stream.size = 0
    save = getattr(data, "save", None)
    if callable(save):
        save()


def _must_inline_bc_dxt(data) -> bool:
    fmt = _as_int(getattr(data, "m_TextureFormat", 0), 0)
    if fmt not in _BC_DXT_FORMATS:
        return False
    width = _as_int(getattr(data, "m_Width", 0), 0)
    height = _as_int(getattr(data, "m_Height", 0), 0)
    return (width % 4 != 0) or (height % 4 != 0)


def _referenced_basename_keys(objects, skip_texture_ids: set[int]) -> set[str]:
    referenced: set[str] = set()
    for obj in objects:
        data = obj.read()
        if (
            _is_texture2d(obj)
            and _as_int(getattr(obj, "path_id", 0)) in skip_texture_ids
        ):
            continue
        for path in _stream_keys_from_data(data):
            referenced.add(_basename_key(path).lower())
    return referenced


def _delete_unreferenced_ress(file_obj, referenced_lower: set[str]) -> None:
    files = getattr(file_obj, "files", None)
    if not files or not hasattr(files, "items"):
        return
    for name in list(files.keys()):
        key = str(name)
        if not key.lower().endswith(".ress"):
            continue
        if _basename_key(key).lower() not in referenced_lower:
            del files[name]


def _orphan_cleanup(file_obj, objects, patched_ids: set[int]) -> None:
    referenced = _referenced_basename_keys(objects, patched_ids)
    _delete_unreferenced_ress(file_obj, referenced)


def _register_cab(env, name: str, item) -> None:
    if env is None:
        return
    register = getattr(env, "register_cab", None)
    if not callable(register):
        return
    register(name, item)
    base = ntpath.basename(name)
    if base != name:
        register(base, item)


def _replace_ress_reader(
    file_obj, dir_name: str, old_reader, payload: bytes, env
) -> None:
    from UnityPy.streams.EndianBinaryReader import EndianBinaryReader

    endian = getattr(old_reader, "endian", ">") or ">"
    new_reader = EndianBinaryReader(payload, endian=endian)
    new_reader.flags = getattr(old_reader, "flags", 0)
    old_name = getattr(old_reader, "name", None)
    if old_name:
        new_reader.name = old_name
    file_obj.files[dir_name] = new_reader
    _register_cab(env, dir_name, new_reader)


def _resource_patch(
    file_obj,
    objects,
    source_path: str,
    relevant: dict[tuple[str, int], StreamCapture],
    env,
    patched_data: dict[tuple[str, int], object] | None,
) -> list[str]:
    warnings: list[str] = []
    groups: dict[str, list[_Member]] = {}
    non_texture_keys: set[str] = set()
    live_objects = patched_data or {}

    for obj in objects:
        path_id = _as_int(getattr(obj, "path_id", 0))
        capture = relevant.get((source_path, path_id))
        if capture is not None:
            data = live_objects.get((source_path, path_id))
            if data is None:
                data = obj.read()
            stream_path = capture.path
            orig_offset = capture.offset
            orig_size = capture.size
            patched = True
            image_bytes = capture.image_bytes or _image_bytes(data)
        else:
            data = obj.read()
            if not _is_texture2d(obj):
                for path in _stream_keys_from_data(data):
                    non_texture_keys.add(_basename_key(path).lower())
                continue
            stream = getattr(data, "m_StreamData", None)
            stream_path = getattr(stream, "path", "") if stream is not None else ""
            if not stream_path:
                continue
            orig_offset = _as_int(getattr(stream, "offset", 0))
            orig_size = _as_int(getattr(stream, "size", 0))
            patched = False
            image_bytes = b""
        key = _basename_key(str(stream_path)).lower()
        groups.setdefault(key, []).append(
            _Member(
                obj=obj,
                data=data,
                stream_path=str(stream_path),
                orig_offset=orig_offset,
                orig_size=orig_size,
                patched=patched,
                image_bytes=image_bytes,
            )
        )

    for key, members in groups.items():
        dir_name, reader = _resolve_ress_entry(file_obj, key)
        has_patched = any(m.patched for m in members)
        if not has_patched:
            continue

        if reader is None or dir_name is None:
            for member in members:
                if member.patched:
                    member.force_inline = True
                    _inline_texture(member.data)
                    _note(
                        warnings,
                        f"Resource patch: .resS reader not found for {key}; inlining texture",
                    )
            continue

        for member in members:
            if member.patched and _must_inline_bc_dxt(member.data):
                member.force_inline = True
                width = _as_int(getattr(member.data, "m_Width", 0))
                height = _as_int(getattr(member.data, "m_Height", 0))
                _inline_texture(member.data)
                _note(
                    warnings,
                    f"Resource patch: BC/DXT {width}x{height} is not a multiple of 4; "
                    "inlining texture",
                )
            if member.patched and not member.image_bytes and not member.force_inline:
                member.force_inline = True
                _note(
                    warnings,
                    f"Resource patch: empty image data for {key}; "
                    "skipping .resS slot (using inlined replace)",
                )

        streamable = [m for m in members if not m.force_inline]
        if not streamable:
            if key not in non_texture_keys:
                files = getattr(file_obj, "files", None)
                if files is not None and dir_name in files:
                    del files[dir_name]
            continue

        streamable.sort(key=lambda member: member.orig_offset)
        payload = bytearray()
        for member in streamable:
            if member.patched:
                chunk = member.image_bytes
            else:
                chunk = _read_slice(reader, member.orig_offset, member.orig_size)
            new_offset = len(payload)
            payload.extend(chunk)
            stream = getattr(member.data, "m_StreamData", None)
            if stream is not None:
                stream.path = member.stream_path
                stream.offset = new_offset
                stream.size = len(chunk)
            member.data.image_data = b""
            save = getattr(member.data, "save", None)
            if callable(save):
                save()

        _replace_ress_reader(file_obj, dir_name, reader, bytes(payload), env)

    return warnings
