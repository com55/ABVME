"""
Save Worker - Background thread for saving bundle files
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from models import ABVMECore
from models.packers import PackerName
from models.save_options import CrcMode, ResourcePatchMode


log = logging.getLogger("ABVME")


class SaveWorker(QThread):
    """
    Background worker for saving Unity bundle files
    Supports save all, save single file, and save multiple selected files
    """

    # Signals
    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(bool, str)  # success, message
    error = Signal(str)  # error message
    warning = Signal(str)

    def __init__(
        self,
        core: ABVMECore,
        output_dir: Path,
        packer: PackerName = "original",
        specific_file: Optional[str] = None,
        output_filename: Optional[str] = None,
        specific_files: Optional[list[str]] = None,
        resource_patch_mode: ResourcePatchMode | str = ResourcePatchMode.RESOURCE_PATCH,
        crc_mode: CrcMode | str = CrcMode.AUTO,
    ):
        """
        Initialize SaveWorker

        Args:
            core: ABVMECore instance
            output_dir: Output directory for saved files
            packer: Compression method (none, lz4, lz4hc, lzma, or original)
            specific_file: If set, save only this file; otherwise save all changed files
            output_filename: Custom output filename (only used with specific_file)
            specific_files: If set, save only these files (list of filepaths)
            resource_patch_mode: Resource-file mode snapshot
            crc_mode: CRC mode snapshot
        """
        super().__init__()
        self.core = core
        self.output_dir = Path(output_dir)
        self.packer: PackerName = packer or "original"
        self.specific_file = specific_file
        self.output_filename = output_filename
        self.specific_files = specific_files
        self.resource_patch_mode = resource_patch_mode
        self.crc_mode = crc_mode

    def run(self):
        """Execute save operation in background thread"""
        try:
            if self.specific_files:
                self._save_multiple_files()
            elif self.specific_file:
                self._save_single_file()
            else:
                self._save_all_files()
        except Exception as e:
            error_msg = f"Save operation failed: {str(e)}"
            log.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            self.finished.emit(False, error_msg)

    def _emit_save_result(self, success_msg: str, warnings: list[str]) -> None:
        for warning in warnings:
            self.warning.emit(warning)
        if warnings:
            seen: set[str] = set()
            unique_warnings: list[str] = []
            for warning in warnings:
                if warning not in seen:
                    seen.add(warning)
                    unique_warnings.append(warning)
            detail = "; ".join(unique_warnings)
            if detail not in success_msg:
                success_msg = f"{success_msg} ({detail})"
        self.finished.emit(True, success_msg)

    def _save_single_file(self):
        """Save a single specific file"""
        assert self.specific_file is not None, "specific_file must be set"
        try:
            filename = self.output_filename or Path(self.specific_file).name
            self.progress.emit(1, 1, filename)

            output_path = self.output_dir / filename
            warnings = (
                self.core.save_file(
                    self.specific_file,
                    output_path,
                    self.packer,
                    crc_mode=self.crc_mode,
                    resource_patch_mode=self.resource_patch_mode,
                )
                or []
            )

            self._emit_save_result(f"Successfully saved {filename}", warnings)

        except Exception as e:
            error_msg = f"Failed to save {self.specific_file}: {str(e)}"
            log.error(error_msg)
            raise

    def _save_multiple_files(self):
        """Save multiple selected files"""
        assert self.specific_files is not None, "specific_files must be set"
        try:
            total = len(self.specific_files)

            if total == 0:
                msg = "No files to save"
                log.info(msg)
                self.finished.emit(True, msg)
                return

            self.output_dir.mkdir(parents=True, exist_ok=True)

            saved = 0
            warnings: list[str] = []
            for idx, filepath in enumerate(self.specific_files, 1):
                filename = Path(filepath).name
                self.progress.emit(idx, total, filename)
                output_path = self.output_dir / filename
                warnings.extend(
                    self.core.save_file(
                        filepath,
                        output_path,
                        self.packer,
                        crc_mode=self.crc_mode,
                        resource_patch_mode=self.resource_patch_mode,
                    )
                    or []
                )
                saved += 1

            success_msg = f"Successfully saved {saved} file(s)"
            log.info(success_msg)
            self._emit_save_result(success_msg, warnings)

        except Exception as e:
            error_msg = f"Failed during batch save: {str(e)}"
            log.error(error_msg)
            raise

    def _save_all_files(self):
        """Save all changed files with progress updates"""
        try:
            changed_files = [
                (path, file)
                for path, file in self.core._env.files.items()
                if hasattr(file, "is_changed") and getattr(file, "is_changed", False)
            ]

            total = len(changed_files)

            if total == 0:
                msg = "No changed files to save"
                log.info(msg)
                self.finished.emit(True, msg)
                return

            self.output_dir.mkdir(parents=True, exist_ok=True)

            saved = 0
            warnings: list[str] = []
            for idx, (path, file_obj) in enumerate(changed_files, 1):
                filename = (
                    Path(path).name
                    if hasattr(Path(path), "name")
                    else getattr(file_obj, "name", f"file_{idx}")
                )
                self.progress.emit(idx, total, filename)
                output_path = self.output_dir / filename
                warnings.extend(
                    self.core._save_fileobj(
                        file_obj,
                        output_path,
                        self.packer,
                        source_path=path,
                        original_crc32=self.core.original_crc32_for(path),
                        crc_mode=self.crc_mode,
                        resource_patch_mode=self.resource_patch_mode,
                    )
                )
                saved += 1

            success_msg = f"Successfully saved {saved} file(s)"
            log.info(success_msg)
            self._emit_save_result(success_msg, warnings)

        except Exception as e:
            error_msg = f"Failed during batch save: {str(e)}"
            log.error(error_msg)
            raise
