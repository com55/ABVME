import multiprocessing
import sys
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, QThread, Signal, SignalInstance, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
    QFileDialog,
    QStatusBar,
    QStackedWidget,
    QTextEdit,
    QLabel,
    QSplitter,
    QMessageBox,
    QProgressBar,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from main import AssetInfo, ModMakerCore, log, ResultStatus, EditResult
from photoviewer import PhotoViewer
from custom_filter_header import FilterHeader
from PIL.Image import Image

class LoaderThread(QThread):
    finished = Signal(list)  # Signal to emit when loading is complete
    
    def __init__(self, core: ModMakerCore, files: list[str]):
        super().__init__()
        self.core = core or ModMakerCore()
        self.files = files
    
    def run(self):
        assets = self.core.load_files(self.files)
        log.info(f"Successfully loaded: {len(self.core.source_paths)} files.")
        self.finished.emit(assets)


class EditThread(QThread):
    finished = Signal(object, object)  # asset, result

    def __init__(self, asset: AssetInfo, source: str):
        super().__init__()
        self.asset = asset
        self.source = source

    def run(self):
        try:
            result = self.asset.edit_data(self.source)
        except Exception as exc:
            result = EditResult(
                status=ResultStatus.ERROR,
                message=f"Edit failed: {exc}",
                error=exc,
            )
        self.finished.emit(self.asset, result)

class StatusBarHandler(logging.Handler):
    def __init__(self, signal: SignalInstance):
        super().__init__()
        self.signal = signal
        
        # Formatter
        formatter = logging.Formatter('%(message)s')
        self.setFormatter(formatter)

    def emit(self, record):
        msg = self.format(record)
        # ส่งต่อให้ UI ผ่าน Signal (ทำงานข้าม Thread ได้ปลอดภัย)
        self.signal.emit(msg, record.levelno)


