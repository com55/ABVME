"""
Main Window - MVVM Pattern
Composes all UI components and wires them with ViewModel
"""

import logging
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QEvent, Signal
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QStatusBar, QProgressBar, QSplitter,
    QFileDialog, QMessageBox
)

from viewmodels import MainViewModel
from views.asset_table_widget import AssetTableWidget
from views.preview_panel_widget import PreviewPanelWidget
from utilities import FileDropWidget, get_resource_str
from services import StatusBarHandler
from models import AssetInfo, EditResult


log = logging.getLogger("ABVME")


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
        
        # Initialize UI
        self._setup_status_bar()
        self._setup_ui()
        self._connect_viewmodel()
        self._setup_logging()
        
    def _setup_status_bar(self):
        """Setup status bar with progress indicator"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        # self.status_bar.setStyleSheet("background-color: '#3c3c3c';")
        
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
        
    def _setup_left_panel(self):
        """Setup left panel with load button and asset table"""
        self.left_panel = FileDropWidget()
        self.left_panel.files_dropped.connect(self._on_files_dropped)
        
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
        self.right_panel = FileDropWidget(
            drop_handler=self._handle_preview_drop,
            can_accept_drop=self._can_accept_preview_drop,
        )
        
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(5, 0, 5, 0)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()
        
        self.edit_button = QPushButton("  Edit")
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
        
        # Setup drop event filters for preview widgets
        self._setup_preview_drop_filters()
        
    def _setup_preview_drop_filters(self):
        """Setup event filters for drag & drop on preview widgets"""
        self._preview_drop_targets = self.preview_panel.get_preview_widgets()
        for target in self._preview_drop_targets:
            target.setAcceptDrops(True)
            target.installEventFilter(self)
            
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
        self.asset_table.clear_table()
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
        self.asset_table.load_assets(assets)
        self.preview_panel.show_placeholder("Select an asset from the list to view its preview.")
        self.asset_table.apply_filter(clear=True)
        
        # Enable Save button if files loaded
        self.save_button.setEnabled(len(assets) > 0)
        
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
        
        # Enable edit button only if exactly one editable asset is selected
        if count == 1:
            asset = self.viewmodel.get_single_selected_asset()
            self.edit_button.setEnabled(asset is not None and asset.is_editable)
        else:
            self.edit_button.setEnabled(False)
        
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
            
    def _on_files_dropped(self, paths: list[str]):
        """Handle files dropped on left panel"""
        self.viewmodel.load_files_from_paths(paths)
        
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
                f"Editing not supported for {asset.obj_type.name}.", 
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
            self.viewmodel.edit_asset(asset, file_path)
            
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
    
    def _can_accept_preview_drop(self) -> bool:
        """Check if preview panel can accept drops"""
        return self.viewmodel.can_edit_asset()
        
    def _handle_preview_drop(self, paths: list[str]) -> bool:
        """Handle files dropped on preview panel"""
        asset = self.viewmodel.get_single_selected_asset()
        if not asset:
            self._on_status_message(
                "Select exactly one asset before editing via drag-drop.", 
                logging.WARNING
            )
            return False
            
        file_path = next((Path(p) for p in paths if Path(p).is_file()), None)
        if not file_path:
            self._on_status_message(
                "Drag-drop must contain at least one file.", 
                logging.WARNING
            )
            return False
            
        reply = QMessageBox.question(
            self,
            "Confirm Edit",
            f"Apply '{file_path.name}' to '{asset.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return False
            
        return self.viewmodel.edit_asset(asset, str(file_path))
        
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Event filter for preview drop targets"""
        if watched in getattr(self, "_preview_drop_targets", []):
            event_type = event.type()
            drag_enter_types = {
                QEvent.Type.DragEnter,
                QEvent.Type.DragMove,
                QEvent.Type.GraphicsSceneDragEnter,
                QEvent.Type.GraphicsSceneDragMove,
            }
            drop_types = {QEvent.Type.Drop, QEvent.Type.GraphicsSceneDrop}

            if event_type in drag_enter_types:
                if self._preview_can_accept_drop(event):
                    event.accept()
                else:
                    event.ignore()
                return True

            if event_type in drop_types:
                paths = self._event_local_file_paths(event)
                if not paths:
                    event.ignore()
                    return True
                accepted = self._handle_preview_drop(paths)
                if accepted:
                    event.accept()
                else:
                    event.ignore()
                return True

        return super().eventFilter(watched, event)
        
    def _preview_can_accept_drop(self, event: QEvent) -> bool:
        """Check if preview can accept specific drop event"""
        if not self._can_accept_preview_drop():
            return False
        return bool(self._event_local_file_paths(event))
        
    @staticmethod
    def _event_local_file_paths(event: QEvent) -> list[str]:
        """Extract local file paths from drop event"""
        get_mime = getattr(event, "mimeData", None)
        mime_data = get_mime() if callable(get_mime) else None
        if not isinstance(mime_data, QMimeData) or not mime_data.hasUrls():
            return []
        return [str(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()]
        
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

