import multiprocessing
from PySide6.QtWidgets import QTableWidgetItem
from typing import Optional
from PySide6.QtCore import Signal, SignalInstance

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QHeaderView, QMainWindow, QTableWidget, QTableWidgetItem, 
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QFileDialog, 
    QStatusBar, QStackedWidget, QTextEdit, QLabel, QSplitter
)
from PySide6.QtCore import QObject, Qt, QTimer, QThread, Signal
from main import AssetInfo, ModMakerCore, log, ResultStatus
import sys
from pathlib import Path
import logging
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
        left_panel = QWidget()
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
        
        # --- Splitter (Optional but makes the UI much better) ---
        left_panel.setMinimumWidth(350)
        self.preview_stack.setMinimumWidth(200)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        splitter.setHandleWidth(10)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.preview_stack)
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
            # Disable the load button while processing
            self.load_button.setEnabled(False)
            self.load_button.setText("Loading...")
            self.table.setSortingEnabled(False)
            
            # Clear previous results
            self.table.setRowCount(0)
            self.preview_stack.setCurrentIndex(self.placeholder_index)

            # Create and start the loader thread
            self.loader_thread = LoaderThread(self.core or ModMakerCore(), files)
            self.loader_thread.finished.connect(self.on_loading_complete)
            self.loader_thread.start()
            
    
    def on_loading_complete(self, assets: list[AssetInfo]):
        # Re-enable the load button
        self.load_button.setEnabled(True)
        self.load_button.setText("Load Bundle Files")
        
        # เก็บรายการ Type ทั้งหมดเพื่อส่งให้ Header ทำ Checkbox
        all_types = set()
        all_sources = set()
        
        self.assets = assets # Store assets
        
        # Update the table with the loaded assets
        self.table.setRowCount(len(assets))
        
        for row, asset in enumerate(assets):
            asset: AssetInfo = asset
            # เก็บ Type
            all_types.add(asset.obj_type.name)
            all_sources.add(asset.source_path)
            
            # Name (Column 0) - Store AssetInfo in UserRole for easy retrieval
            name_item = QTableWidgetItem(asset.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, asset) 
            self.table.setItem(row, 0, name_item)
            
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
                    # ถ้า val ว่าง (ไม่เลือกอะไรเลย) -> ซ่อนหมด
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