class FileDropArea(QWidget):
    files_dropped = Signal(list)

    def __init__(self, parent=None, drop_handler=None, can_accept_drop=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.drop_handler = drop_handler
        self.can_accept_drop = can_accept_drop

    def _can_accept(self) -> bool:
        if self.can_accept_drop:
            return self.can_accept_drop()
        return True

    def dragEnterEvent(self, event: QDragEnterEvent):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()
        if not any(url.isLocalFile() for url in urls):
            event.ignore()
            return

        if not self._can_accept():
            event.ignore()
            return

        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [str(url.toLocalFile()) for url in urls if url.isLocalFile()]
        if not paths or not self._can_accept():
            event.ignore()
            return

        accepted = False
        if self.drop_handler:
            accepted = self.drop_handler(paths)
        else:
            self.files_dropped.emit(paths)
            accepted = True

        if accepted:
            event.acceptProposedAction()
        else:
            event.ignore()

class ModMakerUI(QMainWindow):
    # Initialize
    log_signal: Signal = Signal(str, int)
    core: Optional[ModMakerCore] = None
    assets: list[AssetInfo] = [] # เก็บรายการ AssetInfo

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModMaker Asset Viewer")
        self.setMinimumSize(1000, 600)
        
        # Create status bar and logging handler
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        self.status_bar.setStyleSheet("background-color: '#3c3c3c';")
        self.progress_bar = QProgressBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setContentsMargins(5, 0, 5, 0)
        self.progress_bar.setRange(0, 0)  # busy indicator
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(int(self.width()/2))
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        self._active_background_tasks = 0
        self.edit_thread: EditThread | None = None
        
        self.log_signal.connect(self.on_log_received)
        
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.status_bar.clearMessage)

        # Setup logging handler
        self.status_handler = StatusBarHandler(self.log_signal)
        logger = logging.getLogger("ModMaker")
        logger.addHandler(self.status_handler)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Left Panel: Asset List (Load Button + Table) ---
        left_panel = FileDropArea()
        left_panel.files_dropped.connect(self._start_loading_from_paths)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 5, 0) # ลบ Margin ภายใน

        button_layout = QHBoxLayout()
        self.load_button = QPushButton("Load Bundle Files")
        self.load_button.clicked.connect(self.load_files)
        button_layout.addWidget(self.load_button)
        button_layout.addStretch()
        left_layout.addLayout(button_layout)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(5) # เพิ่มเป็น 5 คอลัมน์
        self.table.setHorizontalHeaderLabels(["Name", "Type", "PathID", "Container", "SourceFile"])
        
        # --- Replace Default Header with FilterHeader ---
        self.header: FilterHeader = FilterHeader(self.table)
        self.header.filter_changed.connect(self.apply_table_filter) # Connect signal
        self.header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.header.setFixedHeight(24)
        self.header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setHorizontalHeader(self.header)
        self.table.verticalHeader().setVisible(False)
        # ------------------------------------------------

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.verticalScrollBar().setSingleStep(10)
        self.table.horizontalScrollBar().setSingleStep(10)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("QTableWidget::item { padding-top: 5px; padding-bottom: 5px; }")
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        # เชื่อมต่อสัญญาณการเลือกแถวเพื่อแสดง Preview
        self.table.itemSelectionChanged.connect(self.on_asset_selected)
        left_layout.addWidget(self.table)
        
        # --- Right Panel: Preview Area (QStackedWidget) ---
        self.preview_stack = QStackedWidget()
        # กำหนดเส้นกรอบและพื้นหลังให้เหมือนกล่อง preview
        self.preview_stack.setStyleSheet(
            "QStackedWidget {"
            " border: 1px solid #616161;"
            " border-radius: 4px;"
            " background-color: #1f1f1f;"
            "}"
        )

        # 1. Image Viewer (for Texture2D)
        self.image_viewer = PhotoViewer(self.preview_stack)
        
        # 2. Text Editor (for TextAsset)
        self.text_editor = QTextEdit(self.preview_stack)
        self.text_editor.setReadOnly(True)
        self.text_editor.setStyleSheet("QTextEdit { font-family: 'Consolas', 'Monospace'; font-size: 10pt; font-weight: normal; }")
        
        # 3. Placeholder (for Mesh/Unsupported)
        self.placeholder = QLabel("Preview not available")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        
        # Add widgets to the stack and store their index
        self.image_index = self.preview_stack.addWidget(self.image_viewer)
        self.text_index = self.preview_stack.addWidget(self.text_editor)
        self.placeholder_index = self.preview_stack.addWidget(self.placeholder)
        
        # Initialize with placeholder
        self.preview_stack.setCurrentIndex(self.placeholder_index)

        self._preview_drop_targets = {
            self.preview_stack,
            self.image_viewer,
            self.image_viewer.viewport(),
            self.text_editor,
            self.placeholder,
        }
        for target in self._preview_drop_targets:
            target.setAcceptDrops(True)
            target.installEventFilter(self)

        right_panel = FileDropArea(
            drop_handler=self._handle_right_panel_drop,
            can_accept_drop=self._right_panel_can_accept_drop,
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 0, 5, 0)

        actions_layout = QHBoxLayout()
        actions_layout.addStretch()
        self.edit_button = QPushButton("Edit Asset")
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self.prompt_edit_selected_asset)
        actions_layout.addWidget(self.edit_button)
        self.export_button = QPushButton("Export Selected")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_selected_assets)
        actions_layout.addWidget(self.export_button)
        right_layout.addLayout(actions_layout)
        right_layout.addWidget(self.preview_stack)
        right_layout.setStretchFactor(self.preview_stack, 1)
        
        # --- Splitter (Optional but makes the UI much better) ---
        left_panel.setMinimumWidth(350)
        self.preview_stack.setMinimumWidth(200)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        splitter.setHandleWidth(10)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([500, 500]) # ตั้งค่าเริ่มต้นให้ตารางใหญ่กว่า Preview เล็กน้อย
        main_layout.addWidget(splitter)
        
    def on_log_received(self, msg, level):
        self.status_bar.showMessage(msg)
        if level == logging.INFO:
            self.status_timer.start(5000) # เรียก start ได้อย่างปลอดภัยเพราะอยู่บน Main Thread

    def load_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Bundle Files",
            str(Path.cwd() / "test"),
            "Bundle Files (*.bundle);;All Files (*.*)"
        )
        if files:
            self._start_loading_from_paths(files)

    def _begin_background_task(self, message: str):
        self._active_background_tasks += 1
        self.progress_bar.setVisible(True)
        self.status_bar.showMessage(message)

    def _end_background_task(self, message: str | None = None):
        self._active_background_tasks = max(0, self._active_background_tasks - 1)
        if self._active_background_tasks == 0:
            self.progress_bar.setVisible(False)
            if message:
                self.status_bar.showMessage(message)
        elif message:
            self.status_bar.showMessage(message)

    def _start_loading_from_paths(self, file_paths: list[str]):
        valid_files = [path for path in file_paths if Path(path).is_file()]
        if not valid_files:
            self.log_signal.emit("No valid bundle files were provided.", logging.WARNING)
            return

        # Guard UI
        self.load_button.setEnabled(False)
        self.load_button.setText("Loading...")
        self.table.setSortingEnabled(False)
        self.table.clearSelection()
        self.export_button.setEnabled(False)
        self.table.setRowCount(0)
        self.preview_stack.setCurrentIndex(self.placeholder_index)

        self.loader_thread = LoaderThread(self.core or ModMakerCore(), valid_files)
        self.loader_thread.finished.connect(self.on_loading_complete)
        self.loader_thread.start()

        self._update_action_buttons([])
        self._begin_background_task("Loading bundle files...")

    def _update_action_buttons(self, selected_rows=None):
        if selected_rows is None:
            selected_rows = self.table.selectionModel().selectedRows()
        has_selection = bool(selected_rows)
        self.export_button.setEnabled(has_selection)
        self.edit_button.setEnabled(len(selected_rows) == 1)

    def prompt_edit_selected_asset(self):
        asset = self._get_single_selected_asset()
        if not asset:
            return

        if asset.obj_type.name == "Texture2D":
            file_filter = "Image Files (*.png *.jpg *.jpeg *.bmp *.tga *.dds);;All Files (*.*)"
        elif asset.obj_type.name == "TextAsset":
            file_filter = "All Files (*.*)"
        else:
            self.log_signal.emit(f"Editing not supported for {asset.obj_type.name}.", logging.WARNING)
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select replacement file",
            str(Path.cwd()),
            file_filter
        )

        if file_path:
            self._apply_edit_for_asset(asset, file_path)

    def _get_single_selected_asset(self) -> Optional[AssetInfo]:
        selected_rows = self.table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            return None
        item = self.table.item(selected_rows[0].row(), 0)
        if not item:
            return None
        asset = item.data(Qt.ItemDataRole.UserRole)
        return asset if isinstance(asset, AssetInfo) else None

    def _apply_changed_style(self, row: int, asset: AssetInfo):
        item = self.table.item(row, 0)
        if not item:
            return
        suffix = " *" if bool(getattr(asset, "is_changed", False)) else "   "
        base_name = asset.name or ""
        item.setText(f"{base_name}{suffix}")

    def _refresh_asset_display(self, asset: AssetInfo):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) is asset:
                self._apply_changed_style(row, asset)
                break

    def _right_panel_can_accept_drop(self) -> bool:
        return bool(self._get_single_selected_asset())

    @staticmethod
    def _event_local_file_paths(event) -> list[str]:
        mime_data = event.mimeData() if hasattr(event, "mimeData") else None
        if not mime_data or not mime_data.hasUrls():
            return []
        return [str(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()]

    def _preview_can_accept_drop(self, event) -> bool:
        if not self._right_panel_can_accept_drop():
            return False
        return bool(self._event_local_file_paths(event))

    def eventFilter(self, obj, event):
        if obj in getattr(self, "_preview_drop_targets", []):
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
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True

            if event_type in drop_types:
                paths = self._event_local_file_paths(event)
                if not paths:
                    event.ignore()
                    return True
                accepted = self._handle_right_panel_drop(paths)
                if accepted:
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True

        return super().eventFilter(obj, event)

    def _handle_right_panel_drop(self, paths: list[str]) -> bool:
        asset = self._get_single_selected_asset()
        if not asset:
            self.log_signal.emit("Select exactly one asset before editing via drag-drop.", logging.WARNING)
            return False

        file_path = next((Path(p) for p in paths if Path(p).is_file()), None)
        if not file_path:
            self.log_signal.emit("Drag-drop must contain at least one file.", logging.WARNING)
            return False

        reply = QMessageBox.question(
            self,
            "Confirm Edit",
            f"Apply '{file_path.name}' to '{asset.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        return self._apply_edit_for_asset(asset, str(file_path))

    def _apply_edit_for_asset(self, asset: AssetInfo, source: str):
        if self.edit_thread and self.edit_thread.isRunning():
            self.log_signal.emit("Another edit is currently running.", logging.WARNING)
            return False

        self._begin_background_task(f"Editing {asset.name}...")
        self.edit_thread = EditThread(asset, source)
        self.edit_thread.finished.connect(self._on_edit_thread_finished)
        self.edit_thread.start()
        return True

    def _on_edit_thread_finished(self, asset_obj, result_obj):
        self._end_background_task()
        self.edit_thread = None

        asset = asset_obj if isinstance(asset_obj, AssetInfo) else None
        result = result_obj if isinstance(result_obj, EditResult) else None

        if not asset or not result:
            self.log_signal.emit("Edit thread returned invalid data.", logging.ERROR)
            return

        level = logging.INFO if result.is_success else logging.ERROR
        message = result.message or (f"Edited {asset.name}" if result.is_success else f"Failed to edit {asset.name}")
        self.log_signal.emit(message, level)
        if result.is_success:
            log.info(message)
            self.on_asset_selected()
            self._refresh_asset_display(asset)
        else:
            log.error(message)
    
    def on_loading_complete(self, assets: list[AssetInfo]):
        self._end_background_task("Loading complete.")
        # Re-enable the load button
        self.load_button.setEnabled(True)
        self.load_button.setText("Load Bundle Files")
        
        # เก็บรายการ Type ทั้งหมดเพื่อส่งให้ Header ทำ Checkbox
        all_types = set()
        all_sources = set()
        
        self.assets = assets # Store assets
        
        # Update the table with the loaded assets
        self.table.setRowCount(len(assets))
        self.table.clearSelection()
        self.export_button.setEnabled(False)
        
        for row, asset in enumerate(assets):
            asset: AssetInfo = asset
            # เก็บ Type
            all_types.add(asset.obj_type.name)
            all_sources.add(asset.source_path)
            
            # Name (Column 0) - Store AssetInfo in UserRole for easy retrieval
            name_item = QTableWidgetItem()
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, asset) 
            self.table.setItem(row, 0, name_item)
            self._apply_changed_style(row, asset)
            
            # Type (Column 1)
            type_item = QTableWidgetItem(asset.obj_type.name)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, type_item)
            
            # PathID (Column 2)
            path_id_item = QTableWidgetItem(asset.path_id)
            path_id_item.setFlags(path_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, path_id_item)
            
            # Container (Column 3)
            container_item = QTableWidgetItem(asset.container)
            container_item.setFlags(container_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, container_item)
            
            # SourceFile (Column 4)
            # Display only filename, but store full path in UserRole
            source_item = QTableWidgetItem(str(Path(asset.source_path).name))
            source_item.setToolTip(asset.source_path)
            source_item.setData(Qt.ItemDataRole.UserRole, asset.source_path)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 4, source_item)
        
        # กำหนดให้ Column 1 (Type) และ Column 4 (SourceFile) ใช้ระบบ Checkbox
        self.header.set_filter_boxes(1, list(all_types))
        self.header.set_filter_boxes(4, list(all_sources))

        # Adjust column widths
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.placeholder.setText("Select an asset from the list to view its preview.")
        
        # Show placeholder
        self.preview_stack.setCurrentIndex(self.placeholder_index)
        self.log_signal.emit(f"Loaded {len(assets)} assets.", logging.INFO)
        self.apply_table_filter(clear=True)  # เรียกใช้ฟังก์ชันกรองเพื่อตั้งค่าเริ่มต้น

    def on_asset_selected(self):
        # ใช้ selectionModel().selectedRows() เพื่อดึงรายการแถวที่ถูกเลือก (เฉพาะแถว ไม่ใช่ทุก cell)
        selected_rows = self.table.selectionModel().selectedRows()
        self._update_action_buttons(selected_rows)
        if not selected_rows:
            self.placeholder.setText("Select an asset from the list to view its preview.")
            self.preview_stack.setCurrentIndex(self.placeholder_index)
            return
        
        # ถ้ามีการเลือกหลายแถว ให้แสดง preview อันเดิม
        if len(selected_rows) > 1:
            return
        
        # ดึง AssetInfo จากแถวแรกที่ถูกเลือกเสมอ (selected_rows[0])
        row = selected_rows[0].row()
        
        asset_item = self.table.item(row, 0)
        asset_info: AssetInfo | None = asset_item.data(Qt.ItemDataRole.UserRole) if asset_item else None
        
        if not asset_info:
            log.error("Could not retrieve AssetInfo from selected item.")
            self.preview_stack.setCurrentIndex(self.placeholder_index)
            return
            
        log.info(f"Preparing preview for: {asset_info.name} ({asset_info.obj_type.name})")

        try:
            preview_result = asset_info.get_preview()
            
            if preview_result.status != ResultStatus.COMPLETE:
                self.placeholder.setText(
                    f"Preview failed for {asset_info.obj_type.name} (Status: {preview_result.status.value}):\n"
                    f"{preview_result.message}"
                )
                self.preview_stack.setCurrentIndex(self.placeholder_index)
                return

            if preview_result.asset_type == "Texture2D":
                # Data is PIL.Image
                if preview_result.data and isinstance(preview_result.data, Image):
                    self.image_viewer.setPhoto(preview_result.data.toqpixmap())
                    self.preview_stack.setCurrentIndex(self.image_index)
                    log.info(f"Showing Texture2D preview: {asset_info.name}")
                else:
                    self.placeholder.setText("Texture2D data is empty.")
                    self.preview_stack.setCurrentIndex(self.placeholder_index)

            elif preview_result.asset_type == "TextAsset":
                # Data is str
                self.text_editor.setText(str(preview_result.data))
                self.preview_stack.setCurrentIndex(self.text_index)
                log.info(f"Showing TextAsset preview: {asset_info.name}")

            elif preview_result.asset_type == "Mesh":
                # Data is str (exported OBJ data)
                # สำหรับ Mesh, ยังไม่มี viewer เฉพาะ เราจะแสดงข้อความเป็น placeholder
                text_data = preview_result.data if preview_result.data else "No Mesh data available."
                self.placeholder.setText(
                    f"Mesh preview (Unsupported):\n"
                    f"Raw OBJ data snippet:\n{str(text_data)[:500]}..."
                )
                self.preview_stack.setCurrentIndex(self.placeholder_index)
                log.warning(f"Mesh preview unsupported: {asset_info.name}")

            else:
                self.placeholder.setText(
                    f"Preview not supported for type: {preview_result.asset_type}"
                )
                self.preview_stack.setCurrentIndex(self.placeholder_index)

        except Exception as e:
            log.error(f"Error generating preview: {e}", exc_info=True)
            self.placeholder.setText(f"An unexpected error occurred during preview:\n{str(e)}")
            self.preview_stack.setCurrentIndex(self.placeholder_index)

    def export_selected_assets(self):
        selection_model = self.table.selectionModel()
        if not selection_model:
            return

        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            self.log_signal.emit("Select assets to export.", logging.WARNING)
            return

        selected_assets: list[AssetInfo] = []
        for index in selected_rows:
            item = self.table.item(index.row(), 0)
            asset = item.data(Qt.ItemDataRole.UserRole) if item else None
            if asset:
                selected_assets.append(asset)

        if not selected_assets:
            self.log_signal.emit("Unable to resolve selected assets.", logging.ERROR)
            return

        if len(selected_assets) == 1:
            asset = selected_assets[0]
            if asset.name and Path(asset.name).suffix:
                suggested_name = asset.name
            elif asset.container:
                suggested_name = Path(asset.container).name
            else:
                suggested_name = f"{asset.name}_{asset.path_id}"
                if asset.obj_type.name == "Texture2D":
                    suggested_name += ".png"
                elif asset.obj_type.name == "TextAsset":
                    suggested_name += ".txt"

            suggested_path = Path.cwd() / suggested_name
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Asset",
                str(suggested_path),
                "All Files (*.*)"
            )

            if not file_path:
                return

            result = asset.export(Path(file_path).parent, Path(file_path).name)
            level = logging.INFO if result.is_success else logging.ERROR
            message = result.message or ("Export completed" if result.is_success else "Export failed")
            self.log_signal.emit(message, level)
            if result.is_success:
                log.info(message)
            else:
                log.error(f"Failed to export {asset.name}: {result.message}")
            return

        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            str(Path.cwd())
        )

        if not output_dir:
            return

        successes = 0
        for asset in selected_assets:
            result = asset.export(output_dir)
            if result.is_success:
                successes += 1
                log.info(result.message or f"Exported {asset.name}")
            else:
                log.error(f"Failed to export {asset.name}: {result.message}")

        if successes == len(selected_assets):
            message = f"Exported {successes} assets to {output_dir}."
            level = logging.INFO
        elif successes:
            message = f"Exported {successes}/{len(selected_assets)} assets to {output_dir}. Check log for details."
            level = logging.WARNING
        else:
            message = "All selected exports failed."
            level = logging.ERROR

        self.log_signal.emit(message, level)

    def apply_table_filter(self, *args, clear: bool = False): 
        # 1. เพิ่ม Logic สำหรับ Reset
        if clear:
            self.header.active_filters.clear()    # ล้างข้อมูล Filter ใน Header
            self.header.viewport().update() # สั่งวาด Header ใหม่ (เอาเส้นสีน้ำเงินออก)
        
        # 2. ดึงข้อมูล Filter ปัจจุบัน
        # เพื่อให้ง่าย เราจะเช็คกับ _filters ของ header โดยตรง
        active_filters = self.header.active_filters
        
        for row in range(self.table.rowCount()):
            should_show = True
            
            # วนลูปเช็คทุกคอลัมน์ที่มีการ Filter
            for col, val in active_filters.items():
                
                item = self.table.item(row, col)
                if not item:
                    should_show = False; break
                
                cell_text = item.text()

                # --- แยก Logic ตามประเภทข้อมูล ---
                if isinstance(val, list): 
                    # แบบ Checkbox (รายการที่เลือก)
                    # ถ้า val ว่าง (ไม่เลือกอะไรเลย) → ซ่อนหมด
                    if not val:
                        should_show = False; break
                    
                    # ตรวจสอบว่ามี UserRole data หรือไม่ (สำหรับ SourceFile)
                    item_data = item.data(Qt.ItemDataRole.UserRole)
                    check_val = item_data if item_data is not None else cell_text
                        
                    if check_val not in val:
                        should_show = False; break
                        
                elif isinstance(val, tuple):
                    # แบบ Text Search (text, match_case)
                    filter_text, use_match_case = val
                    
                    if not filter_text: continue # [FIX] ถ้าข้อความว่าง ให้ข้ามไป (ไม่กรอง)
                    
                    if use_match_case:
                        if filter_text not in cell_text:
                            should_show = False; break
                    else:
                        if filter_text.lower() not in cell_text.lower():
                            should_show = False; break
                            
            self.table.setRowHidden(row, not should_show)
            

