"""
Main Window - MVVM Pattern
Composes all UI components and wires them with ViewModel
"""

import logging
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtCore import QMimeData
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QIcon,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QStatusBar, QProgressBar, QSplitter,
    QFileDialog, QMessageBox, QMenuBar,
)

from viewmodels import MainViewModel
from views.asset_table_widget import AssetTableWidget
from views.drop_overlay import DropOverlay
from views.preview_panel_widget import PreviewPanelWidget
from utilities import FileDropWidget, get_resource_str
from utilities.drop_classifier import (
    DropAction,
    DropDecision,
    classify_drop,
    suffix_in_container,
)
from services import StatusBarHandler
from models import AssetInfo, EditResult


log = logging.getLogger("ABVME")

_MENU_ICON_SIZE = 16


def _menu_icon(relative_path: str | None = None) -> QIcon:
    """Return a menu-item icon, or a transparent placeholder if none is given.

    Qt sizes the icon column from the widest icon in that menu, so every action
    needs an icon — even items with no artwork.
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
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ABVME")
        self.setMinimumSize(1000, 600)
        
        # Create ViewModel
        self.viewmodel = MainViewModel()
        self._auto_fit_columns_on_load = True
        
        # Initialize UI
        self._setup_status_bar()
        self._setup_ui()
        self._setup_menubar()
        self._connect_viewmodel()
        self._setup_logging()
        
    def _setup_status_bar(self):
        """Setup status bar with progress indicator"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        self.status_bar.setStyleSheet("background-color: '#3c3c3c';")
        
        self.progress_bar = QProgressBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setContentsMargins(5, 0, 5, 0)
        self.progress_bar.setRange(0, 0)  # Busy indicator
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(int(self.width()/3))
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self._active_background_tasks = 0
        
        # Status timer for auto-clear
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
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("File")
        self.open_action = QAction("Open Files...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setIcon(_menu_icon("assets/folder-open-regular.svg"))
        self.open_action.triggered.connect(self._on_load_button_clicked)
        file_menu.addAction(self.open_action)

        self.save_action = QAction("Save as...", self)
        self.save_action.setShortcut("Ctrl+Shift+S")
        self.save_action.setIcon(_menu_icon("assets/floppy-disk-regular.svg"))
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self._on_save_button_clicked)
        file_menu.addAction(self.save_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setIcon(_menu_icon())
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        asset_menu = menu_bar.addMenu("Asset")
        self.replace_action = QAction("Replace...", self)
        self.replace_action.setShortcut("Ctrl+R")
        self.replace_action.setIcon(_menu_icon("assets/wand-magic-sparkles-solid.svg"))
        self.replace_action.setEnabled(False)
        self.replace_action.triggered.connect(self._on_edit_button_clicked)
        asset_menu.addAction(self.replace_action)

        self.export_action = QAction("Export...", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setIcon(_menu_icon("assets/file-export-solid.svg"))
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._on_export_button_clicked)
        asset_menu.addAction(self.export_action)

        view_menu = menu_bar.addMenu("View")
        self.show_all_action = QAction("Show all objects", self)
        self.show_all_action.setCheckable(True)
        self.show_all_action.setChecked(self.viewmodel.show_all_objects)
        self.show_all_action.setIcon(_menu_icon())
        self.show_all_action.toggled.connect(self.viewmodel.set_show_all_objects)
        view_menu.addAction(self.show_all_action)
        
    def _setup_left_panel(self):
        """Setup left panel with load button and asset table"""
        self.left_panel = FileDropWidget()
        
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(5, 0, 5, 0)
        
        # Buttons layout
        button_layout = QHBoxLayout()
        self.load_button = QPushButton("  Open Files")
        self.load_button.setIcon(QIcon(get_resource_str("assets/folder-open-regular.svg")))
        self.load_button.setIconSize(QSize(16, 16))
        self.load_button.clicked.connect(self._on_load_button_clicked)
        button_layout.addWidget(self.load_button)
        button_layout.addStretch()
        
        # Save button
        self.save_button = QPushButton("  Save as...")
        self.save_button.setIcon(QIcon(get_resource_str("assets/floppy-disk-regular.svg")))
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
        self.edit_button.setIcon(QIcon(get_resource_str("assets/wand-magic-sparkles-solid.svg")))
        self.edit_button.setIconSize(QSize(16, 16))
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self._on_edit_button_clicked)
        actions_layout.addWidget(self.edit_button)
        
        self.export_button = QPushButton("  Export")
        self.export_button.setIcon(QIcon(get_resource_str("assets/file-export-solid.svg")))
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
        self.asset_table.load_assets(
            assets, auto_fit=self._auto_fit_columns_on_load
        )
        self._auto_fit_columns_on_load = False
        self.preview_panel.show_placeholder("Select an asset from the list to view its preview.")
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
        
        # Close dialog if it exists
        if hasattr(self, '_save_dialog') and self._save_dialog:
            self._save_dialog.on_save_finished(success, message)
        
    # ===== UI Event Handlers =====
    
    def _on_load_button_clicked(self):
        """Handle load button click"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Asset Bundles",
            str(Path.cwd()),
            "Asset Bundles (*.bundle *.unity3d);;All Files (*.*)"
        )
        if files:
            self.viewmodel.load_files_from_paths(files)
            
    def _on_table_selection_changed(self, selected_assets: list[AssetInfo]):
        """Handle table selection changed"""
        self.viewmodel.update_selection(selected_assets)
        
        # Update preview
        if len(selected_assets) == 0:
            self.preview_panel.show_placeholder("Select an asset from the list to view its preview.")
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
        dialog.save_multiple_selected_requested.connect(self._handle_save_multiple_selected)
        
        # Store reference to update it later
        self._save_dialog = dialog
        
        dialog.exec()
        
    def _handle_save_all(
        self, 
        output_dir: str, 
        packer: Literal["none", "lz4", "lzma", "original"] = "none"
    ):
        """Handle save all request from dialog"""
        from pathlib import Path
        
        success = self.viewmodel.save_all_files(Path(output_dir), packer)
        if not success and hasattr(self, '_save_dialog'):
            # Re-enable dialog if save didn't start
            self._save_dialog.setEnabled(True)
            
    def _handle_save_selected(
        self, 
        filepath: str, 
        output_path: str, 
        packer: Literal["none", "lz4", "lzma", "original"] = "none"
    ):
        """Handle save selected file request from dialog"""
        from pathlib import Path
        
        # Split output path into directory and filename
        output_path_obj = Path(output_path)
        output_dir = output_path_obj.parent
        output_filename = output_path_obj.name
        
        success = self.viewmodel.save_selected_file(filepath, output_dir, packer, output_filename)
        if not success and hasattr(self, '_save_dialog'):
            # Re-enable dialog if save didn't start
            self._save_dialog.setEnabled(True)
            
    def _handle_save_multiple_selected(
        self, 
        filepaths: list[str], 
        output_dir: str, 
        packer: Literal["none", "lz4", "lzma", "original"] = "none"
    ):
        """Handle save multiple selected files request from dialog"""
        from pathlib import Path
        
        success = self.viewmodel.save_multiple_files(filepaths, Path(output_dir), packer)
        if not success and hasattr(self, '_save_dialog'):
            # Re-enable dialog if save didn't start
            self._save_dialog.setEnabled(True)
        
    def _on_edit_button_clicked(self):
        """Handle edit button click"""
        asset = self.viewmodel.get_single_selected_asset()
        if not asset:
            return
            
        if not self.viewmodel.is_editing_supported(asset):
            self._on_status_message(
                f"Replace is not supported for {asset.obj_type.name}.", 
                logging.WARNING
            )
            return
            
        file_filter = self.viewmodel.get_edit_file_filter(asset)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select replacement file",
            str(Path.cwd()),
            file_filter or ""
        )
        
        if file_path:
            if (
                asset.obj_type.name == "TextAsset"
                and not suffix_in_container(file_path, asset.container)
            ):
                if not self._confirm_unmatched_textasset_replace(asset, file_path):
                    return
            self.viewmodel.edit_asset(asset, file_path)

    def _confirm_unmatched_textasset_replace(self, asset: AssetInfo, file_path: str) -> bool:
        reply = QMessageBox.question(
            self,
            "Confirm Replace",
            (
                f"The suffix of '{Path(file_path).name}' is not in the container "
                f"of '{asset.name}'. Replace anyway?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes
            
    def _on_export_button_clicked(self):
        """Handle export button click"""
        if len(self.viewmodel.selected_assets) == 1:
            asset = self.viewmodel.selected_assets[0]
            if not asset.is_exportable:
                self._on_status_message(
                    f"Export not supported for {asset.obj_type.name}.", 
                    logging.WARNING
                )
                QMessageBox.warning(
                    self,
                    "Export Not Supported",
                    f"Export not supported for {asset.obj_type.name} currently.",
                    QMessageBox.StandardButton.Ok
                )
                return
        if not self.viewmodel.selected_assets:
            self._on_status_message("Select assets to export.", logging.WARNING)
            QMessageBox.information(
                self,
                "No Assets Selected",
                "Select at least one asset to export.",
                QMessageBox.StandardButton.Ok
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
        suggested_path = Path.cwd() / suggested_name
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {asset.name}",
            str(suggested_path),
            "All Files (*.*)"
        )
        
        if file_path:
            self.viewmodel.export_single_asset(asset, Path(file_path))

    def _export_multiple_assets(self):
        """Export multiple selected assets"""
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            str(Path.cwd())
        )
        
        if output_dir:
            success, total =self.viewmodel.export_multiple_assets(
                self.viewmodel.selected_assets, 
                Path(output_dir)
            )
            message = f"Successfully exported {success} asset(s)."
            if success != total:
                message += f"Failed to export {total - success} asset(s)."
            QMessageBox.information(
                self,
                "Export Completed",
                message,
                QMessageBox.StandardButton.Ok
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
        if decision.action == DropAction.REPLACE:
            if asset.obj_type.name == "Texture2D":
                reply = QMessageBox.question(
                    self,
                    "Confirm Replace",
                    f"Replace '{asset.name}' with '{Path(first_file).name}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            self.viewmodel.edit_asset(asset, first_file)
            event.acceptProposedAction()
            return

        if decision.action == DropAction.REPLACE_CONFIRM:
            if not self._confirm_unmatched_textasset_replace(asset, first_file):
                event.ignore()
                return
            self.viewmodel.edit_asset(asset, first_file)
            event.acceptProposedAction()
            return

        event.ignore()

    def resizeEvent(self, event: QResizeEvent) -> None:
        if getattr(self, "drop_overlay", None) is not None and self.drop_overlay.isVisible():
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
        elif message:
            self.status_bar.showMessage(message)
    
    def _clear_status_bar(self):
        """Clear status bar"""
        if self._active_background_tasks == 0:
            self.status_bar.clearMessage()
        else:
            self.status_timer.start(10000)
        
    def _refresh_preview(self):
        """Refresh current preview"""
        asset = self.viewmodel.get_single_selected_asset()
        if asset:
            self.preview_panel.show_asset_preview(asset)

