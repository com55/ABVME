from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QVBoxLayout, QPushButton, QWidget, QFileDialog, QStatusBar
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from main import AssetInfo, ModMakerCore, log
import sys
from pathlib import Path
import logging

class LoaderThread(QThread):
    finished = Signal(list)  # Signal to emit when loading is complete
    
    def __init__(self, core, files):
        super().__init__()
        self.core: ModMakerCore = core
        self.files = files
    
    def run(self):
        self.core.load_files(self.files)
        assets = self.core.get_available_assets()
        log.info(f"Successfully loaded: {len(self.core.source_paths)} files.")
        self.finished.emit(assets)

class StatusBarHandler(logging.Handler):
    def __init__(self, status_bar):
        super().__init__()
        self.status_bar = status_bar
        self.setLevel(logging.INFO)
        
        # Create a formatter
        formatter = logging.Formatter('%(message)s')
        self.setFormatter(formatter)
        
        # Create a timer for clearing old messages
        self.timer = QTimer()
        self.timer.timeout.connect(self.clear_message)
        self.timer.setSingleShot(True)
        
    def emit(self, record):
        msg = self.format(record)
        self.status_bar.showMessage(msg)
        # Clear message after 5 seconds for INFO, keep ERROR messages until next message
        if record.levelno == logging.INFO:
            self.timer.start(5000)
            
    def clear_message(self):
        self.status_bar.clearMessage()

class ModMakerUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModMaker Asset Viewer")
        self.setGeometry(100, 100, 800, 600)
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Setup logging handler
        self.status_handler = StatusBarHandler(self.status_bar)
        logger = logging.getLogger("ModMaker")
        logger.addHandler(self.status_handler)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create load button
        self.load_button = QPushButton("Load Bundle Files")
        self.load_button.clicked.connect(self.load_files)
        layout.addWidget(self.load_button)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Container", "Path ID", "Type", "Object Info"])
        layout.addWidget(self.table)
        
        # Initialize ModMakerCore
        self.core = ModMakerCore()
        
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
            
            # Create and start the loader thread
            self.loader_thread = LoaderThread(self.core, files)
            self.loader_thread.finished.connect(self.on_loading_complete)
            self.loader_thread.start()
            
    
    def on_loading_complete(self, assets):
        # Re-enable the load button
        self.load_button.setEnabled(True)
        self.load_button.setText("Load Bundle Files")
        
        # Update the table with the loaded assets
        self.table.setRowCount(len(assets))
        
        for row, asset in enumerate(assets):
            # Name
            asset: AssetInfo = asset
            name_item = QTableWidgetItem(asset.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            
            # Container
            container_item = QTableWidgetItem(asset.container)
            container_item.setFlags(container_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, container_item)
            
            # Path ID
            path_id_item = QTableWidgetItem(asset.path_id)
            path_id_item.setFlags(path_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, path_id_item)
            
            # Type
            type_item = QTableWidgetItem(asset.obj_type.name)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, type_item)
        
        # Adjust column widths
        self.table.resizeColumnsToContents()

def main():
    app = QApplication(sys.argv)
    window = ModMakerUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
