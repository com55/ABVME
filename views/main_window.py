"""
Main Window - MVVM Pattern
Composes all UI components and wires them with ViewModel
"""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtCore import QMimeData
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QPixmap,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStatusBar,
    QProgressBar,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
)

from viewmodels import MainViewModel
from views.asset_table_widget import AssetTableWidget
from views.drop_overlay import DropOverlay
from views.preview_panel_widget import PreviewPanelWidget
from utilities.file_drop_widget import FileDropWidget
from utilities.resource_path import get_resource_str
from utilities.drop_classifier import (
    DropAction,
    DropDecision,
    classify_drop,
    suffix_in_container,
)
from services import StatusBarHandler
from models import AssetInfo, EditResult
from models.save_options import CRC_LABELS, PACKER_LABELS, RESOURCE_LABELS
from models.texture_replace_options import TextureReplaceOptions
from views.overwrite_confirm import confirm_overwrite_existing
from views.about_dialog import AboutDialog
from views.texture_replace_dialog import TextureReplaceDialog, pixmap_from_path
from utilities.app_info import app_version, window_title
from utilities.updater import (
    UpdateInfo,
    fetch_latest_release,
    format_update_status_message,
    is_newer,
    should_check_for_updates,
)


log = logging.getLogger("ABVME")

_MENU_ICON_SIZE = 16
_OPEN_FOLDER_CONFIRM_AFTER = 100


def _show_save_finished_message(parent, success: bool, message: str) -> None:
    if not success:
        QMessageBox.critical(parent, "Save Failed", message)
    elif "CRC not applied" in message or "Resource patch:" in message:
        QMessageBox.warning(parent, "Save Complete", message)
    else:
        QMessageBox.information(parent, "Save Complete", message)


