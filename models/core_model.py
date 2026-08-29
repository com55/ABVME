"""
Core Model Layer - MVVM Pattern
Contains core business logic for loading and managing Unity assets
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from .asset_model import AssetInfo
from . import crc as crc_mod
from .crc import compute_crc32, crc_should_run, decimal_crc_from_stem
from .packers import PackerName, data_flag_has_blocks_info_at_end, resolve_packer
from .resource_patch import apply_resource_patch
from .save_options import (
    CrcMode,
    ResourcePatchMode,
    StreamCapture,
    parse_resource_patch_mode,
)

if TYPE_CHECKING:
    from UnityPy import Environment
    from UnityPy.enums import ClassIDType
    from UnityPy.files import BundleFile, SerializedFile, WebFile
    from UnityPy.streams.EndianBinaryReader import EndianBinaryReader

# Configure logger
log = logging.getLogger("ABVME")


def _available_asset_types() -> list[ClassIDType]:
    from UnityPy.enums import ClassIDType

    return [ClassIDType.Texture2D, ClassIDType.TextAsset]


def __getattr__(name: str) -> list[ClassIDType]:
    if name == "available_assets":
        value = _available_asset_types()
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def filter_assets_by_available_types(
    assets: list[AssetInfo],
    available_types: list[ClassIDType],
    show_all: bool,
) -> list[AssetInfo]:
    """Return all assets or only those whose type is in available_types."""
    if show_all:
        return list(assets)
    allowed = set(available_types)
    return [asset for asset in assets if asset.obj_type in allowed]


class ABVMECore:
    """
    Core business logic for ABVME
    Handles loading Unity bundle files and managing assets
    """

    def __init__(self):
        self._env: Environment
        self._all_assets: list[AssetInfo] = []
        self._source_paths: list[
            dict[str, SerializedFile | BundleFile | WebFile | EndianBinaryReader]
        ] = []
        self._stream_captures: dict[tuple[str, int], StreamCapture] = {}
        self._original_crc32: dict[str, int] = {}

    @property
    def source_paths(
        self,
    ) -> list[dict[str, SerializedFile | BundleFile | WebFile | EndianBinaryReader]]:
        """Get list of loaded source file paths"""
        if self._source_paths:
            return self._source_paths
        else:
            for path, file in self._env.files.items():
                self._source_paths.append({path: file})
            return self._source_paths

    def load_files(
        self,
        file_list: list[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[AssetInfo]:
        """
        Load Unity bundle files from file paths

        Args:
            file_list: List of file paths to load
            progress_callback: Optional callback function(current, total, filename) for progress updates

        Returns:
            List of AssetInfo objects extracted from bundles
        """
        from UnityPy import Environment

        self._all_assets = []
        self._source_paths = []
        self._stream_captures = {}
        self._original_crc32 = {}

        env = Environment()
        max_try = 100
        total_files = len(file_list)
        log.info(f"Starting to load {total_files} files...")

        for idx, file in enumerate(file_list, start=1):
            # Emit progress before loading each file
            if progress_callback:
                progress_callback(idx, total_files, file)

            start_time = time.time()
            with open(file, "rb") as f:
                file_byte = f.read()

            self._original_crc32[file] = compute_crc32(file_byte)

            # Check if file has UnityFS header
            if len(file_byte) >= 8 and file_byte[:7] != b"UnityFS":
                log.warning(f"File {file} does not have UnityFS header, skipping...")
                continue

            current_trim = 0
            for i in range(max_try):
                try:
                    if current_trim:
                        data = file_byte[:-current_trim]
                        env.load_file(data, name=file)
                        log.debug(f"Trimmed {current_trim} bytes from {file}")
                    else:
                        env.load_file(file)
                    break
                except Exception as e:
                    current_trim += 1
                    if i == max_try - 1:
                        log.error(f"Failed to load {file}: {e}")

            log.info(f"Took {time.time() - start_time:.4f} seconds to load {file}")

        self._env = env
        self._all_assets = []
        return self.get_available_assets()

    def get_available_assets(self, show_all: bool = False) -> list[AssetInfo]:
        """
        Extract available assets from loaded environment

        Args:
            show_all: When True, return every object in the environment.

        Returns:
            List of AssetInfo objects
        """
        bundle_file_dict = {v: k for k, v in self._env.files.items()}

        if not self._all_assets:
            for obj in self._env.objects:
                source_path = ""
                target = obj.assets_file
                if target in bundle_file_dict:
                    source_path = bundle_file_dict[target]
                elif hasattr(target, "parent") and target.parent in bundle_file_dict:
                    source_path = bundle_file_dict[target.parent]
                self._all_assets.append(
                    AssetInfo(
                        obj,
                        source_path,
                        register_stream_capture=self.register_stream_capture,
                    )
                )

        return filter_assets_by_available_types(
            self._all_assets, _available_asset_types(), show_all
        )

    def original_crc32_for(self, source_path: str) -> int | None:
        return self._original_crc32.get(source_path)

    def register_stream_capture(
        self, source_path: str, path_id: int, capture: StreamCapture
    ) -> None:
        if not source_path:
            return
        key = (source_path, int(path_id))
        existing = self._stream_captures.get(key)
        if existing is not None:
            if capture.image_bytes:
                self._stream_captures[key] = replace(
                    existing, image_bytes=capture.image_bytes
                )
            return
        if not capture.path:
            return
        self._stream_captures[key] = capture

    def _patched_texture_data(self) -> dict[tuple[str, int], object]:
        found: dict[tuple[str, int], object] = {}
        for asset in self._all_assets:
            data = getattr(asset, "_readed_data", None)
            if data is None:
                continue
            try:
                path_id = int(asset._obj.path_id)
            except (TypeError, ValueError):
                continue
            found[(asset.source_path, path_id)] = data
        return found

    def _consume_stream_captures(self, source_path: str) -> None:
        self._stream_captures = {
            key: cap
            for key, cap in self._stream_captures.items()
            if key[0] != source_path
        }

    def save_file(
        self,
        file: str,
        output_path: str | Path,
        packer: PackerName = "original",
        *,
        crc_mode: CrcMode | str = CrcMode.AUTO,
        resource_patch_mode: ResourcePatchMode | str = ResourcePatchMode.RESOURCE_PATCH,
    ) -> list[str]:
        """
        Save a specific bundle file to output path

        Args:
            file: File name/path in loaded files
            output_path: Output file path
            packer: Compression method (none, lz4, lz4hc, lzma, or original)
        """
        from UnityPy.streams.EndianBinaryReader import EndianBinaryReader

        target_file = self._env.files.get(file)
        if not target_file:
            log.error(f"File {file} not found in loaded files.")
            return []

        if isinstance(target_file, EndianBinaryReader):
            return []

        output_path = Path(output_path).resolve()
        return self._save_fileobj(
            target_file,
            output_path,
            packer,
            source_path=file,
            original_crc32=self.original_crc32_for(file),
            crc_mode=crc_mode,
            resource_patch_mode=resource_patch_mode,
        )

    def _desired_crc32(
        self,
        output_path: Path,
        source_path: str,
        original_crc32: int | None,
    ) -> int | None:
        if original_crc32 is not None:
            return original_crc32
        src = Path(source_path)
        if output_path.resolve() != src.resolve():
            try:
                return compute_crc32(src.read_bytes())
            except OSError:
                return None
        return decimal_crc_from_stem(src.stem)

    def _save_fileobj(
        self,
        file_obj: SerializedFile | BundleFile | WebFile,
        output_path: Path,
        packer: PackerName,
        *,
        source_path: str,
        original_crc32: int | None,
        crc_mode: CrcMode | str,
        resource_patch_mode: ResourcePatchMode | str,
    ) -> list[str]:
        """Apply resource patch, save, optional CRC, then write."""
        start_time = time.time()
        warnings: list[str] = []
        mode = parse_resource_patch_mode(resource_patch_mode)
        env = getattr(self, "_env", None)
        warnings.extend(
            apply_resource_patch(
                file_obj=file_obj,
                source_path=source_path,
                captures=self._stream_captures,
                mode=mode,
                env=env,
                patched_data=self._patched_texture_data(),
            )
        )
        if mode in (
            ResourcePatchMode.RESOURCE_PATCH,
            ResourcePatchMode.ORPHAN_CLEANUP,
        ):
            self._consume_stream_captures(source_path)

        resolved = resolve_packer(packer)
        raw = file_obj.save(packer=resolved)

        if crc_should_run(crc_mode, file_obj):
            if data_flag_has_blocks_info_at_end(file_obj, resolved):
                msg = "CRC not applied: blocks info is at end of file"
                log.warning(msg)
                warnings.append(msg)
            else:
                desired = self._desired_crc32(output_path, source_path, original_crc32)
                if desired is None:
                    msg = "CRC not applied"
                    log.warning(msg)
                    warnings.append(msg)
                else:
                    try:
                        raw = crc_mod.crc_corrector(raw, desired)
                    except Exception as exc:
                        log.warning("CRC not applied: %s", exc)
                        warnings.append("CRC not applied")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(raw)
        log.info(f"Took {time.time() - start_time:.2f} seconds to save {output_path}")
        return warnings