class SingleInstance(QObject):
    messageReceived = Signal()

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.server = QLocalServer()

        # ป้องกันกรณี server ค้างจาก crash
        # QLocalServer.removeServer(self.key)

    def start(self):
        result = self.server.listen(self.key)

        # ถ้า listen ไม่ได้ → แปลว่ามี instance อยู่แล้ว
        if not result:
            self._notify_existing_instance()
            return False
        
        # โหมดปกติ → รอรับการเชื่อมต่อจาก instance อื่น
        self.server.newConnection.connect(self._handle_connection)
        return True

    def _notify_existing_instance(self):
        """ส่งสัญญาณไปยัง instance เดิมเพื่อให้ดึงหน้าต่างขึ้นมา"""
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if socket.waitForConnected(500):
            socket.write(b"activate")
            socket.flush()
            socket.waitForBytesWritten(500)
        socket.close()

    def _handle_connection(self):
        """Instance ใหม่พยายามเปิด → รับข้อความ แล้ว emit signal"""
        socket = self.server.nextPendingConnection()
        if socket:
            socket.readAll()
            socket.close()
        self.messageReceived.emit()

def main():
    multiprocessing.freeze_support()

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

    # ชื่อ Instance (จะถูกใช้เป็นชื่อ IPC channel)
    single = SingleInstance("ModMakerUI_Instance")

    # ถ้ามี instance อยู่แล้ว → ไม่เปิดใหม่
    if not single.start():
        print("Program already running → Showing existing window")
        return

    # ตัวหน้าต่างหลัก
    window = ModMakerUI()
    window.show()

    # เมื่อมี instance ใหม่เปิด → ดึงหน้าต่างเดิมขึ้นมา
    def bring_to_front():
        def do_raise():
            # บังคับให้ขึ้นหน้าสุดชั่วคราว
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            window.show()
            window.raise_()
            window.activateWindow()

            # ปิด on-top เพื่อกลับสภาพเดิม
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            window.show()

        QTimer.singleShot(150, do_raise)

    single.messageReceived.connect(bring_to_front)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