def _menu_icon(relative_path: str | None = None) -> QIcon:
    """Return a menu-item icon, or a transparent placeholder if none is given.

    Qt sizes the icon column from the widest icon in that menu, so every
    non-checkable action needs an icon — even items with no artwork.
    Checkable items must stay icon-less so Qt can draw the check mark.
    """
    if relative_path:
        return QIcon(get_resource_str(relative_path))
    pixmap = QPixmap(_MENU_ICON_SIZE, _MENU_ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    return QIcon(pixmap)


class ABVMEMainWindow(QMainWindow):
    """
    Main application window
    Follows MVVM pattern - composes Views and binds them to ViewModel
    """

    # Class-level Signal definition
    log_signal = Signal(str, int)
    update_check_finished = Signal(object)  # ReleaseInfo | None on failure use None

    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle(window_title())
        self._pending_update: UpdateInfo | None = None
        self.setWindowIcon(QIcon(get_resource_str("assets/icon.ico")))
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        # Create ViewModel
        self.viewmodel = MainViewModel(settings=settings)
        self._auto_fit_columns_on_load = True
        self._unitypy_warmup_thread: threading.Thread | None = None
        self._drop_overlay_warmed = False

        # Initialize UI
        self._setup_status_bar()
        self._setup_ui()
        self._setup_menubar()
        self._connect_viewmodel()
        self._setup_logging()
        self.update_check_finished.connect(self._on_update_check_finished)
        self._restore_pending_update()
        QTimer.singleShot(1500, self._maybe_start_update_check)

    def _setup_status_bar(self):
        """Setup status bar with progress indicator"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet("background-color: '#3c3c3c';")

        # Permanent left label for idle text (Ready / update banner). Temporary
        # showMessage() overlays this; clearMessage() reveals it again — so Ready
        # never "vanishes" into a blank bar after a log timeout.
        self.idle_status_label = QLabel("Ready")
        self.idle_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.idle_status_label.setOpenExternalLinks(False)
        self.idle_status_label.linkActivated.connect(
            lambda _href: self._on_about_clicked()
        )
        self.idle_status_label.setStyleSheet(
            "background-color: transparent; color: #cccccc;"
        )
        self.status_bar.addWidget(self.idle_status_label)
        self._update_banner_active = False

        self.progress_bar = QProgressBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setContentsMargins(5, 0, 5, 0)
        self.progress_bar.setRange(0, 0)  # Busy indicator
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(int(self.width() / 3))
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self._active_background_tasks = 0

        # Status timer for auto-clear of temporary showMessage text
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self._clear_status_bar)

    def _setup_logging(self):
        """Setup logging handler to forward logs to status bar"""
        # Connect signal
        self.log_signal.connect(self._on_log_received)

        # Setup handler
        self.status_handler = StatusBarHandler(self.log_signal)
        logger = logging.getLogger("ABVME")
        logger.addHandler(self.status_handler)

    def _setup_ui(self):
        """Setup UI components"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Panel: Asset List
        self._setup_left_panel()

        # Right Panel: Preview Area
        self._setup_right_panel()

        # Splitter to separate panels
        left_panel_widget = self.left_panel
        right_panel_widget = self.right_panel

        left_panel_widget.setMinimumWidth(350)
        self.preview_panel.stack.setMinimumWidth(200)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        splitter.addWidget(left_panel_widget)
        splitter.addWidget(right_panel_widget)
        splitter.setSizes([500, 500])

        main_layout.addWidget(splitter)

        self.drop_overlay = DropOverlay(central_widget)
        self._pending_drop: tuple[DropDecision, str | None] | None = None
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._flush_drop_overlay)
        self._disable_child_drops()
        self.setAcceptDrops(True)

    def _setup_menubar(self) -> None:
        """Setup application menu bar mirroring toolbar actions."""
        menu_bar = self.menuBar()
        self._file_menu = menu_bar.addMenu("&File")
        self.open_action = QAction("Open Files...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setIcon(_menu_icon("assets/folder-open-regular.svg"))
        self.open_action.triggered.connect(self._on_load_button_clicked)
        self._file_menu.addAction(self.open_action)

        self.open_folder_action = QAction("Open Folder...", self)
        self.open_folder_action.setShortcut("Ctrl+Shift+O")
        self.open_folder_action.setIcon(_menu_icon("assets/folder-open-regular.svg"))
        self.open_folder_action.triggered.connect(self._on_open_folder_clicked)
        self._file_menu.addAction(self.open_folder_action)

        self.save_action = QAction("Save as...", self)
        self.save_action.setShortcut("Ctrl+Shift+S")
        self.save_action.setIcon(_menu_icon("assets/floppy-disk-regular.svg"))
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self._on_save_button_clicked)
        self._file_menu.addAction(self.save_action)

        self._file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setIcon(_menu_icon())
        exit_action.triggered.connect(self.close)
        self._file_menu.addAction(exit_action)

        self._asset_menu = menu_bar.addMenu("&Asset")
        self.replace_action = QAction("Replace...", self)
        self.replace_action.setShortcut("Ctrl+R")
        self.replace_action.setIcon(_menu_icon("assets/wand-magic-sparkles-solid.svg"))
        self.replace_action.setEnabled(False)
        self.replace_action.triggered.connect(self._on_edit_button_clicked)
        self._asset_menu.addAction(self.replace_action)

        self.export_action = QAction("Export...", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setIcon(_menu_icon("assets/file-export-solid.svg"))
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._on_export_button_clicked)
        self._asset_menu.addAction(self.export_action)

        options_menu = menu_bar.addMenu("&Options")
        self._options_menu = options_menu
        self.show_all_action = QAction("&Display all assets", self)
        self.show_all_action.setCheckable(True)
        self.show_all_action.setChecked(self.viewmodel.show_all_objects)
        self.show_all_action.toggled.connect(self.viewmodel.set_show_all_objects)
        options_menu.addAction(self.show_all_action)
        options_menu.addSeparator()

        self._save_options_menu = options_menu.addMenu("Save Options")
        self._save_options_menu.menuAction().setIcon(_menu_icon())

        self._packer_group = QActionGroup(self)
        self._packer_group.setExclusive(True)
        self._compression_menu = self._save_options_menu.addMenu("Compression")
        self._compression_menu.menuAction().setIcon(_menu_icon())
        for label, value in PACKER_LABELS.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(value)
            self._packer_group.addAction(action)
            self._compression_menu.addAction(action)
        self._packer_group.triggered.connect(self._on_packer_option)

        self._resource_group = QActionGroup(self)
        self._resource_group.setExclusive(True)
        self._resource_menu = self._save_options_menu.addMenu("Resource Patch Method")
        self._resource_menu.menuAction().setIcon(_menu_icon())
        for label, value in RESOURCE_LABELS.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(value)
            self._resource_group.addAction(action)
            self._resource_menu.addAction(action)
        self._resource_group.triggered.connect(self._on_resource_option)

        self._crc_group = QActionGroup(self)
        self._crc_group.setExclusive(True)
        self._crc_menu = self._save_options_menu.addMenu("CRC Correction")
        self._crc_menu.menuAction().setIcon(_menu_icon())
        for label, value in CRC_LABELS.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(value)
            self._crc_group.addAction(action)
            self._crc_menu.addAction(action)
        self._crc_group.triggered.connect(self._on_crc_option)

        options_menu.aboutToShow.connect(self._sync_options_menu)
        self._sync_options_menu()

        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._on_about_clicked)
        menu_bar.addAction(self.about_action)

    def _on_about_clicked(self) -> None:
        dialog = AboutDialog(
            self,
            pending_update=self._pending_update,
            on_update_found=self._on_update_found,
            on_update_cleared=self._on_update_cleared,
        )
        dialog.exec()

    def _restore_pending_update(self) -> None:
        info = self.viewmodel.get_pending_update()
        if info is None:
            return
        if not is_newer(info.latest_version, app_version()):
            self.viewmodel.clear_pending_update()
            return
        self._apply_pending_update(info, persist=False)

    def _on_update_found(self, update: UpdateInfo) -> None:
        self._apply_pending_update(update, persist=True)

    def _on_update_cleared(self) -> None:
        self._pending_update = None
        self.viewmodel.clear_pending_update()
        self._set_idle_status_ready()

    def _apply_pending_update(self, update: UpdateInfo, *, persist: bool) -> None:
        self._pending_update = update
        if persist:
            self.viewmodel.set_pending_update(update)
        self._show_update_status(update.release_name)

    def _show_update_status(self, release_name: str) -> None:
        self.status_timer.stop()
        self.status_bar.clearMessage()
        self._update_banner_active = True
        self.idle_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.idle_status_label.setText(format_update_status_message(release_name))

    def _set_idle_status_ready(self) -> None:
        self.status_timer.stop()
        self.status_bar.clearMessage()
        self._update_banner_active = False
        self.idle_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.idle_status_label.setText("Ready")

    def _restore_idle_status(self) -> None:
        """Clear temporary showMessage so the permanent idle label shows again."""
        self.status_bar.clearMessage()

    def _maybe_start_update_check(self) -> None:
        from datetime import datetime, timezone

        last = self.viewmodel.get_last_update_check()
        now = datetime.now(timezone.utc)
        if not should_check_for_updates(last, now=now):
            return

        def worker() -> None:
            try:
                latest = fetch_latest_release()
            except Exception as exc:
                log.debug("Startup update check failed: %s", exc)
                self.update_check_finished.emit(None)
                return
            self.update_check_finished.emit(latest)

        threading.Thread(target=worker, daemon=True, name="abvme-update-check").start()

    def _on_update_check_finished(self, latest: object) -> None:
        from datetime import datetime, timezone

        if latest is None:
            return
        self.viewmodel.set_last_update_check(datetime.now(timezone.utc))
        current = app_version()
        if not is_newer(latest.latest_version, current):  # type: ignore[attr-defined]
            self._on_update_cleared()
            return
        info = UpdateInfo(
            current_version=current.lstrip("v"),
            latest_version=latest.latest_version,  # type: ignore[attr-defined]
            release_name=latest.release_name,  # type: ignore[attr-defined]
            release_url=latest.release_url,  # type: ignore[attr-defined]
            tag_name=latest.tag_name,  # type: ignore[attr-defined]
            body=latest.body,  # type: ignore[attr-defined]
            assets=list(latest.assets),  # type: ignore[attr-defined]
        )
        self._on_update_found(info)

    def _on_packer_option(self, action: QAction) -> None:
        self.viewmodel.set_packer(str(action.data()))

    def _on_resource_option(self, action: QAction) -> None:
        self.viewmodel.set_resource_patch_mode(str(action.data()))

    def _on_crc_option(self, action: QAction) -> None:
        self.viewmodel.set_crc_mode(str(action.data()))

    def _sync_options_menu(self) -> None:
        self.show_all_action.blockSignals(True)
        self.show_all_action.setChecked(self.viewmodel.show_all_objects)
        self.show_all_action.blockSignals(False)
        self._sync_option_group(self._packer_group, self.viewmodel.packer)
        self._sync_option_group(
            self._resource_group, self.viewmodel.resource_patch_mode.value
        )
        self._sync_option_group(self._crc_group, self.viewmodel.crc_mode.value)

    def _sync_option_group(self, group: QActionGroup, current: str) -> None:
        for action in group.actions():
            action.blockSignals(True)
            action.setChecked(str(action.data()) == current)
            action.blockSignals(False)

    def _setup_left_panel(self):
        """Setup left panel with load button and asset table"""
        self.left_panel = FileDropWidget()

        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(5, 0, 5, 0)

        # Buttons layout
        button_layout = QHBoxLayout()
        self.load_button = QPushButton("  Open Files")
        self.load_button.setIcon(
            QIcon(get_resource_str("assets/folder-open-regular.svg"))
        )
        self.load_button.setIconSize(QSize(16, 16))
        self.load_button.clicked.connect(self._on_load_button_clicked)
        button_layout.addWidget(self.load_button)
        button_layout.addStretch()

        # Save button
        self.save_button = QPushButton("  Save as...")
        self.save_button.setIcon(
            QIcon(get_resource_str("assets/floppy-disk-regular.svg"))
        )
        self.save_button.setIconSize(QSize(16, 16))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_button_clicked)
        button_layout.addWidget(self.save_button)

        left_layout.addLayout(button_layout)

        # Asset table
        self.asset_table = AssetTableWidget()
        self.asset_table.selection_changed.connect(self._on_table_selection_changed)
        self.asset_table.filter_changed.connect(self._on_filter_changed)
        left_layout.addWidget(self.asset_table)

    def _setup_right_panel(self):
        """Setup right panel with preview and action buttons"""
        self.right_panel = FileDropWidget()

        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(5, 0, 5, 0)

        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.edit_button = QPushButton("  Replace")
        self.edit_button.setIcon(
            QIcon(get_resource_str("assets/wand-magic-sparkles-solid.svg"))
        )
        self.edit_button.setIconSize(QSize(16, 16))
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self._on_edit_button_clicked)
        actions_layout.addWidget(self.edit_button)

        self.export_button = QPushButton("  Export")
        self.export_button.setIcon(
            QIcon(get_resource_str("assets/file-export-solid.svg"))
        )
        self.export_button.setIconSize(QSize(16, 16))
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._on_export_button_clicked)
        actions_layout.addWidget(self.export_button)

        right_layout.addLayout(actions_layout)

        # Preview panel
        self.preview_panel = PreviewPanelWidget()
        right_layout.addWidget(self.preview_panel)
        right_layout.setStretchFactor(self.preview_panel, 1)

    def _connect_viewmodel(self):
        """Connect ViewModel signals to View slots"""
        # Loading signals
        self.viewmodel.loading_started.connect(self._on_loading_started)
        self.viewmodel.loading_progress.connect(self._on_loading_progress)
        self.viewmodel.loading_finished.connect(self._on_loading_finished)
        self.viewmodel.assets_loaded.connect(self._on_assets_loaded)

        # Edit signals
        self.viewmodel.edit_started.connect(self._on_edit_started)
        self.viewmodel.edit_finished.connect(self._on_edit_finished)

        # Export signals
        self.viewmodel.export_completed.connect(self._on_export_completed)

        # Save signals
        self.viewmodel.save_started.connect(self._on_save_started)
        self.viewmodel.save_progress.connect(self._on_save_progress)
        self.viewmodel.save_finished.connect(self._on_save_finished)
        self.viewmodel.save_warning.connect(self._on_save_warning)

        # Selection signals
        self.viewmodel.selection_changed.connect(self._on_selection_changed)

        # Status signals
        self.viewmodel.status_message.connect(self._on_status_message)

    # ===== ViewModel Signal Handlers =====

    def _on_loading_started(self, message: str):
        """Handle loading started"""
        self.setEnabled(False)
        self._auto_fit_columns_on_load = True
        self.asset_table.clear_table()
        self.asset_table.apply_filter(clear=True)
        self.preview_panel.show_placeholder()
        self._begin_background_task(message, show_progress=True)

    def _on_loading_progress(self, current: int, total: int, filename: str):
        """Handle loading progress update"""
        if total == 1:
            self.progress_bar.setRange(0, 0)
        else:
            current -= 1
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{current}/{total}")
            self.status_bar.showMessage(f"Loading: {filename}")

    def _on_loading_finished(self, message: str):
        """Handle loading finished"""
        self.setEnabled(True)
        # Reset progress bar to busy indicator mode
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self._end_background_task(message)

    def _on_assets_loaded(self, assets: list[AssetInfo]):
        """Handle assets loaded into table"""
        self.asset_table.load_assets(assets, auto_fit=self._auto_fit_columns_on_load)
        self._auto_fit_columns_on_load = False
        self.preview_panel.show_placeholder(
            "Select an asset from the list to view its preview."
        )
        self.asset_table.apply_filter()

        has_assets = len(assets) > 0
        self.save_button.setEnabled(has_assets)
        self.save_action.setEnabled(has_assets)

    def _on_edit_started(self, message: str):
        """Handle edit started"""
        self._begin_background_task(message)

    def _on_edit_finished(self, asset: AssetInfo, result: EditResult):
        """Handle edit finished"""
        self._end_background_task()
        if result and result.is_success and asset:
            self._refresh_preview()
            self.asset_table.refresh_asset_display(asset)

    def _on_export_completed(self, message: str, level: int):
        """Handle export completed"""
        self._on_status_message(message, level)

    def _on_selection_changed(self, count: int):
        """Handle selection changed"""
        self.export_button.setEnabled(count > 0)
        self.export_action.setEnabled(count > 0)

        # Enable edit button only if exactly one editable asset is selected
        if count == 1:
            asset = self.viewmodel.get_single_selected_asset()
            can_edit = asset is not None and asset.is_editable
            self.edit_button.setEnabled(can_edit)
            self.replace_action.setEnabled(can_edit)
        else:
            self.edit_button.setEnabled(False)
            self.replace_action.setEnabled(False)

    def _on_status_message(self, message: str, level: int):
        """Handle status message"""
        self.status_bar.showMessage(message)
        if level == logging.INFO:
            self.status_timer.start(10000)

    def _on_log_received(self, msg: str, level: int):
        """Handle log message received"""
        self._on_status_message(msg, level)

    def _on_save_started(self, message: str):
        """Handle save operation started"""
        self.setEnabled(False)
        self._begin_background_task(message, show_progress=True)

    def _on_save_warning(self, message: str) -> None:
        pass

    def _on_save_progress(self, current: int, total: int, filename: str):
        """Handle save progress update"""
        if total == 1:
            self.progress_bar.setRange(0, 0)
        else:
            current -= 1
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{current}/{total}")
            self.status_bar.showMessage(f"Saving: {filename}")

    def _on_save_finished(self, success: bool, message: str):
        """Handle save operation completed"""
        self.setEnabled(True)
        self._end_background_task(message)

        if hasattr(self, "_save_dialog") and self._save_dialog:
            self._save_dialog.on_save_finished(success, message)
        else:
            _show_save_finished_message(self, success, message)

    # ===== UI Event Handlers =====

    def _on_load_button_clicked(self):
        """Handle load button click"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Asset Bundles",
            self.viewmodel.get_open_dialog_start_directory(),
            "Asset Bundles (*.bundle *.unity3d);;All Files (*.*)",
        )
        if files:
            self.viewmodel.load_files_from_paths(files)

    def _on_open_folder_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            self.viewmodel.get_open_dialog_start_directory(),
        )
        if not directory:
            return
        self.viewmodel.remember_open_directory(directory)
        files = self.viewmodel.bundle_files_in_directory(directory)
        if not files:
            self.viewmodel.status_message.emit(
                "No asset bundles were found in the selected folder.",
                logging.WARNING,
            )
            return
        if len(files) > _OPEN_FOLDER_CONFIRM_AFTER:
            reply = QMessageBox.question(
                self,
                "Open Folder",
                (
                    f"The selected folder contains {len(files)} asset bundles.\n\n"
                    "Load them all?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.viewmodel.load_files_from_paths(files)

    def _on_table_selection_changed(self, selected_assets: list[AssetInfo]):
        """Handle table selection changed"""
        self.viewmodel.update_selection(selected_assets)

        # Update preview
        if len(selected_assets) == 0:
            self.preview_panel.show_placeholder(
                "Select an asset from the list to view its preview."
            )
        elif len(selected_assets) == 1:
            self.preview_panel.show_asset_preview(selected_assets[0])
        # If multiple selected, keep current preview

    def _on_filter_changed(self):
        """Handle filter changed"""
        self.asset_table.apply_filter()

    def _on_save_button_clicked(self):
        """Handle Save as... button click"""
        from views.save_dialog import SaveDialog

        # Create and show dialog
        dialog = SaveDialog(self.viewmodel, self)

        # Connect dialog signals
        dialog.save_all_requested.connect(self._handle_save_all)
        dialog.save_selected_requested.connect(self._handle_save_selected)
        dialog.save_multiple_selected_requested.connect(
            self._handle_save_multiple_selected
        )

        # Store reference to update it later
        self._save_dialog = dialog

        dialog.exec()

    def _handle_save_all(
        self,
        output_dir: str,
        packer: str,
        resource_patch_mode: str,
        crc_mode: str,
    ):
        """Handle save all request from dialog"""
        from pathlib import Path

        success = self.viewmodel.save_all_files(
            Path(output_dir), packer, resource_patch_mode, crc_mode
        )
        if not success and hasattr(self, "_save_dialog"):
            # Re-enable dialog if save didn't start
            self._save_dialog.setEnabled(True)

    def _handle_save_selected(
        self,
        filepath: str,
        output_path: str,
        packer: str,
        resource_patch_mode: str,
        crc_mode: str,
    ):
        """Handle save selected file request from dialog"""
        from pathlib import Path

        # Split output path into directory and filename
        output_path_obj = Path(output_path)
        output_dir = output_path_obj.parent
        output_filename = output_path_obj.name

        success = self.viewmodel.save_selected_file(
            filepath,
            output_dir,
            packer,
            output_filename,
            resource_patch_mode,
            crc_mode,
        )
        if not success and hasattr(self, "_save_dialog"):
            # Re-enable dialog if save didn't start
            self._save_dialog.setEnabled(True)

    def _handle_save_multiple_selected(
        self,
        filepaths: list[str],
        output_dir: str,
        packer: str,
        resource_patch_mode: str,
        crc_mode: str,
    ):
        """Handle save multiple selected files request from dialog"""
        from pathlib import Path

        success = self.viewmodel.save_multiple_files(
            filepaths, Path(output_dir), packer, resource_patch_mode, crc_mode
        )
        if not success and hasattr(self, "_save_dialog"):
            # Re-enable dialog if save didn't start
            self._save_dialog.setEnabled(True)

    def _on_edit_button_clicked(self):
        """Handle edit button click"""
        asset = self.viewmodel.get_single_selected_asset()
        if not asset:
            return

        if not self.viewmodel.is_editing_supported(asset):
            self._on_status_message(
                f"Replace is not supported for {asset.obj_type.name}.", logging.WARNING
            )
            return

        file_filter = self.viewmodel.get_edit_file_filter(asset)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select replacement file",
            self.viewmodel.get_replace_dialog_start_directory(),
            file_filter or "",
        )

        if file_path:
            self._start_replace(asset, file_path)

    def _start_replace(self, asset: AssetInfo, file_path: str) -> bool:
        if asset.obj_type.name == "Texture2D":
            options = self._confirm_texture_replace(asset, file_path)
            if options is None:
                return False
            return self.viewmodel.edit_asset(asset, file_path, texture_options=options)
        if asset.obj_type.name == "TextAsset" and not suffix_in_container(
            file_path, asset.container
        ):
            if not self._confirm_unmatched_textasset_replace(asset, file_path):
                return False
        elif not self._confirm_replace(asset, file_path):
            return False
        return self.viewmodel.edit_asset(asset, file_path)

    def _front_dialog(self, box: QDialog) -> None:
        self.raise_()
        self.activateWindow()
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        # Briefly stay on top so Explorer-drop focus does not leave the dialog
        # behind, then clear the hint so it is not stuck above other apps.
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.show()
        box.raise_()
        box.activateWindow()
        handle = box.windowHandle()
        if handle is not None:
            handle.requestActivate()
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        box.show()
        box.raise_()
        box.activateWindow()

    def _ask_yes_no(self, title: str, text: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        self._front_dialog(box)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _ask_replace_with_options(self, title: str, text: str) -> str:
        # Same QMessageBox shell as TextAsset confirm; Options… pinned left.
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        yes_btn = box.addButton(QMessageBox.StandardButton.Yes)
        no_btn = box.addButton(QMessageBox.StandardButton.No)
        options_btn = box.addButton("Options...", QMessageBox.ButtonRole.ActionRole)
        options_btn.setAutoDefault(False)
        options_btn.setDefault(False)
        options_btn.setFlat(True)
        options_btn.setStyleSheet(
            "QPushButton { color: #9d9d9d; border: none; background: transparent; "
            "padding: 6px 12px; }"
            "QPushButton:hover { color: #cccccc; }"
        )
        box.setDefaultButton(yes_btn)
        self._front_dialog(box)
        self._pin_options_button_left(box, options_btn, yes_btn, no_btn)
        # QMessageBox may ignore setMinimumSize; nudge size after layout for a
        # roomier Options… row (best-effort; native styles can still clamp).
        hint = box.sizeHint()
        target_w = max(450, hint.width(), box.width())
        target_h = max(140, hint.height(), box.height())
        box.setMinimumSize(target_w, target_h)
        box.resize(target_w, target_h)
        # Pin again after resize in case the button box relayouts.
        self._pin_options_button_left(box, options_btn, yes_btn, no_btn)
        result = box.exec()
        clicked = box.clickedButton()
        if clicked is options_btn:
            return "options"
        if clicked is yes_btn or result == QMessageBox.StandardButton.Yes:
            return "yes"
        return "no"

    @staticmethod
    def _pin_options_button_left(
        box: QMessageBox,
        options_btn: QPushButton,
        yes_btn: QPushButton,
        no_btn: QPushButton,
    ) -> None:
        """Force row order: Options… | stretch | Yes | No."""
        button_box = box.findChild(QDialogButtonBox)
        if button_box is None:
            return
        layout = button_box.layout()
        if layout is None:
            return
        while layout.count():
            layout.takeAt(0)
        layout.addWidget(options_btn)
        layout.addStretch(1)
        layout.addWidget(yes_btn)
        layout.addWidget(no_btn)

    def _show_texture_replace_dialog(
        self, asset: AssetInfo, file_path: str
    ) -> TextureReplaceOptions | None:
        options = asset.texture_replace_options()
        old_pixmap = None
        try:
            preview = asset.get_preview()
            data = getattr(preview, "data", None)
            to_qpixmap = getattr(data, "toqpixmap", None)
            if callable(to_qpixmap):
                old_pixmap = to_qpixmap()
        except Exception:
            old_pixmap = None
        dialog = TextureReplaceDialog(
            options,
            texture_name=asset.name or "",
            file_name=Path(file_path).name,
            old_pixmap=old_pixmap,
            new_pixmap=pixmap_from_path(file_path),
            always_show=self.viewmodel.always_show_texture_options,
            parent=self,
        )
        self._front_dialog(dialog)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        self.viewmodel.set_always_show_texture_options(dialog.always_show_checked())
        return dialog.collect_options()

    def _confirm_texture_replace(
        self, asset: AssetInfo, file_path: str
    ) -> TextureReplaceOptions | None:
        if self.viewmodel.always_show_texture_options:
            return self._show_texture_replace_dialog(asset, file_path)
        choice = self._ask_replace_with_options(
            "Confirm Replace",
            f"Replace '{asset.name}' with '{Path(file_path).name}'?",
        )
        if choice == "yes":
            return asset.texture_replace_options()
        if choice == "options":
            return self._show_texture_replace_dialog(asset, file_path)
        return None

    def _confirm_replace(self, asset: AssetInfo, file_path: str) -> bool:
        return self._ask_yes_no(
            "Confirm Replace",
            f"Replace '{asset.name}' with '{Path(file_path).name}'?",
        )

    def _confirm_unmatched_textasset_replace(
        self, asset: AssetInfo, file_path: str
    ) -> bool:
        return self._ask_yes_no(
            "Confirm Replace",
            (
                f"The suffix of '{Path(file_path).name}' is not in the container "
                f"of '{asset.name}'. Replace anyway?"
            ),
        )

    def _on_export_button_clicked(self):
        """Handle export button click"""
        if len(self.viewmodel.selected_assets) == 1:
            asset = self.viewmodel.selected_assets[0]
            if not asset.is_exportable:
                self._on_status_message(
                    f"Export not supported for {asset.obj_type.name}.", logging.WARNING
                )
                QMessageBox.warning(
                    self,
                    "Export Not Supported",
                    f"Export not supported for {asset.obj_type.name} currently.",
                    QMessageBox.StandardButton.Ok,
                )
                return
        if not self.viewmodel.selected_assets:
            self._on_status_message("Select assets to export.", logging.WARNING)
            QMessageBox.information(
                self,
                "No Assets Selected",
                "Select at least one asset to export.",
                QMessageBox.StandardButton.Ok,
            )
            return

        if len(self.viewmodel.selected_assets) == 1:
            self._export_single_asset()
        else:
            self._export_multiple_assets()

    def _export_single_asset(self):
        """Export single selected asset"""
        asset = self.viewmodel.selected_assets[0]
        suggested_name = self.viewmodel.get_suggested_export_filename(asset)
        suggested_path = (
            Path(self.viewmodel.get_output_dialog_start_directory()) / suggested_name
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export {asset.name}", str(suggested_path), "All Files (*.*)"
        )

        if file_path:
            self.viewmodel.export_single_asset(asset, Path(file_path))

    def _export_multiple_assets(self):
        """Export multiple selected assets"""
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            self.viewmodel.get_output_dialog_start_directory(),
        )

        if output_dir:
            existing = self.viewmodel.existing_export_destination_names(
                Path(output_dir), self.viewmodel.selected_assets
            )
            if not confirm_overwrite_existing(self, existing):
                return
            success, total = self.viewmodel.export_multiple_assets(
                self.viewmodel.selected_assets, Path(output_dir)
            )
            message = f"Successfully exported {success} asset(s)."
            if success != total:
                message += f"Failed to export {total - success} asset(s)."
            QMessageBox.information(
                self, "Export Completed", message, QMessageBox.StandardButton.Ok
            )

    # ===== Drag & Drop Handlers =====

    def _disable_child_drops(self) -> None:
        """Make the window the only drop target."""
        central = self.centralWidget()
        if central is None:
            return
        central.setAcceptDrops(False)
        for child in central.findChildren(QWidget):
            child.setAcceptDrops(False)

    def _paths_from_mime(self, mime: QMimeData) -> list[str]:
        if not mime.hasUrls():
            return []
        paths: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if path and Path(path).is_file():
                paths.append(path)
        return paths

    def _current_drop_decision(self, paths: list[str]) -> DropDecision:
        asset = self.viewmodel.get_single_selected_asset()
        return classify_drop(
            paths,
            selected_type=asset.obj_type.name if asset else None,
            selected_name=asset.name if asset else None,
            selected_container=asset.container if asset else None,
            can_replace=bool(asset and self.viewmodel.is_editing_supported(asset)),
        )

    def _sync_drop_overlay(self) -> None:
        if not self.drop_overlay.isVisible():
            return
        central = self.centralWidget()
        if central is not None:
            self.drop_overlay.setGeometry(central.rect())
        self.drop_overlay.raise_()

    def _update_drag_overlay(
        self,
        event: QDragEnterEvent | QDragMoveEvent,
        *,
        immediate: bool,
    ) -> None:
        paths = self._paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        decision = self._current_drop_decision(paths)
        asset = self.viewmodel.get_single_selected_asset()
        target_name = asset.name if asset else None
        if self.drop_overlay.matches(decision, target_name):
            self._overlay_timer.stop()
            self._pending_drop = None
            return
        if immediate:
            self._overlay_timer.stop()
            self._pending_drop = None
            self.drop_overlay.show_decision(decision, target_name=target_name)
            self._sync_drop_overlay()
            return
        self._pending_drop = (decision, target_name)
        self._overlay_timer.start(40)

    def _flush_drop_overlay(self) -> None:
        pending = self._pending_drop
        if pending is None:
            return
        decision, target_name = pending
        self._pending_drop = None
        self.drop_overlay.show_decision(decision, target_name=target_name)
        self._sync_drop_overlay()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        self._update_drag_overlay(event, immediate=True)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        self._update_drag_overlay(event, immediate=False)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._overlay_timer.stop()
        self._pending_drop = None
        self.drop_overlay.clear()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._overlay_timer.stop()
        self._pending_drop = None
        self.drop_overlay.clear()
        paths = self._paths_from_mime(event.mimeData())
        decision = self._current_drop_decision(paths)
        if decision.action == DropAction.REJECT or not decision.file_paths:
            event.ignore()
            return

        if decision.action == DropAction.OPEN:
            self.viewmodel.load_files_from_paths(list(decision.file_paths))
            event.acceptProposedAction()
            return

        asset = self.viewmodel.get_single_selected_asset()
        if asset is None:
            event.ignore()
            return

        first_file = decision.file_paths[0]
        if decision.action in (DropAction.REPLACE, DropAction.REPLACE_CONFIRM):
            if not self._start_replace(asset, first_file):
                event.ignore()
                return
            event.acceptProposedAction()
            return

        event.ignore()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._start_unitypy_warmup()
        if not self._drop_overlay_warmed:
            QTimer.singleShot(0, self._warmup_drop_overlay)

    def _warmup_drop_overlay(self) -> None:
        if self._drop_overlay_warmed:
            return
        self._drop_overlay_warmed = True
        dummy = DropDecision(
            DropAction.OPEN,
            ("warmup.bundle",),
            "Open Asset Bundles",
            "warmup.bundle",
        )
        self.setUpdatesEnabled(False)
        try:
            self.drop_overlay.show_decision(dummy)
            self.drop_overlay.grab()
            self.drop_overlay.clear()
        finally:
            self.setUpdatesEnabled(True)

    def _start_unitypy_warmup(self) -> None:
        if self._unitypy_warmup_thread is not None:
            return
        from models.asset_model import warmup_unitypy

        self._unitypy_warmup_thread = threading.Thread(
            target=warmup_unitypy,
            daemon=True,
            name="unitypy-warmup",
        )
        self._unitypy_warmup_thread.start()

    def resizeEvent(self, event: QResizeEvent) -> None:
        if (
            getattr(self, "drop_overlay", None) is not None
            and self.drop_overlay.isVisible()
        ):
            central = self.centralWidget()
            if central is not None:
                self.drop_overlay.setGeometry(central.rect())
            self.drop_overlay.raise_()
        super().resizeEvent(event)

    # ===== Helper Methods =====

    def _begin_background_task(self, message: str, show_progress: bool = False):
        """Begin background task (show progress indicator)

        Args:
            message: Status message to display
            show_progress: If True, show progress bar with text (current/total format)
        """
        self._active_background_tasks += 1
        self.progress_bar.setVisible(True)
        if show_progress:
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setFormat("0/0")
        else:
            self.progress_bar.setRange(0, 0)  # Busy indicator
            self.progress_bar.setTextVisible(False)
        self.status_bar.showMessage(message)

    def _end_background_task(self, message: str | None = None):
        """End background task (hide progress indicator if no more tasks)"""
        self._active_background_tasks = max(0, self._active_background_tasks - 1)
        if self._active_background_tasks == 0:
            self.progress_bar.setVisible(False)
            if message:
                self.status_bar.showMessage(message)
            else:
                self._restore_idle_status()
        elif message:
            self.status_bar.showMessage(message)

    def _clear_status_bar(self):
        """Clear temporary status; permanent idle label (Ready / update) remains."""
        if self._active_background_tasks == 0:
            self._restore_idle_status()
        else:
            self.status_timer.start(10000)

    def _refresh_preview(self):
        """Refresh current preview"""
        asset = self.viewmodel.get_single_selected_asset()
        if asset:
            self.preview_panel.show_asset_preview(asset)
