"""
Main ViewModel - MVVM Pattern
Presentation logic and state management for the main window
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSettings, QStandardPaths, Signal

from models import ABVMECore, AssetInfo, EditResult, ExportResult
from models.asset_model import planned_export_filename
from models.save_options import (
    parse_crc_mode,
    parse_packer,
    parse_resource_patch_mode,
    parse_show_only_changed_files,
)
from services import LoaderWorker, EditWorker, SaveWorker


log = logging.getLogger("ABVME")

_LAST_OPEN_DIRECTORY_KEY = "last_open_directory"
_BUNDLE_SUFFIXES = {".bundle", ".unity3d"}


def desktop_directory() -> str:
    path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DesktopLocation
    )
    if path:
        return path
    return str(Path.home())


def _existing_directory(path_str: str) -> str | None:
    if not path_str:
        return None
    folder = Path(path_str)
    if folder.is_dir():
        return str(folder)
    return None


class MainViewModel(QObject):
    """
    ViewModel for main window
    Manages application state and business logic
    Provides data binding through Qt Signals
    """

    # Signals for data binding with View
    assets_loaded = Signal(list)  # List of AssetInfo
    loading_started = Signal(str)  # Status message
    loading_progress = Signal(int, int, str)  # (current, total, filename) files loaded
    loading_finished = Signal(str)  # Status message

    edit_started = Signal(str)  # Status message
    edit_finished = Signal(object, object)  # asset, result

    export_completed = Signal(str, int)  # Message, log level

    save_started = Signal(str)  # Status message
    save_progress = Signal(int, int, str)  # current, total, filename
    save_finished = Signal(bool, str)  # success, message
    save_warning = Signal(str)

    selection_changed = Signal(int)  # Number of selected assets

    status_message = Signal(str, int)  # Message, log level

    def __init__(self, settings: Optional[QSettings] = None):
        super().__init__()
        self._settings = settings or QSettings("ABVME", "ABVME")
        self.show_all_objects = bool(
            self._settings.value("show_all_objects", False, type=bool)
        )
        self.packer = parse_packer(self._settings.value("packer", "original"))
        self.resource_patch_mode = parse_resource_patch_mode(
            self._settings.value("resource_patch_mode", "resource_patch")
        )
        self.crc_mode = parse_crc_mode(self._settings.value("crc_mode", "auto"))
        self.show_only_changed_files = parse_show_only_changed_files(
            self._settings.value("show_only_changed_files")
        )
        self.core: Optional[ABVMECore] = None
        self.assets: list[AssetInfo] = []
        self.selected_assets: list[AssetInfo] = []
        self._output_directory: str | None = None
        self._replace_directory: str | None = None

        # Background workers
        self.loader_worker: Optional[LoaderWorker] = None
        self.edit_worker: Optional[EditWorker] = None
        self.save_worker: Optional[SaveWorker] = None

    def load_files_from_paths(self, file_paths: list[str]):
        """
        Load bundle files from given paths

        Args:
            file_paths: List of file paths to load
        """
        self.loading_started.emit("Loading bundle files...")

        valid_files = [path for path in file_paths if Path(path).is_file()]
        if not valid_files:
            self.status_message.emit(
                "No valid bundle files were provided.", logging.WARNING
            )
            return

        self.remember_open_directory_from_paths(valid_files)

        # Create worker thread
        self.loader_worker = LoaderWorker(ABVMECore(), valid_files)
        self.loader_worker.progress.connect(self._on_loading_progress)
        self.loader_worker.finished.connect(self._on_loading_complete)
        self.loader_worker.start()

    def _on_loading_progress(self, current: int, total: int, filename: str):
        """Handle loading progress update"""
        self.loading_progress.emit(current, total, filename)

    def _on_loading_complete(self, assets: list[AssetInfo]):
        """Handle loading completion"""
        self.core = self.loader_worker.core if self.loader_worker else None
        if self.core:
            self.assets = self.core.get_available_assets(show_all=self.show_all_objects)
        else:
            self.assets = assets

        self.loading_finished.emit(f"Loaded {len(self.assets)} assets.")
        self.assets_loaded.emit(self.assets)

        log.info(
            f"Successfully loaded: {len(self.core.source_paths) if self.core else 0} files."
        )

    def set_show_all_objects(self, enabled: bool) -> None:
        """Toggle whether the asset list includes every object type."""
        self.show_all_objects = enabled
        self._settings.setValue("show_all_objects", enabled)
        if not self.core:
            return
        self.assets = self.core.get_available_assets(show_all=enabled)
        self.assets_loaded.emit(self.assets)

    def set_show_only_changed_files(self, enabled: bool) -> None:
        self.show_only_changed_files = bool(enabled)
        self._settings.setValue("show_only_changed_files", self.show_only_changed_files)

    def set_packer(self, packer: str) -> None:
        self.persist_save_options(packer, self.resource_patch_mode, self.crc_mode)

    def set_resource_patch_mode(self, resource_patch_mode: str) -> None:
        self.persist_save_options(self.packer, resource_patch_mode, self.crc_mode)

    def set_crc_mode(self, crc_mode: str) -> None:
        self.persist_save_options(self.packer, self.resource_patch_mode, crc_mode)

    def persist_save_options(
        self,
        packer: str | None,
        resource_patch_mode: str | None,
        crc_mode: str | None,
    ) -> None:
        if packer is not None:
            self.packer = parse_packer(packer)
        if resource_patch_mode is not None:
            self.resource_patch_mode = parse_resource_patch_mode(resource_patch_mode)
        if crc_mode is not None:
            self.crc_mode = parse_crc_mode(crc_mode)
        self._settings.setValue("packer", self.packer)
        self._settings.setValue("resource_patch_mode", self.resource_patch_mode.value)
        self._settings.setValue("crc_mode", self.crc_mode.value)

    def update_selection(self, selected_assets: list[AssetInfo]):
        """
        Update current selection

        Args:
            selected_assets: List of selected AssetInfo objects
        """
        self.selected_assets = selected_assets
        self.selection_changed.emit(len(selected_assets))

    def get_single_selected_asset(self) -> Optional[AssetInfo]:
        """Get single selected asset if exactly one is selected"""
        if len(self.selected_assets) == 1:
            return self.selected_assets[0]
        return None

    def _loaded_bundle_directory(self) -> str | None:
        """Folder of the selected or first loaded bundle."""
        candidates: list[str] = []
        selected = self.get_single_selected_asset()
        if selected is not None:
            candidates.append(getattr(selected, "source_path", "") or "")
        for asset in self.assets:
            candidates.append(getattr(asset, "source_path", "") or "")
        seen: set[str] = set()
        for path_str in candidates:
            if not path_str or path_str in seen:
                continue
            seen.add(path_str)
            folder = Path(path_str).parent
            if str(folder) in (".", ""):
                continue
            return str(folder)
        return None

    def get_open_dialog_start_directory(self) -> str:
        remembered = self._settings.value(_LAST_OPEN_DIRECTORY_KEY, "", type=str)
        return _existing_directory(remembered) or desktop_directory()

    def remember_open_directory(self, directory: str) -> None:
        existing = _existing_directory(directory)
        if existing is None:
            return
        self._settings.setValue(_LAST_OPEN_DIRECTORY_KEY, existing)
        self._settings.sync()

    def remember_open_directory_from_paths(self, file_paths: list[str]) -> None:
        for path_str in file_paths:
            if not path_str:
                continue
            folder = Path(path_str).parent
            existing = _existing_directory(str(folder))
            if existing is None:
                continue
            self.remember_open_directory(existing)
            return

    def bundle_files_in_directory(self, directory: str) -> list[str]:
        folder = Path(directory)
        if not folder.is_dir():
            return []
        files = [
            str(path)
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in _BUNDLE_SUFFIXES
        ]
        files.sort(key=lambda path: Path(path).name.lower())
        return files

    def get_output_dialog_start_directory(self) -> str:
        remembered = _existing_directory(self._output_directory or "")
        if remembered:
            return remembered
        return self._loaded_bundle_directory() or desktop_directory()

    def remember_output_directory(self, directory: str) -> None:
        existing = _existing_directory(directory)
        if existing:
            self._output_directory = existing

    def get_replace_dialog_start_directory(self) -> str:
        remembered = _existing_directory(self._replace_directory or "")
        if remembered:
            return remembered
        return self._loaded_bundle_directory() or desktop_directory()

    def remember_replace_directory_from_path(self, file_path: str) -> None:
        if not file_path:
            return
        existing = _existing_directory(str(Path(file_path).parent))
        if existing:
            self._replace_directory = existing

    def existing_destination_names(
        self, output_dir: Path, names: list[str]
    ) -> list[str]:
        dest = Path(output_dir)
        return [name for name in names if (dest / name).exists()]

    def existing_export_destination_names(
        self, output_dir: Path, assets: list
    ) -> list[str]:
        names = [
            planned_export_filename(
                name=getattr(asset, "name", "") or "",
                container=getattr(asset, "container", "") or "",
                path_id=str(getattr(asset, "path_id", "") or ""),
            )
            for asset in assets
        ]
        return self.existing_destination_names(output_dir, names)

    def can_edit_asset(self) -> bool:
        """Check if editing is possible (exactly one asset selected)"""
        return len(self.selected_assets) == 1

    def can_export_assets(self) -> bool:
        """Check if export is possible (at least one asset selected)"""
        return len(self.selected_assets) > 0

    def edit_asset(self, asset: AssetInfo, source_path: str) -> bool:
        """
        Edit asset with new data from source path

        Args:
            asset: Asset to edit
            source_path: Path to replacement data

        Returns:
            True if edit started successfully, False otherwise
        """
        if self.edit_worker and self.edit_worker.isRunning():
            self.status_message.emit(
                "Another replace is currently running.", logging.WARNING
            )
            return False

        self.remember_replace_directory_from_path(source_path)
        self.edit_started.emit(f"Replacing {asset.name}...")
        self.edit_worker = EditWorker(asset, source_path)
        self.edit_worker.finished.connect(self._on_edit_finished)
        self.edit_worker.start()
        return True

    def _on_edit_finished(self, asset_obj: object, result_obj: object) -> None:
        """Handle edit completion"""
        asset = asset_obj if isinstance(asset_obj, AssetInfo) else None
        result = result_obj if isinstance(result_obj, EditResult) else None

        if not asset or not result:
            self.status_message.emit(
                "Edit thread returned invalid data.", logging.ERROR
            )
            self.edit_finished.emit(None, None)
            return

        level = logging.INFO if result.is_success else logging.ERROR
        message = result.message or (
            f"Replaced {asset.name}"
            if result.is_success
            else f"Failed to replace {asset.name}"
        )

        self.status_message.emit(message, level)
        self.edit_finished.emit(asset, result)

        if result.is_success:
            log.info(message)
        else:
            log.error(message)

    def export_single_asset(self, asset: AssetInfo, output_path: Path) -> ExportResult:
        """
        Export single asset to specific path

        Args:
            asset: Asset to export
            output_path: Full output path including filename

        Returns:
            ExportResult object
        """
        self.remember_output_directory(str(output_path.parent))
        result = asset.export(output_path.parent, output_path.name)

        level = logging.INFO if result.is_success else logging.ERROR
        message = result.message or (
            "Export completed" if result.is_success else "Export failed"
        )

        self.export_completed.emit(message, level)

        if result.is_success:
            log.info(message)
        else:
            log.error(f"Failed to export {asset.name}: {result.message}")

        return result

    def export_multiple_assets(
        self, assets: list[AssetInfo], output_dir: Path
    ) -> tuple[int, int]:
        """
        Export multiple assets to directory

        Args:
            assets: List of assets to export
            output_dir: Output directory path

        Returns:
            Tuple of (successful_count, total_count)
        """
        self.remember_output_directory(str(output_dir))
        successes = 0
        total = len(assets)

        for asset in assets:
            result = asset.export(output_dir)
            if result.is_success:
                successes += 1
                log.info(result.message or f"Exported {asset.name}")
            else:
                log.error(f"Failed to export {asset.name}: {result.message}")

        # Determine message and level
        if successes == total:
            message = f"Exported {successes} assets to {output_dir}."
            level = logging.INFO
        elif successes > 0:
            message = f"Exported {successes}/{total} assets to {output_dir}. Check log for details."
            level = logging.WARNING
        else:
            message = "All selected exports failed."
            level = logging.ERROR

        self.export_completed.emit(message, level)
        return successes, total

    def get_suggested_export_filename(self, asset: AssetInfo) -> str:
        """
        Get suggested filename for exporting asset

        Args:
            asset: Asset to get filename for

        Returns:
            Suggested filename string
        """
        if asset.name and Path(asset.name).suffix:
            return asset.name
        elif asset.container:
            return Path(asset.container).name
        else:
            suggested_name = f"{asset.name}_{asset.path_id}"
            if asset.obj_type.name == "Texture2D":
                suggested_name += ".png"
            elif asset.obj_type.name == "TextAsset":
                suggested_name += ".txt"
            return suggested_name

    def get_edit_file_filter(self, asset: AssetInfo) -> Optional[str]:
        """
        Get file dialog filter for editing asset

        Args:
            asset: Asset to get filter for

        Returns:
            Filter string or None if editing not supported
        """
        if asset.obj_type.name == "Texture2D":
            return "Image Files (*.png *.jpg *.jpeg *.bmp *.tga *.dds);;All Files (*.*)"
        elif asset.obj_type.name == "TextAsset":
            return "All Files (*.*)"
        return None

    def is_editing_supported(self, asset: AssetInfo) -> bool:
        """Check if editing is supported for asset type"""
        return asset.obj_type.name in ["Texture2D", "TextAsset"]

    # ===== Save Operations =====

    def get_source_files(self) -> list[tuple[str, bool]]:
        """
        Get list of source files with their change status

        Returns:
            List of tuples (filepath, is_changed)
        """
        if not self.core or not hasattr(self.core, "_env"):
            return []

        files = []
        for path, file_obj in self.core._env.files.items():
            is_changed = hasattr(file_obj, "is_changed") and file_obj.is_changed  # type: ignore
            files.append((path, is_changed))

        return files

    def has_changed_files(self) -> bool:
        """Check if there are any changed files"""
        if not self.core or not hasattr(self.core, "_env"):
            return False

        for file_obj in self.core._env.files.values():
            if hasattr(file_obj, "is_changed") and file_obj.is_changed:  # type: ignore
                return True
        return False

    def save_all_files(
        self,
        output_dir: Path,
        packer: str | None = None,
        resource_patch_mode: str | None = None,
        crc_mode: str | None = None,
    ):
        """
        Save all changed bundle files

        Args:
            output_dir: Output directory path
            packer: Compression method (none, lz4, lz4hc, lzma, or original)
            resource_patch_mode: Resource-file mode
            crc_mode: CRC mode
        """
        if not self.core:
            self.status_message.emit("No files loaded", logging.WARNING)
            return False

        if self.save_worker and self.save_worker.isRunning():
            self.status_message.emit(
                "Another save is currently running.", logging.WARNING
            )
            return False

        if not self.has_changed_files():
            self.status_message.emit("No changed files to save", logging.INFO)
            return False

        self.persist_save_options(packer, resource_patch_mode, crc_mode)
        self.remember_output_directory(str(output_dir))

        self.save_started.emit("Saving all changed files...")
        self._start_save_worker(
            SaveWorker(
                self.core,
                output_dir,
                self.packer,
                resource_patch_mode=self.resource_patch_mode,
                crc_mode=self.crc_mode,
            )
        )
        return True

    def save_selected_file(
        self,
        filepath: str,
        output_dir: Path,
        packer: str | None = None,
        output_filename: Optional[str] = None,
        resource_patch_mode: str | None = None,
        crc_mode: str | None = None,
    ):
        """
        Save a specific bundle file

        Args:
            filepath: Path of file to save
            output_dir: Output directory path
            packer: Compression method (none, lz4, lz4hc, lzma, or original)
            output_filename: Optional custom output filename
            resource_patch_mode: Resource-file mode
            crc_mode: CRC mode
        """
        if not self.core:
            self.status_message.emit("No files loaded", logging.WARNING)
            return False

        if self.save_worker and self.save_worker.isRunning():
            self.status_message.emit(
                "Another save is currently running.", logging.WARNING
            )
            return False

        self.persist_save_options(packer, resource_patch_mode, crc_mode)
        self.remember_output_directory(str(output_dir))

        display_name = output_filename or Path(filepath).name
        self.save_started.emit(f"Saving {display_name}...")

        self._start_save_worker(
            SaveWorker(
                self.core,
                output_dir,
                self.packer,
                filepath,
                output_filename,
                resource_patch_mode=self.resource_patch_mode,
                crc_mode=self.crc_mode,
            )
        )
        return True

    def save_multiple_files(
        self,
        filepaths: list[str],
        output_dir: Path,
        packer: str | None = None,
        resource_patch_mode: str | None = None,
        crc_mode: str | None = None,
    ):
        """
        Save multiple selected bundle files

        Args:
            filepaths: List of file paths to save
            output_dir: Output directory path
            packer: Compression method (none, lz4, lz4hc, lzma, or original)
            resource_patch_mode: Resource-file mode
            crc_mode: CRC mode
        """
        if not self.core:
            self.status_message.emit("No files loaded", logging.WARNING)
            return False

        if self.save_worker and self.save_worker.isRunning():
            self.status_message.emit(
                "Another save is currently running.", logging.WARNING
            )
            return False

        if not filepaths:
            self.status_message.emit("No files selected", logging.INFO)
            return False

        self.persist_save_options(packer, resource_patch_mode, crc_mode)
        self.remember_output_directory(str(output_dir))

        self.save_started.emit(f"Saving {len(filepaths)} selected file(s)...")

        self._start_save_worker(
            SaveWorker(
                self.core,
                output_dir,
                self.packer,
                specific_files=filepaths,
                resource_patch_mode=self.resource_patch_mode,
                crc_mode=self.crc_mode,
            )
        )
        return True

    def _start_save_worker(self, worker: SaveWorker) -> None:
        self.save_worker = worker
        worker.progress.connect(self._on_save_progress)
        worker.finished.connect(self._on_save_finished)
        worker.error.connect(self._on_save_error)
        worker.warning.connect(self.save_warning)
        worker.start()

    def _on_save_progress(self, current: int, total: int, filename: str):
        """Handle save progress updates"""
        self.save_progress.emit(current, total, filename)

    def _on_save_finished(self, success: bool, message: str):
        """Handle save completion"""
        level = logging.INFO if success else logging.ERROR
        self.save_finished.emit(success, message)
        self.status_message.emit(message, level)

    def _on_save_error(self, error_msg: str):
        """Handle save error"""
        self.status_message.emit(error_msg, logging.ERROR)
